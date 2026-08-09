from __future__ import annotations

from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
import time
from typing import Any, Iterator
from uuid import uuid4


class MongoLogRepository:
    def __init__(self, uri: str, database_name: str = "minisplunk") -> None:
        from pymongo import MongoClient

        self.client = MongoClient(uri, serverSelectionTimeoutMS=5000)
        self.db = self.client[database_name]
        self.logs = self.db.logs
        self.locks = self.db.locks
        self.nodes = self.db.nodes
        self._ensure_indexes()

    def insert_logs(self, documents: list[dict[str, Any]]) -> int:
        if not documents:
            return 0

        from pymongo.errors import BulkWriteError
        from pymongo import InsertOne

        with self.coordination_lock("write"):
            try:
                result = self.logs.bulk_write(
                    [InsertOne(doc) for doc in documents],
                    ordered=False,
                )
                return result.inserted_count
            except BulkWriteError as exc:
                return int(exc.details.get("nInserted", 0))

    def search(self, search_type: str, value: str) -> list[dict[str, Any]]:
        query = _query_for(search_type, value)
        with self.coordination_lock("read"):
            return [_public_doc(doc) for doc in self.logs.find(query).sort([("timestamp", 1), ("line_number", 1)])]

    def list_logs(self, filters: dict[str, str] | None = None, limit: int = 250) -> list[dict[str, Any]]:
        query = _log_filters(filters or {})
        with self.coordination_lock("read"):
            cursor = self.logs.find(query).sort([("timestamp", -1), ("line_number", -1)]).limit(limit)
            return [_public_doc(doc) for doc in cursor]

    def list_nodes(self) -> list[dict[str, Any]]:
        return [_public_doc(doc) for doc in self.nodes.find({}).sort("node_name", 1)]

    def mark_worker_active(self, worker_name: str, inserted_count: int) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self.nodes.update_one(
            {"node_name": worker_name},
            {
                "$set": {
                    "node_name": worker_name,
                    "role": "worker",
                    "status": "active",
                    "last_active": now,
                },
                "$setOnInsert": {"first_seen": now},
                "$inc": {
                    "jobs_processed": 1,
                    "logs_inserted": inserted_count,
                },
            },
            upsert=True,
        )

    def count_keyword(self, keyword: str) -> int:
        pattern = re_escape(keyword)
        count = 0
        with self.coordination_lock("read"):
            for doc in self.logs.find({"message": {"$regex": pattern, "$options": "i"}}, {"message": 1}):
                count += str(doc.get("message", "")).lower().count(keyword.lower())
        return count

    def purge(self) -> int:
        with self.coordination_lock("purge"):
            result = self.logs.delete_many({})
        return result.deleted_count

    @contextmanager
    def coordination_lock(self, owner: str, ttl_seconds: int = 30) -> Iterator[None]:
        from pymongo.errors import DuplicateKeyError

        token = str(uuid4())
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        deadline = time.monotonic() + ttl_seconds

        while True:
            self.locks.delete_many({"expires_at": {"$lt": datetime.now(timezone.utc)}})
            try:
                self.locks.insert_one({"_id": "logs", "owner": owner, "token": token, "expires_at": expires_at})
                break
            except DuplicateKeyError:
                if time.monotonic() > deadline:
                    raise TimeoutError("Timed out waiting for distributed logs lock")
                time.sleep(0.2)

        try:
            yield
        finally:
            self.locks.delete_one({"_id": "logs", "token": token})

    def _ensure_indexes(self) -> None:
        self.logs.create_index("dedupe_key", unique=True)
        self.logs.create_index("timestamp")
        self.logs.create_index("hostname")
        self.logs.create_index("process")
        self.logs.create_index("severity")
        self.nodes.create_index("node_name", unique=True)
        self.locks.create_index("expires_at", expireAfterSeconds=0)


def _query_for(search_type: str, value: str) -> dict[str, Any]:
    if search_type == "date":
        return {"timestamp": {"$regex": re_escape(value), "$options": "i"}}
    if search_type == "host":
        return {"hostname": value}
    if search_type == "daemon":
        return {"process": value}
    if search_type == "severity":
        return {"severity": value.lower()}
    if search_type == "keyword":
        return {"message": {"$regex": re_escape(value), "$options": "i"}}
    raise ValueError(f"Unsupported search type: {search_type}")


def _log_filters(filters: dict[str, str]) -> dict[str, Any]:
    query: dict[str, Any] = {}
    if filters.get("severity"):
        query["severity"] = filters["severity"].lower()
    if filters.get("hostname"):
        query["hostname"] = filters["hostname"]
    if filters.get("host"):
        query["hostname"] = filters["host"]
    if filters.get("daemon"):
        query["process"] = filters["daemon"]
    if filters.get("process"):
        query["process"] = filters["process"]
    if filters.get("keyword"):
        query["message"] = {"$regex": re_escape(filters["keyword"]), "$options": "i"}
    return query


def _public_doc(doc: dict[str, Any]) -> dict[str, Any]:
    doc = dict(doc)
    doc.pop("_id", None)
    return doc


def re_escape(value: str) -> str:
    import re

    return re.escape(value)
