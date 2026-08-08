from functools import lru_cache

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """
    Global project configuration.
    """

    #########################
    # Gateway
    #########################

    gateway_host: str = Field(default="0.0.0.0")

    gateway_port: int = Field(default=8000)
    
    gateway_external_port: int = 8000

    #########################
    # RabbitMQ
    #########################

    rabbitmq_host: str = Field(default="rabbitmq")

    rabbitmq_port: int = Field(default=5672)

    rabbitmq_user: str = Field(default="guest")

    rabbitmq_password: str = Field(default="guest")

    queue_name: str = Field(default="ingest_queue")

    #########################
    # MongoDB
    #########################

    mongo_uri: str = Field(
        default="mongodb://mongos:27017"
    )

    database: str = Field(default="minisplunk")

    collection: str = Field(default="logs")

    #########################
    # Replica Sets
    #########################

    config_replset: str = Field(default="configReplSet")

    shard1_replset: str = Field(default="shard1rs")

    shard2_replset: str = Field(default="shard2rs")

    #########################
    # Ports
    #########################

    config_port: int = Field(default=27019)

    shard_port: int = Field(default=27018)

    mongos_port: int = Field(default=27017)

    #########################
    # Worker
    #########################

    worker_prefetch: int = Field(default=5)

    #########################
    # Distributed Lock
    #########################

    lock_collection: str = Field(default="distributed_locks")

    lock_ttl_seconds: int = Field(default=60)

    #########################
    # Logging
    #########################

    log_level: str = Field(default="INFO")

    model_config = SettingsConfigDict(
        env_file="configs/local/app.env",
        extra="ignore",
    )


@lru_cache
def get_settings() -> Settings:
    """
    Cached settings singleton.
    """
    return Settings()


settings = get_settings()