"""MCP HTTP Server — exposes DataForge MCP tools via SSE for TrueForge.

Implements the official MCP SSE transport protocol:
- GET /sse → SSE stream that sends `event: endpoint` with session URL
- POST /messages → receives JSON-RPC messages, responds 202, sends results via SSE
"""

import asyncio
import json
import logging
import os
import re
import uuid
from typing import Any

import httpx
from fastapi import FastAPI, Request, Response
from fastapi.responses import StreamingResponse

logger = logging.getLogger(__name__)

CLICKHOUSE_HOST = os.getenv("CLICKHOUSE_HOST", "localhost")
CLICKHOUSE_PORT = int(os.getenv("CLICKHOUSE_PORT", "8123"))
CLICKHOUSE_DB = os.getenv("CLICKHOUSE_DATABASE", "dataforge")
CLICKHOUSE_URL = f"http://{CLICKHOUSE_HOST}:{CLICKHOUSE_PORT}"

AIRFLOW_URL = os.getenv("AIRFLOW_URL", "http://localhost:8080")
AIRFLOW_USERNAME = os.getenv("AIRFLOW_USERNAME", "airflow")
AIRFLOW_PASSWORD = os.getenv("AIRFLOW_PASSWORD", "airflow")

GITHUB_API = "https://api.github.com"
REPO = os.getenv("GITHUB_REPO", "mohith1306/DataForge")

# Bug 7 fix: require auth token for write tools
MCP_AUTH_TOKEN = os.getenv("MCP_AUTH_TOKEN", "")

# Gap 9: Demo mode — remediation targets controlled resources
DATAFORGE_ENV = os.getenv("DATAFORGE_ENV", "demo")

WRITE_TOOLS = {"rerun_pipeline", "rollback_deployment", "create_incident_ticket"}

# Max characters per tool response to prevent context overflow
MAX_RESPONSE_CHARS = 2000

IDENTIFIER_PATTERN = re.compile(r"^[a-zA-Z_][a-zA-Z0-9_-]*$")

app = FastAPI(title="DataForge MCP Server")

_sessions: dict[str, dict[str, Any]] = {}


def _validate_identifier(name: str) -> str:
    if not name or not IDENTIFIER_PATTERN.match(name):
        raise ValueError(f"Invalid identifier: {name!r}")
    return name


async def _query(sql: str) -> list[dict]:
    async with httpx.AsyncClient(timeout=60) as client:
        resp = await client.post(
            f"{CLICKHOUSE_URL}/",
            params={"database": CLICKHOUSE_DB, "default_format": "JSONEachRow"},
            content=sql,
        )
        if resp.status_code != 200:
            raise RuntimeError(f"ClickHouse query failed ({resp.status_code}): {resp.text}")
        text = resp.text.strip()
        if not text:
            return []
        return [json.loads(line) for line in text.split("\n") if line.strip()]


