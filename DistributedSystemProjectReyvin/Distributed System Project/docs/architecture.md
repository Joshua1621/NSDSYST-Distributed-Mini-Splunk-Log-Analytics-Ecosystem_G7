# Distributed Mini-Splunk Architecture

## Spec Summary

The system ingests syslog files, parses each line into structured fields, stores the
parsed logs in a distributed data layer, and supports scatter-gather queries through an
API gateway.

Required components:

- CLI forwarder
- Communication middleware or IPC layer
- Multiple containerized workers
- Distributed or manually sharded data layer
- Ingest API and Query API/search head

## Recommended Build Order

1. CLI client
2. Ingest API and Query API HTTP contracts
3. RabbitMQ ingestion queue
4. Worker parser and acknowledgement behavior
5. Sharded MongoDB storage write path
6. Search aggregation path
7. Purge coordination
8. Docker Compose and chaos tests

## Proposed Runtime Choices

- Python for CLI, gateway, and workers
- RabbitMQ for ingestion jobs
- Separate HTTP APIs for ingestion and querying
- Sharded MongoDB cluster for distributed storage

## Initial API Contract

The CLI currently expects these endpoints:

- `POST /ingest`
  - Service: Ingest API
  - Default local address: `http://localhost:8081`
  - Body: raw syslog file bytes
  - Headers: `X-File-Name`
  - Expected response: `202 Accepted`
- `POST /query`
  - Service: Query API
  - Default local address: `http://localhost:8080`
  - JSON body: `{"type": "host|date|daemon|severity|keyword", "value": "..."}`
  - Expected response: `200 OK`
- `POST /query/count-keyword`
  - Service: Query API
  - JSON body: `{"keyword": "..."}`
  - Expected response: `200 OK`
- `DELETE /logs`
  - Service: Query API
  - Expected response: `200 OK`

The Ingest API translates ingestion requests into RabbitMQ jobs. The Query API handles
search and purge requests through `mongos`, the MongoDB sharded-cluster router.

The Query API also exposes browser-friendly inspection pages:

- `GET /logs`
  - Shows parsed log records from MongoDB.
  - Supports optional filters: `severity`, `host` or `hostname`, `daemon` or
    `process`, `keyword`, and `limit`.
  - Use `?format=json` for API-style JSON.
- `GET /nodes`
  - Shows worker node metadata.
  - Use `?format=json` for API-style JSON.

## RabbitMQ Contract

The gateway publishes ingestion jobs to a durable direct exchange:

- Exchange: `minisplunk.direct`
- Queue: `log_ingest`
- Routing key: `ingest`
- Message body:

```json
{
  "job_id": "uuid",
  "file_name": "syslog.log",
  "payload": "raw syslog file contents"
}
```

Workers consume with `prefetch_count=1` and manual acknowledgements. A worker only ACKs
after parsed documents are written to MongoDB. Redelivered jobs use a unique
`dedupe_key` per line so repeated delivery does not create duplicates.

## MongoDB Layout

The Docker stack starts a real sharded MongoDB topology:

- Config server replica set: `cfg`
- Shard replica set: `shard1`
- Shard replica set: `shard2`
- Query router: `mongos`

The application connects to `mongos`, and MongoDB distributes `minisplunk.logs` across
the shards using `dedupe_key` as the shard key.

Collection: `logs`

- `job_id`
- `line_number`
- `file_name`
- `dedupe_key`
- `raw`
- `timestamp`
- `hostname`
- `process`
- `severity`
- `message`

Collection: `locks`

- One lock document coordinates purge/read/write operations.

Collection: `nodes`

- `node_name`
- `role`
- `status`
- `first_seen`
- `last_active`
- `jobs_processed`
- `logs_inserted`
