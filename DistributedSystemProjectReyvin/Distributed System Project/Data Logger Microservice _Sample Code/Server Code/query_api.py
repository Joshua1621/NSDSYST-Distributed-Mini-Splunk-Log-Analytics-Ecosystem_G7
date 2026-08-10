from fastapi import FastAPI, Query
from pymongo import MongoClient
import os
from typing import Optional

app = FastAPI(title="Distributed Log Analytics API")

# Connect to MongoDB Data Layer
MONGO_HOST = os.getenv("MONGO_HOST", "mongodb")
mongo_client = MongoClient(f"mongodb://{MONGO_HOST}:27017/")
db = mongo_client["syslog_db"]
logs_collection = db["logs"]
nodes_collection = db["nodes"]

@app.get("/logs", summary="Retrieve all logs or filter by severity/node")
def get_logs(severity: Optional[str] = None, node_name: Optional[str] = None):
    query = {}
    if severity:
        query["severity"] = severity.upper()
    if node_name:
        query["node_name"] = node_name
        
    # Return documents, excluding the MongoDB-specific _id field
    logs = list(logs_collection.find(query, {"_id": 0}))
    return {"count": len(logs), "results": logs}

@app.get("/nodes", summary="Retrieve metadata for all registered nodes")
def get_nodes():
    nodes = list(nodes_collection.find({}, {"_id": 0}))
    return {"count": len(nodes), "active_registry": nodes}
