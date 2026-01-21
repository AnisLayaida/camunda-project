#!/bin/bash
set -e

echo "=========================================="
echo "INSTALLING CAMUNDA PROJECT"
echo "=========================================="

# Verify Docker is available
docker --version
docker compose version

echo "Installation checks complete"