from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from minisplunk.config import RabbitMQConfig


class RabbitMQPublisher:
    def __init__(self, config: RabbitMQConfig) -> None:
        self.config = config

    def publish_ingest_job(self, job: dict[str, Any]) -> None:
        import pika

        credentials = pika.PlainCredentials(self.config.username, self.config.password)
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(self.config.host, self.config.port, "/", credentials)
        )

        try:
            channel = connection.channel()
            _declare_ingest_topology(channel, self.config)
            channel.basic_publish(
                exchange=self.config.exchange,
                routing_key=self.config.routing_key,
                body=json.dumps(job),
                properties=pika.BasicProperties(
                    content_type="application/json",
                    delivery_mode=2,
                    message_id=job["job_id"],
                ),
            )
        finally:
            connection.close()


def consume_ingest_jobs(config: RabbitMQConfig, callback: Callable[[dict[str, Any]], None]) -> None:
    import pika

    credentials = pika.PlainCredentials(config.username, config.password)
    connection = pika.BlockingConnection(
        pika.ConnectionParameters(config.host, config.port, "/", credentials)
    )
    channel = connection.channel()
    _declare_ingest_topology(channel, config)
    channel.basic_qos(prefetch_count=1)

    def on_message(ch: Any, method: Any, properties: Any, body: bytes) -> None:
        try:
            callback(json.loads(body))
        except Exception:
            ch.basic_nack(delivery_tag=method.delivery_tag, requeue=True)
            raise
        else:
            ch.basic_ack(delivery_tag=method.delivery_tag)

    channel.basic_consume(queue=config.queue, on_message_callback=on_message, auto_ack=False)
    channel.start_consuming()


def _declare_ingest_topology(channel: Any, config: RabbitMQConfig) -> None:
    channel.exchange_declare(exchange=config.exchange, exchange_type="direct", durable=True)
    channel.queue_declare(queue=config.queue, durable=True)
    channel.queue_bind(exchange=config.exchange, queue=config.queue, routing_key=config.routing_key)
