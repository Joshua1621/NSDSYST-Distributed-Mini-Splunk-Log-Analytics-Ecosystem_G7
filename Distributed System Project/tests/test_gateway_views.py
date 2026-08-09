from __future__ import annotations

import unittest

from minisplunk.gateway import _positive_int, _render_logs, _render_nodes, _single_value_params


class GatewayViewTests(unittest.TestCase):
    def test_single_value_params_uses_last_query_value(self) -> None:
        self.assertEqual(_single_value_params("severity=error&severity=warn&host=web-1"), {"severity": "warn", "host": "web-1"})

    def test_positive_int_clamps_limit(self) -> None:
        self.assertEqual(_positive_int("0", 250), 1)
        self.assertEqual(_positive_int("5000", 250), 1000)
        self.assertEqual(_positive_int("bad", 250), 250)

    def test_render_logs_includes_log_fields(self) -> None:
        html = _render_logs(
            [
                {
                    "timestamp": "Jul 16 15:20:01",
                    "hostname": "web-1",
                    "process": "sshd",
                    "severity": "error",
                    "message": "Failed password",
                }
            ],
            {},
        )

        self.assertIn("Parsed Logs", html)
        self.assertIn("web-1", html)
        self.assertIn("Failed password", html)

    def test_render_nodes_includes_worker_fields(self) -> None:
        html = _render_nodes(
            [
                {
                    "node_name": "worker-1",
                    "role": "worker",
                    "status": "active",
                    "jobs_processed": 2,
                    "logs_inserted": 12,
                    "last_active": "2026-08-06T12:00:00Z",
                }
            ]
        )

        self.assertIn("Worker Nodes", html)
        self.assertIn("worker-1", html)
        self.assertIn("12", html)


if __name__ == "__main__":
    unittest.main()
