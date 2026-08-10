import pika
import json
import sys

def send_log(node_name, severity, message, rabbitmq_host="103.231.240.136", rabbitmq_port=32101):
    # 1. Establish connection to RabbitMQ
    credentials = pika.PlainCredentials('rabbituser', 'rabbit1234')
    try:
        connection = pika.BlockingConnection(
            pika.ConnectionParameters(host=rabbitmq_host, port=rabbitmq_port, credentials=credentials)
        )
        channel = connection.channel()
        
        # Ensure the queue exists before publishing
        channel.queue_declare(queue='log_queue', durable=True)

        # 2. Construct the log payload
        log_data = {
            "node_name": node_name,
            "severity": severity,
            "message": message
        }

        # 3. Publish the message to the queue
        channel.basic_publish(
            exchange='',
            routing_key='log_queue',
            body=json.dumps(log_data),
            properties=pika.BasicProperties(
                delivery_mode=2,  # Make message persistent
            )
        )
        print(f" [x] Successfully sent log: {severity} from {node_name}")
        connection.close()

    except Exception as e:
        print(f" [!] Failed to connect to Message Broker: {e}")

if __name__ == "__main__":
    # Example usage
    if len(sys.argv) < 4:
        print("Usage: python client_logger.py <NodeName> <Severity> <Message>")
        sys.exit(1)
        
    node = sys.argv[1]
    sev = sys.argv[2]
    msg = " ".join(sys.argv[3:])
    
    send_log(node, sev, msg)
