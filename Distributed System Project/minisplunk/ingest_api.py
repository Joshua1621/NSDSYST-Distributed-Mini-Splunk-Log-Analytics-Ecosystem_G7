from __future__ import annotations

import json
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from typing import Any
from uuid import uuid4

from minisplunk.config import gateway_config, rabbitmq_config
from minisplunk.rabbitmq import RabbitMQPublisher


class IngestApiHandler(BaseHTTPRequestHandler):
    publisher: RabbitMQPublisher

    def do_GET(self) -> None:
        if self.path == "/":
            self._write_json(200, {"service": "ingest-api", "status": "ok"})
            return
        self._write_json(404, {"error": "not found"})

    def do_POST(self) -> None:
        if self.path != "/ingest":
            self._write_json(404, {"error": "not found"})
            return

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

    def _write_json(self, status_code: int, body: dict[str, Any]) -> None:
        encoded = json.dumps(body, default=str).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(encoded)))
        self.end_headers()
        self.wfile.write(encoded)

    def log_message(self, format: str, *args: object) -> None:
        return


def main() -> None:
    config = gateway_config()
    IngestApiHandler.publisher = RabbitMQPublisher(rabbitmq_config())
    server = ThreadingHTTPServer((config.host, config.port), IngestApiHandler)
    print(f"Ingest API listening on {config.host}:{config.port}")
    server.serve_forever()


if __name__ == "__main__":
    main()
