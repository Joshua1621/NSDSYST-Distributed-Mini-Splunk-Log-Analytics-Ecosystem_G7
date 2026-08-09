version: '3.8'

services:
  rabbitmq:
    image: rabbitmq:3-management
    container_name: rabbitmq-broker
    environment:
      RABBITMQ_DEFAULT_USER: rabbituser
      RABBITMQ_DEFAULT_PASS: rabbit1234
    ports:
      - "5672:5672"
      - "15672:15672"

  mongodb:
    image: mongo:latest
    container_name: mongodb-store
    ports:
      - "27017:27017"

  ingestion-worker:
    build: 
      context: .
      dockerfile: Dockerfile.worker
    container_name: logger-ingestion
    environment:
      - RABBITMQ_HOST=rabbitmq
      - MONGO_HOST=mongodb
    depends_on:
      - rabbitmq
      - mongodb

  query-api:
    build: 
      context: .
      dockerfile: Dockerfile.api
    container_name: logger-api
    command: uvicorn query_api:app --host 0.0.0.0 --port 8000
    environment:
      - MONGO_HOST=mongodb
    ports:
      - "8000:8000"
    depends_on:
      - mongodb
