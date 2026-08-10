import pika
import json
import os
import time
from pymongo import MongoClient
from datetime import datetime

# Fetch network addresses from the environment to prevent hardcoding
RABBITMQ_HOST = os.getenv("RABBITMQ_HOST", "rabbitmq")
MONGO_HOST = os.getenv("MONGO_HOST", "mongodb")

# 1. Connect to MongoDB Data Layer
mongo_client = MongoClient(f"mongodb://{MONGO_HOST}:27017/")
db = mongo_client["syslog_db"]
logs_collection = db["logs"]
nodes_collection = db["nodes"]

def callback(ch, method, properties, body):
    try:
        log_data = json.loads(body)
        node_name = log_data.get("node_name", "unknown")
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        # 2. Update node metadata in DB 
        nodes_collection.update_one(
            {"node_name": node_name},
            {
                "$set": {"last_active": timestamp},
                "$setOnInsert": {"first_seen": timestamp},
                "$inc": {"total_logs": 1}
            },
            upsert=True
        )

        # 3. Store structured log entry in DB
        log_entry = {
            "node_name": node_name,
            "timestamp": timestamp,
            "severity": log_data.get("severity", "INFO").upper(),
            "message": log_data.get("message", "")
        }
        logs_collection.insert_one(log_entry)
        
        print(f"[x] Processed log from {node_name}: {log_entry['severity']}")
        
        # Acknowledge the message so RabbitMQ removes it from the queue
        ch.basic_ack(delivery_tag=method.delivery_tag)
    except Exception as e:
        print(f"[!] Error processing message: {e}")

def main():
    print("Distributed Event Ingestion Worker initialized.")
    credentials = pika.PlainCredentials('rabbituser', 'rabbit1234')
    
    connection = None
    
    # --- RETRY LOGIC TO PREVENT DOCKER RACE CONDITIONS ---
    for i in range(5):
        try:
            print(f"[*] Attempting to connect to RabbitMQ (Attempt {i+1}/5)...")
            connection = pika.BlockingConnection(
                pika.ConnectionParameters(host=RABBITMQ_HOST, credentials=credentials)
            )
            print("[+] Successfully connected to RabbitMQ!")
            break  # Exit the loop if successful
        except pika.exceptions.AMQPConnectionError:
            print("[!] RabbitMQ not ready yet. Retrying in 5 seconds...")
            time.sleep(5)
            
    if not connection:
        print("[-] Failed to connect to RabbitMQ after 5 attempts. Crashing gracefully.")
        return
    # -----------------------------------------------------

    channel = connection.channel()
    channel.queue_declare(queue='log_queue', durable=True)

    print(" [*] Waiting for logs. To exit press CTRL+C")
    channel.basic_qos(prefetch_count=1)
    channel.basic_consume(queue='log_queue', on_message_callback=callback)
    channel.start_consuming()

if __name__ == "__main__":
    main()
