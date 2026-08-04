#!/usr/bin/env bash
# NOTE: this script requires the `mongosh` binary. The plain `mongo:7.0`
# image does NOT bundle mongosh (that split from the server image a few
# releases back) -- this script is intended to run in a container built
# from mongo-init/Dockerfile, which installs mongosh on top of a slim
# base. See docker-compose.yml's `mongo-setup` service.
set -euo pipefail

echo "[init] waiting for mongod/mongos processes to accept connections..."

wait_for() {
  local host_port="$1"
  local label="$2"
  for i in $(seq 1 30); do
    if mongosh --quiet --host "$host_port" --eval "db.adminCommand('ping')" >/dev/null 2>&1; then
      echo "[init] $label is up"
      return 0
    fi
    sleep 2
  done
  echo "[init] ERROR: $label did not become ready in time" >&2
  exit 1
}

wait_for "configsvr:27019" "config server"
wait_for "shard1:27018" "shard1"
wait_for "shard2:27018" "shard2"
# NOTE: we deliberately do NOT wait_for mongos here. mongos will not
# fully come up (or reliably answer ping) until the config server
# replica set below has been initiated -- waiting on mongos before that
# happens can deadlock. We check mongos readiness later, right before we
# actually need to talk to it.

echo "[init] initiating config server replica set..."
mongosh --quiet --host configsvr:27019 --eval '
  try {
    rs.initiate({
      _id: "cfgrs",
      configsvr: true,
      members: [{ _id: 0, host: "configsvr:27019" }]
    });
  } catch (e) {
    print("configsvr rs.initiate skipped: " + e);
  }
'

echo "[init] initiating shard1 replica set..."
mongosh --quiet --host shard1:27018 --eval '
  try {
    rs.initiate({
      _id: "shard1rs",
      members: [{ _id: 0, host: "shard1:27018" }]
    });
  } catch (e) {
    print("shard1 rs.initiate skipped: " + e);
  }
'

echo "[init] initiating shard2 replica set..."
mongosh --quiet --host shard2:27018 --eval '
  try {
    rs.initiate({
      _id: "shard2rs",
      members: [{ _id: 0, host: "shard2:27018" }]
    });
  } catch (e) {
    print("shard2 rs.initiate skipped: " + e);
  }
'

echo "[init] waiting for replica sets to elect primaries..."
sleep 8

echo "[init] waiting for mongos to be ready (requires config server rs up)..."
wait_for "mongos:27017" "mongos"

echo "[init] adding shards to cluster via mongos..."
mongosh --quiet --host mongos:27017 --eval '
  try { sh.addShard("shard1rs/shard1:27018"); } catch (e) { print("addShard shard1 skipped: " + e); }
  try { sh.addShard("shard2rs/shard2:27018"); } catch (e) { print("addShard shard2 skipped: " + e); }
'

echo "[init] enabling sharding on minisplunk.logs (hashed hostname key)..."
mongosh --quiet --host mongos:27017 --eval '
  sh.enableSharding("minisplunk");
  db.getSiblingDB("minisplunk").logs.createIndex({ hostname: "hashed" });
  sh.shardCollection("minisplunk.logs", { hostname: "hashed" });

  db.getSiblingDB("minisplunk").logs.createIndex({ msg_id: 1 }, { unique: true });
'

echo "[init] cluster setup complete."
