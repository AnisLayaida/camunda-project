#!/bin/bash
set -e

APP_DIR="$(cd "$(dirname "$0")/.." && pwd)"

echo "Stopping containers from $APP_DIR"
cd "$APP_DIR"

docker compose down || true
