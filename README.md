# DataForge

**Autonomous Data Reliability Engineer** — Incident-to-Recovery Pipeline

DataForge is an AI-driven data reliability platform that autonomously detects, investigates, diagnoses, and remediates data quality incidents across your data stack. Built for the TrueForge hackathon.

## Architecture

```
Incident Alert → Classify → Investigate → Sandbox → Diagnose → Plan → Approve → Execute → Verify
                     │            │           │          │         │         │          │
                     ▼            ▼           ▼          ▼         ▼         ▼          ▼
                  LLM         MCP Tools   LLM Code   LLM Plan   Risk     MCP Tools  DQ Checks
                              (5 tools)   Generation          Check
```

### 6-Phase Pipeline

| Phase | Description | Status |
|-------|-------------|--------|
| **Phase 1** | Foundation — monorepo, FastAPI, React, Docker, LangGraph | ✅ |
| **Phase 2** | Data Layer — ClickHouse, seed data, SQL safety, Database Agent | ✅ |
| **Phase 3** | Investigation — Pipeline/GitHub MCP, cross-source correlation | ✅ |
| **Phase 4** | Agentic Action — sandbox, DQ checks, remediation, verification | ✅ |
| **Phase 5** | Product UI — dashboard, incident detail, chaos lab, SSE streaming | ✅ |
| **Phase 6** | Polish — tests, demo scenario, security checks | ✅ |

## Tech Stack

- **Backend:** Python 3.14, FastAPI, LangGraph, SQLAlchemy async
- **Frontend:** React 18, Vite, React Router
- **Database:** PostgreSQL (metadata), ClickHouse (analytics)
- **LLM:** Groq (Llama 3.3 70B, 128K context)
- **Tools:** MCP protocol (Database, Monitoring, GitHub, Remediation)
- **Infrastructure:** Docker Compose
- **Testing:** pytest, pytest-asyncio, ruff

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

# 7. Run demo scenario
uv run python scripts/demo_scenario.py
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
│   │   ├── state.py        # State schema (IncidentState)
│   │   ├── router.py       # Conditional routing
│   │   └── nodes/          # Graph nodes (9 nodes)
│   ├── models/             # LLM configuration
│   ├── prompts/            # LLM prompts
│   ├── schemas/            # Pydantic schemas
│   └── tools/              # Risk classification
├── mcp/                    # MCP tool servers
│   ├── database/           # ClickHouse tools (client, sql_safety)
│   ├── monitoring/         # Pipeline status tools
│   ├── github/             # GitHub API tools
│   └── remediation/        # Repair action tools
├── sandbox/                # Safe code execution
├── apps/
│   ├── api/                # FastAPI backend
│   │   ├── api/            # Route handlers (6 routers)
│   │   ├── core/           # Config, logging
│   │   ├── db/             # SQLAlchemy models
│   │   └── schemas/        # Request/response schemas
│   └── web/                # React frontend
│       ├── src/
│       │   ├── pages/      # Dashboard, IncidentDetail, ChaosLab
│       │   ├── components/ # AgentTimeline, EvidenceViewer, etc.
│       │   └── api.js      # API client
│       └── package.json
├── tests/                  # Unit tests (47 tests)
├── scripts/                # Demo & security scripts
├── data/seed/              # ClickHouse seed data
├── infrastructure/         # Docker configs
├── docker-compose.yml
└── pyproject.toml
```

## Agents

| Agent | Purpose | Tools |
|-------|---------|-------|
| **Database Agent** | Query ClickHouse for schema, data quality, anomalies | `query_schema`, `profile_column`, `execute_select` |
| **Pipeline Agent** | Check pipeline status, logs, history | `get_pipeline_status`, `get_pipeline_logs` |
| **GitHub Agent** | Review commits, PRs, deployments | `get_commits`, `search_code`, `get_pr_files` |
| **Root Cause Agent** | Analyze evidence, identify root cause | LLM analysis with confidence scoring |
| **Remediation Agent** | Plan and execute repairs | LLM planning with risk classification |
| **Data Quality Agent** | Check freshness, completeness, uniqueness, volume | 6 quality checks |
| **Evidence Merger** | Cross-source correlation with temporal validation | 48h proximity window |

## MCP Tools

### Database
- `query_schema(table)` — Get table schema
- `profile_column(table, column)` — Column statistics
- `execute_select(sql)` — Safe SELECT queries with row limits

### Monitoring
- `get_pipeline_status()` — All pipeline statuses (argMax)
- `get_pipeline_logs(pipeline_id, limit)` — Pipeline logs

### GitHub
- `get_commits(repo, since, sha)` — Recent commits with auth headers
- `search_code(repo, query)` — Search code changes
- `get_pr_files(pr_number)` — Files changed in PR (paginated)

### Remediation
- `rerun_pipeline(pipeline_id)` — Trigger real Airflow DAG rerun (or ClickHouse fallback)
- `reprocess_partition(table, date)` — Reprocess data partition (real ALTER TABLE)
- `validate_schema(table, expected)` — Schema validation
- `backfill_missing(table, date_range)` — Fill missing data
- `notify_stakeholders(incident, action)` — Send notifications
- `rollback_deployment(deployment_id)` — Real Kubernetes rollout restart
- `create_incident_ticket(title, description)` — Real PagerDuty/Jira ticket creation

## API Endpoints

```
GET    /api/health                    — Health check
GET    /api/incidents/stats           — Aggregate stats
GET    /api/incidents                 — List incidents (filterable)
POST   /api/incidents                 — Create incident
GET    /api/incidents/{id}            — Get incident
POST   /api/incidents/{id}/start      — Start investigation
POST   /api/incidents/{id}/remediate  — Execute remediation
POST   /api/incidents/{id}/approval   — Approve/reject plan
GET    /api/incidents/{id}/events     — List events
GET    /api/incidents/{id}/stream     — SSE real-time stream
POST   /api/chaos/{fault_type}        — Inject chaos fault
GET    /api/chaos/faults              — List available faults
```

## Chaos Engineering

DataForge includes a chaos lab for testing incident response:

| Fault Type | Description | Severity |
|------------|-------------|----------|
| `schema_drift` | Add unexpected columns | HIGH |
| `null_injection` | Inject null values | MEDIUM |
| `volume_drop` | Simulate data volume drop | HIGH |
| `duplicate_injection` | Insert duplicate records | MEDIUM |
| `freshness_lag` | Delay data ingestion | LOW |
| `distribution_shift` | Shift data distribution | HIGH |
| `pipeline_failure` | Force pipeline failure | CRITICAL |

## Testing

```bash
# Run all unit tests
uv run pytest tests/ -v

