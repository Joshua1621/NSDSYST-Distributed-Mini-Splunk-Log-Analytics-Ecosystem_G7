"""
MongoDB cluster management utilities.

This module contains low-level administrative operations for:

- Replica set initialization
- Shard registration
- Sharding configuration
- Index creation
- Cluster inspection

All operations are designed to be idempotent.
"""

from __future__ import annotations

from typing import Any

from pymongo import MongoClient
from pymongo.errors import (
    OperationFailure,
    ServerSelectionTimeoutError,
)
from tenacity import retry, stop_after_attempt, wait_fixed

from shared.config import settings
from shared.exceptions import MongoBootstrapError
from shared.logging import get_logger

logger = get_logger("mongo-init.cluster")


class MongoClusterManager:
    """
    Encapsulates MongoDB cluster administration.
    """

    def __init__(self) -> None:
        self._clients: dict[str, MongoClient] = {}
        self.mongos_uri = settings.mongo_uri

    ########################################################
    # Client Management
    ########################################################

    def get_client(self, uri: str) -> MongoClient:
        """
        Return a cached MongoDB client.
        """
        if uri not in self._clients:
            self._clients[uri] = MongoClient(
                uri,
                serverSelectionTimeoutMS=3000,
            )

        return self._clients[uri]

    def close(self) -> None:
        """
        Close all MongoDB clients.
        """
        for client in self._clients.values():
            client.close()

        self._clients.clear()

    ########################################################
    # Connectivity
    ########################################################

    @retry(
        stop=stop_after_attempt(60),
        wait=wait_fixed(2),
    )
    def wait_for_mongo(self, uri: str) -> None:
        """
        Wait until MongoDB becomes available.
        """
        logger.info("Waiting for MongoDB at %s...", uri)

        client = self.get_client(uri)

        client.admin.command("ping")

        logger.info("MongoDB ready.")

    ########################################################
    # Replica Sets
    ########################################################

    def replica_set_initialized(
        self,
        client: MongoClient,
    ) -> bool:
        """
        Check whether the replica set has already been initialized.
        """
        try:
            client.admin.command("replSetGetStatus")
            return True

        except (
            OperationFailure,
            ServerSelectionTimeoutError,
        ):
            return False

    def initialize_replica_set(
        self,
        uri: str,
        config: dict[str, Any],
    ) -> None:
        """
        Initialize a replica set.

        Safe to call multiple times.
        """
        client = self.get_client(uri)

        if self.replica_set_initialized(client):
            logger.info(
                "Replica set '%s' already initialized.",
                config["_id"],
            )
            return

        logger.info(
            "Initializing replica set '%s'...",
            config["_id"],
        )

        try:
            client.admin.command(
                "replSetInitiate",
                config,
            )

        except OperationFailure as exc:
            raise MongoBootstrapError(
                f"Failed to initialize replica set '{config['_id']}'"
            ) from exc

        logger.info(
            "Replica set '%s' initialized successfully.",
            config["_id"],
        )

    ########################################################
    # Shards
    ########################################################

    def list_shards(self) -> list[dict[str, Any]]:
        """
        Return the list of registered shards.
        """
        client = self.get_client(self.mongos_uri)

        result = client.admin.command("listShards")

        return result.get("shards", [])

    def register_shard(
        self,
        replica_name: str,
        host: str,
        port: int,
    ) -> None:
        """
        Register a shard if it is not already present.
        """
        client = self.get_client(self.mongos_uri)

        for shard in self.list_shards():

            if shard["id"] == replica_name:
                logger.info(
                    "Shard '%s' already registered.",
                    replica_name,
                )
                return

        shard_address = f"{replica_name}/{host}:{port}"

        logger.info(
            "Registering shard '%s'...",
            replica_name,
        )

        client.admin.command(
            {
                "addShard": shard_address,
            }
        )

        logger.info(
            "Shard '%s' registered successfully.",
            replica_name,
        )

    ########################################################
    # Sharding
    ########################################################

    def enable_database_sharding(self) -> None:
        """
        Enable sharding for the application database.
        """
        client = self.get_client(self.mongos_uri)

        try:
            client.admin.command(
                {
                    "enableSharding": settings.database,
                }
            )

            logger.info(
                "Database '%s' sharding enabled.",
                settings.database,
            )

        except OperationFailure:
            logger.info(
                "Database '%s' already sharded.",
                settings.database,
            )

    def shard_collection(self) -> None:
        """
        Enable sharding for the logs collection.
        """
        client = self.get_client(self.mongos_uri)

        namespace = (
            f"{settings.database}."
            f"{settings.collection}"
        )

        try:
            client.admin.command(
                {
                    "shardCollection": namespace,
                    "key": {
                        "hostname": "hashed",
                    },
                }
            )

            logger.info(
                "Collection '%s' sharded.",
                namespace,
            )

        except OperationFailure:
            logger.info(
                "Collection '%s' already sharded.",
                namespace,
            )

    ########################################################
    # Indexes
    ########################################################

    def create_indexes(self) -> None:
        """
        Ensure all required indexes exist.
        """
        client = self.get_client(self.mongos_uri)

        collection = client[settings.database][settings.collection]

        logger.info("Ensuring indexes exist...")

        collection.create_index(
            "message_id",
            unique=True,
        )

        collection.create_index("timestamp")
        collection.create_index("hostname")
        collection.create_index("process")
        collection.create_index("severity")
        collection.create_index(
            [("message", "text")]
        )

        logger.info("Indexes verified.")