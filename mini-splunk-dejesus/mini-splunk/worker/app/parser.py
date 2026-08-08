"""
RFC 3164 syslog parser.
"""

from __future__ import annotations

import hashlib
import re
from typing import Any

from shared.logging import get_logger

logger = get_logger("worker.parser")

SYSLOG_PATTERN = re.compile(
    r"""
    ^
    (?P<timestamp>
        [A-Z][a-z]{2}\s+
        \d{1,2}\s+
        \d{2}:\d{2}:\d{2}
    )
    \s+
    (?P<hostname>\S+)
    \s+
    (?P<process>[^\[:]+)
    (?:\[(?P<pid>\d+)\])?
    :
    \s*
    (?P<message>.*)
    $
    """,
    re.VERBOSE,
)

SEVERITY_RULES = [
    ("critical", "CRITICAL"),
    ("fatal", "CRITICAL"),
    ("panic", "CRITICAL"),
    ("error", "ERROR"),
    ("failed", "ERROR"),
    ("warning", "WARNING"),
    ("warn", "WARNING"),
    ("denied", "WARNING"),
    ("notice", "NOTICE"),
    ("debug", "DEBUG"),
    ("info", "INFO"),
]


class SyslogParser:
    """
    RFC 3164 syslog parser.
    """

    @staticmethod
    def infer_severity(message: str) -> str:
        """
        Infer severity from message content.
        """

        text = message.lower()

        for keyword, severity in SEVERITY_RULES:

            if keyword in text:
                return severity

        return "INFO"

    @staticmethod
    def generate_message_id(raw_line: str) -> str:
        """
        Generate a deterministic ID for duplicate prevention.
        """

        return hashlib.sha256(
            raw_line.encode("utf-8")
        ).hexdigest()

    def parse(self, raw_line: str) -> dict[str, Any] | None:
        """
        Parse a single RFC 3164 syslog line.

        Returns:
            Parsed document or None if malformed.
        """

        match = SYSLOG_PATTERN.match(raw_line)

        if match is None:

            logger.warning(
                "Malformed syslog line skipped: %s",
                raw_line,
            )

            return None

        data = match.groupdict()

        message = data["message"]

        return {
            "message_id": self.generate_message_id(raw_line),
            "raw": raw_line,
            "timestamp": data["timestamp"],
            "hostname": data["hostname"],
            "process": data["process"],
            "pid": data["pid"],
            "severity": self.infer_severity(message),
            "message": message,
        }