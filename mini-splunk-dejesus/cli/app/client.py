"""
HTTP client for communicating with the Gateway.
"""

from __future__ import annotations

from pathlib import Path

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

    def ingest(
        self,
        file_path: str,
    ) -> dict:

        path = Path(file_path)

        if not path.exists():

            raise FileNotFoundError(file_path)

        logger.info(
            "Uploading %s",
            file_path,
        )

        with path.open(
            "r",
            encoding="utf-8",
            errors="replace",
        ) as fp:

            response = requests.post(
                f"{self.base_url}/ingest",
                json={
                    "filename": path.name,
                    "content": fp.read(),
                },
                timeout=60,
            )

        response.raise_for_status()

        return response.json()

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