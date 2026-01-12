#!/bin/bash
set -e

APP_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$APP_ROOT"

docker compose down || true
