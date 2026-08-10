from __future__ import annotations

import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory

from minisplunk.cli import InteractiveCLI, run
from minisplunk.transport import GatewayResponse


class FakeGatewayClient:
    calls: list[tuple[str, object]] = []

    def __init__(self, base_url: str) -> None:
        self.base_url = base_url

    def ingest(self, file_path: Path) -> GatewayResponse:
        self.calls.append(("ingest", self.base_url, file_path))
        return GatewayResponse(202, {"accepted": True})

    def search(self, search_type: str, value: str) -> GatewayResponse:
        self.calls.append(("search", self.base_url, search_type, value))
        return GatewayResponse(200, {"results": []})

    def count_keyword(self, keyword: str) -> GatewayResponse:
        self.calls.append(("count_keyword", self.base_url, keyword))
        return GatewayResponse(200, {"count": 0})

    def purge(self) -> GatewayResponse:
        self.calls.append(("purge", self.base_url))
        return GatewayResponse(200, {"purged": True})


class CliTests(unittest.TestCase):
    def setUp(self) -> None:
        FakeGatewayClient.calls = []

    def test_ingest_sends_file_to_gateway(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "syslog.log"
            log_file.write_text("Jul 16 host sshd[123]: failed password\n", encoding="utf-8")

            exit_code = self._run_quietly(["INGEST", str(log_file), "http://gateway:8080"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(FakeGatewayClient.calls, [("ingest", "http://gateway:8080", log_file)])

    def test_search_host_maps_to_gateway_search_type(self) -> None:
        exit_code = self._run_quietly(["QUERY", "http://gateway:8080", "SEARCH_HOST", "web-1"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(FakeGatewayClient.calls, [("search", "http://gateway:8080", "host", "web-1")])

    def test_count_keyword_uses_count_endpoint(self) -> None:
        exit_code = self._run_quietly(["QUERY", "http://gateway:8080", "COUNT_KEYWORD", "timeout"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(FakeGatewayClient.calls, [("count_keyword", "http://gateway:8080", "timeout")])

    def test_purge_calls_gateway(self) -> None:
        exit_code = self._run_quietly(["PURGE", "http://gateway:8080"])

        self.assertEqual(exit_code, 0)
        self.assertEqual(FakeGatewayClient.calls, [("purge", "http://gateway:8080")])


    def test_interactive_ingest_uses_default_server_ingest_port(self) -> None:
        with TemporaryDirectory() as tmp_dir:
            log_file = Path(tmp_dir) / "syslog.log"
            log_file.write_text("Jul 16 host sshd[123]: failed password\n", encoding="utf-8")
            inputs = iter([f"INGEST {log_file}", "!exit"])
            shell = InteractiveCLI(
                client_factory=FakeGatewayClient,
                input_func=lambda _prompt: next(inputs),
                output_func=lambda _message: None,
            )

            exit_code = shell.run()

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            FakeGatewayClient.calls,
            [("ingest", "http://103.231.240.136:31723", log_file)],
        )

    def test_interactive_query_and_purge_use_default_query_port(self) -> None:
        inputs = iter(["QUERY SEARCH_HOST web-1", "PURGE", "!exit"])
        shell = InteractiveCLI(
            client_factory=FakeGatewayClient,
            input_func=lambda _prompt: next(inputs),
            output_func=lambda _message: None,
        )

        exit_code = shell.run()

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            FakeGatewayClient.calls,
            [
                ("search", "http://103.231.240.136:31523", "host", "web-1"),
                ("purge", "http://103.231.240.136:31523"),
            ],
        )

    def test_interactive_server_switch_changes_default_ports(self) -> None:
        inputs = iter(["!server SERVER2", "QUERY COUNT_KEYWORD failed", "!exit"])
        shell = InteractiveCLI(
            client_factory=FakeGatewayClient,
            input_func=lambda _prompt: next(inputs),
            output_func=lambda _message: None,
        )

        exit_code = shell.run()

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            FakeGatewayClient.calls,
            [("count_keyword", "http://103.231.240.136:31524", "failed")],
        )


    def test_interactive_local_target_uses_local_ports(self) -> None:
        inputs = iter(["!target LOCAL", "INGEST ./missing.log", "!exit"])
        shell = InteractiveCLI(
            client_factory=FakeGatewayClient,
            input_func=lambda _prompt: next(inputs),
            output_func=lambda _message: None,
        )

        exit_code = shell.run()

        self.assertEqual(exit_code, 0)
        self.assertEqual(FakeGatewayClient.calls, [])
        self.assertEqual(shell.ingest_url, "http://localhost:8081")
        self.assertEqual(shell.query_url, "http://localhost:8080")

    def test_interactive_internal_target_uses_vm_ip_and_internal_ports(self) -> None:
        inputs = iter(["!target INTERNAL 192.168.1.105", "QUERY SEARCH_HOST web-1", "!exit"])
        shell = InteractiveCLI(
            client_factory=FakeGatewayClient,
            input_func=lambda _prompt: next(inputs),
            output_func=lambda _message: None,
        )

        exit_code = shell.run()

        self.assertEqual(exit_code, 0)
        self.assertEqual(
            FakeGatewayClient.calls,
            [("search", "http://192.168.1.105:8080", "host", "web-1")],
        )
        self.assertEqual(shell.ingest_url, "http://192.168.1.105:8000")
        self.assertEqual(shell.query_url, "http://192.168.1.105:8080")

    def test_interactive_internal_target_requires_vm_ip(self) -> None:
        outputs: list[str] = []
        inputs = iter(["!target INTERNAL", "!exit"])
        shell = InteractiveCLI(
            client_factory=FakeGatewayClient,
            input_func=lambda _prompt: next(inputs),
            output_func=outputs.append,
        )

        exit_code = shell.run()

        self.assertEqual(exit_code, 0)
        self.assertIn("Syntax: !target INTERNAL <VM_IP>", outputs)

    def _run_quietly(self, argv: list[str]) -> int:
        with redirect_stdout(StringIO()):
            return run(argv, FakeGatewayClient)


if __name__ == "__main__":
    unittest.main()
