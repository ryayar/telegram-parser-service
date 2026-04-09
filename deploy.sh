#!/bin/bash
set -e

echo "Pulling latest code..."
git pull

echo "Rebuilding and restarting containers..."
docker compose up --build -d

echo "Done. Logs:"
docker compose logs --tail=20
