"""Database Agent — investigates data incidents by querying ClickHouse.

Workflow:
1. Discover schema (list tables, describe relevant ones)
2. Generate SQL queries based on incident type
3. Execute queries and analyze results
4. Profile affected columns
5. Return structured evidence
"""

from mcp.database.tools.schema import (
    describe_table,
    execute_select,
    list_tables,
    profile_column,
)


async def investigate_database(incident_type: str, description: str) -> dict:
    """Run database investigation and return findings.

    Args:
        incident_type: Type of incident (schema_drift, null_explosion, etc.)
        description: Incident description

    Returns:
        Dict with findings, evidence, and summary.
    """
    findings = []
    errors = []

    # Step 1: Discover schema
    try:
        tables_result = await list_tables()
        tables = tables_result.get("tables", [])
        findings.append({
            "type": "schema_discovery",
            "data": {"tables": tables, "count": len(tables)},
            "summary": f"Discovered {len(tables)} tables in dataforge database",
        })
    except Exception as e:
        errors.append(f"Schema discovery failed: {e}")

    # Step 2: Describe key tables
    key_tables = ["revenue_daily", "customer_orders", "pipeline_events", "data_quality_metrics"]
    for table in key_tables:
        try:
            desc = await describe_table(table)
            findings.append({
                "type": "table_schema",
                "data": desc,
                "summary": f"Table {table}: {desc.get('count', 0)} columns",
            })
        except Exception as e:
            errors.append(f"Describe {table} failed: {e}")

    # Step 3: Query based on incident type
    if incident_type == "schema_drift":
        findings.extend(await _investigate_schema_drift())
    elif incident_type == "null_explosion":
        findings.extend(await _investigate_null_explosion())
    elif incident_type == "volume_anomaly":
        findings.extend(await _investigate_volume_anomaly())
    elif incident_type == "missing_partition":
        findings.extend(await _investigate_missing_partition())
    elif incident_type == "duplicate_records":
        findings.extend(await _investigate_duplicate_records())
    elif incident_type == "pipeline_failure":
        findings.extend(await _investigate_pipeline_failure())
    elif incident_type == "business_metric_anomaly":
        findings.extend(await _investigate_business_metric_anomaly())
    else:
        findings.extend(await _investigate_general())

    return {
        "agent": "database",
        "findings": findings,
        "errors": errors,
        "summary": (
            f"Database investigation complete: {len(findings)} findings, "
            f"{len(errors)} errors"
        ),
    }


async def _investigate_schema_drift() -> list[dict]:
    """Investigate schema drift indicators."""
    findings = []

    try:
        profile = await profile_column("customer_orders", "customer_region")
        findings.append({
            "type": "column_profile",
            "data": profile,
            "summary": (
                f"customer_region: null_rate={profile.get('null_rate', 0):.1%}, "
                f"distinct={profile.get('distinct_count', 0)}"
            ),
        })
    except Exception as e:
        findings.append({"type": "error", "data": {"error": str(e)}})

    try:
        result = await execute_select(
            "SELECT customer_region, count() as cnt, sum(amount) as total "
            "FROM dataforge.customer_orders "
            "GROUP BY customer_region ORDER BY cnt DESC"
        )
        findings.append({
            "type": "aggregation",
            "data": result,
            "summary": f"Region distribution: {result.get('row_count', 0)} groups",
        })
    except Exception as e:
        findings.append({"type": "error", "data": {"error": str(e)}})

    try:
        result = await execute_select(
            "SELECT date, region, sum(revenue) as total_revenue "
            "FROM dataforge.revenue_daily "
            "WHERE date >= today() - 7 "
            "GROUP BY date, region ORDER BY date DESC, region"
        )
        findings.append({
            "type": "revenue_trend",
            "data": result,
            "summary": f"Revenue trend: {result.get('row_count', 0)} data points",
        })
    except Exception as e:
        findings.append({"type": "error", "data": {"error": str(e)}})

    return findings


