#!/bin/bash
set -e

APP_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_ROOT"

echo "Starting containers from $APP_ROOT"

docker compose down || true

docker compose up -d || true

echo "Docker compose started"