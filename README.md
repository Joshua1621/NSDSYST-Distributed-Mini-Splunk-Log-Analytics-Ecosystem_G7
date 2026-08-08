# NSDSYST Mini-Splunk — Distributed Log Analytics Ecosystem

A distributed, fault-tolerant syslog ingestion and search system built for
the NSDSYST machine project. This README covers what the system does, how
each piece works internally, and step-by-step instructions to run and
test it.

---

## Table of contents

1. [What this system does](#1-what-this-system-does)
2. [How it works](#2-how-it-works)
3. [Prerequisites](#3-prerequisites)
4. [Running it](#4-running-it)
5. [Using the CLI](#5-using-the-cli)
6. [Testing without Docker](#6-testing-without-docker)
7. [Chaos testing](#7-chaos-testing)
8. [Troubleshooting](#8-troubleshooting)
9. [Project layout](#9-project-layout)
10. [Known limitations](#10-known-limitations)

---

## 1. What this system does

Mini-Splunk ingests syslog files, parses each line into structured fields
(timestamp, hostname, process, severity, message), stores them in a
distributed database, and lets a client search across all of it. The
entire point of the "distributed" part is that no single component can
take the whole system down: kill any one worker mid-ingestion and the
system keeps going, with no lost logs and no duplicates.

Four operations, all issued from a CLI client:

| Command | What it does |
|---|---|
| `INGEST <file> <gateway>` | Uploads a syslog file for asynchronous parsing and storage |
| `QUERY <gateway> SEARCH_* <arg>` | Searches stored logs by date, host, daemon, severity, or keyword |
| `QUERY <gateway> COUNT_KEYWORD <kw>` | Counts keyword occurrences across all logs |
| `PURGE <gateway>` | Deletes all stored logs, safely coordinated across writers |

---

## 2. How it works

### 2.1 The five components

```
Forwarder (CLI) --HTTP--> Gateway (FastAPI) --publish--> RabbitMQ "ingest" queue
                                |                              |
                                | REST query                   | competing consumers
                                v                               v
                            mongos router  <---writes---   Worker(s) x N
                                |
                     +----------+----------+
                     |                     |
               shard1rs (Mongo)      shard2rs (Mongo)
```

- **Forwarder** (`forwarder/client.py`) — a plain Python CLI. It doesn't
  talk to Mongo or RabbitMQ directly; it only ever speaks REST to the
  Gateway. This is what "decoupled" means in practice: the client has no
  idea how many workers exist or how the data is sharded.

- **Gateway** (`gateway/main.py`) — a FastAPI service, the only thing the
  Forwarder ever contacts. It has two unrelated jobs:
  - On `INGEST`, it reads the uploaded file, chops it into batches of 200
    lines, and publishes each batch as a message to RabbitMQ. It does
    **not** parse anything itself — it returns to the client immediately
    after publishing, before any line has actually been processed. This
    is what "asynchronous" means here: ingestion is accepted, not
    completed, by the time the HTTP response comes back.
  - On `QUERY`, it translates each `SEARCH_*`/`COUNT_KEYWORD` command
    into a MongoDB query and sends it to `mongos`. It does not manually
    contact each shard — `mongos` handles the scatter-gather internally.

- **RabbitMQ** — a durable message queue sitting between the Gateway and
  the Workers. Messages are marked `PERSISTENT`, meaning they survive a
  RabbitMQ restart. Multiple Workers all consume from the same queue as
  *competing consumers*: RabbitMQ hands each message to exactly one
  available worker, so throughput scales with the number of workers
  without any coordination logic needed between them.

- **Worker** (`worker/main.py`) — there are N of these running
  identically (3 by default). Each one pulls a batch message off the
  queue, parses every line in it with `common/syslog_parser.py`, and
  writes the parsed records to MongoDB. A message is only ACKed
  (permanently removed from the queue) after every line in its batch has
  been successfully written. If a worker crashes mid-batch, the message
  it was holding was never ACKed, so RabbitMQ redelivers it — to whatever
  worker is available next, possibly a freshly restarted instance of the
  same one.

- **MongoDB sharded cluster** — not a single database. `mongos` is a
  stateless router; the actual data lives split across `shard1rs` and
  `shard2rs`, chosen by a hashed `hostname` field. There's also a
  `configsvr` holding cluster metadata (which shard owns which data
  range). No component ever talks to a shard directly — everything goes
  through `mongos`.

### 2.2 What happens on INGEST, step by step

1. Forwarder reads the local file, POSTs it to `Gateway:/ingest`.
2. Gateway assigns the upload a UUID (`upload_id`), splits the file into
   line batches of 200, and for each batch:
   - assigns every individual line a deterministic ID:
     `msg_id = "{upload_id}:{line_offset}"`
   - publishes the whole batch as one durable RabbitMQ message
3. Gateway returns immediately: `{upload_id, lines_received,
   batches_published}`. At this point zero lines have been parsed or
   stored — only queued.
4. Some Worker (whichever is free) picks up each batch message.
5. For each line in the batch, the worker calls `parse_line()`
   (`common/syslog_parser.py`), which regex-matches BSD syslog format and
   extracts timestamp, hostname, process, pid, severity, and message.
   Lines that don't match are skipped and logged, not fatal.
6. The worker writes all successfully-parsed lines to MongoDB in one
   `bulk_write` using `UpdateOne(filter={msg_id: ...}, update={$setOnInsert:
   parsed}, upsert=True)`. This is an **upsert keyed on msg_id, not an
   insert** — if a document with that `msg_id` already exists, nothing
   happens. This single design choice is what gives the system its
   "zero duplicate processing" guarantee: if the same message gets
   redelivered (because the worker died before ACKing), replaying the
   same batch just re-attempts the same upserts, which are no-ops the
   second time.
7. Only after the bulk write succeeds does the worker ACK the message.

### 2.3 What happens on QUERY

Gateway translates the command directly into a MongoDB filter and calls
`db.logs.find(...)` (or `count_documents(...)` for `COUNT_KEYWORD`)
against `mongos`. `mongos` consults the config server to determine which
shard(s) could hold matching documents, queries them (in parallel if
more than one shard is relevant), and merges the results before handing
them back to the Gateway. The Gateway just relays that result to the
Forwarder as JSON; the Forwarder formats it for display.

### 2.4 What happens on PURGE — the distributed lock

This is the one operation where a naive implementation would be unsafe:
if a PURGE runs while a Worker is mid-write, you could end up with
"ghost" documents written after the delete finished, or a delete that
misses documents a worker was still inserting.

The fix is a lock **document** stored in Mongo itself
(`minisplunk.locks`, `_id: "purge_lock"`), checked by everyone who
writes:

1. Gateway's `/purge` endpoint calls `acquire_lock()`, which atomically
   flips `locked: false -> true` via `find_one_and_update` (atomic at the
   document level in MongoDB, so two concurrent PURGE calls can't both
   succeed).
2. If the lock was already held, the Gateway returns HTTP 409 and does
   nothing.
3. If acquired, the Gateway runs `db.logs.delete_many({})`, then always
   releases the lock in a `finally` block (so a crash mid-delete doesn't
   leave the system permanently locked).
4. **Critically**, every Worker also checks this same lock *before*
   writing each batch (`purge_in_progress()` in `worker/main.py`). If a
   purge is in progress, the worker `nack`s the message with
   `requeue=True` instead of writing through it, and tries again shortly.
   This is what makes the lock actually effective against Workers — they
   never talk to the Gateway, so a lock enforced only at the Gateway
   wouldn't protect against them.
5. The lock has a 30-second TTL: if whatever holds it crashes without
   releasing, the TTL check in `acquire_lock()`/`purge_in_progress()`
   treats it as stale and lets the system recover instead of deadlocking
   forever.

### 2.5 Idempotency in one sentence

Every write is `upsert-by-deterministic-id`, never `insert`. That single
property is what makes "kill a worker, redeliver the message, get
correct results anyway" work, and it's the thing to point to if asked
during defense how zero-duplicate-processing is actually guaranteed
(not just "RabbitMQ handles it" — RabbitMQ only guarantees *delivery*,
not *exactly-once processing*; the upsert is what makes redelivery safe).

---

## 3. Prerequisites

- **Docker** and **Docker Compose v2** (the `docker compose` command, not
  the older standalone `docker-compose`). Verify with:
  ```bash
  docker --version
  docker compose version
  ```
- **Python 3.10+** locally, for running the Forwarder CLI and the test
  scripts (these run on your host machine, not inside a container).
- No external network access is needed beyond what Docker needs to pull
  base images (`python:3.12-slim`, `mongo:7.0`, `rabbitmq:3.13-management`,
  `debian:bookworm-slim`) the first time.
- Ports `8000` (Gateway), `27017` (mongos), `5672`/`15672` (RabbitMQ) must
  be free on your host.

---

## 4. Running it

From the project root:

```bash
docker compose up --build --scale worker=3
```

### FOR TESTING LANG End-to-end automated test (optional)

An automated test script exercises ingest → chaos → query → purge. It requires Docker and `docker compose` on your machine. From the project root run:

```bash
python scripts/e2e_test.py
```

The script will build and start the stack, upload `tests/sample_syslog.log`, kill a worker to simulate a failure, run a keyword count query, then purge and teardown the environment.


> **Why `--scale worker=3`**: the `deploy.replicas: 3` field in
> `docker-compose.yml` only takes effect under `docker stack deploy`
> (Swarm mode) — under plain `docker compose up` it's ignored, so you
> must pass `--scale worker=3` explicitly or you'll only get one worker.

### What happens on first boot

1. `rabbitmq`, `configsvr`, `shard1`, `shard2` start in parallel.
2. `mongos` starts once those three have *started* (not necessarily
   *ready* — see below).
3. `mongo-setup` builds a small custom image (`mongo-init/Dockerfile`)
   that installs `mongosh` — the stock `mongo:7.0` image does not include
   it — then runs `mongo-init/init-cluster.sh`, which:
   - polls each of `configsvr`, `shard1`, `shard2` until they respond to
     `ping` (up to ~60s each)
   - initiates all three as single-node replica sets
   - waits 8s for primary election
   - polls `mongos` until *it's* ready (this has to happen after the
     config server replica set is initiated, or `mongos` will never come
     up — see the "Bugs found and fixed" section below for why this
     ordering matters)
   - registers both shards with `mongos` via `sh.addShard`
   - enables sharding on `minisplunk.logs`, keyed on hashed `hostname`
   - creates a unique index on `msg_id` (the idempotency mechanism
     described in section 2.5)
4. Only once `mongo-setup` exits with code 0 do `gateway` and `worker`
   start — this is enforced by `depends_on: mongo-setup: condition:
   service_completed_successfully` in the compose file, not just a fixed
   delay.

Total first-boot time is typically 1-2 minutes. Subsequent
`docker compose up` runs (without `--build`, with volumes already
populated) are much faster since the replica sets are already initiated
— `init-cluster.sh` detects this and just logs "skipped" for each step
it's already done.

**Watch the init process directly the first time:**
```bash
docker compose logs -f mongo-setup
```

You should see it work through each step and finish with
`[init] cluster setup complete.`. If it exits non-zero, `gateway` and
`worker` will never start — check the logs for which step failed (see
[Troubleshooting](#8-troubleshooting)).

### Once it's up

- Gateway: `http://localhost:8000` (try `http://localhost:8000/health`)
- RabbitMQ management UI: `http://localhost:15672`
  (user/pass: `minisplunk` / `minisplunk`) — useful for watching queue
  depth live during ingestion or chaos tests
- mongos: `mongodb://localhost:27017/minisplunk` if you want to connect
  with `mongosh` or Compass directly to inspect data

**Shutting down:**
```bash
docker compose down          # stop containers, keep data volumes
docker compose down -v       # stop containers AND wipe all data (fresh start)
```

---

## 5. Using the CLI

```bash
cd forwarder
pip install -r requirements.txt
```

**Ingest a file:**
```bash
python client.py INGEST ../sample-data/sample.log localhost:8000
```
This returns immediately with an `upload_id` and batch count — it does
**not** mean ingestion is finished, only accepted. Give the workers a
moment (for 100 lines, well under a second; for thousands of lines, a
few seconds) before querying.

**Search:**
```bash
python client.py QUERY localhost:8000 SEARCH_DATE "2026-08-02"
python client.py QUERY localhost:8000 SEARCH_HOST webserver01
python client.py QUERY localhost:8000 SEARCH_DAEMON sshd
python client.py QUERY localhost:8000 SEARCH_SEVERITY ERROR
python client.py QUERY localhost:8000 SEARCH_KEYWORD "failed password"
python client.py QUERY localhost:8000 COUNT_KEYWORD "failed password"
```
`SEARCH_DATE` expects `YYYY-MM-DD`. `SEARCH_SEVERITY` is one of
`EMERGENCY, ALERT, CRITICAL, ERROR, WARNING, NOTICE, INFO, DEBUG`
(case-insensitive — the client uppercases it for you).

**Purge everything:**
```bash
python client.py PURGE localhost:8000
```
Returns the number of documents deleted. If a purge is already running
elsewhere, this returns an error rather than silently queuing — try
again in a moment.

---

## 6. Testing without Docker

Two scripts let you validate the core logic on your host machine,
without Docker running at all — useful for isolating "is my pipeline
logic correct" from "is my Docker networking correct" when something
goes wrong.

### 6.1 Generate test data

```bash
cd forwarder
python generate_sample_logs.py --lines 50 --out sample.log --seed 42
```

Produces a deterministic (same `--seed` -> same file), realistic syslog
file spanning multiple hosts, daemons, and severities, so every `QUERY`
subcommand has something real to find. Useful flags:

- `--lines N` — how many lines to generate
- `--out PATH` — output file
- `--seed N` — fixed seed for reproducibility (omit for random)
- `--days-back N` — spread timestamps over N days ending now (default 3;
  useful for testing `SEARCH_DATE` across multiple dates)
- `--malformed-rate 0.0-1.0` — fraction of lines intentionally corrupted,
  to exercise the worker's parse-error skip path. Use `0` (the default)
  for chaos testing where you need an exact expected document count.

### 6.2 Verify pipeline logic in memory

```bash
cd forwarder
python test_pipeline_local.py sample.log
```

This simulates the Gateway's batching (`msg_id` assignment) and the
Worker's upsert logic against an in-memory dict standing in for Mongo —
no real database or queue involved. It then simulates the worst-case
chaos scenario (every single message gets redelivered, as if every
worker crashed right before acking everything) and asserts:

- every line in the file is accounted for (written + skipped == total)
- every successfully-parsed line is written exactly once
- redelivery creates **zero** new documents (the idempotency guarantee)

If this script fails, the bug is in the pipeline logic itself
(`gateway/main.py`'s batching or `worker/main.py`'s upsert), not in
Docker, Mongo, or RabbitMQ — fix it here first before touching the full
stack.

---

## 7. Chaos testing

This is the graded core of the fault-tolerance requirement: prove zero
data loss and zero duplicate processing when a component is killed
mid-operation.

```bash
# 1. Generate a large, deterministic file (malformed-rate 0 for exact counts)
cd forwarder
python generate_sample_logs.py --lines 5000 --out big_sample.log --seed 99 --malformed-rate 0

# 2. Start ingesting
python client.py INGEST ./big_sample.log localhost:8000

# 3. Immediately, in another terminal, kill a worker mid-flight
docker ps --filter "name=nsdsyst-minisplunk-worker" --format "{{.ID}}"
docker kill <worker_container_id>

# 4. Docker Compose restarts it automatically (restart: unless-stopped)
docker compose ps

# 5. Wait a few seconds for redelivery + recovery, then verify
python client.py QUERY localhost:8000 SEARCH_HOST webserver01   # spot-check
```

**To confirm the exact count**, connect to Mongo directly:
```bash
docker exec -it ms-mongos mongosh --eval 'db.getSiblingDB("minisplunk").logs.countDocuments({})'
```
This should equal exactly the line count you generated (5000 in the
example above, since `--malformed-rate 0` guarantees every line parses).

**Other chaos scenarios worth testing and documenting for Section III-B
of the report:**
- Kill the Gateway mid-upload (before all batches are published) — verify
  already-published messages still get processed once workers stabilize.
- Kill 2 of 3 workers simultaneously — verify the 1 remaining worker
  drains the backlog (slower, but correct).
- Concurrent `INGEST` + `PURGE` — verify the lock prevents the race (a
  worker's write should be rejected/requeued while a purge is running,
  not silently lost or silently succeed mid-delete).
- Watch queue depth in the RabbitMQ management UI (`localhost:15672`)
  during a worker kill — you should see the queue depth spike as
  redelivered messages return, then drain back to zero as the surviving
  workers/restarted container catch up.

---

## 8. Troubleshooting

**`mongo-setup` container exits with an error / never completes:**
- Check `docker compose logs mongo-setup` for which step failed.
- If it's stuck on `wait_for ... did not become ready in time` for
  `configsvr`/`shard1`/`shard2`, those mongod processes may be slow to
  start on your machine — try increasing the retry count in
  `mongo-init/init-cluster.sh`'s `wait_for()` function.
- If `addShard` fails with a connection error, the `sleep 8` after
  replica set initiation may not be enough time for primary election on
  a slower machine — increase it.

**Gateway/Worker containers keep restarting:**
- They won't even start until `mongo-setup` succeeds — check that first.
- Check `RABBITMQ_URL`/`MONGO_URI` env vars match what's in
  `docker-compose.yml` if you've modified anything.

**`INGEST` returns success but `QUERY` finds nothing:**
- Ingestion is asynchronous — give it a moment, especially for large
  files. Check `docker compose logs worker` to see batches being
  processed.
- Check RabbitMQ's management UI (`localhost:15672`) to see if messages
  are stuck in the `ingest` queue (workers not consuming — check worker
  logs for connection errors).

**Port already in use:**
- Something else on your machine is using 8000, 27017, 5672, or 15672.
  Either stop it or change the host-side port mapping in
  `docker-compose.yml` (e.g. `"8001:8000"`).

**Want a completely fresh start:**
```bash
docker compose down -v   # wipes all Mongo/RabbitMQ data volumes
docker compose up --build --scale worker=3
```

---

## 9. Project layout

```
nsdsyst-minisplunk/
|-- docker-compose.yml          # full orchestration, one command deploys everything
|-- .dockerignore / .gitignore
|-- common/
|   |-- syslog_parser.py        # shared regex parser (used only by worker)
|   `-- __init__.py
|-- gateway/
|   |-- main.py                 # FastAPI: /ingest, /query/*, /purge
|   |-- Dockerfile
|   `-- requirements.txt
|-- worker/
|   |-- main.py                 # RabbitMQ consumer, parses + upserts to Mongo
|   |-- Dockerfile
|   `-- requirements.txt
|-- forwarder/
|   |-- client.py                # CLI: INGEST / QUERY / PURGE
|   |-- generate_sample_logs.py  # synthetic test data generator
|   |-- test_pipeline_local.py   # Docker-free pipeline logic test
|   `-- requirements.txt
|-- mongo-init/
|   |-- init-cluster.sh          # one-shot cluster bootstrap script
|   `-- Dockerfile               # builds an image with mongosh installed
|-- sample-data/
|   `-- sample.log               # ready-made 100-line file, pre-verified to parse cleanly
`-- docs/
    |-- NSDSYST_Architecture_Report.docx   # Week 8 IEEE-format deliverable
    |-- architecture-diagram.svg
    `-- generate_report.js                 # regenerates the docx from source
```

---

## 10. Known limitations

Worth stating explicitly in the report rather than leaving implicit:

- **Config server and each shard run as single-node "replica sets"**,
  not the usual 3-node minimum, to keep container count manageable for a
  class project. The *sharding/partitioning* requirement (2 independent
  shards, no centralized single-instance DB) is still fully met — this
  only affects each shard's own internal high availability, which is a
  separate concern from the project's distributed-architecture
  requirements.
- **Severity inference is best-effort.** True RFC 3164 severity requires
  a `<PRI>` header, which many plain-text syslog dumps used for testing
  don't include. When absent, severity is guessed from keywords in the
  message body (e.g. "failed" -> ERROR). This is documented behavior, not
  a bug, but worth mentioning if asked during the demo why severity
  sometimes looks inferred rather than authoritative.
- **RabbitMQ and MongoDB themselves are each a single logical broker /
  router** (one `rabbitmq` container, one `mongos` router) — they are not
  clustered/HA at their own level. The project's fault-tolerance
  requirement is about ingestion/worker resilience, which this system
  handles; broker-level HA would be a reasonable "future work" item for
  Section IV of the report.

## Bugs found and fixed during development (useful context for the report)

- **`mongosh` missing from `mongo:7.0`**: the init script originally ran
  directly against the stock `mongo:7.0` image, but that image doesn't
  bundle `mongosh` (split into a separate package a few releases back).
  Fixed by adding `mongo-init/Dockerfile`, which installs `mongosh` from
  MongoDB's apt repo on a `debian:bookworm-slim` base.
- **Startup-order deadlock**: the init script originally waited for
  `mongos` to respond to `ping` *before* the config server replica set
  was initiated. `mongos` won't reliably come up until its config server
  connection succeeds, so this could hang indefinitely, with the very
  step that would unblock it (`rs.initiate()` on the config server)
  never executing because the script never got past the `mongos` wait.
  Fixed by moving the `mongos` readiness check to after all three
  replica sets are initiated.