def _get_github_headers() -> dict:
    headers = {"Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN") or os.environ.get("GH_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    return headers


# ─── Tool Definitions ─────────────────────────────────────────────────────────

TOOLS = [
    {
        "name": "list_tables",
        "description": "List all tables in the database",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "describe_table",
        "description": "Get the schema and columns of a table",
        "inputSchema": {
            "type": "object",
            "properties": {"table": {"type": "string", "description": "Table name"}},
            "required": ["table"],
        },
    },
    {
        "name": "execute_select",
        "description": "Execute a read-only SELECT query on the database",
        "inputSchema": {
            "type": "object",
            "properties": {"query": {"type": "string", "description": "SQL SELECT query"}},
            "required": ["query"],
        },
    },
    {
        "name": "get_pipeline_status",
        "description": "Get status of all data pipelines. No args needed.",
        "inputSchema": {"type": "object", "properties": {}},
    },
    {
        "name": "get_pipeline_logs",
        "description": "Get error logs for a specific pipeline",
        "inputSchema": {
            "type": "object",
            "properties": {
                "pipeline_id": {"type": "string", "description": "Pipeline ID"},
            },
            "required": ["pipeline_id"],
        },
    },
    {
        "name": "get_recent_commits",
        "description": "Get recent git commits from the repository",
        "inputSchema": {
            "type": "object",
            "properties": {
                "limit": {"type": "integer", "default": 10},
            },
        },
    },
]


# ─── Tool Execution ───────────────────────────────────────────────────────────

async def execute_tool(name: str, args: dict) -> Any:
    if name == "list_tables":
        rows = await _query(f"SHOW TABLES FROM {CLICKHOUSE_DB}")
        return [{"name": row.get("name", "")} for row in rows]

    elif name == "describe_table":
        tbl_name = args.get("table") or args.get("table_name") or args.get("name")
        if not tbl_name:
            available = [r.get("name", "") for r in await _query(f"SHOW TABLES FROM {CLICKHOUSE_DB}")]
            raise ValueError(
                f"Missing required parameter 'table'. "
                f"Available tables in {CLICKHOUSE_DB}: {available}"
            )
        tbl = _validate_identifier(tbl_name)
        try:
            rows = await _query(f"DESCRIBE TABLE {CLICKHOUSE_DB}.{tbl}")
        except RuntimeError as e:
            available = [r.get("name", "") for r in await _query(f"SHOW TABLES FROM {CLICKHOUSE_DB}")]
            raise ValueError(
                f"Table '{tbl}' not found in {CLICKHOUSE_DB}. "
                f"Available tables: {available}"
            ) from e
        return {"table": tbl, "columns": rows}

    elif name == "execute_select":
        q = (args.get("query") or args.get("sql") or "").strip()
        if not q:
            raise ValueError("Missing required parameter 'query'")
        if not q.upper().startswith("SELECT"):
            raise ValueError("Only SELECT queries are allowed")
        if "LIMIT" not in q.upper():
            q += " LIMIT 1000"
        return await _query(q)

    elif name == "profile_column":
        tbl_name = args.get("table") or args.get("table_name") or ""
        col_name = args.get("column") or args.get("column_name") or ""
        if not tbl_name or not col_name:
            raise ValueError(f"Missing required parameters. Got table={tbl_name!r}, column={col_name!r}")
        tbl = _validate_identifier(tbl_name)
        col = _validate_identifier(col_name)
        sql = (
            f"SELECT count() as total_rows, countIf({col} IS NULL) as null_count, "
            f"round(countIf({col} IS NULL) / count(), 4) as null_rate, "
            f"uniq({col}) as distinct_count, "
            f"min(CAST({col} AS String)) as min_val, "
            f"max(CAST({col} AS String)) as max_val "
            f"FROM {CLICKHOUSE_DB}.{tbl}"
        )
        rows = await _query(sql)
        return {"table": tbl, "column": col, "stats": rows[0] if rows else {}}

    elif name == "get_pipeline_status":
        pid = args.get("pipeline_id")
        if pid:
            pid_clean = _validate_identifier(pid)
            sql = (
                f"SELECT pipeline_id, pipeline_name, status, "
                f"started_at, completed_at, error_message, "
                f"rows_processed FROM {CLICKHOUSE_DB}.pipeline_events "
                f"WHERE pipeline_id = '{pid_clean}' "
                f"ORDER BY started_at DESC LIMIT 1"
            )
        else:
            sql = (
                f"SELECT pipeline_id, pipeline_name, status, started_at, error_message "
                f"FROM {CLICKHOUSE_DB}.pipeline_events "
                f"WHERE (pipeline_id, started_at) IN "
                f"(SELECT pipeline_id, max(started_at) FROM {CLICKHOUSE_DB}.pipeline_events GROUP BY pipeline_id) "
                f"ORDER BY started_at DESC"
            )
        rows = await _query(sql)
        return {"pipelines": rows, "count": len(rows)}

    elif name == "get_pipeline_logs":
        pid_val = args.get("pipeline_id") or args.get("pipeline") or ""
        if not pid_val:
            raise ValueError("Missing required parameter 'pipeline_id'")
        pid = _validate_identifier(pid_val)
        limit = args.get("limit", 50)
        sql = (
            f"SELECT pipeline_id, pipeline_name, status, started_at, error_message "
            f"FROM {CLICKHOUSE_DB}.pipeline_events "
            f"WHERE pipeline_id = '{pid}' AND status = 'FAILED' "
            f"ORDER BY started_at DESC LIMIT {limit}"
        )
        rows = await _query(sql)
        return {"pipeline_id": pid, "error_logs": rows, "count": len(rows)}

    elif name == "get_failed_jobs":
        days = args.get("days", 7)
        sql = (
            f"SELECT pipeline_id, pipeline_name, status, started_at, error_message "
            f"FROM {CLICKHOUSE_DB}.pipeline_events "
            f"WHERE status = 'FAILED' AND started_at >= now() - INTERVAL {days} DAY "
            f"ORDER BY started_at DESC"
        )
        rows = await _query(sql)
        return {"failed_jobs": rows, "count": len(rows)}

    elif name == "get_recent_commits":
        branch = args.get("branch", "main")
        limit = args.get("limit", 20)
        url = f"{GITHUB_API}/repos/{REPO}/commits"
        params = {"sha": branch, "per_page": min(limit, 100)}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params=params, headers=_get_github_headers())
            if resp.status_code != 200:
                return {"commits": [], "error": resp.text}
            data = resp.json()
            commits = [
                {
                    "sha": c["sha"][:7],
                    "message": c["commit"]["message"].split("\n")[0],
                    "author": c["commit"]["author"]["name"],
                    "date": c["commit"]["author"]["date"],
                }
                for c in data
            ]
            return {"commits": commits, "count": len(commits)}

    elif name == "search_commits":
        keyword = args.get("keyword") or args.get("query") or args.get("search") or ""
        if not keyword:
            raise ValueError("Missing required parameter 'keyword'")
        limit = args.get("limit", 10)
        url = f"{GITHUB_API}/repos/{REPO}/commits"
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params={"per_page": 100}, headers=_get_github_headers())
            if resp.status_code != 200:
                return {"commits": [], "error": resp.text}
            data = resp.json()
            matched = []
            for c in data:
                if keyword.lower() in c["commit"]["message"].lower():
                    matched.append({
                        "sha": c["sha"][:7],
                        "message": c["commit"]["message"].split("\n")[0],
                        "date": c["commit"]["author"]["date"],
                    })
                    if len(matched) >= limit:
                        break
            return {"commits": matched, "count": len(matched)}

    elif name == "get_pull_requests":
        state = args.get("state", "all")
        limit = args.get("limit", 20)
        url = f"{GITHUB_API}/repos/{REPO}/pulls"
        params = {"state": state, "per_page": min(limit, 100), "sort": "updated"}
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.get(url, params=params, headers=_get_github_headers())
            if resp.status_code != 200:
                return {"pull_requests": [], "error": resp.text}
            data = resp.json()
            prs = [
                {
                    "number": pr["number"],
                    "title": pr["title"],
                    "state": pr["state"],
                    "merged": pr.get("merged_at") is not None,
                    "created_at": pr["created_at"],
                }
                for pr in data
            ]
            return {"pull_requests": prs, "count": len(prs)}

    elif name == "get_changed_files":
        pr_val = args.get("pr_number") or args.get("pr") or args.get("pull_request") or ""
        if not pr_val:
            raise ValueError("Missing required parameter 'pr_number'")
        try:
            pr_number = int(pr_val)
        except (ValueError, TypeError):
            raise ValueError(f"Invalid pr_number: {pr_val!r}")
        url = f"{GITHUB_API}/repos/{REPO}/pulls/{pr_number}/files"
        all_files = []
        page = 1
        async with httpx.AsyncClient(timeout=30) as client:
            while True:
                resp = await client.get(
                    url,
                    params={"per_page": 100, "page": page},
                    headers=_get_github_headers(),
                )
                if resp.status_code != 200:
                    if page == 1:
                        return {"files": [], "error": resp.text}
                    break
                data = resp.json()
                if not data:
                    break
                for f in data:
                    all_files.append({
                        "filename": f["filename"],
                        "status": f["status"],
                        "additions": f["additions"],
                        "deletions": f["deletions"],
                        "changes": f["changes"],
                    })
                if len(data) < 100:
                    break
                page += 1
        return {
            "files": all_files,
            "count": len(all_files),
            "truncated": False,
        }

    elif name == "rerun_pipeline":
        pid_val = args.get("pipeline_id") or args.get("pipeline") or ""
        if not pid_val:
            raise ValueError("Missing required parameter 'pipeline_id'")
        pid = _validate_identifier(pid_val)
        # Gap 9: Demo mode — simulate without real mutation
        if DATAFORGE_ENV == "demo":
            return {
                "status": "success",
                "pipeline_id": pid,
                "message": "Simulated pipeline rerun (DEMO MODE — no real mutation)",
                "dag_run_id": f"demo-run-{pid}",
                "environment": "demo",
            }
        else:
            # Production mode — actual Airflow call
            try:
                url = f"{AIRFLOW_URL}/api/v1/dags/{pid}/dagRuns"
                async with httpx.AsyncClient(timeout=30) as client:
                    resp = await client.post(
                        url,
                        json={"conf": {"rerun": True}},
                        auth=(AIRFLOW_USERNAME, AIRFLOW_PASSWORD),
                    )
                    if resp.status_code in (200, 201):
                        data = resp.json()
                        return {
                            "status": "success",
                            "pipeline_id": pid,
                            "message": "Triggered via Airflow",
                            "dag_run_id": data.get("dag_run_id"),
                            "environment": "production",
                        }
                    return {
                        "status": "failed",
                        "pipeline_id": pid,
                        "message": f"Airflow returned {resp.status_code}: {resp.text[:500]}",
                        "environment": "production",
                    }
            except Exception as e:
                return {
                    "status": "failed",
                    "pipeline_id": pid,
                    "message": f"Airflow request failed: {e}",
                    "environment": "production",
                }

    elif name == "rollback_deployment":
        did = args.get("deployment_id", "v2.8.0")
        return {"status": "pending_manual", "deployment_id": did, "message": f"Rollback to {did}"}

    elif name == "validate_data_quality":
        checks = []
        try:
            rows = await _query(
                f"SELECT countIf(customer_region IS NULL) as nulls, count() as total "
                f"FROM {CLICKHOUSE_DB}.customer_orders"
            )
            if rows:
                nulls = rows[0].get("nulls", 0)
                total = rows[0].get("total", 1)
                null_rate = nulls / total if total > 0 else 0
                checks.append({
                    "check": "null_rate",
                    "value": round(null_rate, 4),
                    "passed": null_rate < 0.05,
                })
        except Exception as e:
            checks.append({"check": "null_rate", "error": str(e), "passed": False})
        passed = sum(1 for c in checks if c.get("passed"))
        return {"checks": checks, "passed_count": passed, "total_count": len(checks)}

    else:
        raise ValueError(f"Unknown tool: {name}")


