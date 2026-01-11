#!/bin/bash
set -e

APP_DIR=$(pwd)

echo "Starting containers from $APP_DIR"
docker compose up -d