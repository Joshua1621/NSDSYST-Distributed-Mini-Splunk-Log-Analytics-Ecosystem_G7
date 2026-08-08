"""
Mini-Splunk Worker Service.

Responsibilities

- Consume RabbitMQ jobs

- Parse syslog entries

- Generate deterministic IDs

- Write to MongoDB

- ACK messages

- Requeue failures
"""