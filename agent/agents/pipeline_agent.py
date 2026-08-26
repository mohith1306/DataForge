"""Pipeline Agent — investigates pipeline failures using real ClickHouse data."""

import logging

from mcp.monitoring.tools.pipelines import (
    get_failed_jobs,
    get_pipeline_logs,
    get_pipeline_metrics,
    get_pipeline_status,
)

logger = logging.getLogger(__name__)


async def investigate_pipeline(incident_type: str, description: str) -> dict:
    """Investigate pipeline-related issues using real MCP tools."""
    findings = []
    errors = []

    # Step 1: Get current pipeline status
    try:
        status = await get_pipeline_status()
        pipelines = status.get("pipelines", [])
        failed = [p for p in pipelines if p.get("status") == "FAILED"]
        findings.append({
            "type": "pipeline_overview",
            "data": {
                "total": len(pipelines),
                "failed_count": len(failed),
                "pipelines": pipelines[:10],
            },
            "summary": f"{len(pipelines)} pipeline records, {len(failed)} failed",
        })
    except Exception as e:
        errors.append(f"Pipeline status check failed: {e}")

    # Step 2: Get failed jobs
    try:
        failed_result = await get_failed_jobs(days=7)
        failed_jobs = failed_result.get("failed_jobs", [])
        if failed_jobs:
            findings.append({
                "type": "failed_jobs",
                "data": {"jobs": failed_jobs, "count": len(failed_jobs)},
                "summary": f"{len(failed_jobs)} failed pipeline jobs in last 7 days",
            })
            for job in failed_jobs[:3]:
                findings.append({
                    "type": "failed_job_detail",
                    "data": job,
                    "summary": (
                        f"FAILED: {job.get('pipeline_id', 'unknown')} "
                        f"at {job.get('started_at', 'unknown')} — "
                        f"{job.get('error_message', 'no error msg')[:200]}"
                    ),
                })
    except Exception as e:
        errors.append(f"Failed jobs query failed: {e}")

    # Step 3: Get pipeline logs for failed pipelines
    pipeline_ids = set()
    for f in findings:
        data = f.get("data", {})
        if "pipeline_id" in data:
            pipeline_ids.add(data["pipeline_id"])
        if "jobs" in data:
            for job in data["jobs"]:
                if "pipeline_id" in job:
                    pipeline_ids.add(job["pipeline_id"])

    for pid in list(pipeline_ids)[:3]:
        try:
            logs = await get_pipeline_logs(pid, limit=10)
            error_logs = logs.get("error_logs", [])
            if error_logs:
                findings.append({
                    "type": "pipeline_logs",
                    "data": {"pipeline_id": pid, "logs": error_logs},
                    "summary": f"Pipeline {pid}: {len(error_logs)} error log entries",
                })
        except Exception as e:
            errors.append(f"Pipeline logs for {pid} failed: {e}")

    # Step 4: Get metrics for affected pipelines
    for pid in list(pipeline_ids)[:3]:
        try:
            metrics = await get_pipeline_metrics(pid)
            m = metrics.get("metrics", {})
            if m:
                success_rate = 0
                total = m.get("total_runs", 0)
                if total > 0:
                    success_rate = m.get("success_count", 0) / total
                findings.append({
                    "type": "pipeline_metrics",
                    "data": {"pipeline_id": pid, "metrics": m},
                    "summary": (
                        f"Pipeline {pid}: {m.get('success_count', 0)}/{total} "
                        f"success ({success_rate:.0%}), "
                        f"avg {m.get('avg_duration_sec', 0):.0f}s"
                    ),
                })
        except Exception as e:
            errors.append(f"Pipeline metrics for {pid} failed: {e}")

    return {
        "agent": "pipeline",
        "findings": findings,
        "errors": errors,
        "summary": f"Pipeline investigation: {len(findings)} findings, {len(errors)} errors",
    }
