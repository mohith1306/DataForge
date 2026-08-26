"""Verify node — verifies that remediation actions actually resolved the incident."""

import logging

from mcp.database.tools.schema import execute_select, profile_column
from mcp.monitoring.tools.pipelines import get_pipeline_status

logger = logging.getLogger(__name__)


async def verify_remediation(state: dict) -> dict:
    """Verify that remediation was successful by checking data and pipeline state."""
    verification_results = []

    # Check 1: Pipeline status
    try:
        status = await get_pipeline_status()
        pipelines = status.get("pipelines", [])
        failed = [p for p in pipelines if p.get("status") == "FAILED"]
        pipeline_ok = len(failed) == 0
        verification_results.append({
            "metric": "pipeline_health",
            "before": "FAILED",
            "after": "HEALTHY" if pipeline_ok else "STILL_FAILED",
            "status": "resolved" if pipeline_ok else "unresolved",
        })
    except Exception as e:
        logger.error(f"Pipeline verification failed: {e}")
        verification_results.append({
            "metric": "pipeline_health",
            "before": "FAILED",
            "after": "UNKNOWN",
            "status": "error",
        })

    # Check 2: Data quality — customer_region null rate
    try:
        profile = await profile_column("customer_orders", "customer_region")
        null_rate = profile.get("null_rate", 0)
        quality_ok = null_rate < 0.05
        verification_results.append({
            "metric": "customer_region_null_rate",
            "before": "18.7%",
            "after": f"{null_rate:.1%}",
            "status": "resolved" if quality_ok else "unresolved",
        })
    except Exception as e:
        logger.error(f"Data quality verification failed: {e}")
        verification_results.append({
            "metric": "customer_region_null_rate",
            "before": "18.7%",
            "after": "UNKNOWN",
            "status": "error",
        })

    # Check 3: Revenue trend
    try:
        result = await execute_select(
            "SELECT sum(revenue) as total_revenue, count() as days "
            "FROM dataforge.revenue_daily "
            "WHERE date >= today() - 7"
        )
        rows = result.get("rows", [])
        if rows:
            recent_revenue = rows[0].get("total_revenue", 0)
            revenue_ok = recent_revenue > 1000000
            if recent_revenue > 1000000:
                rev_str = f"${recent_revenue / 1000000:.1f}M"
            else:
                rev_str = f"${recent_revenue:,.0f}"
            verification_results.append({
                "metric": "revenue_7day",
                "before": "$12.7M",
                "after": rev_str,
                "status": "resolved" if revenue_ok else "unresolved",
            })
    except Exception as e:
        logger.error(f"Revenue verification failed: {e}")
        verification_results.append({
            "metric": "revenue_7day",
            "before": "$12.7M",
            "after": "UNKNOWN",
            "status": "error",
        })

    # Check 4: Record counts
    try:
        result = await execute_select(
            "SELECT count() as cnt FROM dataforge.customer_orders"
        )
        rows = result.get("rows", [])
        if rows:
            count = rows[0].get("cnt", 0)
            volume_ok = count > 3000
            verification_results.append({
                "metric": "record_count",
                "before": "< 3000",
                "after": f"{count:,}",
                "status": "resolved" if volume_ok else "unresolved",
            })
    except Exception as e:
        logger.error(f"Volume verification failed: {e}")
        verification_results.append({
            "metric": "record_count",
            "before": "< 3000",
            "after": "UNKNOWN",
            "status": "error",
        })

    resolved = sum(1 for v in verification_results if v["status"] == "resolved")
    total = len(verification_results)
    overall = "resolved" if resolved == total else "partially_resolved"

    return {
        "status": "verifying",
        "verification_result": {
            "results": verification_results,
            "overall_status": overall,
            "resolved_count": resolved,
            "total_count": total,
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
