"""
RabbitMQ consumer for the Mini-Splunk Worker.
"""

from __future__ import annotations

import json
from typing import Callable

import pika
from pika.adapters.blocking_connection import BlockingChannel
from pika.spec import Basic, BasicProperties
from tenacity import retry, stop_after_attempt, wait_fixed

from shared.config import settings
from shared.logging import get_logger

logger = get_logger("worker.consumer")


class RabbitMQConsumer:
    """
    RabbitMQ consumer.

    Consumes ingestion jobs from RabbitMQ using
    manual acknowledgements.
    """

    def __init__(
        self,
        callback: Callable[
            [BlockingChannel, Basic.Deliver, BasicProperties, dict],
            None,
        ],
    ) -> None:

        self.callback = callback

    ########################################################
    # Connection
    ########################################################

    @retry(
        stop=stop_after_attempt(30),
        wait=wait_fixed(2),
        reraise=True,
    )
    def start(self) -> None:
        """
        Connect to RabbitMQ and begin consuming.
        """

        logger.info("Connecting to RabbitMQ...")

        credentials = pika.PlainCredentials(
            settings.rabbitmq_user,
            settings.rabbitmq_password,
        )

        parameters = pika.ConnectionParameters(
            host=settings.rabbitmq_host,
            port=settings.rabbitmq_port,
            credentials=credentials,
            heartbeat=60,
        )

        connection = pika.BlockingConnection(parameters)

        channel = connection.channel()

        channel.queue_declare(
            queue=settings.queue_name,
            durable=True,
        )

        channel.basic_qos(
            prefetch_count=settings.worker_prefetch
        )

        logger.info(
            "Worker consuming queue '%s'.",
            settings.queue_name,
        )

        ####################################################
        # Wrapper callback
        ####################################################

        def _consume(
            ch: BlockingChannel,
            method: Basic.Deliver,
            properties: BasicProperties,
            body: bytes,
        ) -> None:

            message = json.loads(body.decode())

            self.callback(
                ch,
                method,
                properties,
                message,
            )

        channel.basic_consume(
            queue=settings.queue_name,
            on_message_callback=_consume,
            auto_ack=False,
        )

        logger.info("Waiting for messages...")

        channel.start_consuming()