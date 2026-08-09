from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import urlparse

from minisplunk.config import gateway_config, mongo_uri
from minisplunk.gateway import _positive_int, _render_home, _render_logs, _render_nodes, _single_value_params
from minisplunk.storage import MongoLogRepository


class QueryApiHandler(BaseHTTPRequestHandler):
    repository: MongoLogRepository

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self._write_html(200, _render_home())
            return
        if parsed.path == "/logs":
            self._handle_logs_page(parsed.query)
            return
        if parsed.path == "/nodes":
            self._handle_nodes_page(parsed.query)
            return
        self._write_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path == "/query":
            self._handle_query()
            return
        if self.path == "/query/count-keyword":
            self._handle_count_keyword()
            return
        self._write_json(404, {"error": "not found"})

    def do_DELETE(self) -> None:
        if self.path != "/logs":
            self._write_json(404, {"error": "not found"})
            return

        deleted_count = self.repository.purge()
        self._write_json(200, {"purged": True, "deleted_count": deleted_count})

    def _handle_query(self) -> None:
        try:
            body = self._read_json()
            results = self.repository.search(str(body["type"]), str(body["value"]))
        except (KeyError, ValueError, json.JSONDecodeError) as exc:
            self._write_json(400, {"error": str(exc)})
            return

        self._write_json(200, {"results": results, "count": len(results)})

    def _handle_count_keyword(self) -> None:
        try:
            body = self._read_json()
            count = self.repository.count_keyword(str(body["keyword"]))
        except (KeyError, json.JSONDecodeError) as exc:
            self._write_json(400, {"error": str(exc)})
            return

        self._write_json(200, {"keyword": body["keyword"], "count": count})

    def _handle_logs_page(self, raw_query: str) -> None:
        query_params = _single_value_params(raw_query)
        limit = _positive_int(query_params.pop("limit", "250"), default=250)
        output_format = query_params.pop("format", "html")
        logs = self.repository.list_logs(query_params, limit=limit)
        body = {"count": len(logs), "results": logs}

        if output_format == "json":
            self._write_json(200, body)
            return

        self._write_html(200, _render_logs(logs, query_params))

    def _handle_nodes_page(self, raw_query: str) -> None:
        query_params = _single_value_params(raw_query)
        nodes = self.repository.list_nodes()
        body = {"count": len(nodes), "active_registry": nodes}

        if query_params.get("format") == "json":
            self._write_json(200, body)
            return

        self._write_html(200, _render_nodes(nodes))

    def _read_json(self) -> dict[str, Any]:
        content_length = int(self.headers.get("Content-Length", "0"))
        return json.loads(self.rfile.read(content_length).decode("utf-8"))

    def _write_json(self, status_code: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body, default=str).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def _write_html(self, status_code: int, body: str) -> None:
        encoded = body.encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    config = gateway_config()
    QueryApiHandler.repository = MongoLogRepository(mongo_uri())
    server = ThreadingHTTPServer((config.host, config.port), QueryApiHandler)
    print(f"Query API listening on {config.host}:{config.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