# Run specific test file
uv run pytest tests/test_risk.py -v

# Run integration tests (requires Postgres)
uv run pytest tests/test_api.py -v

# Run security check
uv run python scripts/security_check.py
```

### Test Coverage

| Module | Tests | Coverage |
|--------|-------|----------|
| Graph routing | 7 | State transitions, routing logic |
| Risk classification | 12 | Tool risk levels, approval requirements |
| Sandbox execution | 10 | Code execution, security, timeouts |
| SQL safety | 11 | Query validation, injection prevention |
| API endpoints | 7 | CRUD, chaos, stats (integration) |

## Environment Variables

```bash
# Required
GROQ_API_KEY=your_groq_key

# ClickHouse
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_DATABASE=dataforge

# PostgreSQL
POSTGRES_URL=postgresql://user:pass@localhost:5432/dataforge

# GitHub
GITHUB_REPO=owner/repo
GITHUB_TOKEN=your_token

# Airflow (for pipeline rerun)
AIRFLOW_URL=http://localhost:8080
AIRFLOW_USERNAME=airflow
AIRFLOW_PASSWORD=airflow

# Kubernetes (for rollback)
K8S_ENABLED=true
K8S_NAMESPACE=dataforge
K8S_DEPLOYMENT=dataforge-pipeline

# PagerDuty (for ticketing)
PAGERDUTY_ENABLED=true
PAGERDUTY_ROUTING_KEY=your_routing_key

# Jira (for ticketing)
JIRA_ENABLED=true
JIRA_URL=https://your-org.atlassian.net
JIRA_EMAIL=you@company.com
JIRA_API_TOKEN=your_token
JIRA_PROJECT=DATA
```

## Qodo Code Review

DataForge uses Qodo for automated code review on every PR. PRs are reviewed for:
- Correctness bugs
- Security vulnerabilities
- Code quality issues
- Best practices

### PR History

| PR | Phase | Bugs Found | Bugs Fixed |
|----|-------|------------|------------|
| #1 | Phase 1: Foundation | — | — |
| #2 | Phase 2: Data Layer | 16 | 16 |
| #3 | Phase 3: Investigation | 14 | 14 |
| #4 | Phase 4: Agentic Action | 14 | 14 |
| #5 | Phase 5: Product UI | 13 | 13 |
| #6 | Phase 6: Polish | — | — |

## License

MIT
