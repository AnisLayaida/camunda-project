#!/bin/bash
set -e

echo "Creating app directory"
mkdir -p /opt/camunda
chmod 755 /opt/camunda

echo "Ensuring Docker is running"
systemctl start docker
systemctl enable docker