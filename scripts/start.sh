#!/bin/bash
set -e

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "Starting containers from $APP_DIR"
cd "$APP_DIR"

docker compose up -d
