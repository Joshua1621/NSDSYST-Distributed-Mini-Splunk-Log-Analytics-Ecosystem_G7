from __future__ import annotations

import json
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from urllib.parse import parse_qs, urlparse
from uuid import uuid4

from minisplunk.config import gateway_config, mongo_uri, rabbitmq_config
from minisplunk.rabbitmq import RabbitMQPublisher
from minisplunk.storage import MongoLogRepository


class GatewayHandler(BaseHTTPRequestHandler):
    publisher: RabbitMQPublisher
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
        if self.path == "/ingest":
            self._handle_ingest()
            return
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

    def _handle_ingest(self) -> None:
        content_length = int(self.headers.get("Content-Length", "0"))
        raw_payload = self.rfile.read(content_length).decode("utf-8", errors="replace")
        file_name = self.headers.get("X-File-Name", "syslog.log")
        job_id = str(uuid4())

        self.publisher.publish_ingest_job(
            {
                "job_id": job_id,
                "file_name": file_name,
                "payload": raw_payload,
            }
        )
        self._write_json(202, {"accepted": True, "job_id": job_id})

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


def _single_value_params(raw_query: str) -> dict[str, str]:
    params = parse_qs(raw_query, keep_blank_values=False)
    return {key: values[-1] for key, values in params.items() if values}


def _positive_int(value: str, default: int) -> int:
    try:
        parsed = int(value)
    except ValueError:
        return default
    return max(1, min(parsed, 1000))


def _render_home() -> str:
    return _page(
        "Mini-Splunk Gateway",
        """
        <section>
          <h2>Gateway</h2>
          <p>Use the links below to inspect data currently stored in the sharded MongoDB cluster.</p>
          <nav class="actions">
            <a href="/logs">View Logs</a>
            <a href="/nodes">View Nodes</a>
          </nav>
        </section>
        """,
    )


def _render_logs(logs: list[dict[str, Any]], filters: dict[str, str]) -> str:
    rows = "\n".join(
        f"""
        <tr>
          <td>{escape(str(log.get("timestamp", "")))}</td>
          <td>{escape(str(log.get("hostname", "")))}</td>
          <td>{escape(str(log.get("process", "")))}</td>
          <td><span class="badge {escape(str(log.get("severity", "info")))}">{escape(str(log.get("severity", "")))}</span></td>
          <td>{escape(str(log.get("message", "")))}</td>
        </tr>
        """
        for log in logs
    )
    if not rows:
        rows = '<tr><td colspan="5" class="empty">No logs found.</td></tr>'

    filter_note = ", ".join(f"{escape(key)}={escape(value)}" for key, value in filters.items()) or "none"
    return _page(
        "Logs",
        f"""
        <section>
          <div class="header-row">
            <div>
              <h2>Parsed Logs</h2>
              <p>{len(logs)} record(s). Filters: {filter_note}</p>
            </div>
            <a href="/nodes">Nodes</a>
          </div>
          <table>
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>Host</th>
                <th>Daemon</th>
                <th>Severity</th>
                <th>Message</th>
              </tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
        </section>
        """,
    )


def _render_nodes(nodes: list[dict[str, Any]]) -> str:
    rows = "\n".join(
        f"""
        <tr>
          <td>{escape(str(node.get("node_name", "")))}</td>
          <td>{escape(str(node.get("role", "")))}</td>
          <td>{escape(str(node.get("status", "")))}</td>
          <td>{escape(str(node.get("jobs_processed", 0)))}</td>
          <td>{escape(str(node.get("logs_inserted", 0)))}</td>
          <td>{escape(str(node.get("last_active", "")))}</td>
        </tr>
        """
        for node in nodes
    )
    if not rows:
        rows = '<tr><td colspan="6" class="empty">No worker nodes have processed jobs yet.</td></tr>'

    return _page(
        "Nodes",
        f"""
        <section>
          <div class="header-row">
            <div>
              <h2>Worker Nodes</h2>
              <p>{len(nodes)} registered node(s).</p>
            </div>
            <a href="/logs">Logs</a>
          </div>
          <table>
            <thead>
              <tr>
                <th>Name</th>
                <th>Role</th>
                <th>Status</th>
                <th>Jobs</th>
                <th>Logs Inserted</th>
                <th>Last Active</th>
              </tr>
            </thead>
            <tbody>{rows}</tbody>
          </table>
        </section>
        """,
    )


def _page(title: str, content: str) -> str:
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{escape(title)} | Mini-Splunk</title>
  <style>
    :root {{
      color-scheme: light;
      --bg: #f6f7f9;
      --panel: #ffffff;
      --text: #1f2937;
      --muted: #667085;
      --border: #d9dee7;
      --accent: #1864ab;
    }}
    body {{
      margin: 0;
      background: var(--bg);
      color: var(--text);
      font: 14px/1.45 system-ui, -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    }}
    header {{
      background: #18212f;
      color: white;
      padding: 18px 28px;
    }}
    header h1 {{ margin: 0; font-size: 22px; }}
    main {{ padding: 24px; }}
    section {{
      background: var(--panel);
      border: 1px solid var(--border);
      border-radius: 8px;
      overflow: hidden;
    }}
    h2 {{ margin: 0; font-size: 20px; }}
    p {{ margin: 4px 0 0; color: var(--muted); }}
    a {{ color: var(--accent); font-weight: 600; text-decoration: none; }}
    .actions {{ display: flex; gap: 14px; margin-top: 16px; }}
    .header-row {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 16px;
      padding: 18px;
      border-bottom: 1px solid var(--border);
    }}
    table {{ width: 100%; border-collapse: collapse; }}
    th, td {{
      border-bottom: 1px solid var(--border);
      padding: 10px 12px;
      text-align: left;
      vertical-align: top;
    }}
    th {{
      background: #eef2f7;
      color: #344054;
      font-size: 12px;
      text-transform: uppercase;
    }}
    .badge {{
      display: inline-block;
      min-width: 46px;
      border-radius: 999px;
      padding: 2px 8px;
      font-size: 12px;
      text-align: center;
      background: #e7f5ff;
      color: #0b558f;
    }}
    .badge.error {{ background: #ffe3e3; color: #b42318; }}
    .badge.warn {{ background: #fff3bf; color: #8a5a00; }}
    .empty {{ color: var(--muted); text-align: center; padding: 24px; }}
  </style>
</head>
<body>
  <header><h1>Distributed Mini-Splunk</h1></header>
  <main>{content}</main>
</body>
</html>"""


def main() -> None:
    config = gateway_config()
    GatewayHandler.publisher = RabbitMQPublisher(rabbitmq_config())
    GatewayHandler.repository = MongoLogRepository(mongo_uri())
    server = ThreadingHTTPServer((config.host, config.port), GatewayHandler)
    print(f"Gateway listening on {config.host}:{config.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
