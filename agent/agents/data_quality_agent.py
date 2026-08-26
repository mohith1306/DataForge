"""Data Quality Agent — comprehensive data quality checks across all dimensions."""

import logging

from mcp.database.tools.schema import execute_select, profile_column

logger = logging.getLogger(__name__)


async def check_data_quality(incident_type: str = "unknown") -> dict:
    """Run comprehensive data quality checks and return findings."""
    findings = []
    errors = []

    # 1. Freshness check
    try:
        result = await execute_select(
            "SELECT max(date) as latest_date, "
            "dateDiff('day', max(date), today()) as days_behind "
            "FROM dataforge.revenue_daily"
        )
        rows = result.get("rows", [])
        if rows:
            latest = rows[0].get("latest_date", "unknown")
            days_behind = rows[0].get("days_behind", 0)
            fresh = days_behind <= 1
            findings.append({
                "type": "freshness",
                "data": {"latest_date": str(latest), "days_behind": days_behind},
                "summary": (
                    f"Revenue data freshness: latest={latest}, "
                    f"{days_behind} days behind — {'OK' if fresh else 'STALE'}"
                ),
                "passed": fresh,
            })
    except Exception as e:
        errors.append(f"Freshness check failed: {e}")

    # 2. Completeness checks
    for table, column in [
        ("customer_orders", "customer_region"),
        ("customer_orders", "amount"),
        ("revenue_daily", "revenue"),
    ]:
        try:
            profile = await profile_column(table, column)
            # Check if profile returned an error
            if "error" in profile:
                findings.append({
                    "type": "completeness",
                    "data": {"table": table, "column": column, "error": profile["error"]},
                    "summary": f"{table}.{column}: profile check FAILED — {profile['error']}",
                    "passed": False,
                })
            else:
                null_rate = profile.get("null_rate", 0)
                completeness = 1.0 - null_rate
                passed = completeness > 0.95
                findings.append({
                    "type": "completeness",
                    "data": {
                        "table": table,
                        "column": column,
                        "completeness": round(completeness, 4),
                        "null_rate": round(null_rate, 4),
                    },
                    "summary": (
                        f"{table}.{column}: completeness={completeness:.1%}, "
                        f"null_rate={null_rate:.1%} — "
                        f"{'OK' if passed else 'DEGRADED'}"
                    ),
                    "passed": passed,
                })
        except Exception as e:
            errors.append(f"Completeness check for {table}.{column} failed: {e}")

    # 3. Uniqueness check
    try:
        result = await execute_select(
            "SELECT count() as total, uniq(order_id) as unique_count "
            "FROM dataforge.customer_orders"
        )
        rows = result.get("rows", [])
        if rows:
            total = rows[0].get("total", 0)
            unique = rows[0].get("unique_count", 0)
            dup_rate = (total - unique) / total if total > 0 else 0
            passed = dup_rate < 0.01
            findings.append({
                "type": "uniqueness",
                "data": {"total": total, "unique": unique, "duplicate_rate": round(dup_rate, 4)},
                "summary": (
                    f"Uniqueness: {unique}/{total} unique orders, "
                    f"dup_rate={dup_rate:.2%} — {'OK' if passed else 'DUPLICATES DETECTED'}"
                ),
                "passed": passed,
            })
    except Exception as e:
        errors.append(f"Uniqueness check failed: {e}")

    # 4. Volume check — use calendar days (not just days with data)
    try:
        result = await execute_select(
            "SELECT day, ifNull(cnt, 0) as cnt FROM "
            "(SELECT arrayMap(x -> today() - x, range(7)) as days) "
            "ARRAY JOIN days as day "
            "LEFT JOIN "
            "(SELECT toDate(order_date) as day, count() as cnt "
            "FROM dataforge.customer_orders GROUP BY day) AS d USING (day) "
            "ORDER BY day DESC"
        )
        rows = result.get("rows", [])
        if rows:
            counts = [r.get("cnt", 0) for r in rows]
            avg = sum(counts) / len(counts) if counts else 0
            min_count = min(counts) if counts else 0
            zero_days = sum(1 for c in counts if c == 0)
            volume_ok = min_count > avg * 0.5 if avg > 0 else True
            findings.append({
                "type": "volume",
                "data": {
                    "daily_counts": counts,
                    "average": round(avg, 1),
                    "min": min_count,
                    "zero_days": zero_days,
                },
                "summary": (
                    f"Volume (7d calendar): avg={avg:.0f}, min={min_count}, "
                    f"{zero_days} empty days — "
                    f"{'STABLE' if volume_ok else 'VOLUME DROP DETECTED'}"
                ),
                "passed": volume_ok,
            })
    except Exception as e:
        errors.append(f"Volume check failed: {e}")

    # 5. Distribution check — region balance
    try:
        result = await execute_select(
            "SELECT customer_region, count() as cnt "
            "FROM dataforge.customer_orders "
            "GROUP BY customer_region ORDER BY cnt DESC"
        )
        rows = result.get("rows", [])
        if rows:
            counts = {r.get("customer_region", "?"): r.get("cnt", 0) for r in rows}
            total = sum(counts.values())
            apac_share = counts.get("APAC", 0) / total if total > 0 else 0
            # APAC should be ~25% in balanced state
            dist_ok = apac_share > 0.15
            findings.append({
                "type": "distribution",
                "data": {"region_counts": counts, "apac_share": round(apac_share, 3)},
                "summary": (
                    f"Region distribution: APAC={apac_share:.1%} of total — "
                    f"{'BALANCED' if dist_ok else 'APAC UNDERREPRESENTED'}"
                ),
                "passed": dist_ok,
            })
    except Exception as e:
        errors.append(f"Distribution check failed: {e}")

    # 6. Schema consistency check
    try:
        result = await execute_select(
            "SELECT pipeline_id, countIf(status = 'FAILED') as failed "
            "FROM dataforge.pipeline_events "
            "WHERE started_at >= now() - INTERVAL 3 DAY "
            "GROUP BY pipeline_id"
        )
        rows = result.get("rows", [])
        failed_pipelines = [r for r in rows if r.get("failed", 0) > 0]
        pipeline_ok = len(failed_pipelines) == 0
        findings.append({
            "type": "pipeline_health",
            "data": {"failed_pipelines": failed_pipelines, "count": len(failed_pipelines)},
            "summary": (
                f"Pipeline health: {len(failed_pipelines)} failing pipelines — "
                f"{'HEALTHY' if pipeline_ok else 'FAILURES DETECTED'}"
            ),
            "passed": pipeline_ok,
        })
    except Exception as e:
        errors.append(f"Pipeline health check failed: {e}")

    passed_count = sum(1 for f in findings if f.get("passed"))
    total_count = len(findings)

    return {
        "agent": "data_quality",
        "findings": findings,
        "errors": errors,
        "summary": f"DQ check: {passed_count}/{total_count} passed",
        "passed_count": passed_count,
        "total_count": total_count,
        "all_passed": passed_count == total_count,
    }