async def _investigate_null_explosion() -> list[dict]:
    """Investigate null explosion indicators."""
    findings = []

    columns = ["customer_region", "amount", "status", "product_line"]
    for col in columns:
        try:
            profile = await profile_column("customer_orders", col)
            findings.append({
                "type": "column_profile",
                "data": profile,
                "summary": f"{col}: null_rate={profile.get('null_rate', 0):.1%}",
            })
        except Exception as e:
            findings.append({"type": "error", "data": {"error": str(e)}})

    return findings


async def _investigate_volume_anomaly() -> list[dict]:
    """Investigate volume anomaly indicators."""
    findings = []

    try:
        result = await execute_select(
            "SELECT date, count() as order_count, sum(amount) as total "
            "FROM dataforge.customer_orders "
            "GROUP BY date ORDER BY date DESC LIMIT 14"
        )
        findings.append({
            "type": "volume_trend",
            "data": result,
            "summary": f"Volume trend: {result.get('row_count', 0)} days",
        })
    except Exception as e:
        findings.append({"type": "error", "data": {"error": str(e)}})

    return findings


async def _investigate_missing_partition() -> list[dict]:
    """Investigate missing partition indicators."""
    findings = []

    try:
        result = await execute_select(
            "SELECT date, count() as order_count "
            "FROM dataforge.customer_orders "
            "GROUP BY date ORDER BY date DESC LIMIT 30"
        )
        rows = result.get("rows", [])
        dates = [r.get("date") for r in rows]
        findings.append({
            "type": "partition_dates",
            "data": result,
            "summary": f"Found {len(dates)} partitions in last 30 days",
        })

        if len(dates) >= 2:
            from datetime import datetime

            date_objs = sorted(
                [datetime.strptime(str(d)[:10], "%Y-%m-%d") for d in dates if d],
                reverse=True,
            )
            gaps = []
            for i in range(len(date_objs) - 1):
                diff = (date_objs[i] - date_objs[i + 1]).days
                if diff > 1:
                    gaps.append(
                        f"Gap: {date_objs[i + 1].strftime('%Y-%m-%d')} "
                        f"to {date_objs[i].strftime('%Y-%m-%d')} ({diff} days)"
                    )
            if gaps:
                findings.append({
                    "type": "partition_gaps",
                    "data": {"gaps": gaps},
                    "summary": f"Detected {len(gaps)} partition gap(s)",
                })
    except Exception as e:
        findings.append({"type": "error", "data": {"error": str(e)}})

    try:
        result = await execute_select(
            "SELECT date, region, sum(revenue) as total_revenue "
            "FROM dataforge.revenue_daily "
            "WHERE date >= today() - 7 "
            "GROUP BY date, region ORDER BY date DESC"
        )
        findings.append({
            "type": "revenue_by_date",
            "data": result,
            "summary": f"Revenue by date: {result.get('row_count', 0)} data points",
        })
    except Exception as e:
        findings.append({"type": "error", "data": {"error": str(e)}})

    return findings


async def _investigate_duplicate_records() -> list[dict]:
    """Investigate duplicate record indicators."""
    findings = []

    try:
        result = await execute_select(
            "SELECT order_id, count() as cnt "
            "FROM dataforge.customer_orders "
            "GROUP BY order_id HAVING cnt > 1 "
            "ORDER BY cnt DESC LIMIT 10"
        )
        rows = result.get("rows", [])
        findings.append({
            "type": "duplicate_orders",
            "data": result,
            "summary": f"Found {len(rows)} duplicate order_ids",
        })
    except Exception as e:
        findings.append({"type": "error", "data": {"error": str(e)}})

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
            findings.append({
                "type": "duplication_rate",
                "data": {"total": total, "unique": unique, "duplicate_rate": dup_rate},
                "summary": f"Duplicate rate: {dup_rate:.1%} ({total - unique} duplicates)",
            })
    except Exception as e:
        findings.append({"type": "error", "data": {"error": str(e)}})

    try:
        result = await execute_select(
            "SELECT date, count() as order_count "
            "FROM dataforge.customer_orders "
            "GROUP BY date ORDER BY date DESC LIMIT 14"
        )
        findings.append({
            "type": "volume_trend",
            "data": result,
            "summary": f"Volume trend: {result.get('row_count', 0)} days",
        })
    except Exception as e:
        findings.append({"type": "error", "data": {"error": str(e)}})

    return findings


