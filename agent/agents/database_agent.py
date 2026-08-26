"""Database Agent — investigates data incidents by querying ClickHouse."""

from mcp.database.tools.schema import (
    describe_table,
    execute_select,
    list_tables,
    profile_column,
)


async def investigate_database(incident_type: str, description: str) -> dict:
    """Run database investigation and return findings."""
    findings = []
    errors = []

    # Step 1: Discover schema
    result = await list_tables()
    if result.get("error"):
        errors.append(f"Schema discovery failed: {result['error']}")
    else:
        tables = result.get("tables", [])
        findings.append({
            "type": "schema_discovery",
            "data": {"tables": tables, "count": len(tables)},
            "summary": f"Discovered {len(tables)} tables in dataforge database",
        })

    # Step 2: Describe key tables
    key_tables = ["revenue_daily", "customer_orders", "pipeline_events", "data_quality_metrics"]
    for table in key_tables:
        desc = await describe_table(table)
        if desc.get("error"):
            errors.append(f"Describe {table} failed: {desc['error']}")
        else:
            findings.append({
                "type": "table_schema",
                "data": desc,
                "summary": f"Table {table}: {desc.get('count', 0)} columns",
            })

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
        "summary": f"Database investigation: {len(findings)} findings, {len(errors)} errors",
    }


def _safe_finding(result: dict, finding_type: str, summary: str) -> dict | None:
    """Return a finding dict if result is valid, None if it's an error."""
    if result.get("error"):
        return {"type": "error", "data": {"error": result["error"]}, "summary": result["error"]}
    return {"type": finding_type, "data": result, "summary": summary}


async def _investigate_schema_drift() -> list[dict]:
    findings = []

    profile = await profile_column("customer_orders", "customer_region")
    if not profile.get("error"):
        findings.append({
            "type": "column_profile",
            "data": profile,
            "summary": (
                f"customer_region: null_rate={profile.get('null_rate', 0):.1%}, "
                f"distinct={profile.get('distinct_count', 0)}"
            ),
        })

    result = await execute_select(
        "SELECT customer_region, count() as cnt, sum(amount) as total "
        "FROM dataforge.customer_orders "
        "GROUP BY customer_region ORDER BY cnt DESC"
    )
    n = result.get("row_count", 0)
    f = _safe_finding(result, "aggregation", f"Region distribution: {n} groups")
    if f:
        findings.append(f)

    result = await execute_select(
        "SELECT date, region, sum(revenue) as total_revenue "
        "FROM dataforge.revenue_daily "
        "WHERE date >= today() - 7 "
        "GROUP BY date, region ORDER BY date DESC, region"
    )
    n = result.get("row_count", 0)
    f = _safe_finding(result, "revenue_trend", f"Revenue trend: {n} data points")
    if f:
        findings.append(f)

    return findings


async def _investigate_null_explosion() -> list[dict]:
    findings = []
    for col in ["customer_region", "amount", "status", "product_line"]:
        profile = await profile_column("customer_orders", col)
        if not profile.get("error"):
            findings.append({
                "type": "column_profile",
                "data": profile,
                "summary": f"{col}: null_rate={profile.get('null_rate', 0):.1%}",
            })
    return findings


async def _investigate_volume_anomaly() -> list[dict]:
    findings = []
    result = await execute_select(
        "SELECT toDate(order_date) as order_day, count() as order_count, sum(amount) as total "
        "FROM dataforge.customer_orders "
        "GROUP BY order_day ORDER BY order_day DESC LIMIT 14"
    )
    f = _safe_finding(result, "volume_trend", f"Volume trend: {result.get('row_count', 0)} days")
    if f:
        findings.append(f)
    return findings


async def _investigate_missing_partition() -> list[dict]:
    findings = []

    result = await execute_select(
        "SELECT toDate(order_date) as order_day, count() as order_count "
        "FROM dataforge.customer_orders "
        "GROUP BY order_day ORDER BY order_day DESC LIMIT 30"
    )
    if not result.get("error"):
        rows = result.get("rows", [])
        dates = [r.get("order_day") for r in rows]
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

    result = await execute_select(
        "SELECT date, region, sum(revenue) as total_revenue "
        "FROM dataforge.revenue_daily "
        "WHERE date >= today() - 7 "
        "GROUP BY date, region ORDER BY date DESC"
    )
    n = result.get("row_count", 0)
    f = _safe_finding(result, "revenue_by_date", f"Revenue by date: {n} data points")
    if f:
        findings.append(f)

    return findings


