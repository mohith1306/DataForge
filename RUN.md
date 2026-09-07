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
cd /Users/mohith/DataForge/dataforge
uv run python data/seed/seed_clickhouse.py
```

## 4. Run Database Migrations

```bash
cd /Users/mohith/DataForge/dataforge
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
cd /Users/mohith/DataForge/dataforge/apps/web
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
cd /Users/mohith/DataForge/dataforge/apps/web
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

## Enterprise API Endpoints

Once the API is running, these enterprise endpoints are available:

### Authentication
```bash
# Create API key
curl -X POST http://localhost:8000/api/auth/api-keys \
  -H "Content-Type: application/json" \
  -d '{"name": "test-key", "scopes": ["read", "write", "admin"]}'
```

### AI Agents
```bash
# Classify risk
curl -X POST http://localhost:8000/api/ai/risk/classify \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"action_type": "database_migration", "target": "production"}'
```

### Reliability Graph
```bash
# Get full graph
curl -H "X-API-Key: YOUR_API_KEY" http://localhost:8000/api/graph/full
```

### Metadata Engine
```bash
# Discover schema
curl -X POST http://localhost:8000/api/metadata/schemas/discover \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"name": "users", "source_id": "pg_prod", "data": [{"id": 1, "name": "Alice"}]}'
```

### Intelligence
```bash
# Calculate blast radius
curl -X POST http://localhost:8000/api/intelligence/blast-radius \
  -H "Content-Type: application/json" \
  -H "X-API-Key: YOUR_API_KEY" \
  -d '{"incident": {"id": "inc1", "affected_services": ["api"]}}'
```

---

## Running Tests

### All Tests (146 tests)
```bash
cd /Users/mohith/DataForge/dataforge
uv run pytest tests/ -v
```

### By Phase
```bash
# Phase 1: Auth + Graph (14 tests)
uv run pytest tests/test_auth.py tests/test_reliability_graph.py -v

# Phase 2: Agents + Policy (26 tests)
uv run pytest tests/test_agents.py tests/test_policy.py -v

# Phase 3: Execution + Verification + Memory (33 tests)
uv run pytest tests/test_execution.py tests/test_verification.py tests/test_memory.py -v

# Phase 4: Metadata + Intelligence (25 tests)
uv run pytest tests/test_metadata.py tests/test_intelligence.py -v

# Phase 5: Gateway (26 tests)
uv run pytest tests/test_gateway.py -v
```

### By Category
```bash
# Integration tests (7 tests)
uv run pytest tests/test_integration.py -v

# Runtime/Performance tests (15 tests)
uv run pytest tests/test_runtime.py -v
```

### With Coverage
```bash
uv run pytest tests/ --cov=apps --cov-report=html
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

## Environment Variables

Create a `.env` file in the dataforge directory:

```bash
# Database
DATABASE_URL=postgresql+asyncpg://dataforge:dataforge@localhost:5432/dataforge

# ClickHouse
CLICKHOUSE_URL=http://localhost:8123
CLICKHOUSE_DATABASE=dataforge

# TrueForge
TRUEFORGE_URL=http://localhost:8790

# API
API_HOST=0.0.0.0
API_PORT=8000
SECRET_KEY=your-secret-key-here
```

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

### API starts but enterprise endpoints return 401
- Create an API key first: `POST /api/auth/api-keys`
- Include `X-API-Key` header in requests

### Rate limiting returns 429
- Check `X-RateLimit-Remaining` header
- Wait for `Retry-After` seconds or `X-RateLimit-Reset` timestamp
