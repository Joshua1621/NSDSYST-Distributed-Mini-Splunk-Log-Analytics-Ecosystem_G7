"""
RabbitMQ publisher used by the Gateway.

Responsible for publishing ingestion jobs to the
durable RabbitMQ queue.
"""

from __future__ import annotations

import json

import pika
from pika.exceptions import AMQPConnectionError
from tenacity import retry, stop_after_attempt, wait_fixed

from shared.config import settings
from shared.logging import get_logger

logger = get_logger("gateway.publisher")


class RabbitMQPublisher:
    """
    RabbitMQ publisher.

    The Gateway is stateless.

    A new RabbitMQ connection is created for each publish
    operation, making the publisher thread-safe for FastAPI.
    """

    ########################################################
    # Connection
    ########################################################

    @retry(
        stop=stop_after_attempt(30),
        wait=wait_fixed(2),
        reraise=True,
    )
    def _create_connection(self) -> pika.BlockingConnection:
        """
        Create a RabbitMQ connection.
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

        return pika.BlockingConnection(parameters)

    ########################################################
    # Publish
    ########################################################

    def publish(self, message: dict) -> None:
        """
        Publish a persistent message.

        A fresh RabbitMQ connection is used for every publish,
        making this method safe for concurrent FastAPI requests.
        """

        connection = None

        try:

            connection = self._create_connection()

            channel = connection.channel()

            channel.queue_declare(
                queue=settings.queue_name,
                durable=True,
            )

            body = json.dumps(message)

            channel.basic_publish(
                exchange="",
                routing_key=settings.queue_name,
                body=body,
                properties=pika.BasicProperties(
                    delivery_mode=pika.DeliveryMode.Persistent,
                ),
            )

            logger.info("Job published successfully.")

        except AMQPConnectionError:
            logger.exception("Failed to publish job to RabbitMQ.")
            raise

        finally:

            if connection and connection.is_open:
                connection.close()

                logger.debug("RabbitMQ connection closed.")