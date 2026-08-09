from __future__ import annotations

import unittest

from minisplunk.parser import infer_severity, parse_syslog_line


class ParserTests(unittest.TestCase):
    def test_parse_standard_syslog_line(self) -> None:
        parsed = parse_syslog_line("Jul 16 15:20:01 web-1 sshd[123]: Failed password for root")

        self.assertEqual(parsed.timestamp, "Jul 16 15:20:01")
        self.assertEqual(parsed.hostname, "web-1")
        self.assertEqual(parsed.process, "sshd")
        self.assertEqual(parsed.severity, "error")
        self.assertEqual(parsed.message, "Failed password for root")

    def test_parse_unmatched_line_keeps_raw_message(self) -> None:
        parsed = parse_syslog_line("this does not look like syslog")

        self.assertEqual(parsed.process, "unknown")
        self.assertEqual(parsed.message, "this does not look like syslog")

    def test_infer_severity(self) -> None:
        self.assertEqual(infer_severity("operation completed"), "info")
        self.assertEqual(infer_severity("connection timeout"), "warn")
        self.assertEqual(infer_severity("fatal disk error"), "error")


if __name__ == "__main__":
    unittest.main()
