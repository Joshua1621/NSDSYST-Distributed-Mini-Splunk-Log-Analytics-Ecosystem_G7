#!/bin/sh
set -eu

attempts=60
echo "Waiting for mongos..."
until mongosh --host mongos:27017 --quiet --eval 'db.adminCommand({ ping: 1 }).ok' >/dev/null 2>&1; do
  attempts=$((attempts - 1))
  if [ "${attempts}" -le 0 ]; then
    echo "Timed out waiting for mongos"
    exit 1
  fi
  sleep 2
done

mongosh --host mongos:27017 --eval '
  try { sh.addShard("shard1/shard1a:27017,shard1b:27017") } catch (err) { print(err) }
  try { sh.addShard("shard2/shard2a:27017,shard2b:27017") } catch (err) { print(err) }
  try { sh.enableSharding("minisplunk") } catch (err) { print(err) }
  db = db.getSiblingDB("minisplunk")
  db.logs.createIndex({ dedupe_key: 1 }, { unique: true })
  try { sh.shardCollection("minisplunk.logs", { dedupe_key: 1 }, true) } catch (err) { print(err) }
'

echo "Sharding initialized."
