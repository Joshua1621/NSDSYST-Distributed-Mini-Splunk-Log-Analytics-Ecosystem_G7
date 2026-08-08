"""
MongoDB cluster initialization entry point.
"""

from shared.logging import get_logger

from mongo_init.app.bootstrap import bootstrap_cluster
from mongo_init.app.verifier import verify_cluster

logger = get_logger("mongo-init")


def main() -> None:
    """
    Initialize and verify the MongoDB cluster.
    """

    logger.info("=" * 60)
    logger.info("Mini-Splunk MongoDB Initializer")
    logger.info("=" * 60)

    try:

        bootstrap_cluster()

        verify_cluster()

        logger.info("=" * 60)
        logger.info("MongoDB cluster is READY.")
        logger.info("=" * 60)

    except Exception:
        logger.exception("MongoDB initialization failed.")
        raise


if __name__ == "__main__":
    main()