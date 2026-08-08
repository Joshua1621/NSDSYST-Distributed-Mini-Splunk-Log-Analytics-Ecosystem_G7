"""
MongoDB cluster verification.

Verifies that the Mini-Splunk MongoDB cluster has been
initialized correctly.
"""

from pymongo.errors import OperationFailure

from shared.config import settings
from shared.exceptions import MongoBootstrapError
from shared.logging import get_logger

from mongo_init.app.cluster import MongoClusterManager

logger = get_logger("mongo-init.verifier")


def verify_cluster() -> None:
    """
    Verify the MongoDB cluster infrastructure.

    This verification intentionally checks only infrastructure
    components. Application objects such as the logs collection
    and its indexes are created lazily by the Worker during the
    first successful ingestion.
    """

    manager = MongoClusterManager()

    try:

        ####################################################
        # Verify Registered Shards
        ####################################################

        logger.info("Verifying registered shards...")

        shards = manager.list_shards()

        shard_names = {shard["id"] for shard in shards}

        expected = {
            settings.shard1_replset,
            settings.shard2_replset,
        }

        missing = expected - shard_names

        if missing:
            raise MongoBootstrapError(
                f"Missing shard(s): {', '.join(sorted(missing))}"
            )

        logger.info("Registered shards verified.")

        ####################################################
        # Verify Database Connectivity
        ####################################################

        logger.info(
            "Verifying database connectivity..."
        )

        client = manager.get_client(settings.mongo_uri)

        client.admin.command("ping")

        logger.info(
            "MongoDB router is reachable."
        )

        ####################################################
        # Verification Complete
        ####################################################

        logger.info(
            "MongoDB cluster verification successful."
        )

    except OperationFailure as exc:
        raise MongoBootstrapError(
            "MongoDB cluster verification failed."
        ) from exc

    finally:
        manager.close()