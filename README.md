# DataForge

**Autonomous Data Reliability Engineer** — Incident-to-Recovery Pipeline

DataForge is an AI-driven data reliability platform that autonomously detects, investigates, diagnoses, and remediates data quality incidents across your data stack. Built for the TrueForge hackathon.

## Architecture

```
Incident Alert → Classify → Investigate → Sandbox Analysis → Diagnose → Plan → Execute → Verify
                     │            │              │              │          │         │
                     ▼            ▼              ▼              ▼          ▼         ▼
                  LLM         MCP Tools     Python Code    LLM Plan   MCP Tools  DQ Checks
```

### 6-Phase Pipeline

| Phase | Description | Status |
|-------|-------------|--------|
| **Phase 1** | Foundation — monorepo, FastAPI, React, Docker, LangGraph | ✅ |
| **Phase 2** | Data Layer — ClickHouse, seed data, SQL safety, Database Agent | ✅ |
| **Phase 3** | Investigation — Pipeline/GitHub MCP, cross-source correlation | ✅ |
| **Phase 4** | Agentic Action — sandbox, DQ checks, remediation, verification | ✅ |
| **Phase 5** | Product UI — dashboard, incident timeline, chaos lab | 🔜 |
| **Phase 6** | Polish — deployment, monitoring, documentation | 🔜 |

## Tech Stack

- **Backend:** Python 3.14, FastAPI, LangGraph
- **Frontend:** React 19, Vite, Tailwind CSS
- **Database:** PostgreSQL (metadata), ClickHouse (analytics)
- **LLM:** Groq (Llama 3.3 70B)
- **Tools:** MCP protocol (Database, Monitoring, GitHub, Remediation)
- **Infrastructure:** Docker Compose

## Quick Start

```bash
# 1. Clone
git clone https://github.com/mohith1306/DataForge.git
cd DataForge/dataforge

# 2. Install dependencies
uv sync

# 3. Start infrastructure
docker compose up -d

# 4. Seed ClickHouse
uv run python data/seed/seed_clickhouse.py

# 5. Run API
uv run uvicorn apps.api.app.main:app --reload

# 6. Run frontend (separate terminal)
cd apps/web && npm run dev
```

## Project Structure

```
dataforge/
├── agent/                  # AI agents and graph
│   ├── agents/             # Specialized agents
│   │   ├── database_agent.py
│   │   ├── pipeline_agent.py
│   │   ├── github_agent.py
│   │   ├── root_cause_agent.py
│   │   ├── remediation_agent.py
│   │   ├── data_quality_agent.py
│   │   └── evidence_merger.py
│   ├── graph/              # LangGraph workflow
│   │   ├── graph.py        # Graph definition
│   │   ├── state.py        # State schema
│   │   └── nodes/          # Graph nodes
│   └── prompts/            # LLM prompts
├── mcp/                    # MCP tool servers
│   ├── database/           # ClickHouse tools
│   ├── monitoring/         # Pipeline status tools
│   ├── github/             # GitHub API tools
│   └── remediation/        # Repair action tools
├── sandbox/                # Safe code execution
├── apps/
│   ├── api/                # FastAPI backend
│   └── web/                # React frontend
├── infrastructure/
│   ├── postgres/           # PostgreSQL init
│   └── clickhouse/         # ClickHouse config
├── docker-compose.yml
└── pyproject.toml
```

## Agents

| Agent | Purpose | Tools |
|-------|---------|-------|
| **Database Agent** | Query ClickHouse for schema, data quality, anomalies | `query_schema`, `profile_column`, `execute_select` |
| **Pipeline Agent** | Check pipeline status, logs, history | `get_pipeline_status`, `get_pipeline_logs` |
| **GitHub Agent** | Review commits, PRs, deployments | `get_commits`, `search_code`, `get_pr_files` |
| **Root Cause Agent** | Analyze evidence, identify root cause | LLM analysis |
| **Remediation Agent** | Plan and execute repairs | `rerun_pipeline`, `reprocess_partition` |
| **Data Quality Agent** | Check freshness, completeness, uniqueness, volume | 6 quality checks |

## MCP Tools

### Database
- `query_schema(table)` — Get table schema
- `profile_column(table, column)` — Column statistics
- `execute_select(sql)` — Safe SELECT queries

### Monitoring
- `get_pipeline_status()` — All pipeline statuses
- `get_pipeline_logs(pipeline_id, limit)` — Pipeline logs

### GitHub
- `get_commits(repo, since, sha)` — Recent commits
- `search_code(repo, query)` — Search code changes
- `get_pr_files(pr_number)` — Files changed in PR

### Remediation
- `rerun_pipeline(pipeline_id)` — Trigger re-execution
- `reprocess_partition(table, date)` — Reprocess data partition
- `validate_schema(table, expected)` — Schema validation
- `backfill_missing(table, date_range)` — Fill missing data
- `notify_stakeholders(incident, action)` — Send notifications

## API Endpoints

```
GET    /api/health              — Health check
GET    /api/incidents           — List incidents
POST   /api/incidents           — Create incident
GET    /api/incidents/{id}      — Get incident
POST   /api/incidents/{id}/start — Start investigation
POST   /api/incidents/{id}/remediate — Execute remediation
POST   /api/chaos/{fault_type}  — Inject chaos fault
```

## Chaos Engineering

DataForge includes a chaos lab for testing incident response:

| Fault Type | Description |
|------------|-------------|
| `schema_drift` | Add unexpected columns |
| `null_injection` | Inject null values |
| `volume_drop` | Simulate data volume drop |
| `duplicate_injection` | Insert duplicate records |
| `freshness_lag` | Delay data ingestion |
| `distribution_shift` | Shift data distribution |
| `pipeline_failure` | Force pipeline failure |

## Environment Variables

```bash
# Required
GROQ_API_KEY=your_groq_key

# Optional
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_DATABASE=dataforge
POSTGRES_URL=postgresql://user:pass@localhost:5432/dataforge
```

## License

MIT
