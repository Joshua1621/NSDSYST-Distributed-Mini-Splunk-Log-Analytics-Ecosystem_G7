# 1. Use a lightweight, stable version of Python
FROM python:3.11-slim

# 2. Set the working directory inside the container
WORKDIR /app

# 3. Copy the requirements file first to leverage Docker cache
COPY requirements.txt .

# 4. Install the necessary Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# 5. Copy the actual worker script into the container
# Make sure you are copying the INGESTION script, not the API script!
COPY ingestion_service.py .

# 6. Execute the script in unbuffered mode
# The "-u" flag is critical! It forces Python to print to the terminal 
# immediately so you can see the logs in Docker.
CMD ["python", "-u", "ingestion_service.py"]
