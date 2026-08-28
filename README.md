# DataForge

**Autonomous Data Reliability Engineer** — Incident-to-Recovery Pipeline

DataForge is an AI-driven data reliability platform that autonomously detects, investigates, diagnoses, and remediates data quality incidents across your data stack. Powered by **TrueForge** as the agent runtime, with MCP tool connectivity and human-in-the-loop approval. Built for the TrueForge hackathon.

## Architecture

```
Incident Alert → Classify → Investigate → Sandbox → Diagnose → Plan → Approve → Execute → Verify
                     │            │           │          │         │         │          │
                     ▼            ▼           ▼          ▼         ▼         ▼          ▼
                  LLM        MCP Tools    LLM Code    LLM Plan   Risk     MCP Tools  DQ Checks
                              (13 tools)  Generation          Check
```

### TrueForge Integration

DataForge uses **TrueForge** as the primary agent runtime:

- **Agent Execution**: TrueForge orchestrates the investigation via LLM + tool calls
- **MCP Tool Connectivity**: Tools exposed via SSE+JSON-RPC protocol on port 8791
- **Human Approval**: TrueForge checkpoints for sensitive actions (rerun, rollback)
- **Sandbox**: Code execution delegated to TrueForge sandbox
- **Subagents**: Dynamic sub-agent spawning for parallel investigation

```
API → TrueForge Runtime → TrueForge Agent (openai/gpt-oss-20b)
                              ↓
                    MCP Servers (port 8791)
                    ├── dataforge-database
                    ├── dataforge-monitoring
                    ├── dataforge-github
                    └── dataforge-remediation
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
| **Phase 7** | TrueForge Integration — agent runtime, MCP HTTP, approval flow | ✅ |

## Tech Stack

- **Backend:** Python 3.14, FastAPI, LangGraph, SQLAlchemy async
- **Frontend:** React 18, Vite, React Router
- **Database:** PostgreSQL (metadata), ClickHouse (analytics)
- **LLM:** Groq (`openai/gpt-oss-20b` — 20B params, tool calling support)
- **Agent Runtime:** TrueForge (local, port 8790)
- **Tools:** MCP protocol via SSE+JSON-RPC (13 tools across 4 servers)
- **Infrastructure:** Docker Compose
- **Testing:** pytest, pytest-asyncio, ruff

## Quick Start

```bash
# 1. Clone
git clone https://github.com/mohith1306/DataForge.git
cd DataForge/dataforge

# 2. Install dependencies
uv sync

# 3. Install TrueForge
npm install
npx @truefoundry/trueforge

# 4. Start infrastructure
docker compose up -d

# 5. Seed ClickHouse
uv run python data/seed/seed_clickhouse.py

# 6. Start MCP server (port 8791)
uv run python -m mcp_servers.http_server

# 7. Start TrueForge (port 8790)
npx @truefoundry/trueforge

# 8. Register MCP servers + agent in TrueForge
# (via TrueForge UI at http://localhost:8790)

# 9. Run API
uv run uvicorn apps.api.app.main:app --reload

# 10. Run frontend (separate terminal)
cd apps/web && npm run dev

