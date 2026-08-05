#!/bin/bash
set -e

echo "=== Voice Agent Clinic Deploy Script ==="

ENV=${1:-dev}

echo "Deploying to environment: $ENV"

# Build images (Docker Compose v2)
echo "Building Docker images..."
docker compose -f infra/docker-compose.yml build

# Deploy
echo "Starting services..."
docker compose -f infra/docker-compose.yml up -d

# Health check
# Note: The agent is a LiveKit worker without an HTTP endpoint.
# Health checks for the webhook server and widget are below.
echo "Running health checks..."
sleep 5
curl -sf http://localhost:8000/health || echo "Webhook server health check failed"
curl -sf http://localhost:3000 || echo "Widget health check failed"

echo "=== Deployment complete ==="
