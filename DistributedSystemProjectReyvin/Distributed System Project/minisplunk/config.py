from __future__ import annotations

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class RabbitMQConfig:
    host: str
    port: int
    username: str
    password: str
    exchange: str
    queue: str
    routing_key: str


@dataclass(frozen=True)
class GatewayConfig:
    host: str
    port: int


def rabbitmq_config() -> RabbitMQConfig:
    return RabbitMQConfig(
        host=os.getenv("RABBITMQ_HOST", "localhost"),
        port=int(os.getenv("RABBITMQ_PORT", "5672")),
        username=os.getenv("RABBITMQ_USER", "rabbituser"),
        password=os.getenv("RABBITMQ_PASSWORD", "rabbit1234"),
        exchange=os.getenv("RABBITMQ_EXCHANGE", "minisplunk.direct"),
        queue=os.getenv("RABBITMQ_INGEST_QUEUE", "log_ingest"),
        routing_key=os.getenv("RABBITMQ_INGEST_ROUTING_KEY", "ingest"),
    )


def gateway_config() -> GatewayConfig:
    return GatewayConfig(
        host=os.getenv("GATEWAY_HOST", "127.0.0.1"),
        port=int(os.getenv("GATEWAY_PORT", "8080")),
    )


def mongo_uri() -> str:
    return os.getenv(
        "MONGO_URI",
        "mongodb://localhost:27017/minisplunk",
    )
