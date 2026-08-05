"""
MongoDB distributed lock implementation.

Used to coordinate distributed operations
such as PURGE across multiple Worker nodes.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from pymongo import ASCENDING, MongoClient
from pymongo.collection import Collection
from pymongo.errors import DuplicateKeyError

from shared.config import settings
from shared.logging import get_logger

logger = get_logger("shared.database.lock")


class DistributedLock:
    """
    MongoDB-backed distributed lock.

    A TTL index ensures automatic recovery if the
    process holding the lock terminates unexpectedly.
    """

    LOCK_ID = "purge_lock"

    def __init__(self) -> None:

        self.client = MongoClient(
            settings.mongo_uri,
            serverSelectionTimeoutMS=3000,
        )

        self.collection: Collection = (
            self.client[settings.database]
            [settings.lock_collection]
        )

        ####################################################
        # TTL Index
        ####################################################

        self.collection.create_index(
            [("expires_at", ASCENDING)],
            expireAfterSeconds=0,
            name="expires_at_ttl",
        )

    ########################################################
    # Acquire
    ########################################################

    def acquire(self) -> bool:
        """
        Acquire the distributed lock.

        Returns:
            True if acquired.
            False if another process owns it.
        """

        now = datetime.utcnow()

        expires = now + timedelta(
            seconds=settings.lock_ttl_seconds,
        )

        ####################################################
        # Remove stale lock if TTL monitor
        # has not yet deleted it.
        ####################################################

        self.collection.delete_many(
            {
                "_id": self.LOCK_ID,
                "expires_at": {
                    "$lte": now,
                },
            }
        )

        try:

            self.collection.insert_one(
                {
                    "_id": self.LOCK_ID,
                    "owner": "gateway",
                    "created_at": now,
                    "expires_at": expires,
                }
            )

            logger.info(
                "Distributed lock acquired."
            )

            return True

        except DuplicateKeyError:

            logger.info(
                "Distributed lock already held."
            )

            return False

    ########################################################
    # Release
    ########################################################

    def release(self) -> None:
        """
        Release the distributed lock.
        """

        self.collection.delete_one(
            {
                "_id": self.LOCK_ID,
            }
        )

        logger.info(
            "Distributed lock released."
        )

    ########################################################
    # Status
    ########################################################

    def active(self) -> bool:
        """
        Returns True if a valid lock exists.
        """

        now = datetime.utcnow()

        return (
            self.collection.count_documents(
                {
                    "_id": self.LOCK_ID,
                    "expires_at": {
                        "$gt": now,
                    },
                }
            )
            > 0
        )

    ########################################################
    # Cleanup
    ########################################################

    def close(self) -> None:
        """
        Close MongoDB connection.
        """

        self.client.close()