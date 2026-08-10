from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib import error, request


class GatewayError(RuntimeError):
    """Raised when the gateway cannot be reached or returns an error."""


@dataclass(frozen=True)
class GatewayResponse:
    status_code: int
    body: dict[str, Any]


class GatewayClient:
    def __init__(self, base_url: str, timeout_seconds: float = 30.0) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds

    def ingest(self, file_path: Path) -> GatewayResponse:
        payload = file_path.read_bytes()
        headers = {
            "Content-Type": "text/plain; charset=utf-8",
            "X-File-Name": file_path.name,
        }
        return self._send("POST", "/ingest", payload, headers)

    def search(self, search_type: str, value: str) -> GatewayResponse:
        payload = json.dumps({"type": search_type, "value": value}).encode("utf-8")
        return self._send("POST", "/query", payload, {"Content-Type": "application/json"})

    def count_keyword(self, keyword: str) -> GatewayResponse:
        payload = json.dumps({"keyword": keyword}).encode("utf-8")
        return self._send("POST", "/query/count-keyword", payload, {"Content-Type": "application/json"})

    def purge(self) -> GatewayResponse:
        return self._send("DELETE", "/logs", b"", {})

    def _send(
        self,
        method: str,
        path: str,
        payload: bytes,
        headers: dict[str, str],
    ) -> GatewayResponse:
        req = request.Request(
            url=f"{self.base_url}{path}",
            data=payload,
            headers=headers,
            method=method,
        )

        try:
            with request.urlopen(req, timeout=self.timeout_seconds) as response:
                raw = response.read().decode("utf-8")
                return GatewayResponse(response.status, _parse_json_body(raw))
        except error.HTTPError as exc:
            raw = exc.read().decode("utf-8")
            raise GatewayError(f"Gateway returned HTTP {exc.code}: {raw}") from exc
        except error.URLError as exc:
            raise GatewayError(f"Could not reach gateway at {self.base_url}: {exc.reason}") from exc


def _parse_json_body(raw: str) -> dict[str, Any]:
    if not raw:
        return {}

    try:
        body = json.loads(raw)
    except json.JSONDecodeError:
        return {"raw": raw}

    if isinstance(body, dict):
        return body
    return {"data": body}
