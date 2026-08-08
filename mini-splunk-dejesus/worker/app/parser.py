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
    def generate_message_id(job_id: str, line_offset: int) -> str:
        """
        Generate a deterministic ID for duplicate prevention.

        The ID is derived from the ingestion job and the line's
        position within that job's file -- NOT from the line's
        content. This distinguishes two responsibilities that a
        content-based hash would otherwise conflate:

        1. Redelivery safety: if RabbitMQ redelivers the same
           message (e.g. because a Worker crashed before acking),
           the same job_id + offset is regenerated, so the upsert
           in MongoRepository.upsert_log() is a safe no-op.
        2. Distinctness: two genuinely different log events that
           happen to share identical text (e.g. repeated heartbeat
           or health-check lines, or the same auth failure logged
           twice) get DIFFERENT ids, because they occupy different
           offsets in the file, so both are stored rather than the
           second silently overwriting the first.

        A content-based hash (the previous approach) only achieves
        (1) -- it satisfies redelivery safety but fails (2), since
        identical content always hashes to the same id regardless
        of how many times or where it appears in the file.
        """

        return hashlib.sha256(
            f"{job_id}:{line_offset}".encode("utf-8")
        ).hexdigest()

    @staticmethod
    def normalize_timestamp(raw_timestamp: str) -> str:
        """
        Collapse internal whitespace in a syslog timestamp to single
        spaces.

        RFC 3164 pads single-digit days with an extra space to keep
        the field width constant (e.g. "Aug  4" for the 4th vs.
        "Aug 14" for the 14th). Left as-is, this makes exact-string
        and prefix matching fragile: a user naturally typing
        "Aug 4" (one space) would not match a stored "Aug  4" (two
        spaces). Normalizing on both the write side (here) and the
        read side (Gateway's search_date) makes matching depend only
        on the actual date, not on how many spaces RFC 3164 happens
        to insert.
        """

        return " ".join(raw_timestamp.split())

    def parse(
        self,
        raw_line: str,
        job_id: str,
        line_offset: int,
    ) -> dict[str, Any] | None:
        """
        Parse a single RFC 3164 syslog line.

        Args:
            raw_line: the raw syslog line text.
            job_id: the ingestion job this line belongs to.
            line_offset: this line's position (0-indexed) within
                the job's file, counting every non-blank line seen
                -- including ones that fail to parse -- so the same
                raw line always maps to the same offset on retry.

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
            "message_id": self.generate_message_id(
                job_id,
                line_offset,
            ),
            "raw": raw_line,
            "timestamp": self.normalize_timestamp(
                data["timestamp"]
            ),
            "hostname": data["hostname"],
            "process": data["process"],
            "pid": data["pid"],
            "severity": self.infer_severity(message),
            "message": message,
        }