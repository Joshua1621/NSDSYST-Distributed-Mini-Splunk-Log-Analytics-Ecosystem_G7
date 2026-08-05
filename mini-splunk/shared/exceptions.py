"""
Shared application exceptions.
"""


class MiniSplunkError(Exception):
    """Base exception."""


class MongoBootstrapError(MiniSplunkError):
    """MongoDB cluster initialization failed."""


class RabbitMQConnectionError(MiniSplunkError):
    """RabbitMQ unavailable."""


class DistributedLockError(MiniSplunkError):
    """Distributed lock acquisition failed."""


class ConfigurationError(MiniSplunkError):
    """Invalid configuration."""