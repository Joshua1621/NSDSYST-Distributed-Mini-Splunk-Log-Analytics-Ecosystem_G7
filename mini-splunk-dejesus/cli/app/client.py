"""
HTTP client for communicating with the Gateway.
"""

from __future__ import annotations

import uuid
from pathlib import Path
from typing import Iterator

import requests

from shared.config import settings
from shared.logging import get_logger

logger = get_logger("cli.client")


class GatewayClient:
    """
    Gateway REST client.
    """

    def __init__(
        self,
        gateway_ip: str,
    ) -> None:

        self.base_url = (
            f"http://{gateway_ip}:{settings.gateway_external_port}/api"
        )

    ########################################################
    # INGEST
    ########################################################

    @staticmethod
    def _iter_batches(
        path: Path,
        batch_size: int,
    ) -> Iterator[list[str]]:
        """
        Read a file and yield successive batches of up to
        batch_size non-blank lines.

        Reading and yielding one batch at a time (rather than
        `fp.read()`-ing the whole file first) keeps memory usage
        bounded by batch_size regardless of file size.
        """

        batch: list[str] = []

        with path.open(
            "r",
            encoding="utf-8",
            errors="replace",
        ) as fp:

            for raw_line in fp:

                line = raw_line.rstrip("\n")

                if not line.strip():
                    continue

                batch.append(line)

                if len(batch) >= batch_size:

                    yield batch

                    batch = []

        if batch:

            yield batch

    def ingest(
        self,
        file_path: str,
    ) -> dict:
        """
        Upload a syslog file, split into batches.

        Every batch is sent as its own request, sharing a single
        job_id generated for this upload, so no single HTTP
        request needs to hold more than
        settings.ingest_batch_size lines in memory or on the wire.

        Returns a summary dict covering the whole upload -- the
        last batch's response plus totals -- since the caller
        (the CLI's INGEST command) expects one result for the
        file, not one per batch.
        """

        path = Path(file_path)

        if not path.exists():

            raise FileNotFoundError(file_path)

        job_id = str(uuid.uuid4())

        logger.info(
            "Uploading %s as job %s (batch_size=%d)",
            file_path,
            job_id,
            settings.ingest_batch_size,
        )

        batches = list(
            self._iter_batches(
                path,
                settings.ingest_batch_size,
            )
        )

        if not batches:

            raise ValueError(
                f"{file_path} contains no non-blank lines to ingest."
            )

        last_response: dict = {}
        total_lines = 0

        for batch_index, lines in enumerate(batches):

            is_final_batch = (
                batch_index == len(batches) - 1
            )

            response = requests.post(
                f"{self.base_url}/ingest",
                json={
                    "job_id": job_id,
                    "filename": path.name,
                    "batch_index": batch_index,
                    "is_final_batch": is_final_batch,
                    "lines": lines,
                },
                timeout=60,
            )

            response.raise_for_status()

            last_response = response.json()
            total_lines += len(lines)

            logger.info(
                "Uploaded batch %d/%d (%d lines) for job %s",
                batch_index + 1,
                len(batches),
                len(lines),
                job_id,
            )

        return {
            **last_response,
            "batches_sent": len(batches),
            "total_lines_sent": total_lines,
        }

    ########################################################
    # Generic GET
    ########################################################

    def _get(
        self,
        endpoint: str,
        value: str,
    ) -> dict:

        response = requests.get(
            f"{self.base_url}/{endpoint}",
            params={
                "value": value,
            },
            timeout=60,
        )

        response.raise_for_status()

        return response.json()

    ########################################################
    # SEARCH
    ########################################################

    def search_date(self, value: str):

        return self._get(
            "search/date",
            value,
        )

    def search_host(self, value: str):

        return self._get(
            "search/host",
            value,
        )

    def search_daemon(self, value: str):

        return self._get(
            "search/daemon",
            value,
        )

    def search_severity(self, value: str):

        return self._get(
            "search/severity",
            value,
        )

    def search_keyword(self, value: str):

        return self._get(
            "search/keyword",
            value,
        )

    def count_keyword(self, value: str):

        return self._get(
            "count/keyword",
            value,
        )

    ########################################################
    # PURGE
    ########################################################

    def purge(self) -> dict:
        """
        Delete all indexed log entries through the Gateway.
        """

        response = requests.delete(
            f"{self.base_url}/purge",
            timeout=60,
        )

        response.raise_for_status()

        return response.json()