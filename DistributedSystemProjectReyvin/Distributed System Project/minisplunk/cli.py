from __future__ import annotations

import argparse
import json
import shlex
import sys
from pathlib import Path
from typing import Callable, Sequence

from minisplunk.transport import GatewayClient, GatewayError, GatewayResponse


SEARCH_COMMANDS = {
    "SEARCH_DATE": "date",
    "SEARCH_HOST": "host",
    "SEARCH_DAEMON": "daemon",
    "SEARCH_SEVERITY": "severity",
    "SEARCH_KEYWORD": "keyword",
}

# Public/external endpoints documented by the project.  Keeping them here means
# the interactive CLI can supply the correct port automatically per command.
PUBLIC_HOST = "103.231.240.136"
PUBLIC_ENDPOINTS = {
    "SERVER0": {"ingest": 31722, "query": 31522},
    "SERVER1": {"ingest": 31723, "query": 31523},
    "SERVER2": {"ingest": 31724, "query": 31524},
}
LOCAL_ENDPOINTS = {"ingest": 8081, "query": 8080}
INTERNAL_ENDPOINTS = {"ingest": 8000, "query": 8080}
DEFAULT_TARGET = "SERVER1"


class InteractiveCLI:
    """Small interactive shell that keeps the existing command API intact."""

    def __init__(
        self,
        client_factory: type[GatewayClient] = GatewayClient,
        input_func: Callable[[str], str] = input,
        output_func: Callable[[str], None] = print,
    ) -> None:
        self.client_factory = client_factory
        self.input = input_func
        self.output = output_func
        self.target = DEFAULT_TARGET
        self.internal_host: str | None = None

    @property
    def ingest_url(self) -> str:
        return self._endpoint_url("ingest")

    @property
    def query_url(self) -> str:
        return self._endpoint_url("query")

    def _endpoint_url(self, service: str) -> str:
        if self.target == "LOCAL":
            return f"http://localhost:{LOCAL_ENDPOINTS[service]}"
        if self.target == "INTERNAL":
            if not self.internal_host:
                raise ValueError("INTERNAL target requires a VM IP. Use: !target INTERNAL <VM_IP>")
            return f"http://{self.internal_host}:{INTERNAL_ENDPOINTS[service]}"
        return f"http://{PUBLIC_HOST}:{PUBLIC_ENDPOINTS[self.target][service]}"

    def run(self) -> int:
        self._print_banner()
        while True:
            try:
                line = self.input("minisplunk> ").strip()
            except (EOFError, KeyboardInterrupt):
                self.output("\nExiting Mini-Splunk CLI.")
                return 0

            if not line:
                continue

            if line.lower() in {"exit", "quit", "!exit", "!quit"}:
                self.output("Exiting Mini-Splunk CLI.")
                return 0

            if line.lower() in {"!help", "help"}:
                self.print_help()
                continue

            if line.lower().startswith("!target"):
                self._handle_target(line)
                continue

            # Keep the earlier !server command as a backward-compatible alias.
            if line.lower().startswith("!server"):
                self._handle_server(line)
                continue

            try:
                argv = shlex.split(line)
                response = self._execute_interactive(argv)
            except (GatewayError, FileNotFoundError, IsADirectoryError, PermissionError, ValueError) as exc:
                self.output(f"error: {exc}")
                continue

            if response is not None:
                self.output(json.dumps(response.body, indent=2, sort_keys=True))

    def _execute_interactive(self, argv: list[str]) -> GatewayResponse | None:
        if not argv:
            return None

        command = argv[0].upper()
        if command == "INGEST":
            if len(argv) != 2:
                raise ValueError("Syntax: INGEST <file_path>")
            return _run_ingest(Path(argv[1]), self.ingest_url, self.client_factory)

        if command == "QUERY":
            if len(argv) != 3:
                raise ValueError("Syntax: QUERY <query_type> <value>")
            query_type = argv[1].upper()
            if query_type not in {"COUNT_KEYWORD", *SEARCH_COMMANDS.keys()}:
                raise ValueError(f"Unknown query type: {argv[1]}")
            return _run_query(self.query_url, query_type, argv[2], self.client_factory)

        if command == "PURGE":
            if len(argv) != 1:
                raise ValueError("Syntax: PURGE")
            return self.client_factory(self.query_url).purge()

        raise ValueError("Unknown command. Type !help to see available commands.")

    def _handle_target(self, line: str) -> None:
        parts = shlex.split(line)
        if len(parts) < 2 or parts[1].upper() not in {"LOCAL", "INTERNAL", *PUBLIC_ENDPOINTS.keys()}:
            self.output("Syntax: !target LOCAL | !target INTERNAL <VM_IP> | !target SERVER0|SERVER1|SERVER2")
            return

        target = parts[1].upper()
        if target == "INTERNAL":
            if len(parts) != 3:
                self.output("Syntax: !target INTERNAL <VM_IP>")
                return
            self.internal_host = parts[2]
        elif len(parts) != 2:
            self.output("Syntax: !target LOCAL | !target SERVER0|SERVER1|SERVER2")
            return

        self.target = target
        self._print_target()

    def _handle_server(self, line: str) -> None:
        parts = shlex.split(line)
        if len(parts) != 2 or parts[1].upper() not in PUBLIC_ENDPOINTS:
            self.output("Syntax: !server SERVER0|SERVER1|SERVER2")
            return
        self.target = parts[1].upper()
        self._print_target()

    def _print_target(self) -> None:
        self.output(f"Target set to {self.target}.")
        self.output(f"  INGEST      -> {self.ingest_url}")
        self.output(f"  QUERY/PURGE -> {self.query_url}")

    def _print_banner(self) -> None:
        self.output("Distributed Mini-Splunk CLI")
        self.output(f"Target: {self.target}")
        self.output(f"  INGEST      -> {self.ingest_url}")
        self.output(f"  QUERY/PURGE -> {self.query_url}")
        self.output("Type !help for commands, !target to change target, or !exit to quit.")

    def print_help(self) -> None:
        self.output(
            "\n".join(
                [
                    "Available commands:",
                    "  INGEST <file_path>",
                    "      Upload a local syslog file using the selected server's ingest port.",
                    "",
                    "  QUERY <query_type> <value>",
                    "      query_type: SEARCH_DATE, SEARCH_HOST, SEARCH_DAEMON,",
                    "                  SEARCH_SEVERITY, SEARCH_KEYWORD, COUNT_KEYWORD",
                    "",
                    "  PURGE",
                    "      Delete all indexed log entries using the selected server's query port.",
                    "",
                    "  !target LOCAL",
                    "      Use localhost:8081 for INGEST and localhost:8080 for QUERY/PURGE.",
                    "",
                    "  !target INTERNAL <VM_IP>",
                    "      Use <VM_IP>:8000 for INGEST and <VM_IP>:8080 for QUERY/PURGE.",
                    "",
                    "  !target SERVER0|SERVER1|SERVER2",
                    "      Change the public server target. Ports are selected automatically.",
                    "",
                    "  !server SERVER0|SERVER1|SERVER2",
                    "      Backward-compatible alias for selecting a public server.",
                    "",
                    "  !help",
                    "      Display this help message.",
                    "",
                    "  !exit / !quit",
                    "      Gracefully exit the CLI.",
                ]
            )
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="minisplunk",
        description="CLI forwarder for the distributed Mini-Splunk project.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    ingest = subparsers.add_parser("INGEST", help="Send a local syslog file to the gateway.")
    ingest.add_argument("file_path", type=Path)
    ingest.add_argument("gateway_ip")

    query = subparsers.add_parser("QUERY", help="Run a distributed search through the gateway.")
    query.add_argument("gateway_ip")
    query.add_argument("query_type", choices=[*SEARCH_COMMANDS.keys(), "COUNT_KEYWORD"])
    query.add_argument("value")

    purge = subparsers.add_parser("PURGE", help="Delete all indexed log entries.")
    purge.add_argument("gateway_ip")

    return parser


def run(argv: Sequence[str], client_factory: type[GatewayClient] = GatewayClient) -> int:
    # No arguments now launches the interactive CLI.  Existing explicit
    # command-line invocations continue to use the original argparse path.
    if not argv:
        return InteractiveCLI(client_factory=client_factory).run()

    parser = build_parser()
    args = parser.parse_args(argv)

    try:
        if args.command == "INGEST":
            response = _run_ingest(args.file_path, args.gateway_ip, client_factory)
        elif args.command == "QUERY":
            response = _run_query(args.gateway_ip, args.query_type, args.value, client_factory)
        elif args.command == "PURGE":
            response = client_factory(args.gateway_ip).purge()
        else:
            parser.error(f"Unsupported command: {args.command}")
    except (GatewayError, FileNotFoundError, IsADirectoryError, PermissionError) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 1

    print(json.dumps(response.body, indent=2, sort_keys=True))
    return 0


def _run_ingest(
    file_path: Path,
    gateway_ip: str,
    client_factory: type[GatewayClient],
) -> GatewayResponse:
    if not file_path.is_file():
        raise FileNotFoundError(f"Syslog file does not exist: {file_path}")
    return client_factory(gateway_ip).ingest(file_path)


def _run_query(
    gateway_ip: str,
    query_type: str,
    value: str,
    client_factory: type[GatewayClient],
) -> GatewayResponse:
    client = client_factory(gateway_ip)
    if query_type == "COUNT_KEYWORD":
        return client.count_keyword(value)
    return client.search(SEARCH_COMMANDS[query_type], value)


def main() -> None:
    raise SystemExit(run(sys.argv[1:]))


if __name__ == "__main__":
    main()
