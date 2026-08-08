"""
Gateway / Search Head — the single entry point clients talk to.
"""

import json
import os
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime

import aio_pika
from fastapi import FastAPI, File, HTTPException, UploadFile
from pymongo import MongoClient

RABBITMQ_URL = os.environ["RABBITMQ_URL"]
MONGO_URI = os.environ["MONGO_URI"]
INGEST_QUEUE = "ingest"
BATCH_SIZE = 200

LOCK_ID = "purge_lock"
LOCK_TTL_SECONDS = 30

mongo_client: MongoClient | None = None
rabbit_connection: aio_pika.RobustConnection | None = None
rabbit_channel: aio_pika.Channel | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    global mongo_client, rabbit_connection, rabbit_channel

    mongo_client = MongoClient(MONGO_URI)
    db = mongo_client.get_default_database()
    db.locks.update_one(
        {"_id": LOCK_ID},
        {"$setOnInsert": {"locked": False, "locked_at": None}},
        upsert=True,
    )

    rabbit_connection = await aio_pika.connect_robust(RABBITMQ_URL)
    rabbit_channel = await rabbit_connection.channel()
    await rabbit_channel.declare_queue(INGEST_QUEUE, durable=True)

    yield

    await rabbit_connection.close()
    mongo_client.close()


app = FastAPI(title="Mini-Splunk Gateway", lifespan=lifespan)


def get_db():
    return mongo_client.get_default_database()


def acquire_lock() -> bool:
    db = get_db()
    now = time.time()
    result = db.locks.find_one_and_update(
        {
            "_id": LOCK_ID,
            "$or": [
                {"locked": False},
                {"locked_at": {"$lt": now - LOCK_TTL_SECONDS}},
            ],
        },
        {"$set": {"locked": True, "locked_at": now}},
    )
    return result is not None


def release_lock():
    db = get_db()
    db.locks.update_one(
        {"_id": LOCK_ID},
        {"$set": {"locked": False, "locked_at": None}},
    )


@app.post("/ingest")
async def ingest(file: UploadFile = File(...)):
    upload_id = str(uuid.uuid4())
    content = (await file.read()).decode("utf-8", errors="replace")
    lines = content.splitlines()

    if not lines:
        raise HTTPException(status_code=400, detail="uploaded file is empty")

    batches_published = 0
    for offset in range(0, len(lines), BATCH_SIZE):
        batch_lines = lines[offset : offset + BATCH_SIZE]
        payload = {
            "upload_id": upload_id,
            "offset": offset,
            "lines": [
                {"msg_id": f"{upload_id}:{offset + i}", "raw": line}
                for i, line in enumerate(batch_lines)
            ],
        }
        message = aio_pika.Message(
            body=json.dumps(payload).encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
        )
        await rabbit_channel.default_exchange.publish(message, routing_key=INGEST_QUEUE)
        batches_published += 1

    return {
        "status": "accepted",
        "upload_id": upload_id,
        "lines_received": len(lines),
        "batches_published": batches_published,
    }


def _serialize(doc: dict) -> dict:
    doc = dict(doc)
    doc.pop("_id", None)
    if isinstance(doc.get("timestamp"), datetime):
        doc["timestamp"] = doc["timestamp"].isoformat()
    return doc


@app.get("/query/date")
def search_date(date_string: str):
    try:
        day_start = datetime.strptime(date_string, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(status_code=400, detail="date_string must be YYYY-MM-DD")
    day_end = day_start.replace(hour=23, minute=59, second=59)

    db = get_db()
    results = db.logs.find({"timestamp": {"$gte": day_start, "$lte": day_end}})
    return {"results": [_serialize(d) for d in results]}


@app.get("/query/host")
def search_host(hostname: str):
    db = get_db()
    results = db.logs.find({"hostname": hostname})
    return {"results": [_serialize(d) for d in results]}


@app.get("/query/daemon")
def search_daemon(daemon_name: str):
    db = get_db()
    results = db.logs.find({"process": daemon_name})
    return {"results": [_serialize(d) for d in results]}


@app.get("/query/severity")
def search_severity(severity_level: str):
    db = get_db()
    results = db.logs.find({"severity": severity_level.upper()})
    return {"results": [_serialize(d) for d in results]}


@app.get("/query/keyword")
def search_keyword(keyword: str):
    db = get_db()
    results = db.logs.find({"message": {"$regex": keyword, "$options": "i"}})
    return {"results": [_serialize(d) for d in results]}


@app.get("/query/count_keyword")
def count_keyword(keyword: str):
    db = get_db()
    count = db.logs.count_documents({"message": {"$regex": keyword, "$options": "i"}})
    return {"keyword": keyword, "count": count}


@app.post("/purge")
def purge():
    if not acquire_lock():
        raise HTTPException(
            status_code=409,
            detail="purge already in progress elsewhere; try again shortly",
        )
    try:
        db = get_db()
        result = db.logs.delete_many({})
        return {"status": "purged", "deleted_count": result.deleted_count}
    finally:
        release_lock()


@app.get("/health")
def health():
    return {"status": "ok"}