# ─── MCP SSE Protocol ─────────────────────────────────────────────────────────
# Reference: @modelcontextprotocol/sdk/server/sse.js
# - GET /sse: opens SSE stream, sends "event: endpoint\\ndata: /messages?sessionId=<uuid>\\n\\n"
# - POST /messages?sessionId=<uuid>: receives JSON-RPC, responds 202, sends results via SSE
# - SSE message events: "event: message\\ndata: <json-rpc>\\n\\n"

@app.get("/sse")
async def sse_endpoint(request: Request):
    session_id = str(uuid.uuid4())
    queue: asyncio.Queue = asyncio.Queue()
    _sessions[session_id] = {"queue": queue, "sse_response": None}

    async def event_stream():
        _sessions[session_id]["sse_response"] = True

        yield f"event: endpoint\ndata: /messages?sessionId={session_id}\n\n"

        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    msg = await asyncio.wait_for(queue.get(), timeout=30)
                    yield f"event: message\ndata: {json.dumps(msg)}\n\n"
                except TimeoutError:
                    yield ": keepalive\n\n"
        finally:
            # Mark SSE disconnected but keep session for POST responses
            if session_id in _sessions:
                _sessions[session_id]["sse_response"] = None

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "Connection": "keep-alive",
        },
    )


@app.post("/messages")
async def messages_endpoint(request: Request):
    sid = request.query_params.get("sessionId")
    if not sid or sid not in _sessions:
        return Response(content="Invalid or missing sessionId", status_code=400)

    body = await request.json()
    queue = _sessions[sid]["queue"]

    method = body.get("method")
    req_id = body.get("id")

    # Notifications (no id) don't require a response per JSON-RPC spec
    if req_id is None and method in ("notifications/initialized",):
        return Response(status_code=202)

    # Ensure req_id is always valid (MCP SDK requires string|number, not null)
    if req_id is None:
        req_id = 0

    if method == "initialize":
        result = {
            "protocolVersion": "2024-11-05",
            "capabilities": {"tools": {"listChanged": False}},
            "serverInfo": {"name": "dataforge-mcp", "version": "1.0.0"},
        }
        await queue.put({"jsonrpc": "2.0", "id": req_id, "result": result})
        return Response(status_code=202)

    elif method == "notifications/initialized":
        return Response(status_code=202)

    elif method == "ping":
        await queue.put({"jsonrpc": "2.0", "id": req_id, "result": {}})
        return Response(status_code=202)

    elif method == "tools/list":
        await queue.put({"jsonrpc": "2.0", "id": req_id, "result": {"tools": TOOLS}})
        return Response(status_code=202)

    elif method == "tools/call":
        tool_name = body.get("params", {}).get("name")
        tool_args = body.get("params", {}).get("arguments", {})

        # Bug 7 fix: require auth token for write tools
        if tool_name in WRITE_TOOLS and MCP_AUTH_TOKEN:
            auth_header = body.get("params", {}).get("metadata", {}).get("authorization", "")
            if auth_header != f"Bearer {MCP_AUTH_TOKEN}":
                await queue.put({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -1,
                        "message": (
                            f"Unauthorized: tool '{tool_name}' requires "
                            f"Bearer token in metadata.authorization"
                        ),
                    },
                })
                return Response(status_code=202)

        try:
            result = await execute_tool(tool_name, tool_args)
            text = json.dumps(result, default=str)
            if len(text) > MAX_RESPONSE_CHARS:
                text = text[:MAX_RESPONSE_CHARS] + f"\n... [truncated, {len(text)} total chars]"
            await queue.put({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "content": [{"type": "text", "text": text}]
                },
            })
        except Exception as e:
            await queue.put({
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -1, "message": str(e)},
            })
        return Response(status_code=202)

    else:
        await queue.put({
            "jsonrpc": "2.0",
            "id": req_id,
            "error": {"code": -1, "message": f"Unknown method: {method}"},
        })
        return Response(status_code=202)


@app.get("/health")
async def health():
    return {"status": "ok"}


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8791)
