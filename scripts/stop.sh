#!/bin/bash
set -e

cd /opt/camunda || exit 0
docker compose down || true