# 11. Run demo scenario
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
│   │   ├── trueforge_graph.py  # TrueForge-powered graph
│   │   ├── state.py        # State schema (IncidentState)
│   │   ├── router.py       # Conditional routing
│   │   └── nodes/          # Graph nodes (9 nodes)
│   ├── models/             # LLM configuration
│   ├── prompts/            # LLM prompts
│   ├── schemas/            # Pydantic schemas
│   └── tools/              # Risk classification
├── mcp/                    # MCP tool implementations
│   ├── database/           # ClickHouse tools (client, sql_safety)
│   ├── monitoring/         # Pipeline status tools
│   ├── github/             # GitHub API tools
│   └── remediation/        # Repair action tools
├── mcp_servers/            # MCP server instances
│   ├── http_server.py      # SSE+JSON-RPC server (port 8791)
│   ├── monitoring_server.py
│   ├── github_server.py
│   └── remediation_server.py
├── trueforge/              # TrueForge integration
│   ├── client.py           # Async Python client for TrueForge API
│   ├── runtime.py          # Runtime manager (session, approval)
│   └── agents.py           # Agent spec (model, MCP servers, skills)
├── sandbox/                # Safe code execution
├── skills/                 # TrueForge skills
│   └── dataops-investigator/  # Investigation methodology
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
├── package.json            # TrueForge dependency
└── pyproject.toml
```

## Agents

| Agent | Purpose | Tools |
|-------|---------|-------|
| **Database Agent** | Query ClickHouse for schema, data quality, anomalies | `list_tables`, `describe_table`, `execute_select`, `profile_column` |
| **Pipeline Agent** | Check pipeline status, logs, history | `get_pipeline_status`, `get_pipeline_logs`, `get_failed_jobs` |
| **GitHub Agent** | Review commits, PRs, deployments | `get_recent_commits`, `search_commits`, `get_pull_requests` |
| **Root Cause Agent** | Analyze evidence, identify root cause | LLM analysis with confidence scoring |
| **Remediation Agent** | Plan and execute repairs | LLM planning with risk classification |
| **Data Quality Agent** | Check freshness, completeness, uniqueness, volume | 6 quality checks |
| **Evidence Merger** | Cross-source correlation with temporal validation | 48h proximity window |

### TrueForge Agent Spec

The DataForge investigator runs on TrueForge with:

- **Model:** `openai/gpt-oss-20b` (Groq, tool calling)
- **MCP Servers:** 4 servers (database, monitoring, github, remediation)
- **Skills:** `dataops-investigator` (investigation methodology)
- **Approval:** Required for `rerun_pipeline`, `rollback_deployment`, `create_incident_ticket`
- **Sandbox:** Enabled for code execution
- **Iteration Limit:** 50 turns

## MCP Tools

### Database (read-only)
- `list_tables()` — List all tables in dataforge database
- `describe_table(table)` — Get table schema
- `execute_select(query)` — Safe SELECT queries with row limits
- `profile_column(table, column)` — Column statistics (null rate, distinct, min, max)

### Monitoring (read-only)
- `get_pipeline_status(pipeline_id?)` — All pipeline statuses
- `get_pipeline_logs(pipeline_id, limit)` — Pipeline error logs
- `get_failed_jobs(days)` — Failed jobs in last N days

### GitHub (read-only)
- `get_recent_commits(branch, limit)` — Recent commits
- `search_commits(keyword, limit)` — Search commits by message
- `get_pull_requests(state, limit)` — Pull requests

### Remediation (approval required for write actions)
- `rerun_pipeline(pipeline_id)` — Trigger Airflow DAG rerun
- `rollback_deployment(deployment_id)` — Rollback deployment
- `validate_data_quality()` — Run data quality checks

## API Endpoints

```
GET    /api/health                    — Health check (includes TrueForge status)
GET    /api/incidents/stats           — Aggregate stats
GET    /api/incidents                 — List incidents (filterable)
POST   /api/incidents                 — Create incident
GET    /api/incidents/{id}            — Get incident
POST   /api/incidents/{id}/start      — Start TrueForge investigation
POST   /api/incidents/{id}/remediate  — Execute remediation
POST   /api/incidents/{id}/approval   — Approve/reject (forwards to TrueForge)
GET    /api/incidents/{id}/events     — List events
GET    /api/incidents/{id}/stream     — SSE real-time stream
POST   /api/chaos/{fault_type}        — Inject chaos fault
GET    /api/chaos/faults              — List available faults
```

### TrueForge Investigation Flow

1. `POST /api/incidents/{id}/start` — Creates TrueForge session, starts investigation
2. SSE events stream: `investigation.connecting` → `investigation.session_created` → `agent.message` / `tool.completed` → `investigation.completed`
3. `POST /api/incidents/{id}/approval` — Forwards approval to TrueForge (validates session ownership)

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
# ─── Core ────────────────────────────────────────────────
GROQ_API_KEY=your_groq_key
MODEL_NAME=openai/gpt-oss-20b

# ─── TrueForge ───────────────────────────────────────────
TRUEFORGE_URL=http://localhost:8790
TRUEFORGE_ENABLED=true
MCP_AUTH_TOKEN=your_auth_token  # Required for write tools

# ─── ClickHouse ──────────────────────────────────────────
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_DATABASE=dataforge

# ─── PostgreSQL ──────────────────────────────────────────
POSTGRES_URL=postgresql://user:pass@localhost:5432/dataforge

# ─── GitHub ──────────────────────────────────────────────
GITHUB_REPO=owner/repo
GITHUB_TOKEN=your_token

# ─── Airflow (for pipeline rerun) ────────────────────────
AIRFLOW_URL=http://localhost:8080
AIRFLOW_USERNAME=airflow
AIRFLOW_PASSWORD=airflow

# ─── Kubernetes (for rollback) ───────────────────────────
K8S_ENABLED=true
K8S_NAMESPACE=dataforge
K8S_DEPLOYMENT=dataforge-pipeline

# ─── PagerDuty (for ticketing) ───────────────────────────
PAGERDUTY_ENABLED=true
PAGERDUTY_ROUTING_KEY=your_routing_key

# ─── Jira (for ticketing) ────────────────────────────────
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
| #1 | Phase 2: Data Layer | 16 | 16 |
| #2 | Phase 3: Investigation | 14 | 14 |
| #3 | Phase 4: Agentic Action | 14 | 14 |
| #4 | Phase 5: Product UI | 13 | 13 |
| #5 | Phase 6: Polish | — | — |
| #7 | TrueForge Integration | 10 | 10 |

## License

MIT
