# Distributed Mini-Splunk

Course machine project for a distributed log analytics ecosystem.

This repository is being built in slices:

1. CLI forwarder/client
2. Ingest API, Query API, and RabbitMQ middleware
3. Distributed worker nodes
4. Sharded MongoDB data layer
5. Fault-tolerance and chaos-test hardening

## Current Slice: CLI Client

The CLI supports both the original one-shot command syntax and a new interactive
shell. The original syntax is unchanged, so existing scripts and manual commands
continue to work.

Start the interactive shell with:

```bash
python3 -m minisplunk.cli
```

The shell defaults to `SERVER1` and automatically selects the documented ports for
each command. You no longer need to type the IP address or port for every operation.
The shell can also switch between local Docker access, another VM on the same internal
network, and the public Server0/1/2 mappings.

```text
Distributed Mini-Splunk CLI
Target: SERVER1 (103.231.240.136)
  INGEST      -> http://103.231.240.136:31723
  QUERY/PURGE -> http://103.231.240.136:31523

minisplunk> INGEST ./sample.log
minisplunk> QUERY SEARCH_HOST my-host
minisplunk> QUERY SEARCH_DATE "Jul 16"
minisplunk> QUERY SEARCH_DAEMON sshd
minisplunk> QUERY SEARCH_SEVERITY error
minisplunk> QUERY SEARCH_KEYWORD failed
minisplunk> QUERY COUNT_KEYWORD failed
minisplunk> PURGE
minisplunk> !help
minisplunk> !target LOCAL
minisplunk> !target INTERNAL 192.168.1.105
minisplunk> !target SERVER0
minisplunk> !exit
```

### Interactive CLI commands

- `INGEST <file_path>` — uses the selected server's external ingest port.
- `QUERY <query_type> <value>` — uses the selected server's external query port.
- `PURGE` — uses the selected server's external query port.
- `!target LOCAL` — uses `localhost:8081` for INGEST and `localhost:8080` for QUERY/PURGE.
- `!target INTERNAL <VM_IP>` — uses `<VM_IP>:8000` for INGEST and `<VM_IP>:8080` for QUERY/PURGE.
- `!target SERVER0|SERVER1|SERVER2` — changes the public target and automatically updates
  the default ports.
- `!server SERVER0|SERVER1|SERVER2` — backward-compatible alias for selecting a public server.
- `!help` — displays the available commands and syntax.
- `!exit` / `!quit` — exits the CLI cleanly.

Public endpoints configured by the interactive CLI are: `SERVER0` = ingest `31722`,
query/purge `31522`; `SERVER1` = ingest `31723`, query/purge `31523`; and `SERVER2` =
ingest `31724`, query/purge `31524`, all using `103.231.240.136`. These are the
external mappings documented by this repository.

Target port mappings are:

| Target | INGEST | QUERY/PURGE |
| --- | --- | --- |
| `LOCAL` | `localhost:8081` | `localhost:8080` |
| `INTERNAL <VM_IP>` | `<VM_IP>:8000` | `<VM_IP>:8080` |
| `SERVER0` | `103.231.240.136:31722` | `103.231.240.136:31522` |
| `SERVER1` | `103.231.240.136:31723` | `103.231.240.136:31523` |
| `SERVER2` | `103.231.240.136:31724` | `103.231.240.136:31524` |

The internal Docker addresses remain unchanged: ingest `localhost:8081` and query/purge
`localhost:8080` when the CLI runs inside the VM. When the CLI runs from another machine
on the same internal VM network, use `!target INTERNAL <VM_IP>`; the documented internal
ports are ingest `8000` and query `8080`.

The original one-shot commands remain supported:

```bash
python3 -m minisplunk.cli INGEST ./sample.log http://localhost:8081
python3 -m minisplunk.cli QUERY http://localhost:8080 SEARCH_HOST my-host
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
username: rabbituser
password: rabbit1234
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
Server1, use `localhost:8080`, not `103.231.240.136:31523`.

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
| Server0 | `http://103.231.240.136:31722` | `http://103.231.240.136:31522` | `http://103.231.240.136:31922` |
| Server1 | `http://103.231.240.136:31723` | `http://103.231.240.136:31523` | `http://103.231.240.136:31923` |
| Server2 | `http://103.231.240.136:31724` | `http://103.231.240.136:31524` | `http://103.231.240.136:31924` |

Example from another machine for Server1:

```bash
python3 -m minisplunk.cli INGEST ./sample.log http://103.231.240.136:31723
python3 -m minisplunk.cli QUERY http://103.231.240.136:31523 SEARCH_HOST web-1
python3 -m minisplunk.cli QUERY http://103.231.240.136:31523 COUNT_KEYWORD password
python3 -m minisplunk.cli PURGE http://103.231.240.136:31523
```

Browser views for Server1:

```text
http://103.231.240.136:31523/logs
http://103.231.240.136:31523/nodes
```

Command target summary:

| Where command runs                | Ingest target                  | Query/Purge target             |
| --------------------------------- | ------------------------------ | ------------------------------ |
| Inside the VM running Docker      | `http://localhost:8081`        | `http://localhost:8080`        |
| Same internal VM network          | `http://<VM_IP>:8000`          | `http://<VM_IP>:8080`          |
| Laptop/public internet to Server0 | `http://103.231.240.136:31722` | `http://103.231.240.136:31522` |
| Laptop/public internet to Server1 | `http://103.231.240.136:31723` | `http://103.231.240.136:31523` |
| Laptop/public internet to Server2 | `http://103.231.240.136:31724` | `http://103.231.240.136:31524` |

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
