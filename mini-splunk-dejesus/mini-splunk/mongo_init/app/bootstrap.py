"""
MongoDB cluster bootstrap orchestration.

This module coordinates the initialization of the MongoDB
sharded cluster used by the Mini-Splunk system.

Responsibilities:
- Wait for MongoDB services
- Initialize replica sets
- Register shards
- Enable database sharding
- Configure collection sharding
"""

from shared.config import settings
from shared.logging import get_logger

from mongo_init.app.cluster import MongoClusterManager

logger = get_logger("mongo-init.bootstrap")


def bootstrap_cluster() -> None:
    """
    Bootstrap the complete MongoDB cluster.
    """

    manager = MongoClusterManager()

    try:

        ####################################################
        # Wait for Services
        ####################################################

        logger.info("Waiting for Config Server...")

        manager.wait_for_mongo(
            f"mongodb://configsvr:{settings.config_port}"
        )

        logger.info("Waiting for Shard 1...")

        manager.wait_for_mongo(
            f"mongodb://shard1:{settings.shard_port}"
        )

        logger.info("Waiting for Shard 2...")

        manager.wait_for_mongo(
            f"mongodb://shard2:{settings.shard_port}"
        )

        logger.info("Waiting for mongos...")

        manager.wait_for_mongo(settings.mongo_uri)

        ####################################################
        # Initialize Replica Sets
        ####################################################

        logger.info("Initializing Config Server replica set...")

        manager.initialize_replica_set(
            f"mongodb://configsvr:{settings.config_port}",
            {
                "_id": settings.config_replset,
                "configsvr": True,
                "members": [
                    {
                        "_id": 0,
                        "host": f"configsvr:{settings.config_port}",
                    }
                ],
            },
        )

        logger.info("Initializing Shard 1 replica set...")

        manager.initialize_replica_set(
            f"mongodb://shard1:{settings.shard_port}",
            {
                "_id": settings.shard1_replset,
                "members": [
                    {
                        "_id": 0,
                        "host": f"shard1:{settings.shard_port}",
                    }
                ],
            },
        )

        logger.info("Initializing Shard 2 replica set...")

        manager.initialize_replica_set(
            f"mongodb://shard2:{settings.shard_port}",
            {
                "_id": settings.shard2_replset,
                "members": [
                    {
                        "_id": 0,
                        "host": f"shard2:{settings.shard_port}",
                    }
                ],
            },
        )

        ####################################################
        # Register Shards
        ####################################################

        logger.info("Registering shards...")

        manager.register_shard(
            settings.shard1_replset,
            "shard1",
            settings.shard_port,
        )

        manager.register_shard(
            settings.shard2_replset,
            "shard2",
            settings.shard_port,
        )

        ####################################################
        # Configure Sharding
        ####################################################

        logger.info("Enabling database sharding...")

        manager.enable_database_sharding()

        logger.info("Configuring collection sharding...")

        manager.shard_collection()

        logger.info("MongoDB cluster bootstrap completed successfully.")

    finally:
        manager.close()