async def _investigate_duplicate_records() -> list[dict]:
    findings = []

    result = await execute_select(
        "SELECT order_id, count() as cnt "
        "FROM dataforge.customer_orders "
        "GROUP BY order_id HAVING cnt > 1 "
        "ORDER BY cnt DESC LIMIT 10"
    )
    if not result.get("error"):
        rows = result.get("rows", [])
        findings.append({
            "type": "duplicate_orders",
            "data": result,
            "summary": f"Found {len(rows)} duplicate order_ids",
        })

    result = await execute_select(
        "SELECT count() as total, uniq(order_id) as unique_count "
        "FROM dataforge.customer_orders"
    )
    if not result.get("error"):
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

    result = await execute_select(
        "SELECT toDate(order_date) as order_day, count() as order_count "
        "FROM dataforge.customer_orders "
        "GROUP BY order_day ORDER BY order_day DESC LIMIT 14"
    )
    f = _safe_finding(result, "volume_trend", f"Volume trend: {result.get('row_count', 0)} days")
    if f:
        findings.append(f)

    return findings


async def _investigate_pipeline_failure() -> list[dict]:
    findings = []

    result = await execute_select(
        "SELECT pipeline_id, status, count() as cnt "
        "FROM dataforge.pipeline_events "
        "GROUP BY pipeline_id, status ORDER BY cnt DESC"
    )
    n = result.get("row_count", 0)
    f = _safe_finding(result, "pipeline_status_summary", f"Pipeline statuses: {n} groups")
    if f:
        findings.append(f)

    result = await execute_select(
        "SELECT pipeline_id, started_at, error_message "
        "FROM dataforge.pipeline_events "
        "WHERE status = 'FAILED' "
        "ORDER BY started_at DESC LIMIT 5"
    )
    n = result.get("row_count", 0)
    f = _safe_finding(result, "failed_jobs", f"Failed jobs: {n}")
    if f:
        findings.append(f)

    result = await execute_select(
        "SELECT pipeline_id, "
        "avg(dateDiff('second', started_at, completed_at)) as avg_duration, "
        "max(dateDiff('second', started_at, completed_at)) as max_duration "
        "FROM dataforge.pipeline_events "
        "WHERE completed_at IS NOT NULL "
        "GROUP BY pipeline_id"
    )
    n = result.get("row_count", 0)
    f = _safe_finding(
        result, "pipeline_performance", f"Pipeline performance: {n} pipelines"
    )
    if f:
        findings.append(f)

    return findings


async def _investigate_business_metric_anomaly() -> list[dict]:
    findings = []

    result = await execute_select(
        "SELECT date, region, sum(revenue) as total_revenue, "
        "sum(orders) as total_orders "
        "FROM dataforge.revenue_daily "
        "WHERE date >= today() - 14 "
        "GROUP BY date, region ORDER BY date DESC"
    )
    n = result.get("row_count", 0)
    f = _safe_finding(result, "revenue_trend", f"Revenue trend: {n} data points")
    if f:
        findings.append(f)

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
    n = result.get("row_count", 0)
    f = _safe_finding(result, "revenue_statistics", f"Revenue statistics: {n} regions")
    if f:
        findings.append(f)

    result = await execute_select(
        "SELECT date, "
        "sum(revenue) as daily_total, "
        "sum(orders) as daily_orders "
        "FROM dataforge.revenue_daily "
        "WHERE date >= today() - 14 "
        "GROUP BY date ORDER BY date"
    )
    n = result.get("row_count", 0)
    f = _safe_finding(result, "daily_metrics", f"Daily metrics: {n} days")
    if f:
        findings.append(f)

    return findings


async def _investigate_general() -> list[dict]:
    findings = []
    result = await execute_select(
        "SELECT region, sum(revenue) as total, count() as days "
        "FROM dataforge.revenue_daily "
        "GROUP BY region ORDER BY total DESC"
    )
    n = result.get("row_count", 0)
    f = _safe_finding(result, "revenue_summary", f"Revenue by region: {n} regions")
    if f:
        findings.append(f)
    return findings
