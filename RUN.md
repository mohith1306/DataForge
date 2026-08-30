# DataForge — Run Guide

## Prerequisites

- Python 3.14+ (`uv` package manager)
- Node.js 18+ (for web UI)
- Docker (for Postgres + ClickHouse)
- TrueForge CLI (`npx @truefoundry/trueforge`)

---

## 1. Start Infrastructure (Postgres + ClickHouse)

```bash
cd /Users/mohith/DataForge/dataforge
docker compose up -d postgres clickhouse
```

Wait for both to be healthy:

```bash
docker compose ps
```

## 2. Initialize ClickHouse Schema

```bash
docker compose exec clickhouse clickhouse-client --database dataforge --multiquery < infrastructure/clickhouse/init.sql
```

## 3. Seed ClickHouse Demo Data

```bash
uv run python data/seed/seed_clickhouse.py
```

## 4. Run Database Migrations

```bash
uv run python -c "
import asyncio
from apps.api.app.db.session import ensure_schema
asyncio.run(ensure_schema())
print('Migrations complete')
"
```

## 5. Start MCP Server (port 8791)

```bash
cd /Users/mohith/DataForge/dataforge
uv run python mcp_servers/http_server.py
```

## 6. Start TrueForge (port 8790)

```bash
cd /Users/mohith/DataForge/dataforge
npx @truefoundry/trueforge --port 8790
```

### Configure TrueForge Providers (one-time setup)

In a separate terminal, after TrueForge starts:

```bash
# Create Groq model provider
curl -s -X POST http://localhost:8790/api/v1/settings/model-providers \
  -H "Content-Type: application/json" \
  -d '{
    "manifest": {
      "type": "custom",
      "name": "groq",
      "base_url": "https://api.groq.com/openai/v1",
      "auth": {
        "api_key": "YOUR_GROQ_API_KEY"
      },
      "models": [
        {"model_id": "openai/gpt-oss-20b", "name": "gpt-oss-20b", "properties": {"context_length": 32768, "max_output_tokens": 4096}},
        {"model_id": "llama-3.3-70b-versatile", "name": "llama-3.3-70b-versatile", "properties": {"context_length": 128000, "max_output_tokens": 32768}}
      ]
    }
  }'

# Register MCP servers
for name in dataforge-database dataforge-monitoring dataforge-github dataforge-remediation; do
  curl -s -X POST http://localhost:8790/api/v1/settings/mcp-servers \
    -H "Content-Type: application/json" \
    -d "{\"manifest\":{\"type\":\"remote\",\"name\":\"$name\",\"url\":\"http://localhost:8791/sse\",\"description\":\"DataForge MCP: $name\"}}"
done
```

## 7. Start DataForge API (port 8000)

```bash
cd /Users/mohith/DataForge/dataforge
uv run uvicorn apps.api.app.main:app --host 0.0.0.0 --port 8000 --reload
```

## 8. Start Web UI (port 3000)

```bash
cd /Users/mohith/DataForge/dataforge
npm install
npm run dev
```

---

## Quick Start (All Services)

Open 4 terminals and run:

```bash
# Terminal 1 — Infrastructure
cd /Users/mohith/DataForge/dataforge
docker compose up -d postgres clickhouse

# Terminal 2 — MCP Server
cd /Users/mohith/DataForge/dataforge
uv run python mcp_servers/http_server.py

# Terminal 3 — TrueForge
cd /Users/mohith/DataForge/dataforge
npx @truefoundry/trueforge --port 8790

# Terminal 4 — API + Web UI
cd /Users/mohith/DataForge/dataforge
uv run uvicorn apps.api.app.main:app --host 0.0.0.0 --port 8000 --reload
# Then in another terminal:
cd /Users/mohith/DataForge/dataforge
npm run dev
```

---

## Verify All Services

```bash
# Postgres
docker compose exec postgres psql -U dataforge -d dataforge -c "SELECT 1;"

# ClickHouse
curl -s "http://localhost:8123/?query=SELECT+1"

# MCP Server
curl -s http://localhost:8791/health

# TrueForge
curl -s http://localhost:8790/api/v1/capabilities

# DataForge API
curl -s http://localhost:8000/health

# Web UI
open http://localhost:3000
```

---

## Ports

| Service       | Port  |
|---------------|-------|
| Postgres      | 5432  |
| ClickHouse    | 8123  |
| MCP Server    | 8791  |
| TrueForge     | 8790  |
| DataForge API | 8000  |
| Web UI        | 3000  |

---

## Troubleshooting

### TrueForge agent creation fails
- Ensure Groq provider is configured (step 6)
- Ensure MCP servers are registered with `/sse` path
- Delete stale agents: check `http://localhost:8790/api/v1/agents`

### MCP server connection fails
- Ensure MCP server is running on port 8791
- Verify URL includes `/sse` suffix
- Test: `curl -s -N http://localhost:8791/sse` should stream events

### reasoning_content error
- Patch `node_modules/@truefoundry/trueforge-core/dist/core/llm/VercelAILLM.mjs`
- See `buildStreamTextArgs` function — strip `reasoning_content` and `thinking_blocks` from assistant messages

### Database connection errors
- Ensure Docker containers are running: `docker compose ps`
- Check `.env` for correct `DATABASE_URL`

### ClickHouse seed fails
- Ensure ClickHouse is healthy: `curl http://localhost:8123/?query=SELECT+1`
- Re-run: `uv run python data/seed/seed_clickhouse.py`
