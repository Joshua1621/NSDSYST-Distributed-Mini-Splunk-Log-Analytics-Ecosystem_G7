"""
Worker lifecycle and message processing.
"""

from __future__ import annotations

from io import StringIO

from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic, BasicProperties

from shared.logging import get_logger

from worker.app.consumer import RabbitMQConsumer
from worker.app.database import MongoRepository
from worker.app.parser import SyslogParser

logger = get_logger("worker.lifecycle")


class Worker:
    """
    Mini-Splunk Worker.

    Responsibilities:
    - Consume RabbitMQ messages
    - Parse RFC3164 syslog entries
    - Store parsed logs in MongoDB
    - ACK messages only after successful persistence
    """

    REQUIRED_FIELDS = (
        "job_id",
        "filename",
        "content",
    )

    def __init__(self) -> None:

        logger.info("Initializing Worker...")

        self.parser = SyslogParser()

        self.repository = MongoRepository()

        self.consumer = RabbitMQConsumer(
            self.process_message
        )

        logger.info("Worker initialized.")

    ########################################################
    # Lifecycle
    ########################################################

    def start(self) -> None:
        """
        Start consuming RabbitMQ jobs.
        """

        logger.info("Worker started.")

        self.consumer.start()

    def stop(self) -> None:
        """
        Gracefully stop the Worker.
        """

        logger.info("Stopping Worker...")

        try:
            self.repository.close()

        except Exception:

            logger.exception(
                "Failed to close MongoDB connection."
            )

        logger.info("Worker stopped.")

    ########################################################
    # Validation
    ########################################################

    def validate_message(
        self,
        message: dict,
    ) -> bool:
        """
        Validate the RabbitMQ message payload.
        """

        for field in self.REQUIRED_FIELDS:

            if field not in message:

                logger.error(
                    "Invalid message. Missing '%s'.",
                    field,
                )

                return False

        return True

    ########################################################
    # Message Processing
    ########################################################

    def process_message(
        self,
        channel: BlockingChannel,
        method: Basic.Deliver,
        properties: BasicProperties,
        message: dict,
    ) -> None:
        """
        Process one ingestion job.
        """

        ####################################################
        # Validate Message
        ####################################################

        if not self.validate_message(message):

            logger.error(
                "Rejecting malformed RabbitMQ message."
            )

            channel.basic_ack(
                delivery_tag=method.delivery_tag,
            )

            return

        job_id = message["job_id"]

        filename = message["filename"]

        logger.info(
            "Processing job %s (%s)",
            job_id,
            filename,
        )

        try:

            ####################################################
            # Distributed Purge Lock
            ####################################################

            if self.repository.purge_lock_active():

                logger.warning(
                    "Purge lock active. Requeueing job %s.",
                    job_id,
                )

                channel.basic_nack(
                    delivery_tag=method.delivery_tag,
                    requeue=True,
                )

                return

            ####################################################
            # Parse File
            ####################################################

            stream = StringIO(
                message["content"]
            )

            inserted = 0
            skipped = 0

            for raw_line in stream:

                raw_line = raw_line.strip()

                if not raw_line:
                    continue

                parsed = self.parser.parse(
                    raw_line
                )

                if parsed is None:

                    skipped += 1

                    continue

                self.repository.upsert_log(
                    parsed
                )

                inserted += 1

            ####################################################
            # ACK ONLY AFTER SUCCESS
            ####################################################

            channel.basic_ack(
                delivery_tag=method.delivery_tag,
            )

            logger.info(
                (
                    "Job %s completed successfully. "
                    "Inserted=%d Skipped=%d"
                ),
                job_id,
                inserted,
                skipped,
            )

        except Exception:

            logger.exception(
                "Worker failed processing job %s.",
                job_id,
            )

            ####################################################
            # Transient failure
            ####################################################

            channel.basic_nack(
                delivery_tag=method.delivery_tag,
                requeue=True,
            )