async def _investigate_pipeline_failure() -> list[dict]:
    """Investigate pipeline failure indicators."""
    findings = []

    try:
        result = await execute_select(
            "SELECT pipeline_id, status, count() as cnt "
            "FROM dataforge.pipeline_events "
            "GROUP BY pipeline_id, status ORDER BY cnt DESC"
        )
        findings.append({
            "type": "pipeline_status_summary",
            "data": result,
            "summary": f"Pipeline statuses: {result.get('row_count', 0)} groups",
        })
    except Exception as e:
        findings.append({"type": "error", "data": {"error": str(e)}})

    try:
        result = await execute_select(
            "SELECT pipeline_id, event_time, error_message "
            "FROM dataforge.pipeline_events "
            "WHERE status = 'FAILED' "
            "ORDER BY event_time DESC LIMIT 5"
        )
        findings.append({
            "type": "failed_jobs",
            "data": result,
            "summary": f"Failed jobs: {result.get('row_count', 0)}",
        })
    except Exception as e:
        findings.append({"type": "error", "data": {"error": str(e)}})

    try:
        result = await execute_select(
            "SELECT pipeline_id, avg(duration_seconds) as avg_duration, "
            "max(duration_seconds) as max_duration "
            "FROM dataforge.pipeline_events "
            "GROUP BY pipeline_id"
        )
        findings.append({
            "type": "pipeline_performance",
            "data": result,
            "summary": f"Pipeline performance: {result.get('row_count', 0)} pipelines",
        })
    except Exception as e:
        findings.append({"type": "error", "data": {"error": str(e)}})

    return findings


async def _investigate_business_metric_anomaly() -> list[dict]:
    """Investigate business metric anomaly indicators."""
    findings = []

    try:
        result = await execute_select(
            "SELECT date, region, sum(revenue) as total_revenue, "
            "sum(order_count) as total_orders "
            "FROM dataforge.revenue_daily "
            "WHERE date >= today() - 14 "
            "GROUP BY date, region ORDER BY date DESC"
        )
        findings.append({
            "type": "revenue_trend",
            "data": result,
            "summary": f"Revenue trend: {result.get('row_count', 0)} data points",
        })
    except Exception as e:
        findings.append({"type": "error", "data": {"error": str(e)}})

    try:
        result = await execute_select(
            "SELECT region, "
            "avg(revenue) as avg_revenue, "
            "stddev(revenue) as std_revenue, "
            "min(revenue) as min_revenue, "
            "max(revenue) as max_revenue "
            "FROM dataforge.revenue_daily "
            "WHERE date >= today() - 30 "
            "GROUP BY region"
        )
        findings.append({
            "type": "revenue_statistics",
            "data": result,
            "summary": f"Revenue statistics: {result.get('row_count', 0)} regions",
        })
    except Exception as e:
        findings.append({"type": "error", "data": {"error": str(e)}})

    try:
        result = await execute_select(
            "SELECT date, "
            "sum(revenue) as daily_total, "
            "sum(order_count) as daily_orders "
            "FROM dataforge.revenue_daily "
            "WHERE date >= today() - 14 "
            "GROUP BY date ORDER BY date"
        )
        findings.append({
            "type": "daily_metrics",
            "data": result,
            "summary": f"Daily metrics: {result.get('row_count', 0)} days",
        })
    except Exception as e:
        findings.append({"type": "error", "data": {"error": str(e)}})

    return findings


async def _investigate_general() -> list[dict]:
    """General investigation — check all key metrics."""
    findings = []

    try:
        result = await execute_select(
            "SELECT region, sum(revenue) as total, count() as days "
            "FROM dataforge.revenue_daily "
            "GROUP BY region ORDER BY total DESC"
        )
        findings.append({
            "type": "revenue_summary",
            "data": result,
            "summary": f"Revenue by region: {result.get('row_count', 0)} regions",
        })
    except Exception as e:
        findings.append({"type": "error", "data": {"error": str(e)}})

    return findings
