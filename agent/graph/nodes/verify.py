"""Verify node — verifies remediation with before/after comparison."""

import logging

from agent.agents.data_quality_agent import check_data_quality
from mcp.monitoring.tools.pipelines import get_pipeline_status

logger = logging.getLogger(__name__)


async def verify_remediation(state: dict) -> dict:
    """Verify remediation success with before/after comparison."""
    verification_results = []

    # Run comprehensive data quality check
    try:
        dq_result = await check_data_quality(state.get("incident_type", "unknown"))
        dq_findings = dq_result.get("findings", [])
        dq_errors = dq_result.get("errors", [])

        # Add each finding with unique metric key
        for f in dq_findings:
            metric_key = f["type"]
            # Make completeness keys unique per table.column
            if f["type"] == "completeness":
                data = f.get("data", {})
                metric_key = f"completeness_{data.get('table', '')}_{data.get('column', '')}"

            verification_results.append({
                "metric": metric_key,
                "before": _get_before_value(f["type"], f.get("data", {}), state),
                "after": f["summary"],
                "status": "resolved" if f.get("passed") else "unresolved",
            })

        # Include DQ errors as unresolved checks
        for err_msg in dq_errors:
            verification_results.append({
                "metric": f"dq_error_{len(verification_results)}",
                "before": "unknown",
                "after": f"ERROR: {err_msg}",
                "status": "error",
            })
    except Exception as e:
        logger.error(f"Data quality check failed: {e}")
        verification_results.append({
            "metric": "data_quality_check",
            "before": "unknown",
            "after": f"Error: {e}",
            "status": "error",
        })

    # Pipeline status check
    try:
        status = await get_pipeline_status()
        pipelines = status.get("pipelines", [])
        failed = [p for p in pipelines if p.get("status") == "FAILED"]
        pipeline_ok = len(failed) == 0
        verification_results.append({
            "metric": "pipeline_health",
            "before": "FAILED",
            "after": "HEALTHY" if pipeline_ok else f"STILL_FAILED ({len(failed)})",
            "status": "resolved" if pipeline_ok else "unresolved",
        })
    except Exception as e:
        logger.error(f"Pipeline verification failed: {e}")
        verification_results.append({
            "metric": "pipeline_health",
            "before": "FAILED",
            "after": f"Error: {e}",
            "status": "error",
        })

    resolved = sum(1 for v in verification_results if v["status"] == "resolved")
    total = len(verification_results)
    overall = "resolved" if resolved == total else "partially_resolved"

    # Build before/after summary
    before_summary = {}
    after_summary = {}
    for v in verification_results:
        before_summary[v["metric"]] = v["before"]
        after_summary[v["metric"]] = v["after"]

    return {
        "status": "verifying",
        "verification_result": {
            "results": verification_results,
            "overall_status": overall,
            "resolved_count": resolved,
            "total_count": total,
            "before_summary": before_summary,
            "after_summary": after_summary,
        },
        "events": state.get("events", []) + [
            {
                "type": "verification.completed",
                "agent": "verifier",
                "message": (
                    f"Verification: {resolved}/{total} checks passed — "
                    f"overall: {overall}"
                ),
            }
        ],
    }


def _get_before_value(metric_type: str, data: dict, state: dict) -> str:
    """Get the before value from incident context."""
    evidence = state.get("evidence", [])

    # Try to extract before values from evidence
    for e in evidence:
        if e.get("source") == "database":
            content = e.get("content", {})
            if metric_type == "freshness" and "latest_date" in content:
                return f"latest={content['latest_date']}"
            if metric_type.startswith("completeness") and "null_rate" in content:
                return f"null_rate={content['null_rate']:.1%}"
            if metric_type == "uniqueness" and "duplicate_rate" in content:
                return f"dup_rate={content['duplicate_rate']:.1%}"
            if metric_type == "volume" and "daily_counts" in content:
                counts = content["daily_counts"]
                return f"avg={sum(counts) / len(counts):.0f}" if counts else "unknown"
            if metric_type == "distribution" and "apac_share" in content:
                return f"APAC={content['apac_share']:.1%}"

    # Default before values based on metric type
    defaults = {
        "freshness": "unknown",
        "completeness": "degraded",
        "uniqueness": "unknown",
        "volume": "degraded",
        "distribution": "imbalanced",
        "pipeline_health": "FAILED",
    }
    # Match prefix for completeness_*
    for key, val in defaults.items():
        if metric_type.startswith(key):
            return val
    return "unknown"
