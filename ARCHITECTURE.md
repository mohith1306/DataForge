# DataForge — Architecture & Full Walkthrough

**Autonomous Data Reliability Engineer**
Detects data pipeline anomalies, investigates root causes with an AI agent, and orchestrates safe remediation with human approval gates.

---

## Table of Contents

1. [System Overview](#1-system-overview)
2. [Repository Structure](#2-repository-structure)
3. [Tech Stack](#3-tech-stack)
4. [Backend Architecture (FastAPI)](#4-backend-architecture-fastapi)
5. [Frontend Architecture (React)](#5-frontend-architecture-react)
6. [Database Layer](#6-database-layer)
7. [Database Connectors System](#7-database-connectors-system)
8. [Background Monitor](#8-background-monitor)
9. [Agent System (LangGraph + TrueForge)](#9-agent-system-langgraph--trueforge)
10. [MCP Servers](#10-mcp-servers)
11. [Sandbox Execution](#11-sandbox-execution)
12. [Risk Classification & Approval](#12-risk-classification--approval)
13. [Incident Lifecycle (End-to-End Flow)](#13-incident-lifecycle-end-to-end-flow)
14. [Configuration](#14-configuration)
15. [Docker Setup](#15-docker-setup)
16. [Testing](#16-testing)
17. [Running the Project](#17-running-the-project)

---

## 1. System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│                        DataForge Architecture                       │
├─────────────────────────────────────────────────────────────────────┤
│                                                                     │
│  ┌──────────┐    ┌──────────────┐    ┌──────────────────────────┐  │
│  │ React UI │───▶│  FastAPI API  │───▶│   Background Monitor     │  │
│  │ (port    │    │  (port 8000)  │    │   (polls every 30s)      │  │
│  │  3000)   │    │              │    │                          │  │
│  └──────────┘    └──────┬───────┘    └──────────┬───────────────┘  │
│                         │                        │                  │
│                         ▼                        ▼                  │
│              ┌──────────────────┐     ┌──────────────────┐         │
│              │   Incident API   │     │  User Databases  │         │
│              │   (CRUD + SSE)   │     │  (CH/PG/Mysql/   │         │
│              └────────┬─────────┘     │   SF/Databricks) │         │
│                       │               └──────────────────┘         │
│                       ▼                                            │
│              ┌──────────────────┐                                  │
│              │  TrueForge Agent │◀── 4 MCP Servers                 │
│              │  (LLM Runtime)   │    (database, pipeline,         │
│              │                  │     github, remediation)         │
│              └────────┬─────────┘                                  │
│                       │                                            │
│              ┌────────▼─────────┐                                  │
│              │  Sandboxed Code  │◀── Python subprocess isolation   │
│              │  Execution       │                                  │
│              └────────┬─────────┘                                  │
│                       │                                            │
│              ┌────────▼─────────┐                                  │
│              │  Human Approval  │◀── HIGH/CRITICAL risk actions    │
│              │  Gate             │                                  │
│              └──────────────────┘                                  │
│                                                                     │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Repository Structure

```
dataforge/
├── apps/
│   ├── api/                    # FastAPI backend
│   │   └── app/
│   │       ├── api/            # Route handlers
│   │       │   ├── incidents.py    # Incident CRUD + investigation
│   │       │   ├── connectors.py   # Database connector lifecycle
│   │       │   ├── database.py     # Schema setup wizard
│   │       │   ├── chaos.py        # Chaos injection triggers
│   │       │   ├── monitor.py      # Background monitor API
│   │       │   ├── events.py       # Incident event history
│   │       │   ├── stream.py       # SSE streaming endpoints
│   │       │   └── health.py       # Health check
│   │       ├── core/
│   │       │   ├── config.py       # Settings (env-driven)
│   │       │   └── logging.py      # Structured logging
│   │       ├── db/
│   │       │   ├── models.py       # SQLAlchemy ORM models
│   │       │   └── session.py      # Engine, migrations, get_db
│   │       ├── schemas/
│   │       │   └── incident.py     # Pydantic request/response models
│   │       └── services/
│   │           ├── monitor.py          # Background anomaly detection
│   │           ├── db_adapter.py       # Database adapter abstraction
│   │           ├── schema_mapping.py   # User schema config
│   │           └── connectors/
│   │               ├── base.py         # DatabaseConnector ABC
│   │               ├── registry.py     # Connector lifecycle mgmt
│   │               ├── clickhouse.py   # ClickHouse connector
│   │               ├── postgres.py     # PostgreSQL connector
│   │               ├── mysql.py        # MySQL connector
│   │               ├── snowflake.py    # Snowflake connector
│   │               └── databricks.py   # Databricks connector
│   └── web/                    # React frontend
│       └── src/
│           ├── App.jsx             # Router & nav
│           ├── api.js              # API client functions
│           ├── pages/
│           │   ├── Connectors.jsx      # Database connection wizard
│           │   ├── Dashboard.jsx       # Per-database health cards
│           │   ├── DatabaseDetail.jsx  # Database detail (3 tabs)
│           │   ├── IncidentDetail.jsx  # Investigation timeline
│           │   └── ChaosLab.jsx        # Chaos injection UI
│           └── components/
│               ├── EvidenceViewer.jsx      # Evidence display
│               ├── RootCausePanel.jsx      # Root cause analysis
│               ├── ApprovalUI.jsx          # Human approval gate
│               └── VerificationUI.jsx      # Post-remediation verify
│
├── agent/                      # AI agent system
│   ├── config.py               # Agent configuration
│   ├── graph/
│   │   ├── graph.py            # Standard LangGraph workflow
│   │   ├── trueforge_graph.py  # TrueForge-powered graph
│   │   ├── state.py            # IncidentState TypedDict
│   │   ├── edges.py            # Transition helpers
│   │   └── nodes/
│   │       ├── classify.py         # LLM incident classification
│   │       ├── investigate.py      # Multi-source evidence collection
│   │       ├── investigate_db.py   # Database investigation wrapper
│   │       ├── sandbox.py          # Sandboxed code analysis
│   │       ├── diagnose.py         # Root cause analysis
│   │       ├── plan.py             # Remediation planning
│   │       ├── approval.py         # Human approval gate
│   │       ├── execute.py          # Remediation execution
│   │       └── verify.py           # Post-fix verification
│   ├── agents/
│   │   ├── database_agent.py   # ClickHouse investigation agent
│   │   └── evidence_merger.py  # Multi-source evidence ranking
│   ├── models/
│   │   └── llm.py              # LLM factory (Gemini)
│   ├── prompts/
│   │   ├── database.py         # DB investigation prompts
│   │   ├── investigation.py    # Coordination prompts
│   │   └── system.py           # System prompts
│   ├── schemas/
│   │   └── evidence.py         # Evidence/root-cause models
│   └── tools/
│       └── risk.py             # Risk classification (LOW/MED/HIGH/CRIT)
│
├── trueforge/                  # TrueForge runtime integration
│   ├── agents.py               # Agent spec (model, MCP, instructions)
│   ├── client.py               # HTTP client for TrueForge API
│   └── runtime.py              # Session/stream management
│
├── mcp_servers/                # Model Context Protocol servers
│   ├── http_server.py          # Unified HTTP MCP server (all tools)
│   ├── database_server.py      # Database MCP tools
│   ├── monitoring_server.py    # Pipeline monitoring MCP tools
│   ├── github_server.py        # GitHub MCP tools
│   └── remediation_server.py   # Remediation MCP tools
│
├── sandbox/
│   └── executor.py             # Isolated Python code execution
│
├── tests/
│   ├── test_e2e.py             # End-to-end lifecycle tests (20 tests)
│   └── test_*.py               # Unit tests per module
│
├── data/                       # Runtime data
│   └── connectors.json         # Persisted connector credentials
│
├── docker-compose.yml          # ClickHouse + PostgreSQL
├── pyproject.toml              # Python dependencies
├── package.json                # Node.js dependencies
└── .env                        # Environment configuration
```

---

## 3. Tech Stack

| Layer | Technology | Why |
|-------|-----------|-----|
| **Frontend** | React + Vite | Fast dev server, modern bundling |
| **Backend** | FastAPI + SQLAlchemy async | Async-first, auto-docs, high performance |
| **Database** | PostgreSQL (incidents) + ClickHouse (monitoring) | PG for structured data, CH for time-series analytics |
| **Agent Runtime** | TrueForge | MCP-native agent orchestration, sandbox, approval |
| **Agent Graph** | LangGraph | State-machine workflow with conditional routing |
| **LLM** | Google Gemini 3.6 Flash | Free tier, fast, good at structured output |
| **MCP Protocol** | HTTP JSON-RPC 2.0 | Standard tool protocol for agent ↔ tools communication |
| **Sandbox** | Python subprocess isolation | Process-level security, resource limits |
| **Containerization** | Docker Compose | One-command database setup |

---

## 4. Backend Architecture (FastAPI)

### API Routers

| Router | Prefix | Purpose |
|--------|--------|---------|
| `health` | `/api/health` | Service health check |
| `incidents` | `/api/incidents` | CRUD + investigation streaming |
| `events` | `/api/events` | Incident event history |
| `stream` | `/api/stream` | SSE event streams |
| `chaos` | `/api/chaos` | Chaos injection triggers |
| `monitor` | `/api/monitor` | Background monitor control |
| `database` | `/api/database` | Schema setup wizard |
| `connectors` | `/api/connectors` | Database connector lifecycle |

### Key Endpoints

```
POST   /api/incidents                    # Create incident
GET    /api/incidents                    # List incidents (filterable)
GET    /api/incidents/{id}               # Get incident detail
POST   /api/incidents/{id}/investigate   # Start TrueForge investigation
POST   /api/incidents/{id}/remediate     # Execute remediation
POST   /api/incidents/{id}/approve       # Approve/deny remediation
GET    /api/incidents/{id}/events        # Event timeline

POST   /api/connectors                  # Add database connector
GET    /api/connectors                  # List connectors
DELETE /api/connectors/{id}             # Remove connector
POST   /api/connectors/{id}/test        # Test connection
POST   /api/connectors/{id}/check       # Run monitoring check
POST   /api/connectors/{id}/inject      # Inject test data

POST   /api/database/setup              # Schema mapping wizard
GET    /api/database/config             # Current DB config
GET    /api/database/schema-example     # Example configs
GET    /api/database/test-connection    # Test adapter connectivity

POST   /api/chaos/trigger               # Inject chaos (pipeline failure)
POST   /api/monitor/start               # Start background monitor
POST   /api/monitor/stop                # Stop background monitor
```

### Lifespan Events

On startup:
1. Run schema migrations (add missing columns)
2. Start background monitor (polls ClickHouse every 30s)
3. Start monitoring for all enabled database connectors

On shutdown:
1. Stop background monitor
2. Stop all connector monitoring loops

---

## 5. Frontend Architecture (React)

### Pages

| Route | Component | Purpose |
|-------|-----------|---------|
| `/` | `Connectors` | Database connection wizard (landing page) |
| `/dashboard` | `Dashboard` | Per-database health cards, stats, incidents |
| `/databases/:id` | `DatabaseDetail` | Database detail with 3 tabs (Overview/Tables/Incidents) |
| `/incidents/:id` | `IncidentDetail` | Investigation timeline, evidence, approval |
| `/chaos` | `ChaosLab` | Chaos injection controls |

### Navigation Flow

```
User lands on / → Connects database → Redirected to /dashboard
                                          │
                    ┌─────────────────────┤
                    ▼                     ▼
            Click database card    Click incident
                    │                     │
                    ▼                     ▼
            /databases/:id         /incidents/:id
            (3 tabs)              (investigation view)
```

### Component Hierarchy

```
App.jsx
├── Nav (Databases | Dashboard | Chaos Lab)
├── Connectors.jsx          # Database connection form
├── Dashboard.jsx           # Per-database cards + global stats
│   └── Per-DB Card
│       ├── Run Check button → live results
│       └── Filtered incidents list
├── DatabaseDetail.jsx      # 3 tabs
│   ├── Overview (check results, stats)
│   ├── Tables (discovered schemas)
│   └── Incidents (filtered by connector_id)
├── IncidentDetail.jsx      # Investigation timeline
│   ├── EvidenceViewer       # Parsed evidence items
│   ├── RootCausePanel       # Parsed root cause + confidence
│   ├── ApprovalUI           # Approve/Deny buttons
│   └── VerificationUI       # Post-fix verification status
└── ChaosLab.jsx            # Inject chaos triggers
```

---

## 6. Database Layer

### PostgreSQL (Incident Storage)

**Tables:**

| Table | Purpose |
|-------|---------|
| `incidents` | Incident records with severity, status, connector_id |
| `incident_events` | Timestamped event log per incident |
| `incident_evidence` | Collected evidence items |
| `incident_approvals` | Approval records |

**Key Columns on `incidents`:**
- `id` (PK), `title`, `description`, `severity`, `status`
- `incident_type` (pipeline_failure, data_quality, freshness_lag)
- `connector_id` (links to database connector)
- `trueforge_session_id` (links to TrueForge investigation)
- `verification_result` (post-remediation outcome)

### ClickHouse (Monitoring Analytics)

**Tables (auto-created by monitor):**

| Table | Purpose |
|-------|---------|
| `pipeline_events` | Pipeline run history (status, timestamps, errors) |
| `revenue_daily` | Business metrics (revenue, orders by region/date) |
| `customer_orders` | Order data with region for quality checks |
| `data_quality_metrics` | Quality check results |

---

## 7. Database Connectors System

### Architecture

```
User → POST /api/connectors → ConnectorRegistry
                                    │
                          ┌─────────┼─────────┐
                          ▼         ▼         ▼
                    ClickHouse  PostgreSQL  MySQL  Snowflake  Databricks
                    Connector   Connector  Conn   Connector  Connector
                          │         │         │         │         │
                          └─────────┼─────────┘─────────┘─────────┘
                                    ▼
                          Auto-Discovery (table scanning + scoring)
                                    ▼
                          Monitoring Query Builder
                                    ▼
                          Background Poll Loop (every N seconds)
                                    ▼
                          Incident Creation (via monitor service)
```

### Connector Base Class (`DatabaseConnector`)

Abstract methods implemented by each connector:
- `connect() → bool` — Test connection
- `disconnect()` — Cleanup
- `list_tables(schema) → list[str]` — List all tables
- `describe_table(table, schema) → list[dict]` — Column metadata
- `execute_query(sql) → list[dict]` — Run read-only query
- `count_rows(table, schema) → int` — Row count
- `get_inject_sql() → list[str]` — SQL to create test data
- `build_monitoring_queries(mapping) → dict` — Generate monitoring SQL

### Auto-Discovery

When a user connects a database:
1. List all tables via `list_tables()`
2. For each table, analyze name + columns against heuristics:
   - **Table name keywords**: `pipeline`, `event`, `log`, `order`, `quality` (weight: 0.3)
   - **Column matches**: `status`, `started_at`, `error_message`, `pipeline_id` (weight: 0.1 each)
3. Score ≥ 0.4 + must have `status` + `started_at` columns → qualifies as pipeline table
4. Generate monitoring queries based on discovered schema

### Supported Databases

| Database | Connection | Monitoring SQL |
|----------|-----------|---------------|
| **ClickHouse** | HTTP interface (port 8123) | `INTERVAL N SECOND`, `countIf()` |
| **PostgreSQL** | asyncpg (port 5432) | `interval 'N seconds'`, `FILTER (WHERE ...)` |
| **MySQL** | aiomysql (port 3306) | `INTERVAL N SECOND`, `SUM(... IS NULL)` |
| **Snowflake** | snowflake-connector-python | `DATEADD(SECOND, -N, CURRENT_TIMESTAMP())` |
| **Databricks** | SQL Warehouse HTTP API | `INTERVAL N HOUR`, Spark SQL syntax |

---

## 8. Background Monitor

### How It Works

```
Every 30 seconds:
  1. Check pipeline_failures query → find recently failed runs
  2. Check pipeline_freshness query → find stale pipelines
  3. Check data_quality query → find null-rate violations

  For each issue found:
    → Create incident via POST /api/incidents
    → If TrueForge enabled → auto-start investigation
```

### Adapter Abstraction

The monitor supports multiple database backends via `MonitorDBAdapter`:

```
ClickHouseAdapter  ──┐
PostgresAdapter    ──┼──▶ create_monitor_adapter() ──▶ Monitor
CustomSQLAdapter   ──┘      (reads MONITOR_DB_TYPE)
```

Configured via environment:
- `MONITOR_DB_TYPE=clickhouse|postgres|custom`
- `MONITOR_DB_URL=postgresql://...` (for postgres)
- `MONITOR_CUSTOM_QUERY_URL=http://...` (for custom)

---

## 9. Agent System (LangGraph + TrueForge)

### Two Graph Variants

**1. Standard LangGraph** (`agent/graph/graph.py`)
- All nodes run locally in Python
- Uses direct LLM calls for classification
- Custom sandbox executor
- Custom approval gate

**2. TrueForge-Powered** (`agent/graph/trueforge_graph.py`)
- Investigation delegated to TrueForge agent runtime
- Agent uses MCP tools directly (not pre-fetched data)
- TrueForge handles sandbox, approval, streaming
- Falls back to standard graph if TrueForge unavailable

### Graph Workflow

```
                    ┌─────────────┐
                    │   CLASSIFY  │  LLM categorizes incident type + severity
                    └──────┬──────┘
                           │
                    ┌──────▼──────┐
              ┌────▶│ INVESTIGATE │◀──┐  Collect evidence from 4 sources
              │     └──────┬──────┘   │  (database, pipeline, github, remediation)
              │            │          │
              │     (if < 3 evidence) │
              │            │          │
              │     ┌──────▼──────┐   │
              │     │   SANDBOX   │   │  Run Python analysis code
              │     └──────┬──────┘   │  in isolated subprocess
              │            │          │
              │     ┌──────▼──────┐   │
              │     │   DIAGNOSE  │   │  LLM root cause analysis
              │     └──────┬──────┘   │
              │            │          │
              │     (if confidence < 0.5)
              │            │          │
              │     ┌──────▼──────┐   │
              │     │    PLAN     │   │  Generate remediation steps
              │     └──────┬──────┘   │
              │            │          │
              │     ┌──────▼──────┐   │
              │     │  APPROVAL   │   │  Human reviews HIGH/CRITICAL actions
              │     └──────┬──────┘   │
              │            │          │
              │     ┌──────▼──────┐   │
              │     │   EXECUTE   │   │  Run remediation via MCP tools
              │     └──────┬──────┘   │
              │            │          │
              │     ┌──────▼──────┐   │
              └─────│   VERIFY    │───┘  Check if incident is resolved
                    └──────┬──────┘
                           │
                      (if resolved)
                           │
                    ┌──────▼──────┐
                    │     END     │
                    └─────────────┘
```

### Node Details

| Node | Input | Output | LLM Call? |
|------|-------|--------|-----------|
| `classify` | incident details | type, severity, category | Yes (Gemini) |
| `investigate` | incident + DB schema | evidence list | No (tool calls) |
| `sandbox` | code + context | analysis results | Yes (code gen) |
| `diagnose` | evidence + analysis | root cause, confidence | Yes (Gemini) |
| `plan` | root cause | remediation steps | Yes (Gemini) |
| `approval` | plan + risk level | approval status | No (human) |
| `execute` | approved plan | execution result | No (tool calls) |
| `verify` | execution result | verification status | Yes (Gemini) |

### State (`IncidentState`)

```python
class IncidentState(TypedDict):
    incident_id: str
    user_request: str
    description: str
    status: str
    events: list[dict]           # Timestamped event log
    evidence: list[dict]         # Collected evidence items
    database_findings: list[dict]
    pipeline_findings: list[dict]
    github_findings: list[dict]
    analysis_results: dict       # Sandbox output
    root_cause: dict             # Diagnosis result
    confidence: float            # 0.0 - 1.0
    remediation_plan: dict       # Proposed actions
    risk_level: str              # LOW/MEDIUM/HIGH/CRITICAL
    approval_required: bool
    approval_status: str         # pending/approved/rejected
    execution_result: dict
    verification_result: dict
    incident_type: str
    severity: str
    business_impact: str
    data_quality_results: dict
```

### TrueForge Integration

**Agent Spec** (`trueforge/agents.py`):
- Model: `google/gemini-3.6-flash`
- MCP Servers: database, pipeline, github, remediation (all 4 enabled)
- Sandbox: enabled
- Dynamic sub-agents: enabled
- Iteration limit: 15
- Approval required for: `rollback_deployment`, `reprocess_partition`, `rerun_pipeline`

**Runtime** (`trueforge/runtime.py`):
- Creates/updates TrueForge agent on startup
- Creates session per incident investigation
- Streams tool call events back to DataForge
- Translates tool results into evidence format

---

## 10. MCP Servers

### Unified HTTP Server (`mcp_servers/http_server.py`)

All 13 tools are served via a single HTTP endpoint (port 8791) using JSON-RPC 2.0:

| Server | Tools |
|--------|-------|
| **dataforge-database** | `list_tables`, `describe_table`, `execute_select`, `profile_column`, `get_recent_records` |
| **dataforge-pipeline** | `get_pipeline_status`, `get_pipeline_runs`, `get_pipeline_logs`, `get_failed_jobs`, `get_metrics` |
| **dataforge-github** | `get_recent_commits`, `get_commit`, `get_pull_request`, `get_changed_files`, `search_commits` |
| **dataforge-remediation** | `rerun_pipeline`, `create_incident_ticket`, `rollback_deployment`, `reprocess_partition`, `validate_data_quality` |

### Tool Execution Flow

```
TrueForge Agent
    │
    ├──▶ MCP Request (JSON-RPC 2.0)
    │        │
    │        ▼
    │    http_server.py (port 8791)
    │        │
    │        ├──▶ database_server.py → ClickHouse HTTP
    │        ├──▶ monitoring_server.py → Pipeline API
    │        ├──▶ github_server.py → GitHub API
    │        └──▶ remediation_server.py → Airflow/Pipeline APIs
    │
    ◀── Tool Response (JSON)
```

---

## 11. Sandbox Execution

### Security Layers

```
Layer 1: Static Validation (defense-in-depth)
    └── Blocked patterns: eval, exec, open, os., subprocess, etc.
    └── Import whitelist: math, json, statistics, datetime, collections, re

Layer 2: Subprocess Isolation
    └── Separate Python process (not thread)
    └── Cannot affect host memory/filesystem

Layer 3: Resource Limits (via resource module)
    └── CPU time: 15 seconds
    └── Memory: 128 MB
    └── Disk: 1 MB
    └── Max processes: 1 (no forking)

Layer 4: Restricted Environment
    └── No network access
    └── Minimal PATH (/usr/bin:/bin)
    └── Temp directory only
    └── No user site directory (-S -s flags)

Layer 5: Timeout Protection
    └── 30-second hard timeout
    └── Process killed on timeout
```

### Execution Flow

```
1. LLM generates Python analysis code
2. Static validation (blocked patterns check)
3. Write sandbox wrapper + user code to temp file
4. Write context to temp file (avoids apostrophe issues)
5. Execute subprocess: python -u -S -s analysis.py
6. Pass user code via stdin
7. Parse JSON result from stdout
8. Return result + output + error + execution_time
```

---

## 12. Risk Classification & Approval

### Risk Levels

| Level | Tools | Approval? |
|-------|-------|-----------|
| **LOW** | `list_tables`, `describe_table`, `execute_select`, `profile_column`, `get_pipeline_status`, `get_recent_commits`, etc. | No |
| **MEDIUM** | `rerun_pipeline`, `create_incident_ticket` | No |
| **HIGH** | `rollback_deployment`, `reprocess_partition` | **Yes** |
| **CRITICAL** | `delete_data`, `modify_schema` | **Yes** (never auto-approved) |

### Unknown Tools

Any tool not in the risk map defaults to **HIGH** risk (conservative approach).

### Approval Flow

```
1. Plan generates remediation actions
2. classify_remediation_risk() checks each action's tool
3. If any action is HIGH or CRITICAL:
   → approval_status = "pending"
   → Graph pauses at approval node
   → UI shows approve/deny buttons
4. Human approves → approval_status = "approved" → execute
5. Human rejects → approval_status = "rejected" → re-investigate
```

### API Approval Endpoint

```
POST /api/incidents/{id}/approve
Body: { "approved": true/false, "note": "optional reason" }
```

---

## 13. Incident Lifecycle (End-to-End Flow)

### Phase 1: Detection

```
Background Monitor (every 30s)
    │
    ├── Check pipeline_failures query
    ├── Check pipeline_freshness query
    └── Check data_quality query
            │
            ▼
    Issue detected → Create incident in PostgreSQL
            │
            ▼
    Auto-start TrueForge investigation (if enabled)
```

### Phase 2: Investigation

```
TrueForge Agent receives incident context
    │
    ├──▶ get_pipeline_status()     → which pipelines are failing
    ├──▶ get_pipeline_logs()       → actual error messages
    ├──▶ list_tables()             → schema check
    ├──▶ profile_column()          → data quality metrics
    ├──▶ get_recent_commits()      → correlate with deployments
    └──▶ validate_data_quality()   → null rates, freshness
            │
            ▼
    Evidence collected → Streamed to UI via SSE
```

### Phase 3: Diagnosis

```
LLM analyzes all evidence
    │
    ├── Temporal correlation (failure after deployment?)
    ├── Data pattern (sudden vs gradual?)
    ├── Dependency chain (upstream/downstream?)
    └── Resource constraint (capacity/permissions?)
            │
            ▼
    Root cause + confidence score
```

### Phase 4: Remediation Planning

```
LLM generates remediation steps
    │
    ├── Step 1: Identify root cause
    ├── Step 2: Propose fix action (tool name + params)
    ├── Step 3: Risk assessment per action
    └── Step 4: Overall risk level
            │
            ▼
    Plan ready → Risk classification
```

### Phase 5: Approval Gate

```
Risk level check:
    │
    ├── LOW/MEDIUM → Auto-approve → Execute
    │
    └── HIGH/CRITICAL → Pause → Human reviews in UI
            │
            ├── Approve → Execute
            └── Reject → Re-investigate
```

### Phase 6: Execution

```
Approved remediation actions
    │
    ├──▶ rollback_deployment()    → via MCP remediation server
    ├──▶ reprocess_partition()    → via MCP remediation server
    └──▶ rerun_pipeline()         → via MCP remediation server
            │
            ▼
    Actions executed → Results captured
```

### Phase 7: Verification

```
LLM checks if incident is resolved
    │
    ├── Re-check pipeline status
    ├── Verify data quality metrics
    └── Compare before/after state
            │
            ├── Resolved → Incident closed
            └── Unresolved → Loop back to investigate
```

---

## 14. Configuration

### Environment Variables (`.env`)

```bash
# Database
DATABASE_URL=postgresql+asyncpg://dataforge:dataforge@localhost:5432/dataforge

# ClickHouse
CLICKHOUSE_HOST=localhost
CLICKHOUSE_PORT=8123
CLICKHOUSE_DATABASE=dataforge

# LLM (Gemini free tier)
GEMINI_API_KEY=your-gemini-api-key
MODEL_NAME=google/gemini-3.6-flash

# TrueForge
TRUEFORGE_URL=http://localhost:8790
TRUEFORGE_ENABLED=true

# Monitor Backend
MONITOR_DB_TYPE=clickhouse   # clickhouse | postgres | custom
# MONITOR_DB_URL=postgresql://...  (for postgres)
# MONITOR_CUSTOM_QUERY_URL=http://...  (for custom)

# App
DATAFORGE_ENV=demo
```

---

## 15. Docker Setup

### Services

```yaml
services:
  postgres:
    image: postgres:16-alpine
    ports: ["5432:5432"]
    environment:
      POSTGRES_USER: dataforge
      POSTGRES_PASSWORD: dataforge
      POSTGRES_DB: dataforge

  clickhouse:
    image: clickhouse/clickhouse-server:latest
    ports: ["8123:8123", "9000:9000"]
    environment:
      CLICKHOUSE_DB: dataforge
```

### Start

```bash
docker compose up -d postgres clickhouse
```

---

## 16. Testing

### End-to-End Tests (`tests/test_e2e.py`)

20 tests across 5 scenarios:

| Scenario | Tests | What It Covers |
|----------|-------|----------------|
| **A: Safe investigation** | 4 | Read-only tools, auto-approval, blocking dangerous actions |
| **B: Denied remediation** | 4 | HIGH risk classification, approval gate, rejection flow |
| **C: Approved remediation** | 4 | Approval flow, execute after approval, full lifecycle |
| **D: Sandbox failure** | 5 | Timeout, import restriction, file access, valid code, empty code |
| **E: Verification failure** | 3 | Unresolved detection, partial resolution |

### Risk Classification Tests

- Known tools return correct risk levels
- Unknown tools default to HIGH
- `classify_remediation_risk()` returns highest risk among actions

### Run Tests

```bash
cd dataforge
.venv/bin/python -m pytest tests/test_e2e.py -v
```

---

## 17. Running the Project

### Prerequisites

- Python 3.14+ (via uv)
- Node.js 18+
- Docker Desktop
- Gemini API key (free tier)

### Quick Start

```bash
# 1. Start databases
docker compose up -d postgres clickhouse

# 2. Install Python dependencies
uv sync

# 3. Install frontend dependencies
cd apps/web && npm install && cd ../..

# 4. Start API server
uvicorn apps.api.app.main:app --host 0.0.0.0 --port 8000 --reload

# 5. Start frontend (in separate terminal)
cd apps/web && npm run dev

# 6. Start TrueForge (in separate terminal)
npx @truefoundry/trueforge --port 8790
```

### Service URLs

| Service | URL |
|---------|-----|
| Frontend | http://localhost:3000 |
| API | http://localhost:8000 |
| API Docs | http://localhost:8000/docs |
| TrueForge | http://localhost:8790 |
| ClickHouse | http://localhost:8123 |
| PostgreSQL | localhost:5432 |

### Demo Flow

1. Open http://localhost:3000
2. Connect a database (ClickHouse on localhost:8123, database: dataforge)
3. Auto-discovery finds `pipeline_events` table
4. Click "Run Check" → detects 3 failures + 5 stale pipelines
5. Incidents appear in dashboard
6. Click incident → investigation timeline shows
7. TrueForge agent investigates using MCP tools
8. Root cause analysis displayed
9. Remediation plan shown with risk level
10. If HIGH risk → approve/deny buttons appear
11. After approval → remediation executed
12. Verification confirms resolution

---

## Design Decisions

### Why TrueForge as Agent Runtime?

TrueForge provides MCP-native agent orchestration with:
- Built-in tool calling and response handling
- Sandbox execution environment
- Human approval checkpoints
- Dynamic sub-agent spawning
- Event streaming for real-time UI updates

DataForge uses TrueForge as the actual runtime — the agent spec enables all 4 MCP servers, sandbox, and dynamic sub-agents. The agent uses MCP tools directly rather than pre-fetched data.

### Why Two Graph Variants?

- **Standard LangGraph**: Works without TrueForge dependency, good for testing
- **TrueForge Graph**: Production path with full agent capabilities

The system auto-detects TrueForge availability and falls back gracefully.

### Why Subprocess Sandbox?

- **Process isolation**: Cannot affect host memory/filesystem
- **Resource limits**: CPU, memory, disk, process count
- **No network**: Prevents data exfiltration
- **Static validation**: Defense-in-depth against dangerous patterns

### Why connector_id on Incidents?

Each incident is tagged with the database connector that detected it. This enables:
- Per-database incident filtering in UI
- Separate incident streams per connected database
- Clean separation when monitoring multiple databases

---

*Generated for DataForge hackathon submission.*
