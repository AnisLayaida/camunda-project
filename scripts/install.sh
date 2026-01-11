#!/bin/bash
set -e

yum update -y

if ! command -v docker &> /dev/null; then
  amazon-linux-extras install docker -y
fi

systemctl start docker
systemctl enable docker