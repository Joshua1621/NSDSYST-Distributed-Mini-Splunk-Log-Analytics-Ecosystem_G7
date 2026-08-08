"""
Worker lifecycle and message processing.
"""

from __future__ import annotations

from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic, BasicProperties

from shared.config import settings
from shared.logging import get_logger

from worker.app.consumer import RabbitMQConsumer
from worker.app.database import MongoRepository
from worker.app.parser import SyslogParser

logger = get_logger("worker.lifecycle")


class Worker:
    """
    Mini-Splunk Worker.

    Responsibilities:
    - Consume RabbitMQ messages, each holding one batch of lines
    - Parse RFC3164 syslog entries
    - Store parsed logs in MongoDB
    - ACK messages only after successful persistence
    """

    REQUIRED_FIELDS = (
        "job_id",
        "filename",
        "batch_index",
        "lines",
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
    # Offset Calculation
    ########################################################

    @staticmethod
    def compute_base_offset(batch_index: int) -> int:
        """
        Compute the global line offset of the first line in a
        batch.

        Every batch published by the CLI holds up to
        settings.ingest_batch_size lines (the last batch may hold
        fewer, if the file's line count isn't an exact multiple of
        the batch size -- but every batch BEFORE the last one is
        always exactly full, so the arithmetic below still lands
        each batch on the correct starting offset regardless of
        the final batch's actual size). Multiplying by batch_index
        gives every line in the file a globally unique, stable
        offset without the Worker needing to know the file's total
        length in advance.
        """

        return batch_index * settings.ingest_batch_size

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
        Process one batch of an ingestion job.
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

        batch_index = message["batch_index"]

        logger.info(
            "Processing job %s batch %d (%s)",
            job_id,
            batch_index,
            filename,
        )

        try:

            ####################################################
            # Distributed Purge Lock
            ####################################################

            if self.repository.purge_lock_active():

                logger.warning(
                    "Purge lock active. Requeueing job %s batch %d.",
                    job_id,
                    batch_index,
                )

                channel.basic_nack(
                    delivery_tag=method.delivery_tag,
                    requeue=True,
                )

                return

            ####################################################
            # Parse Batch
            ####################################################

            base_offset = self.compute_base_offset(batch_index)

            inserted = 0
            skipped = 0

            for position, raw_line in enumerate(message["lines"]):

                raw_line = raw_line.strip()

                if not raw_line:
                    continue

                # Global offset: stable across redelivery of this
                # exact batch (same job_id, batch_index, position
                # always reproduce the same offset), and unique
                # across every other batch in this job (different
                # batch_index -> different base_offset range).
                line_offset = base_offset + position

                parsed = self.parser.parse(
                    raw_line,
                    job_id,
                    line_offset,
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
                    "Job %s batch %d completed successfully. "
                    "Inserted=%d Skipped=%d"
                ),
                job_id,
                batch_index,
                inserted,
                skipped,
            )

        except Exception:

            logger.exception(
                "Worker failed processing job %s batch %d.",
                job_id,
                batch_index,
            )

            ####################################################
            # Transient failure
            ####################################################

            channel.basic_nack(
                delivery_tag=method.delivery_tag,
                requeue=True,
            )