"""
MongoDB repository for Gateway search operations.
"""

from __future__ import annotations

import re

from pymongo import MongoClient
from pymongo.collection import Collection

from shared.config import settings
from shared.logging import get_logger

logger = get_logger("gateway.database")


class GatewayRepository:
    """
    Repository used by the Gateway to query the MongoDB
    sharded cluster through mongos.
    """

    def __init__(self) -> None:

        logger.info("Connecting to MongoDB...")

        self.client = MongoClient(
            settings.mongo_uri,
            serverSelectionTimeoutMS=3000,
        )

        self.collection: Collection = (
            self.client[settings.database]
            [settings.collection]
        )

        logger.info("MongoDB connection established.")

    ########################################################
    # Search Operations
    ########################################################

    def search_date(
        self,
        date: str,
    ) -> list[dict]:
        """
        Search logs by timestamp prefix.

        Examples:
            Jan
            Jan 10
            Jan 10 12
        """

        cursor = self.collection.find(
            {
                "timestamp": {
                    "$regex": f"^{re.escape(date)}"
                }
            },
            {
                "_id": 0,
            },
        )

        return list(cursor)

    def search_host(
        self,
        hostname: str,
    ) -> list[dict]:
        """
        Search by hostname (case-insensitive exact match).
        """

        cursor = self.collection.find(
            {
                "hostname": {
                    "$regex": f"^{re.escape(hostname)}$",
                    "$options": "i",
                }
            },
            {
                "_id": 0,
            },
        )

        return list(cursor)

    def search_daemon(
        self,
        daemon: str,
    ) -> list[dict]:
        """
        Search by daemon/process (case-insensitive exact match).
        """

        cursor = self.collection.find(
            {
                "process": {
                    "$regex": f"^{re.escape(daemon)}$",
                    "$options": "i",
                }
            },
            {
                "_id": 0,
            },
        )

        return list(cursor)

    def search_severity(
        self,
        severity: str,
    ) -> list[dict]:
        """
        Search by severity (case-insensitive exact match).
        """

        cursor = self.collection.find(
            {
                "severity": {
                    "$regex": f"^{re.escape(severity)}$",
                    "$options": "i",
                }
            },
            {
                "_id": 0,
            },
        )

        return list(cursor)

    def search_keyword(
        self,
        keyword: str,
    ) -> list[dict]:
        """
        Search for a keyword using MongoDB text search.
        """

        cursor = self.collection.find(
            {
                "$text": {
                    "$search": keyword
                }
            },
            {
                "_id": 0,
            },
        )

        return list(cursor)

    def count_keyword(
        self,
        keyword: str,
    ) -> int:
        """
        Count occurrences of a keyword.
        """

        return self.collection.count_documents(
            {
                "$text": {
                    "$search": keyword
                }
            }
        )

    ########################################################
    # Purge
    ########################################################

    def purge(self) -> int:
        """
        Delete all indexed log entries.

        NOTE:
        Distributed locking will be added in a later phase.
        """

        result = self.collection.delete_many({})

        return result.deleted_count

    ########################################################
    # Cleanup
    ########################################################

    def close(self) -> None:
        """
        Close the MongoDB connection.
        """

        self.client.close()

        logger.info("MongoDB connection closed.")