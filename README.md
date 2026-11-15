# Distributed Mini-Splunk

Course machine project for a distributed log analytics ecosystem.

This repository is being built in slices:

1. CLI forwarder/client
2. Ingest API, Query API, and RabbitMQ middleware
3. Distributed worker nodes
4. Sharded MongoDB data layer
5. Fault-tolerance and chaos-test hardening

## Current Slice: CLI Client

Run the client locally. In the Docker stack, ingestion and query are separate API
services:

- Ingest API: `http://localhost:8081`
- Query API: `http://localhost:8080`

```bash
python3 -m minisplunk.cli INGEST ./sample.log http://localhost:8081
python3 -m minisplunk.cli QUERY http://localhost:8080 SEARCH_HOST my-host
python3 -m minisplunk.cli QUERY http://localhost:8080 SEARCH_DATE "Jul 16"
python3 -m minisplunk.cli QUERY http://localhost:8080 SEARCH_DAEMON sshd
python3 -m minisplunk.cli QUERY http://localhost:8080 SEARCH_SEVERITY error
python3 -m minisplunk.cli QUERY http://localhost:8080 SEARCH_KEYWORD failed
python3 -m minisplunk.cli QUERY http://localhost:8080 COUNT_KEYWORD failed
python3 -m minisplunk.cli PURGE http://localhost:8080
```

The CLI targets HTTP APIs. The Ingest API enqueues ingestion jobs through RabbitMQ.
The Query API reads query results from the sharded MongoDB data layer.

## Run The Stack

Start RabbitMQ, the APIs, workers, and the MongoDB sharded cluster:

```bash
docker compose up --build
```

In another terminal:

```bash
python3 -m minisplunk.cli INGEST ./sample.log http://localhost:8081
python3 -m minisplunk.cli QUERY http://localhost:8080 SEARCH_HOST my-host
python3 -m minisplunk.cli QUERY http://localhost:8080 COUNT_KEYWORD failed
```

RabbitMQ management UI:

```text
http://localhost:15672
Sign in with the RabbitMQ username and password set in `docker-compose.yml`.
```

Mini-Splunk browser views:

```text
http://localhost:8080/logs
http://localhost:8080/nodes
```

JSON versions:

```text
http://localhost:8080/logs?format=json
http://localhost:8080/nodes?format=json
```

## Linux VM Setup

These steps assume Docker and Docker Compose are already installed on the VM.

From the project directory:

```bash
docker compose down --remove-orphans
docker compose up --build
```

For a clean database reset during testing:

```bash
docker compose down --volumes --remove-orphans
docker compose up --build
```

If you run the CLI inside the VM, use `localhost` as the API address:

```bash
python3 -m minisplunk.cli INGEST ./sample.log http://localhost:8081
python3 -m minisplunk.cli QUERY http://localhost:8080 SEARCH_HOST web-1
python3 -m minisplunk.cli QUERY http://localhost:8080 COUNT_KEYWORD password
python3 -m minisplunk.cli PURGE http://localhost:8080
```

Do not use the public mapped ports from inside the VM. For example, from inside
Server1, use `localhost:8080`, not `<PUBLIC_IP>:31523`.

If you run the CLI from another machine on the same internal network, use the VM's
internal IP address:

```bash
python3 -m minisplunk.cli INGEST ./sample.log http://<VM_IP>:8000
python3 -m minisplunk.cli QUERY http://<VM_IP>:8080 SEARCH_HOST web-1
python3 -m minisplunk.cli QUERY http://<VM_IP>:8080 COUNT_KEYWORD password
```

If you run the CLI from your laptop using the provided public IP and external port
mappings, use:

| VM      | Ingest API                     | Query API / Web Logs           | RabbitMQ UI                    |
| ------- | ------------------------------ | ------------------------------ | ------------------------------ |
| Server0 | `http://<PUBLIC_IP>:31722` | `http://<PUBLIC_IP>:31522` | `http://<PUBLIC_IP>:31922` |
| Server1 | `http://<PUBLIC_IP>:31723` | `http://<PUBLIC_IP>:31523` | `http://<PUBLIC_IP>:31923` |
| Server2 | `http://<PUBLIC_IP>:31724` | `http://<PUBLIC_IP>:31524` | `http://<PUBLIC_IP>:31924` |

Example from another machine for Server1:

```bash
python3 -m minisplunk.cli INGEST ./sample.log http://<PUBLIC_IP>:31723
python3 -m minisplunk.cli QUERY http://<PUBLIC_IP>:31523 SEARCH_HOST web-1
python3 -m minisplunk.cli QUERY http://<PUBLIC_IP>:31523 COUNT_KEYWORD password
python3 -m minisplunk.cli PURGE http://<PUBLIC_IP>:31523
```

Browser views for Server1:

```text
http://<PUBLIC_IP>:31523/logs
http://<PUBLIC_IP>:31523/nodes
```

Command target summary:

| Where command runs                | Ingest target                  | Query/Purge target             |
| --------------------------------- | ------------------------------ | ------------------------------ |
| Inside the VM running Docker      | `http://localhost:8081`        | `http://localhost:8080`        |
| Same internal VM network          | `http://<VM_IP>:8000`          | `http://<VM_IP>:8080`          |
| Laptop/public internet to Server0 | `http://<PUBLIC_IP>:31722` | `http://<PUBLIC_IP>:31522` |
| Laptop/public internet to Server1 | `http://<PUBLIC_IP>:31723` | `http://<PUBLIC_IP>:31523` |
| Laptop/public internet to Server2 | `http://<PUBLIC_IP>:31724` | `http://<PUBLIC_IP>:31524` |

Ports used by the stack:

- `8080`: Query API, `PURGE`, `/logs`, and `/nodes`
- `8081`: Ingest API inside the VM
- `8000`: Ingest API external-friendly host port
- `15672`: RabbitMQ management UI
- `5672`: RabbitMQ broker inside Docker; expose externally only if needed
- `27017`: MongoDB `mongos` router for debugging

Recommended VM resources:

- Minimum: 4 GB RAM
- Recommended: 6-8 GB RAM

Verify the stack:

```bash
docker compose ps
docker compose exec mongos mongosh --eval 'sh.status()'
```

Manual smoke test:

```bash
printf 'Jul 16 15:20:01 web-1 sshd[123]: Failed password for root\nJul 16 15:21:10 db-1 mongod[55]: connection accepted\nJul 16 15:22:33 web-1 nginx[88]: request timeout warning\n' > sample.log

python3 -m minisplunk.cli INGEST ./sample.log http://localhost:8081
python3 -m minisplunk.cli QUERY http://localhost:8080 SEARCH_HOST web-1
python3 -m minisplunk.cli QUERY http://localhost:8080 SEARCH_SEVERITY error
python3 -m minisplunk.cli QUERY http://localhost:8080 COUNT_KEYWORD password
```

Failure-isolation checks:

```bash
docker compose stop query-api
python3 -m minisplunk.cli INGEST ./sample.log http://localhost:8081

docker compose start query-api
docker compose stop ingest-api
python3 -m minisplunk.cli QUERY http://localhost:8080 SEARCH_HOST web-1
```

## Test

```bash
python3 -m unittest discover -v
```

## Current MongoDB Topology

- `mongos` query router exposed on `localhost:27017`
- 3 config servers in replica set `cfg`
- 2 shards: `shard1` and `shard2`
- Each shard has 2 MongoDB nodes
- `minisplunk.logs` is sharded by `dedupe_key`

## Open Decisions

- How much chaos-test automation to include in the final submission.
