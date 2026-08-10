#!/bin/sh
set -eu

wait_for_mongo() {
  host="$1"
  attempts=60

  echo "Waiting for ${host}..."
  until mongosh --host "${host}" --quiet --eval 'db.adminCommand({ ping: 1 }).ok' >/dev/null 2>&1; do
    attempts=$((attempts - 1))
    if [ "${attempts}" -le 0 ]; then
      echo "Timed out waiting for ${host}"
      exit 1
    fi
    sleep 2
  done
}

init_replica_set() {
  host="$1"
  script="$2"

  wait_for_mongo "${host}"
  mongosh --host "${host}" --eval "${script}"
}

init_replica_set "configsvr1:27017" '
  try {
    rs.status()
  } catch (err) {
    rs.initiate({
      _id: "cfg",
      configsvr: true,
      members: [
        { _id: 0, host: "configsvr1:27017" },
        { _id: 1, host: "configsvr2:27017" },
        { _id: 2, host: "configsvr3:27017" }
      ]
    })
  }
'

init_replica_set "shard1a:27017" '
  try {
    rs.status()
  } catch (err) {
    rs.initiate({
      _id: "shard1",
      members: [
        { _id: 0, host: "shard1a:27017" },
        { _id: 1, host: "shard1b:27017" }
      ]
    })
  }
'

init_replica_set "shard2a:27017" '
  try {
    rs.status()
  } catch (err) {
    rs.initiate({
      _id: "shard2",
      members: [
        { _id: 0, host: "shard2a:27017" },
        { _id: 1, host: "shard2b:27017" }
      ]
    })
  }
'

echo "Replica sets initialized."
