# DataForge — Deployment Guide

Complete deployment instructions for all environments.

---

## Table of Contents

1. [Prerequisites](#1-prerequisites)
2. [Quick Start (Local)](#2-quick-start-local)
3. [Environment Variables](#3-environment-variables)
4. [Database Setup](#4-database-setup)
5. [API Server](#5-api-server)
6. [Frontend](#6-frontend)
7. [TrueForge Agent Runtime](#7-trueforge-agent-runtime)
8. [Docker Full Stack](#8-docker-full-stack)
9. [Cloud Deployment](#9-cloud-deployment)
10. [Production Checklist](#10-production-checklist)
11. [Troubleshooting](#11-troubleshooting)

---

## 1. Prerequisites

### Required

| Tool | Version | Install |
|------|---------|---------|
| **Python** | 3.11+ | `brew install python@3.11` (macOS) |
| **uv** | Latest | `curl -LsSf https://astral.sh/uv/install.sh \| sh` |
| **Node.js** | 18+ | `brew install node@18` (macOS) |
| **Docker Desktop** | Latest | https://docker.com/products/docker-desktop |
| **Git** | Latest | `brew install git` |

### Optional (for specific features)

| Tool | Purpose |
|------|---------|
| **Gemini API Key** | LLM for agent (free tier: 20 req/day) |
| **GitHub Token** | GitHub MCP tools (commit/PR lookup) |
| **Airflow** | Pipeline rerun remediation |
| **Snowflake account** | Snowflake connector |
| **Databricks workspace** | Databricks connector |

---

## 2. Quick Start (Local)

```bash
# 1. Clone the repo
git clone https://github.com/mohith1306/DataForge.git
cd DataForge/dataforge

# 2. Copy environment file
cp .env.example .env
# Edit .env with your API keys (see Section 3)

# 3. Start databases
docker compose up -d postgres clickhouse

# 4. Install Python dependencies
uv sync

# 5. Install frontend dependencies
cd apps/web && npm install && cd ../..

# 6. Seed demo data (optional)
uv run python data/seed/seed_clickhouse.py

# 7. Start API server
uv run uvicorn apps.api.app.main:app --host 0.0.0.0 --port 8000 --reload

# 8. Start frontend (new terminal)
cd apps/web && npm run dev

# 9. Start TrueForge (new terminal)
npx @truefoundry/trueforge --port 8790
```

### Access Points

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| TrueForge UI | http://localhost:8790 |
| ClickHouse | http://localhost:8123 |
| PostgreSQL | localhost:5432 |

---

## 3. Environment Variables

### Required

```bash
# .env

# LLM — Get from https://aistudio.google.com/apikey
GEMINI_API_KEY=your-gemini-api-key

# Database (default works with Docker)
DATABASE_URL=postgresql+asyncpg://dataforge:dataforge@localhost:5432/dataforge

# ClickHouse (default works with Docker)
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_DATABASE=dataforge
```

### Optional

```bash
# TrueForge (enable agent runtime)
TRUEFORGE_URL=http://localhost:8790
TRUEFORGE_ENABLED=true

# LLM Model (default: gemini-3.6-flash)
MODEL_NAME=google/gemini-3.6-flash

# GitHub (for MCP tools)
GITHUB_TOKEN=ghp_your_token_here
GITHUB_REPO=owner/repo

# Airflow (for pipeline rerun remediation)
AIRFLOW_URL=http://localhost:8080
AIRFLOW_USERNAME=airflow
AIRFLOW_PASSWORD=airflow

# Monitor backend (clickhouse | postgres | custom)
MONITOR_DB_TYPE=clickhouse

# App mode
DATAFORGE_ENV=demo
```

### Getting API Keys

**Gemini (free tier):**
1. Go to https://aistudio.google.com/apikey
2. Create API key
3. Add to `.env` as `GEMINI_API_KEY=...`
4. Free tier: 20 requests/day, 250K tokens/minute

**GitHub Token (optional):**
1. Go to https://github.com/settings/tokens
2. Generate new token (classic)
3. Select `repo` scope
4. Add to `.env` as `GITHUB_TOKEN=ghp_...`

---

## 4. Database Setup

### Option A: Docker (Recommended)

```bash
# Start PostgreSQL + ClickHouse
docker compose up -d postgres clickhouse

# Verify
docker ps
# Should show: dataforge-postgres-1, dataforge-clickhouse-1
```

**Ports:**
- PostgreSQL: 5432
- ClickHouse: 8123 (HTTP), 9000 (native)

**Auto-created tables:**
- PostgreSQL: `incidents`, `incident_events`, `evidence`, `remediation_plans`, `approvals`, `executions`, `verifications`
- ClickHouse: `revenue_daily`, `customer_orders`, `pipeline_events`, `data_quality_metrics`

### Option B: External Database

**PostgreSQL:**
```bash
# Set in .env
DATABASE_URL=postgresql+asyncpg://user:password@your-host:5432/your-db
```

**ClickHouse:**
```bash
# Set in .env
CLICKHOUSE_HOST=your-clickhouse-host
CLICKHOUSE_PORT=8123
CLICKHOUSE_DATABASE=your-database
```

### Seed Demo Data

```bash
# Seed ClickHouse with demo data (pipeline failures, revenue drops)
uv run python data/seed/seed_clickhouse.py
```

This creates:
- 60 days of revenue data with 42% APAC drop in last 7 days
- 7 pipeline events (3 failed, 2 stale, 2 OK)
- Customer orders with quality issues
- Data quality metrics

---

## 5. API Server

### Development

```bash
# Start with auto-reload
uv run uvicorn apps.api.app.main:app --host 0.0.0.0 --port 8000 --reload
```

### Production

```bash
# Start with workers (4 cores)
uv run uvicorn apps.api.app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### Verify

```bash
# Health check
curl http://localhost:8000/api/health

# Expected response:
# {"status":"healthy","service":"dataforge-api","environment":"demo",...}
```

### API Documentation

Interactive docs available at: http://localhost:8000/docs

---

## 6. Frontend

### Development

```bash
cd apps/web
npm run dev
# Vite dev server on http://localhost:3000
```

### Production Build

```bash
cd apps/web
npm run build
# Output: apps/web/dist/

# Serve with any static server
npx serve dist -p 3000
```

### Environment

The frontend reads `VITE_API_URL` for API endpoint:

```bash
# Default: http://localhost:8000
# For production, set in apps/web/.env:
VITE_API_URL=https://your-api-domain.com
```

---

## 7. TrueForge Agent Runtime

TrueForge is the AI agent runtime that orchestrates investigations.

### Install

```bash
# Already in package.json
npm install
```

### Start

```bash
npx @truefoundry/trueforge --port 8790
```

### Verify

```bash
curl http://localhost:8790/api/v1/agents
# Should return agent list
```

### How It Works

1. DataForge creates a `dataforge-investigator` agent in TrueForge
2. Agent spec includes:
   - Model: `google/gemini-3.6-flash`
   - MCP servers: database, pipeline, github, remediation
   - Sandbox: enabled
   - Approval required for: rollback, reprocess, rerun
3. When an incident is created, DataForge sends it to TrueForge
4. TrueForge agent uses MCP tools to investigate
5. Results stream back to DataForge via SSE

---

## 8. Docker Full Stack

### Create Dockerfiles

The docker-compose.yml references Dockerfiles that need to be created:

**`infrastructure/docker/Dockerfile.api`:**
```dockerfile
FROM python:3.11-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Copy dependency files
COPY pyproject.toml uv.lock ./

# Install dependencies
RUN uv sync --frozen --no-dev

# Copy application code
COPY . .

EXPOSE 8000

CMD ["uv", "run", "uvicorn", "apps.api.app.main:app", "--host", "0.0.0.0", "--port", "8000"]
```

**`infrastructure/docker/Dockerfile.web`:**
```dockerfile
FROM node:18-alpine as build

WORKDIR /app

COPY apps/web/package*.json ./
RUN npm install

COPY apps/web/ ./
RUN npm run build

FROM nginx:alpine
COPY --from=build /app/dist /usr/share/nginx/html
COPY infrastructure/nginx.conf /etc/nginx/conf.d/default.conf

EXPOSE 3000
```

### Build and Run

```bash
# Build all services
docker compose build

# Start everything
docker compose up -d

# Check status
docker compose ps

# View logs
docker compose logs -f api
docker compose logs -f web
```

### Stop

```bash
docker compose down
# Add -v to also remove volumes
docker compose down -v
```

---

## 9. Cloud Deployment

### Option A: Railway (Easiest)

```bash
# Install Railway CLI
npm install -g @railway/cli

# Login
railway login

# Init project
railway init

# Add PostgreSQL
railway add --database postgres

# Set environment variables
railway variables set GEMINI_API_KEY=your_key
railway variables set TRUEFORGE_ENABLED=false
railway variables set MONITOR_DB_TYPE=postgres

# Deploy
railway up
```

### Option B: Render

1. Create Render account at https://render.com
2. New → Web Service → Connect GitHub repo
3. Settings:
   - Build Command: `cd apps/web && npm install && npm run build && cd ../.. && uv sync`
   - Start Command: `uv run uvicorn apps.api.app.main:app --host 0.0.0.0 --port $PORT`
4. Add PostgreSQL database
5. Set environment variables in Render dashboard

### Option C: Fly.io

```bash
# Install flyctl
curl -L https://fly.io/install.sh | sh

# Login
fly auth login

# Launch
fly launch

# Add Postgres
fly postgres create --name dataforge-db
fly postgres connect --app dataforge-db

# Set secrets
fly secrets set GEMINI_API_KEY=your_key
fly secrets set DATABASE_URL=postgres://...

# Deploy
fly deploy
```

### Option D: AWS (Advanced)

```bash
# ECS Fargate
# 1. Push images to ECR
# 2. Create ECS cluster
# 3. Define task definition with:
#    - API container (port 8000)
#    - Web container (port 3000)
#    - Sidecar: TrueForge (port 8790)
# 4. Use RDS for PostgreSQL
# 5. Use AmazonMSK or self-hosted ClickHouse

# Or use AWS App Runner for simpler setup
```

---

## 10. Production Checklist

### Security

- [ ] Change default PostgreSQL password (`dataforge` → strong password)
- [ ] Enable HTTPS (reverse proxy with Let's Encrypt)
- [ ] Set `DATAFORGE_ENV=production`
- [ ] Restrict CORS origins (replace `*` with your domain)
- [ ] Add authentication to API endpoints
- [ ] Encrypt connector passwords at rest
- [ ] Use secrets manager for API keys (not `.env` file)

### Performance

- [ ] Use connection pooling (PgBouncer for PostgreSQL)
- [ ] Set ClickHouse `max_threads` for query performance
- [ ] Enable Redis for session caching (optional)
- [ ] Use CDN for frontend static assets

### Monitoring

- [ ] Add health check endpoint to load balancer
- [ ] Set up alerting for API errors
- [ ] Monitor ClickHouse query performance
- [ ] Track Gemini API usage (free tier limits)

### Reliability

- [ ] Database backups (pg_dump, ClickHouse backups)
- [ ] Auto-restart on crash (systemd, Docker restart policy)
- [ ] Rate limiting on API endpoints
- [ ] Graceful shutdown handling

---

## 11. Troubleshooting

### Common Issues

**"Docker not running"**
```bash
# Start Docker Desktop
open -a Docker
# Wait for it to fully start
docker info
```

**"Port already in use"**
```bash
# Find and kill process on port
lsof -ti:8000 | xargs kill -9
lsof -ti:3000 | xargs kill -9
```

**"ModuleNotFoundError"**
```bash
# Reinstall dependencies
uv sync
cd apps/web && npm install
```

**"ClickHouse connection refused"**
```bash
# Check if ClickHouse is running
docker ps | grep clickhouse
# Restart if needed
docker compose restart clickhouse
```

**"Gemini rate limit exceeded"**
```bash
# Free tier: 20 requests/day
# Wait for reset or upgrade plan
# Check usage: logs will show 429 errors
```

**"TrueForge not connecting"**
```bash
# Check if TrueForge is running
curl http://localhost:8790/api/v1/agents
# If not, start it
npx @truefoundry/trueforge --port 8790
```

**"Schema migration errors"**
```bash
# Auto-applied on startup
# If issues, check PostgreSQL logs
docker compose logs postgres | tail -20
```

### View Logs

```bash
# API logs
docker compose logs -f api

# PostgreSQL logs
docker compose logs -f postgres

# ClickHouse logs
docker compose logs -f clickhouse

# All services
docker compose logs -f
```

### Reset Everything

```bash
# Stop all containers
docker compose down

# Remove volumes (destroys data)
docker compose down -v

# Remove cached dependencies
rm -rf .venv node_modules

# Start fresh
docker compose up -d
uv sync
cd apps/web && npm install && cd ../..
```

---

## Summary Commands

```bash
# One-liner to start everything locally
docker compose up -d postgres clickhouse && uv sync && uv run uvicorn apps.api.app.main:app --port 8000 & cd apps/web && npm run dev & npx @truefoundry/trueforge --port 8790

# Production build
cd apps/web && npm run build && cd ../.. && uv run uvicorn apps.api.app.main:app --host 0.0.0.0 --port 8000 --workers 4

# Docker full stack
docker compose build && docker compose up -d
```
