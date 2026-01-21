# Camunda 7 BPM Platform on AWS

## Enterprise-Grade Business Process Management Infrastructure

This repository contains a production-ready deployment of Camunda Platform 7 on Amazon Web Services, designed to support enterprise workflow automation with a focus on security, reliability, and operational excellence.

---

## Table of Contents

1. [Project Overview](#project-overview)
2. [High-Level Architecture](#high-level-architecture)
3. [CI/CD Pipeline Breakdown](#cicd-pipeline-breakdown)
4. [Camunda Runtime](#camunda-runtime)
5. [Database Layer](#database-layer)
6. [BPMN and DMN Lifecycle](#bpmn-and-dmn-lifecycle)
7. [Python External Task Workers](#python-external-task-workers)
8. [Security Model](#security-model)
9. [Running the Platform](#running-the-platform)
10. [Monitoring and Logs](#monitoring-and-logs)
11. [Failure and Risk Management](#failure-and-risk-management)
12. [Why This Architecture Is Enterprise-Grade](#why-this-architecture-is-enterprise-grade)
13. [Future Improvements](#future-improvements)

---

## Project Overview

### What This System Does

This platform provides a complete Business Process Management (BPM) solution for automating insurance application workflows. The system orchestrates the following business processes:

**Insurance Application Processing**: A multi-stage workflow that receives insurance applications, evaluates risk using DMN decision tables, routes applications through approval paths based on risk classification (Green, Yellow, Red), manages human task assignments, handles document requests, and delivers automated notifications to policyholders.

**Risk Assessment Engine**: A Decision Model and Notation (DMN) implementation that evaluates applicant risk based on multiple factors including age, vehicle make, vehicle model, and geographic region. The decision tables determine premium calculations and staff assignments.

**Document Request Subprocess**: A dedicated workflow for handling incomplete applications, managing document collection, timeout handling, and rejection processing.

### Why Camunda Was Chosen

Camunda Platform 7 was selected for this implementation based on the following technical and business requirements:

**Standards Compliance**: Camunda provides native support for BPMN 2.0 and DMN 1.3 standards, ensuring process definitions remain portable and vendor-agnostic. This prevents vendor lock-in and enables process models to be understood by business analysts without proprietary knowledge.

**External Task Pattern**: Unlike embedded Java delegates, Camunda's external task pattern allows worker implementations in any programming language. This project leverages Python workers, enabling integration with data science libraries, machine learning models, and existing Python-based enterprise systems.

**Operational Visibility**: Camunda Cockpit provides real-time visibility into running process instances, incident management, and historical data analysis. This is essential for production support teams to diagnose issues without database access.

**REST API First**: The comprehensive REST API enables programmatic control over deployments, process instantiation, task management, and administrative operations. This supports automation and integration with external systems.

**Proven Enterprise Adoption**: Camunda Platform 7 has extensive production deployments across financial services, insurance, telecommunications, and government sectors, providing confidence in stability and long-term support.

### Why This Architecture Exists

The architectural decisions in this project address specific enterprise requirements:

**Separation of Concerns**: Infrastructure deployment (via CI/CD) is deliberately separated from process deployment (manual/controlled). This prevents broken BPMN definitions from automatically reaching production and causing process failures.

**Managed Services**: Amazon Aurora PostgreSQL and AWS-managed CI/CD services reduce operational burden, provide automated backups, and ensure high availability without requiring dedicated database administration staff.

**Security Boundaries**: Network segmentation ensures the database is never publicly accessible, all traffic flows through defined security groups, and access is restricted to corporate IP ranges.

**Reproducibility**: Infrastructure as Code via CloudFormation ensures environments can be recreated consistently, disaster recovery is possible, and configuration drift is prevented.

---

## High-Level Architecture

### System Components

```
┌─────────────────────────────────────────────────────────────────────────────────┐
│                           INTERNAL CORPORATE NETWORK                            │
├─────────────────────────────────────────────────────────────────────────────────┤
│                                                                                 │
│  ┌──────────────┐    ┌──────────────┐    ┌──────────────┐                      │
│  │   Manager    │───▶│   Business   │───▶│   Process    │                      │
│  │              │    │   Analysts   │    │   Owners     │                      │
│  └──────────────┘    └──────────────┘    └──────────────┘                      │
│         │                   │                   │                              │
│         │                   │                   │                              │
│         ▼                   ▼                   ▼                              │
│  ┌──────────────────────────────────────────────────────────────────┐          │
│  │                     CAMUNDA MODELER                              │          │
│  │  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────┐  │          │
│  │  │ insurance_      │  │ mini_process.   │  │ risk_rating.    │  │          │
│  │  │ process.bpmn    │  │ bpmn            │  │ dmn             │  │          │
│  │  └─────────────────┘  └─────────────────┘  └─────────────────┘  │          │
│  └──────────────────────────────────────────────────────────────────┘          │
│                                    │                                           │
│                                    │ REST API Deploy                           │
│                                    ▼                                           │
└────────────────────────────────────┼───────────────────────────────────────────┘
                                     │
┌────────────────────────────────────┼───────────────────────────────────────────┐
│                                AWS │ VPC                                       │
│  ┌─────────────────────────────────┼─────────────────────────────────────────┐ │
│  │                    EC2 SECURITY │ GROUP                                   │ │
│  │  ┌──────────────────────────────┴──────────────────────────────────────┐  │ │
│  │  │                        EC2 INSTANCE (t2.micro)                      │  │ │
│  │  │  ┌────────────────────────────────────────────────────────────────┐ │  │ │
│  │  │  │                      DOCKER HOST                               │ │  │ │
│  │  │  │  ┌─────────────────────────────────────────────────────────┐  │ │  │ │
│  │  │  │  │              CAMUNDA 7 CONTAINER                        │  │ │  │ │
│  │  │  │  │                                                         │  │ │  │ │
│  │  │  │  │  ┌─────────────┐ ┌─────────────┐ ┌─────────────┐       │  │ │  │ │
│  │  │  │  │  │  Cockpit    │ │  Tasklist   │ │  Admin      │       │  │ │  │ │
│  │  │  │  │  │  :8080/     │ │  :8080/     │ │  :8080/     │       │  │ │  │ │
│  │  │  │  │  │  camunda/   │ │  camunda/   │ │  camunda/   │       │  │ │  │ │
│  │ ┌──┼──┼──▶│  app/cockpit│ │  app/tasklist│ │  app/admin │       │  │ │  │ │
│  │ │  │  │  │  └─────────────┘ └─────────────┘ └─────────────┘       │  │ │  │ │
│  │ │  │  │  │                                                         │  │ │  │ │
│  │ │  │  │  │  ┌─────────────────────────────────────────────────┐   │  │ │  │ │
│  │ │  │  │  │  │              REST API (:8080)                   │   │  │ │  │ │
│  │ │  │  │  │  │  /engine-rest/deployment/create                 │   │  │ │  │ │
│  │ │  │  │  │  │  /engine-rest/process-definition                │   │  │ │  │ │
│  │ │  │  │  │  │  /engine-rest/external-task/fetchAndLock        │   │  │ │  │ │
│  │ │  │  │  │  └─────────────────────────────────────────────────┘   │  │ │  │ │
│  │ │  │  │  └────────────────────────────┬──────────────────────────┘  │ │  │ │
│  │ │  │  │                               │                             │ │  │ │
│  │ │  │  │  ┌────────────────────────────┴────────────────────────┐   │ │  │ │
│  │ │  │  │  │            PYTHON WORKERS CONTAINER                 │   │ │  │ │
│  │ │  │  │  │  ┌──────────────────┐  ┌──────────────────┐        │   │ │  │ │
│  │ │  │  │  │  │ worker_insurance │  │ worker_risk      │        │   │ │  │ │
│  │ │  │  │  │  │ .py              │  │ .py              │        │   │ │  │ │
│  │ │  │  │  │  └──────────────────┘  └──────────────────┘        │   │ │  │ │
│  │ │  │  │  └─────────────────────────────────────────────────────┘   │ │  │ │
│  │ │  │  └────────────────────────────────────────────────────────────┘ │  │ │
│  │ │  └──────────────────────────────────┬──────────────────────────────┘  │ │
│  │ │                                     │ JDBC                            │ │
│  │ │                                     ▼                                 │ │
│  │ │   ┌───────────────────────────────────────────────────────────────┐   │ │
│  │ │   │                  AURORA SECURITY GROUP                        │   │ │
│  │ │   │  ┌─────────────────────────────────────────────────────────┐  │   │ │
│  │ │   │  │           AMAZON AURORA POSTGRESQL                      │  │   │ │
│  │ │   │  │                                                         │  │   │ │
│  │ │   │  │  Endpoint: camunda-instance-database-instance-1         │  │   │ │
│  │ │   │  │            .c1eogicauczi.eu-west-2.rds.amazonaws.com    │  │   │ │
│  │ │   │  │  Port: 5432                                             │  │   │ │
│  │ │   │  │  Engine: Aurora PostgreSQL                              │  │   │ │
│  │ │   │  │  Instance: db.t3.medium                                 │  │   │ │
│  │ │   │  │  Publicly Accessible: NO                                │  │   │ │
│  │ │   │  │                                                         │  │   │ │
│  │ │   │  │  Tables: ACT_RE_*, ACT_RU_*, ACT_HI_*, ACT_GE_*         │  │   │ │
│  │ │   │  └─────────────────────────────────────────────────────────┘  │   │ │
│  │ │   └───────────────────────────────────────────────────────────────┘   │ │
│  │ │                                                                       │ │
│  │ │  Inbound: EC2 Security Group Only                                     │ │
│  │ └───────────────────────────────────────────────────────────────────────┘ │
│  │                                                                           │
│  │  Inbound: Corporate IP Only (BT Network)                                  │
│  └───────────────────────────────────────────────────────────────────────────┘
│                                                                               │
└───────────────────────────────────────────────────────────────────────────────┘
```

### Data Flow Through the System

**Process Definition Deployment Flow**:
1. Business analysts model processes in Camunda Modeler on the corporate network
2. Process definitions (BPMN/DMN files) are validated locally before deployment
3. Deployment occurs via REST API call to `POST /engine-rest/deployment/create`
4. Camunda parses the XML, validates schema compliance, and stores in Aurora
5. Process definitions become available for instantiation

**Process Instance Execution Flow**:
1. External system or user initiates process via REST API or Tasklist
2. Camunda engine reads process definition from database
3. Engine executes BPMN elements sequentially, persisting state after each step
4. External tasks are published to the task queue
5. Python workers poll `/engine-rest/external-task/fetchAndLock`
6. Workers execute business logic and report completion/failure
7. Human tasks appear in Tasklist for manual completion
8. Process completes and history is recorded

**Infrastructure Deployment Flow**:
1. Developer pushes code to GitHub (main branch)
2. CodePipeline detects change and triggers pipeline
3. CodeBuild executes `buildspec.yml` commands
4. Artifacts are stored in S3 bucket
5. CodeDeploy retrieves artifacts and deploys to EC2
6. EC2 scripts start Docker containers

### Why This Design Is Production-Safe

**Stateless Compute Tier**: The EC2 instance and Docker containers contain no persistent state. All process data resides in Aurora PostgreSQL. This enables instance replacement without data loss.

**Managed Database**: Aurora provides automated backups, point-in-time recovery, automatic failover, and storage auto-scaling. The operations team does not need to manage backup scripts or storage capacity.

**Network Isolation**: The database accepts connections only from the EC2 security group. There is no path from the internet to the database, even if database credentials were compromised.

**Deployment Atomicity**: CodeDeploy performs atomic deployments. If any deployment script fails, the previous version remains running. This prevents partial deployments that could leave the system in an inconsistent state.

---

## CI/CD Pipeline Breakdown

### Pipeline Stages

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│   GitHub    │───▶│ CodePipeline│───▶│  CodeBuild  │───▶│     S3      │───▶│ CodeDeploy  │
│             │    │             │    │             │    │             │    │             │
│  Source     │    │ Orchestrator│    │   Build     │    │  Artifacts  │    │   Deploy    │
└─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘    └─────────────┘
       │                  │                  │                  │                  │
       │                  │                  │                  │                  │
       ▼                  ▼                  ▼                  ▼                  ▼
  Push to main      Detect change      Build Docker       Store build       Execute on EC2
  branch            Start pipeline     images             artifacts         Run scripts
```

### Stage 1: Source (GitHub)

**Repository**: `AnisLayaida/camunda-project`

**Trigger**: Push to `main` branch

**Connection**: GitHub App integration via CodeStar Connections

The source stage monitors the GitHub repository for changes. When a commit is pushed to the main branch, CodePipeline downloads the repository contents and passes them to the build stage.

**Files included in source artifact**:
- `docker-compose.yml` - Container orchestration configuration
- `buildspec.yml` - CodeBuild instructions
- `appspec.yml` - CodeDeploy instructions
- `scripts/` - Deployment lifecycle scripts
- `camunda/` - BPMN and DMN files (included but NOT auto-deployed)
- `python-workers/` - External task worker implementations

### Stage 2: Build (CodeBuild)

**Project**: `camunda-project`

**Compute**: AWS managed Linux container

**Duration**: Approximately 1-2 minutes per build

The `buildspec.yml` defines the build process:

```yaml
version: 0.2

env:
  variables:
    AWS_REGION: eu-west-2
    CODEARTIFACT_DOMAIN: anis-camunda-project
    CODEARTIFACT_REPO: instance-repository
    ACCOUNT_ID: 201786699573

phases:
  install:
    runtime-versions:
      python: 3.9
    commands:
      - echo "Installing system dependencies..."
      - yum install -y docker
      - pip install --upgrade pip

  pre_build:
    commands:
      - echo "Logging in to AWS CodeArtifact..."
      - export CODEARTIFACT_AUTH_TOKEN=$(aws codeartifact get-authorization-token --domain $CODEARTIFACT_DOMAIN --domain-owner $ACCOUNT_ID --region $AWS_REGION --query authorizationToken --output text)

  build:
    commands:
      - echo "Build started on $(date)"
      - echo "Installing Python worker dependencies..."
      - pip install -r workers/requirements.txt || true
      - echo "Building Docker images..."
      - docker compose build

  post_build:
    commands:
      - echo "Build completed on $(date)"
      - echo "Ready for deployment to EC2"

artifacts:
  files:
    - '**/*'
```

**What happens during build**:
1. Python 3.9 runtime is provisioned
2. Docker is installed for image building
3. CodeArtifact authentication token is obtained for private package access
4. Python dependencies are installed
5. Docker images are built (but not pushed to a registry)
6. All files are packaged as deployment artifacts

### Stage 3: Artifact Storage (S3)

**Bucket**: `anis-s3bucket`

**Object**: `anis-codeartifact-file`

The build artifacts are compressed and stored in S3. CodeDeploy retrieves artifacts from this location during deployment.

**Artifact contents**:
- Compiled/validated configuration files
- Docker Compose configuration
- Deployment scripts
- Application code

**Artifact retention**: Objects are overwritten on each build. Historical artifacts are not retained by default.

### Stage 4: Deploy (CodeDeploy)

**Application**: `camunda-app`

**Deployment Group**: `CAMUNDA-PROJECT`

**Deployment Type**: In-place

**Target**: EC2 instances tagged for the deployment group

The `appspec.yml` defines the deployment lifecycle:

```yaml
version: 0.0
os: linux
files:
  - source: /
    destination: /home/ec2-user/camunda-project

hooks:
  BeforeInstall:
    - location: scripts/stop.sh
      timeout: 300
      runas: root

  AfterInstall:
    - location: scripts/install.sh
      timeout: 600
      runas: root

  ApplicationStart:
    - location: scripts/start.sh
      timeout: 300
      runas: root
```

**Deployment lifecycle**:

1. **BeforeInstall** (`scripts/stop.sh`): Stops existing Docker containers gracefully
2. **Install**: CodeDeploy copies files to `/home/ec2-user/camunda-project`
3. **AfterInstall** (`scripts/install.sh`): Installs dependencies, configures environment
4. **ApplicationStart** (`scripts/start.sh`): Starts Docker containers

### What Is Deployed vs What Is NOT Deployed

| Component | Auto-Deployed by CI/CD | Reason |
|-----------|------------------------|--------|
| Docker images | Yes | Required for runtime |
| docker-compose.yml | Yes | Container orchestration |
| Python workers | Yes | External task handlers |
| Deployment scripts | Yes | Lifecycle management |
| Environment configs | Yes | Runtime configuration |
| **BPMN files** | **NO** | Controlled deployment required |
| **DMN files** | **NO** | Controlled deployment required |

**Critical distinction**: The CI/CD pipeline deploys the infrastructure and runtime environment. It does NOT deploy process definitions to the Camunda engine. This is intentional and explained in the BPMN and DMN Lifecycle section.

---

## Camunda Runtime

### Docker Image

**Image**: `camunda/camunda-bpm-platform:run-7.23.0`

**Base**: Eclipse Temurin JDK 17 on Debian

**Variant**: Camunda Run (lightweight, production-ready distribution)

The `docker-compose.yml` configures the Camunda container:

```yaml
version: '3.8'

services:
  camunda:
    image: camunda/camunda-bpm-platform:run-7.23.0
    container_name: camunda
    ports:
      - "8080:8080"
    environment:
      - SPRING_DATASOURCE_URL=jdbc:postgresql://${DB_HOST}:5432/${DB_NAME}
      - SPRING_DATASOURCE_USERNAME=${DB_USER}
      - SPRING_DATASOURCE_PASSWORD=${DB_PASSWORD}
      - SPRING_DATASOURCE_DRIVER_CLASS_NAME=org.postgresql.Driver
      - CAMUNDA_BPM_RUN_AUTH_ENABLED=true
      - CAMUNDA_BPM_ADMIN_USER_ID=admin
      - CAMUNDA_BPM_ADMIN_USER_PASSWORD=${ADMIN_PASSWORD}
    restart: unless-stopped
    healthcheck:
      test: ["CMD", "curl", "-f", "http://localhost:8080/camunda/app/welcome/"]
      interval: 30s
      timeout: 10s
      retries: 3
      start_period: 60s

  python-workers:
    build:
      context: ./python-workers
      dockerfile: Dockerfile
    container_name: python-workers
    environment:
      - CAMUNDA_URL=http://camunda:8080/engine-rest
    depends_on:
      camunda:
        condition: service_healthy
    restart: unless-stopped
```

### Exposed Ports

| Port | Protocol | Purpose |
|------|----------|---------|
| 8080 | HTTP | Camunda web applications and REST API |

**Port 8080 services**:
- `/camunda/app/welcome/` - Welcome page
- `/camunda/app/cockpit/` - Process monitoring
- `/camunda/app/tasklist/` - Human task interface
- `/camunda/app/admin/` - Administration
- `/engine-rest/` - REST API endpoints

### REST API

The Camunda REST API provides programmatic access to all engine functionality.

**Key endpoints**:

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/engine-rest/deployment/create` | POST | Deploy BPMN/DMN definitions |
| `/engine-rest/process-definition` | GET | List deployed process definitions |
| `/engine-rest/process-definition/key/{key}/start` | POST | Start a process instance |
| `/engine-rest/external-task/fetchAndLock` | POST | Poll for external tasks |
| `/engine-rest/external-task/{id}/complete` | POST | Complete an external task |
| `/engine-rest/external-task/{id}/failure` | POST | Report task failure |
| `/engine-rest/task` | GET | List human tasks |
| `/engine-rest/task/{id}/complete` | POST | Complete a human task |
| `/engine-rest/decision-definition` | GET | List deployed decision definitions |

**API authentication**: Basic authentication is enabled. All API requests require valid credentials.

### Web Applications

**Camunda Cockpit** (`/camunda/app/cockpit/`)

Cockpit provides operational visibility into running and completed process instances:
- Dashboard with process instance counts by definition
- Individual instance inspection with variable values
- Incident management and resolution
- Process definition visualization with instance overlay
- Historical data queries and reporting

**Camunda Tasklist** (`/camunda/app/tasklist/`)

Tasklist provides a web interface for human task completion:
- Task inbox for assigned and claimable tasks
- Task forms for data entry
- Task filtering and sorting
- Task delegation and assignment

**Camunda Admin** (`/camunda/app/admin/`)

Admin provides system administration capabilities:
- User and group management
- Authorization configuration
- System settings
- Deployed definitions management

---

## Database Layer

### Amazon Aurora PostgreSQL

**Cluster identifier**: `camunda-instance-database`

**Instance identifier**: `camunda-instance-database-instance-1`

**Endpoint**: `camunda-instance-database-instance-1.c1eogicauczi.eu-west-2.rds.amazonaws.com`

**Port**: 5432

**Engine**: Aurora PostgreSQL

**Instance class**: `db.t3.medium`

**Availability Zone**: `eu-west-2a`

### JDBC Connectivity

The Camunda container connects to Aurora using the PostgreSQL JDBC driver:

```
jdbc:postgresql://camunda-instance-database-instance-1.c1eogicauczi.eu-west-2.rds.amazonaws.com:5432/camunda
```

**Connection pool configuration** (Camunda defaults):
- Maximum pool size: 10
- Minimum idle connections: 1
- Connection timeout: 30 seconds
- Idle timeout: 10 minutes

### Schema Creation

Camunda automatically creates its database schema on first startup. The schema includes:

**Repository tables** (`ACT_RE_*`): Store deployed process definitions, decision definitions, and their resources.

| Table | Purpose |
|-------|---------|
| ACT_RE_DEPLOYMENT | Deployment metadata |
| ACT_RE_PROCDEF | Process definitions |
| ACT_RE_DECISION_DEF | Decision definitions |
| ACT_RE_DECISION_REQ_DEF | Decision requirements definitions |

**Runtime tables** (`ACT_RU_*`): Store active process instance state.

| Table | Purpose |
|-------|---------|
| ACT_RU_EXECUTION | Process instance executions |
| ACT_RU_TASK | Active human tasks |
| ACT_RU_VARIABLE | Process variables |
| ACT_RU_EXT_TASK | External task queue |
| ACT_RU_JOB | Asynchronous jobs |
| ACT_RU_INCIDENT | Active incidents |

**History tables** (`ACT_HI_*`): Store completed process instance history.

| Table | Purpose |
|-------|---------|
| ACT_HI_PROCINST | Completed process instances |
| ACT_HI_TASKINST | Completed tasks |
| ACT_HI_VARINST | Historical variable values |
| ACT_HI_ACTINST | Activity instance history |

**Identity tables** (`ACT_ID_*`): Store users, groups, and memberships.

**General tables** (`ACT_GE_*`): Store binary resources and properties.

### Why Managed Database Is Used

**Automated backups**: Aurora performs continuous backups to S3 with point-in-time recovery. No backup scripts or manual intervention required.

**Automatic failover**: In multi-AZ deployments, Aurora automatically promotes a replica if the primary fails. Application connections are automatically redirected.

**Storage auto-scaling**: Aurora storage automatically grows as data increases, up to 128 TiB. No capacity planning or manual expansion required.

**Maintenance automation**: Minor version upgrades and patches can be applied automatically during defined maintenance windows.

**Performance insights**: Aurora provides detailed query performance metrics without requiring additional monitoring agents.

**Security**: Encryption at rest is enabled by default. Network traffic is encrypted in transit. IAM authentication is available.

---

## BPMN and DMN Lifecycle

### BPMN-as-Code Philosophy

Process definitions in this project are treated as code artifacts that require the same rigor as application code:

**Version control**: All BPMN and DMN files are stored in the Git repository under the `camunda/` directory. Changes are tracked, reviewed, and can be reverted.

**Change management**: Process changes should follow a pull request workflow with peer review before merging to main.

**Environment parity**: The same process definition files can be deployed to development, staging, and production environments, ensuring consistency.

### Why Auto-Deploy Is Dangerous

Unlike application code that fails fast with exceptions, broken BPMN definitions can cause insidious failures:

**Silent failures**: A BPMN with a misconfigured gateway may route all instances to an unintended path without raising errors.

**Data corruption**: A BPMN that reads variables in the wrong order may process incorrect data and persist invalid state.

**Cascading failures**: A BPMN with an infinite loop can exhaust thread pools and database connections, affecting all process instances.

**Irreversible state**: Once a process instance executes past a broken element, the damage may be permanent. Fixing the BPMN only helps new instances.

**Production impact**: Unlike a web application where a bad deployment affects new requests, a broken BPMN affects all running process instances that reach the broken element.

For these reasons, **this CI/CD pipeline deliberately does NOT auto-deploy BPMN/DMN files**. Process deployments require explicit human action.

### Manual and Controlled Deployment

**Option 1: Camunda Modeler Direct Deployment**

1. Open the process definition in Camunda Modeler
2. Click the "Deploy" button in the toolbar
3. Enter the REST API endpoint: `http://<EC2-IP>:8080/engine-rest`
4. Provide credentials when prompted
5. Review the deployment summary and confirm

**Option 2: REST API Deployment**

Using `curl`:

```bash
curl -X POST \
  "http://<EC2-IP>:8080/engine-rest/deployment/create" \
  -u admin:<password> \
  -F "deployment-name=insurance-process-v1.2.0" \
  -F "enable-duplicate-filtering=true" \
  -F "deploy-changed-only=true" \
  -F "insurance_process.bpmn=@camunda/insurance_process.bpmn" \
  -F "risk_rating.dmn=@camunda/risk_rating.dmn"
```

Using Python:

```python
import requests

url = "http://<EC2-IP>:8080/engine-rest/deployment/create"
auth = ("admin", "<password>")

files = {
    "deployment-name": (None, "insurance-process-v1.2.0"),
    "enable-duplicate-filtering": (None, "true"),
    "deploy-changed-only": (None, "true"),
    "insurance_process.bpmn": open("camunda/insurance_process.bpmn", "rb"),
    "risk_rating.dmn": open("camunda/risk_rating.dmn", "rb"),
}

response = requests.post(url, auth=auth, files=files)
print(response.json())
```

**Option 3: Semi-Automated Deployment Script**

A deployment script with validation can be created for controlled releases:

```bash
#!/bin/bash
# deploy-process.sh - Validates and deploys BPMN with confirmation

CAMUNDA_URL="${CAMUNDA_URL:-http://localhost:8080}"
DEPLOYMENT_NAME="${1:-manual-deployment}"
BPMN_FILE="${2:-camunda/insurance_process.bpmn}"

# Validate BPMN exists
if [ ! -f "$BPMN_FILE" ]; then
    echo "ERROR: BPMN file not found: $BPMN_FILE"
    exit 1
fi

# Check Camunda is reachable
if ! curl -sf "$CAMUNDA_URL/engine-rest/engine" > /dev/null; then
    echo "ERROR: Camunda is not reachable at $CAMUNDA_URL"
    exit 1
fi

# Show deployment preview
echo "========================================="
echo "DEPLOYMENT PREVIEW"
echo "========================================="
echo "Target:     $CAMUNDA_URL"
echo "Name:       $DEPLOYMENT_NAME"
echo "File:       $BPMN_FILE"
echo "========================================="

read -p "Proceed with deployment? (yes/no): " CONFIRM
if [ "$CONFIRM" != "yes" ]; then
    echo "Deployment cancelled."
    exit 0
fi

# Execute deployment
curl -X POST \
    "$CAMUNDA_URL/engine-rest/deployment/create" \
    -u admin:$CAMUNDA_ADMIN_PASSWORD \
    -F "deployment-name=$DEPLOYMENT_NAME" \
    -F "enable-duplicate-filtering=true" \
    -F "$(basename $BPMN_FILE)=@$BPMN_FILE"

echo ""
echo "Deployment complete. Verify in Cockpit."
```

### REST API Deployment Endpoint Reference

**Endpoint**: `POST /engine-rest/deployment/create`

**Content-Type**: `multipart/form-data`

**Parameters**:

| Parameter | Type | Required | Description |
|-----------|------|----------|-------------|
| deployment-name | text | No | Human-readable name for the deployment |
| enable-duplicate-filtering | text | No | Skip deployment if identical definition exists |
| deploy-changed-only | text | No | Only deploy definitions that changed |
| deployment-source | text | No | Source identifier (e.g., "modeler", "ci-cd") |
| tenant-id | text | No | Tenant identifier for multi-tenant deployments |
| *.bpmn | file | Yes | BPMN 2.0 XML file(s) |
| *.dmn | file | No | DMN 1.3 XML file(s) |

**Response** (201 Created):

```json
{
  "id": "deployment-id",
  "name": "insurance-process-v1.2.0",
  "source": "modeler",
  "deploymentTime": "2025-01-21T12:00:00.000+0000",
  "deployedProcessDefinitions": {
    "insurance_process:3:def-id": {
      "id": "insurance_process:3:def-id",
      "key": "insurance_process",
      "version": 3,
      "name": "InsuranceProcess"
    }
  },
  "deployedDecisionDefinitions": {
    "risk_rating:2:dec-id": {
      "id": "risk_rating:2:dec-id",
      "key": "risk_rating",
      "version": 2,
      "name": "Risk Rating"
    }
  }
}
```

---

## Python External Task Workers

### What External Tasks Are

External tasks are BPMN service tasks that delegate execution to external worker applications. Instead of executing business logic inside the Camunda JVM, the engine publishes tasks to a queue that workers poll and process.

In BPMN, an external task is defined by setting the implementation to "External" and specifying a topic:

```xml
<bpmn:serviceTask id="DetermineRiskgroup" name="Determine Riskgroup" 
                  camunda:type="external" 
                  camunda:topic="determine-riskgroup">
</bpmn:serviceTask>
```

### Why External Tasks Are Used

**Language flexibility**: Workers can be implemented in any language that can make HTTP requests. This project uses Python, enabling integration with Python data science and machine learning libraries.

**Failure isolation**: If a worker crashes, it does not affect the Camunda engine or other workers. The task remains in the queue and is retried.

**Horizontal scaling**: Multiple worker instances can poll the same topic for parallel processing. Load balancing is automatic.

**Independent deployment**: Workers can be deployed, updated, and scaled independently of the Camunda engine.

**Transaction boundary**: Each external task execution is its own transaction. Long-running tasks do not hold database locks.

### How Workers Interact with Camunda

**Polling pattern**:

1. Worker calls `POST /engine-rest/external-task/fetchAndLock`
2. Engine reserves matching tasks for the worker (locks them)
3. Worker receives task details including process variables
4. Worker executes business logic
5. Worker reports completion or failure
6. Engine releases lock and continues process execution

**Lock mechanism**: When a worker fetches a task, it specifies a lock duration (e.g., 10 minutes). If the worker crashes without completing, the lock expires and the task becomes available for other workers.

### Failure Isolation Benefits

**Worker failure**: If a Python worker throws an unhandled exception, only that task is affected. The worker process restarts and continues processing other tasks. The failed task is retried after the lock expires.

**Network failure**: If network connectivity is lost between the worker and Camunda, locks expire and tasks are automatically retried by other workers.

**Poison message handling**: Tasks that consistently fail are marked as incidents after exhausting retries. An operator can investigate and resolve in Cockpit without affecting other tasks.

**Resource exhaustion**: If a worker runs out of memory or CPU, it only affects tasks locked by that worker. Other workers continue processing normally.

### Worker Implementation

The following Python workers implement the external tasks defined in the BPMN:

**worker_insurance.py**: Handles insurance-specific business logic including document validation, approval routing, and notification sending.

**worker_risk.py**: Implements risk calculation logic that could integrate with external risk assessment services or machine learning models.

---

## Security Model

### Security Groups

**EC2 Security Group** (`camunda-project-stack-PublicSecurityGroup-*`)

| Direction | Protocol | Port | Source | Purpose |
|-----------|----------|------|--------|---------|
| Inbound | TCP | 22 | Corporate IP /32 | SSH access |
| Inbound | TCP | 8080 | Corporate IP /32 | Camunda web/API |
| Outbound | All | All | 0.0.0.0/0 | Internet access |

**Aurora Security Group** (`rds-ec2-1`)

| Direction | Protocol | Port | Source | Purpose |
|-----------|----------|------|--------|---------|
| Inbound | TCP | 5432 | EC2 Security Group | PostgreSQL from EC2 only |
| Outbound | TCP | All | 0.0.0.0/0 | Response traffic |

### Network Isolation

The network architecture enforces defense in depth:

**Public subnet**: The EC2 instance resides in a public subnet with a public IP address. However, security group rules restrict inbound traffic to corporate IP addresses only.

**Private database**: The Aurora database is NOT publicly accessible. The only path to the database is through the EC2 security group. Even if database credentials were exposed, external attackers could not connect.

**No direct database access**: Developers and operators do not connect directly to the database. All database interaction occurs through the Camunda web applications and REST API.

### Why Public Database Access Is Forbidden

**Attack surface reduction**: Every network path to the database is a potential attack vector. By allowing only EC2 connections, the attack surface is minimized.

**Credential protection**: Even if database credentials are accidentally committed to version control or exposed in logs, attackers cannot use them without network access.

**Audit trail**: All database changes occur through Camunda, which logs user actions. Direct database access would bypass this audit trail.

**Data integrity**: The Camunda schema has complex relationships and constraints. Direct SQL modifications could violate constraints and corrupt data.

### Access Control Philosophy

**Principle of least privilege**: Each component has only the permissions necessary for its function. The EC2 instance role has permissions for CodeDeploy, CloudWatch, and SSM, but not administrative access.

**Network-based trust**: Internal components (Camunda to database, worker to Camunda) communicate within the VPC and trust each other. External access requires authentication.

**Authentication enforcement**: The Camunda REST API requires authentication. Anonymous access is disabled.

**Role-based authorization**: Camunda's internal authorization system controls which users can access which process definitions, tasks, and data.

---

## Running the Platform

### Docker Commands

**Start the platform**:

```bash
cd /home/ec2-user/camunda-project
docker compose up -d
```

**Stop the platform**:

```bash
docker compose down
```

**View running containers**:

```bash
docker ps
```

**View container logs**:

```bash
# All containers
docker compose logs -f

# Camunda only
docker logs -f camunda

# Workers only
docker logs -f python-workers
```

**Restart a specific container**:

```bash
docker compose restart camunda
```

**Rebuild and restart workers**:

```bash
docker compose up -d --build python-workers
```

### Verifying Container Health

**Check container status**:

```bash
docker ps --format "table {{.Names}}\t{{.Status}}\t{{.Ports}}"
```

Expected output:
```
NAMES           STATUS                    PORTS
camunda         Up 2 hours (healthy)      0.0.0.0:8080->8080/tcp
python-workers  Up 2 hours                
```

**Verify Camunda is responding**:

```bash
curl -s http://localhost:8080/engine-rest/engine | jq
```

Expected response:
```json
[
  {
    "name": "default"
  }
]
```

**Check database connectivity**:

```bash
docker exec camunda curl -s http://localhost:8080/engine-rest/process-definition/count
```

Expected response:
```json
{
  "count": 2
}
```

### Accessing Camunda Cockpit

1. Obtain the EC2 public IP from the AWS Console or by running:
   ```bash
   curl -s http://169.254.169.254/latest/meta-data/public-ipv4
   ```

2. Open a browser and navigate to:
   ```
   http://<EC2-PUBLIC-IP>:8080/camunda/app/cockpit/
   ```

3. Log in with administrator credentials

4. The dashboard displays:
   - Count of deployed process definitions
   - Count of running process instances
   - Count of open incidents
   - Count of open human tasks

---

## Monitoring and Logs

### Docker Logs

**Real-time log streaming**:

```bash
# Follow all container logs
docker compose logs -f

# Follow Camunda logs only
docker logs -f camunda 2>&1 | grep -v "DEBUG"

# Follow worker logs only
docker logs -f python-workers
```

**Historical log retrieval**:

```bash
# Last 100 lines from Camunda
docker logs --tail 100 camunda

# Logs from the last hour
docker logs --since 1h camunda

# Logs with timestamps
docker logs -t camunda
```

**Log levels**: Camunda uses SLF4J with Logback. The default level is INFO. To enable DEBUG logging, set the environment variable:

```yaml
environment:
  - LOGGING_LEVEL_ORG_CAMUNDA=DEBUG
```

### Camunda Cockpit Monitoring

**Process Instance Monitoring**:
- Navigate to Cockpit > Processes
- Click a process definition to see running instances
- Each instance shows current activity, variables, and history

**Incident Management**:
- Navigate to Cockpit > Incidents
- Incidents are created when tasks fail after retries
- Click an incident to see the error message and stack trace
- Resolve incidents by fixing the cause and clicking "Retry"

**History Queries**:
- Navigate to Cockpit > History
- Query completed process instances by time range, process definition, or business key
- Drill into individual instances to see execution timeline

### Database Observability

**Aurora Performance Insights**:

1. Navigate to RDS Console > Databases > camunda-instance-database-instance-1
2. Click "Monitoring" tab
3. Click "Performance Insights"

Performance Insights shows:
- Database load by wait events
- Top SQL statements by execution time
- Active session history

**CloudWatch Metrics**:

Key metrics to monitor:
- `CPUUtilization`: Should stay below 80%
- `DatabaseConnections`: Should stay below connection limit
- `FreeableMemory`: Should not approach zero
- `ReadIOPS` / `WriteIOPS`: Baseline for capacity planning

**Connection monitoring from Camunda**:

```bash
curl -s "http://localhost:8080/engine-rest/metrics/process-engine-process-instances" | jq
```

---

## Failure and Risk Management

### What Happens If BPMN Is Broken

**Scenario**: A BPMN file with a syntax error is deployed.

**Impact**: The deployment fails. Camunda validates BPMN against the schema during deployment. Existing process definitions remain unchanged. Running instances are unaffected.

**Recovery**: Fix the BPMN file and deploy again.

---

**Scenario**: A BPMN file with a logical error (e.g., gateway missing outgoing path) is deployed.

**Impact**: Process instances reaching the broken element fail and create incidents. Other process definitions and instances are unaffected.

**Recovery**: 
1. Fix the BPMN file
2. Deploy the corrected version (creates a new version)
3. New instances use the corrected version
4. Existing stuck instances must be manually migrated or cancelled in Cockpit

---

**Scenario**: A BPMN file references a non-existent external task topic.

**Impact**: Process instances reaching the external task wait indefinitely. No workers subscribe to the topic, so tasks are never completed.

**Recovery**:
1. Deploy a worker that handles the topic, OR
2. Fix the BPMN to use the correct topic and deploy
3. Cancel stuck instances or wait for workers to clear the backlog

### What Happens If Workers Fail

**Scenario**: A Python worker crashes with an unhandled exception.

**Impact**: The task the worker was processing becomes locked until the lock expires (default 10 minutes). After expiration, another worker can pick it up. The crashed worker container restarts automatically due to `restart: unless-stopped`.

**Recovery**: Automatic. Docker restarts the worker, locks expire, tasks are retried.

---

**Scenario**: A worker has a bug that causes it to always fail a specific type of task.

**Impact**: The task is retried according to the retry configuration (default 3 retries). After exhausting retries, an incident is created. The process instance is blocked at that activity.

**Recovery**:
1. Check the incident in Cockpit to see the error message
2. Fix the worker code
3. Redeploy the worker container
4. Click "Retry" on the incident in Cockpit

---

**Scenario**: Workers are overloaded and cannot keep up with task volume.

**Impact**: External tasks accumulate in the queue. Process instances progress slowly but are not blocked. Users may notice delays.

**Recovery**:
1. Scale workers horizontally by running additional instances
2. Increase worker polling batch size
3. Optimize worker code for performance

### How Production Stability Is Protected

**Infrastructure stability**:
- CI/CD pipeline deploys infrastructure changes atomically
- Rollback is possible by re-deploying previous Git commit
- Database is managed by AWS with automated backups

**Process definition stability**:
- BPMN/DMN files are NOT auto-deployed
- Human approval required for process deployments
- Version control enables rollback of definitions

**Runtime stability**:
- External task pattern isolates worker failures
- Incident system prevents silent failures
- Health checks restart unhealthy containers
- Lock expiration handles worker crashes

---

## Why This Architecture Is Enterprise-Grade

### Explicit Justification

This architecture meets enterprise requirements in the following ways:

**Reliability**: The system has no single point of failure. The EC2 instance can be replaced without data loss. The Aurora database has automated backups. Workers can fail and restart without affecting the engine.

**Scalability**: External task workers can scale horizontally. The database can scale vertically or add read replicas. The architecture supports growth without redesign.

**Security**: Defense in depth with security groups, network isolation, and authentication. Credentials are managed through environment variables, not code. Database is never publicly accessible.

**Operability**: Cockpit provides visibility without database access. Docker logs are accessible. CloudWatch metrics enable alerting. Incidents surface problems for resolution.

**Maintainability**: Infrastructure as Code enables reproducibility. Deployment scripts are versioned. Configuration is externalized. Components are loosely coupled.

**Auditability**: Git history tracks all code changes. Camunda logs user actions. Database changes occur through the engine, not directly.

### Trade-offs

| Decision | Benefit | Cost |
|----------|---------|------|
| Manual BPMN deployment | Production stability | Slower process changes |
| External task pattern | Language flexibility, failure isolation | Network overhead |
| Managed Aurora | Reduced ops burden | Higher cost than self-managed |
| Single EC2 instance | Simplicity | No automatic failover |
| No container registry | Simpler pipeline | Slower deployments (build each time) |

### Real-World Relevance

This architecture reflects patterns used in production BPM deployments:

**Financial services**: Banks use similar patterns for loan origination, with strict change control on process definitions.

**Insurance**: Insurers deploy claims processing workflows with external task workers integrating policy systems.

**Government**: Public sector organizations use controlled deployments to meet compliance requirements.

The separation of infrastructure deployment from process deployment is a best practice recommended by Camunda consultants and is documented in Camunda's enterprise deployment guides.

---

## Future Improvements

### Staging Environments

**Current state**: Single production environment.

**Improvement**: Implement development, staging, and production environments:
- Development: Local Docker Compose for developers
- Staging: Separate AWS account/VPC mirroring production
- Production: Current setup with additional hardening

**Benefits**:
- Test process changes before production
- Validate infrastructure changes safely
- Enable performance testing at scale

### Automated Validation

**Current state**: BPMN validation occurs during deployment, after human approval.

**Improvement**: Add pre-deployment validation:
- Linting BPMN for common mistakes
- Schema validation for XML compliance
- Simulation testing for logic errors
- Integration tests for external task handlers

**Implementation**:
```bash
# Example validation in CI/CD
npx bpmnlint camunda/insurance_process.bpmn
java -jar camunda-bpm-assert.jar --validate camunda/insurance_process.bpmn
```

### Secrets Management

**Current state**: Credentials in environment variables on EC2.

**Improvement**: Use AWS Secrets Manager:
- Store database credentials in Secrets Manager
- Rotate credentials automatically
- Retrieve at runtime without storing on disk

**Implementation**:
```yaml
environment:
  - SPRING_DATASOURCE_PASSWORD=${aws secretsmanager get-secret-value --secret-id camunda/db-password --query SecretString --output text}
```

### Observability Enhancements

**Current state**: Docker logs and Cockpit.

**Improvements**:

**Centralized logging**:
- Ship logs to CloudWatch Logs or ELK stack
- Enable log-based alerting
- Retain logs beyond container lifecycle

**Distributed tracing**:
- Implement OpenTelemetry in workers
- Trace requests across Camunda and workers
- Visualize in Jaeger or AWS X-Ray

**Metrics export**:
- Export Camunda metrics to Prometheus
- Create Grafana dashboards
- Alert on process SLOs (e.g., average completion time)

**Health checks**:
- Implement deep health checks beyond HTTP response
- Check database connectivity
- Check worker responsiveness

### High Availability

**Current state**: Single EC2 instance, single-AZ database.

**Improvements**:

**EC2 Auto Scaling**:
- Launch template with user data
- Auto Scaling group across availability zones
- Application Load Balancer for distribution

**Aurora Multi-AZ**:
- Add Aurora replica in another AZ
- Automatic failover on primary failure
- Read queries can use replica

**Container orchestration**:
- Migrate to Amazon ECS or EKS
- Enable container auto-scaling
- Improve deployment strategies (blue/green)

---

## Repository Structure

```
camunda-project/
│
├── camunda/                          # BPMN and DMN process definitions
│   ├── insurance_process.bpmn       # Main insurance workflow
│   ├── mini_process.bpmn            # Document request subprocess
│   └── risk_rating.dmn              # Risk assessment decision table
│
├── python-workers/                   # External task worker implementations
│   ├── worker_insurance.py          # Insurance task handler
│   ├── worker_risk.py               # Risk calculation worker
│   ├── requirements.txt             # Python dependencies
│   └── Dockerfile                   # Worker container definition
│
├── scripts/                          # Deployment lifecycle scripts
│   ├── install.sh                   # Post-install configuration
│   ├── start.sh                     # Application startup
│   └── stop.sh                      # Graceful shutdown
│
├── docker-compose.yml               # Container orchestration
├── buildspec.yml                    # CodeBuild instructions
├── appspec.yml                      # CodeDeploy instructions
├── README.md                        # This documentation
└── .gitignore                       # Git ignore patterns
```

---

## Quick Reference

### Useful Commands

```bash
# Check Camunda status
curl http://localhost:8080/engine-rest/engine

# List deployed process definitions
curl http://localhost:8080/engine-rest/process-definition

# Start a process instance
curl -X POST http://localhost:8080/engine-rest/process-definition/key/insurance_process/start \
  -H "Content-Type: application/json" \
  -d '{"variables": {"applicantName": {"value": "John Doe"}}}'

# View running instances
curl http://localhost:8080/engine-rest/process-instance

# View external tasks
curl http://localhost:8080/engine-rest/external-task

# View incidents
curl http://localhost:8080/engine-rest/incident
```

### Important URLs

| Resource | URL |
|----------|-----|
| Cockpit | `http://<IP>:8080/camunda/app/cockpit/` |
| Tasklist | `http://<IP>:8080/camunda/app/tasklist/` |
| Admin | `http://<IP>:8080/camunda/app/admin/` |
| REST API | `http://<IP>:8080/engine-rest/` |
| API Docs | `https://docs.camunda.org/manual/7.23/reference/rest/` |

### Contact and Support

For issues with this deployment:
1. Check the incident list in Cockpit
2. Review Docker container logs
3. Verify security group rules
4. Check Aurora connectivity and status

---

## License

This project is provided for educational and demonstration purposes. Camunda Platform 7 is available under the Apache License 2.0 for the Community Edition.

---

*Last updated: January 2025*