#!/bin/bash
set -e

echo "START.SH VERSION: 2026-01-12-TEST-123"

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "Starting containers from $APP_DIR"
cd "$APP_DIR"

docker compose down || true
docker compose up -d