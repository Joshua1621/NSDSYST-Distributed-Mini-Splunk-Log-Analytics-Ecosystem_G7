from __future__ import annotations

import re
from dataclasses import asdict, dataclass
from typing import Iterable


SYSLOG_RE = re.compile(
    r"^(?P<timestamp>[A-Z][a-z]{2}\s+\d{1,2}\s+\d{2}:\d{2}:\d{2})\s+"
    r"(?P<hostname>\S+)\s+"
    r"(?P<process>[A-Za-z0-9_.\/-]+)(?:\[(?P<pid>\d+)\])?:\s*"
    r"(?P<message>.*)$"
)


@dataclass(frozen=True)
class ParsedLog:
    raw: str
    timestamp: str
    hostname: str
    process: str
    severity: str
    message: str

    def to_document(self, job_id: str, line_number: int, file_name: str) -> dict[str, object]:
        doc = asdict(self)
        doc.update(
            {
                "job_id": job_id,
                "line_number": line_number,
                "file_name": file_name,
                "dedupe_key": f"{job_id}:{line_number}",
            }
        )
        return doc


def parse_syslog_lines(lines: Iterable[str]) -> list[ParsedLog]:
    parsed = []
    for line in lines:
        cleaned = line.rstrip("\n")
        if not cleaned:
            continue
        parsed.append(parse_syslog_line(cleaned))
    return parsed


def parse_syslog_line(line: str) -> ParsedLog:
    match = SYSLOG_RE.match(line)
    if not match:
        return ParsedLog(
            raw=line,
            timestamp="",
            hostname="",
            process="unknown",
            severity=infer_severity(line),
            message=line,
        )

    message = match.group("message")
    return ParsedLog(
        raw=line,
        timestamp=match.group("timestamp"),
        hostname=match.group("hostname"),
        process=match.group("process"),
        severity=infer_severity(message),
        message=message,
    )


def infer_severity(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ("panic", "fatal", "critical", "crit", "error", "failed", "failure")):
        return "error"
    if any(token in lowered for token in ("warn", "warning", "retry", "timeout", "denied")):
        return "warn"
    return "info"
