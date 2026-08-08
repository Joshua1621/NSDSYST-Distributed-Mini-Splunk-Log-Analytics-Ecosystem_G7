"""
Mini-Splunk Gateway Service.

Responsibilities

- Receive ingestion requests
- Publish jobs to RabbitMQ
- Execute search requests
- Coordinate distributed purge
"""