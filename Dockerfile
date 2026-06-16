# syntax=docker/dockerfile:1

FROM python:3.12-slim

# Install git for MAC address detection and network tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    iproute2 \
    net-tools \
    && rm -rf /var/lib/apt/lists/*

# Create app directory
WORKDIR /app

# Copy dependencies first for better layer caching
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY src/ src/
COPY scripts/ scripts/

# Create data directory for SQLite database
RUN mkdir -p /app/data

# Expose the Agent Hub port
EXPOSE 8765

# Set default environment variables
ENV AGENT_HUB_HOST=0.0.0.0
ENV AGENT_HUB_PORT=8765

# Run the server
CMD ["python", "src/server.py", "--port", "8765", "--host", "0.0.0.0"]
