"""Seed ClickHouse with deterministic demo data for the golden scenario."""

import random
import uuid
from datetime import datetime, timedelta

import httpx

CLICKHOUSE_URL = "http://localhost:8123"
CLICKHOUSE_DB = "dataforge"

REGIONS = ["APAC", "EMEA", "Americas", "NA"]
PRODUCT_LINES = ["Enterprise", "SMB", "Mid-Market", "Startup"]

# Deterministic seed for reproducibility
random.seed(42)


def execute_query(query: str) -> None:
    resp = httpx.post(
        f"{CLICKHOUSE_URL}/",
        params={"database": CLICKHOUSE_DB, "default_format": "JSONEachRow"},
        content=query,
        timeout=30,
    )
    if resp.status_code != 200:
        raise RuntimeError(f"Query failed: {resp.text}")


def create_tables() -> None:
    """Create ClickHouse tables."""
    execute_query("""
        CREATE TABLE IF NOT EXISTS revenue_daily (
            date Date,
            region String,
            product_line String,
            revenue Float64,
            orders UInt32,
            avg_order_value Float64
        ) ENGINE = MergeTree()
        ORDER BY (date, region, product_line)
    """)

    execute_query("""
        CREATE TABLE IF NOT EXISTS customer_orders (
            order_id String,
            customer_id String,
            customer_region String,
            product_line String,
            order_date DateTime,
            amount Float64,
            status String
        ) ENGINE = MergeTree()
        ORDER BY (order_date, order_id)
    """)

    execute_query("""
        CREATE TABLE IF NOT EXISTS pipeline_events (
            pipeline_id String,
            pipeline_name String,
            status String,
            started_at DateTime,
            completed_at Nullable(DateTime),
            error_message Nullable(String),
            rows_processed UInt32
        ) ENGINE = MergeTree()
        ORDER BY (started_at, pipeline_id)
    """)

    execute_query("""
        CREATE TABLE IF NOT EXISTS data_quality_metrics (
            metric_date Date,
            table_name String,
            column_name String,
            null_rate Float64,
            uniqueness Float64,
            completeness Float64,
            volume UInt32
        ) ENGINE = MergeTree()
        ORDER BY (metric_date, table_name, column_name)
    """)
    print("Created ClickHouse tables")


def seed_revenue_daily() -> None:
    """Seed 30 days of daily revenue data (historical, no future dates)."""
    rows = []
    base_date = datetime(2026, 7, 1)
    # Only generate data up to today (2026-08-25 for the demo)
    end_date = datetime(2026, 8, 25)
    num_days = (end_date - base_date).days

    for day_offset in range(num_days):
        date = base_date + timedelta(days=day_offset)
        date_str = date.strftime("%Y-%m-%d")

        for region in REGIONS:
            for product in PRODUCT_LINES:
                base_rev = {
                    "APAC": 180000,
                    "EMEA": 150000,
                    "Americas": 200000,
                    "NA": 170000,
                }[region]

                # Simulate 42% drop in APAC during incident window (last 5 days)
                if day_offset >= num_days - 5 and region == "APAC":
                    base_rev *= 0.58
                elif day_offset >= num_days - 5:
                    base_rev *= 0.95

                noise = random.uniform(0.9, 1.1)
                revenue = round(base_rev * noise, 2)
                orders = int(revenue / random.uniform(150, 300))
                avg_order = round(revenue / max(orders, 1), 2)

                rows.append(
                    f"('{date_str}', '{region}', '{product}', {revenue}, {orders}, {avg_order})"
                )

    values = ", ".join(rows)
    cols = "date, region, product_line, revenue, orders, avg_order_value"
    execute_query(f"INSERT INTO revenue_daily ({cols}) VALUES {values}")
    print(f"Seeded {len(rows)} revenue_daily rows")


def seed_customer_orders() -> None:
    """Seed customer orders with region distribution."""
    rows = []
    base_date = datetime(2026, 7, 1)
    incident_start = datetime(2026, 8, 20)

    for _ in range(5000):
        order_date = base_date + timedelta(
            days=random.randint(0, 55),
            hours=random.randint(0, 23),
            minutes=random.randint(0, 59),
        )
        region = random.choice(REGIONS)
        product = random.choice(PRODUCT_LINES)
        amount = round(random.uniform(50, 5000), 2)

        # 42% of APAC orders suppressed during incident window
        if order_date >= incident_start and region == "APAC":
            if random.random() < 0.42:
                continue

        rows.append(
            f"('ORD-{uuid.uuid4().hex[:8]}', 'CUST-{uuid.uuid4().hex[:6]}', "
            f"'{region}', '{product}', '{order_date.strftime('%Y-%m-%d %H:%M:%S')}', "
            f"{amount}, '{random.choice(['completed', 'pending', 'completed'])}')"
        )

    values = ", ".join(rows)
    execute_query(
        f"INSERT INTO customer_orders (order_id, customer_id, customer_region, "
        f"product_line, order_date, amount, status) VALUES {values}"
    )
    print(f"Seeded {len(rows)} customer_orders rows")


def seed_pipeline_events() -> None:
    """Seed pipeline run history showing failure in incident window."""
    rows = []
    base_date = datetime(2026, 8, 1)

    pipelines = [
        ("PL-001", "customer-revenue"),
        ("PL-002", "order-aggregation"),
        ("PL-003", "region-metrics"),
        ("PL-004", "quality-checks"),
    ]

    for day_offset in range(25):
        date = base_date + timedelta(days=day_offset, hours=2, minutes=30)

        for pipe_id, pipe_name in pipelines:
            status = "SUCCESS"
            error = "NULL"
            completed = (date + timedelta(minutes=random.randint(5, 25))).strftime(
                "%Y-%m-%d %H:%M:%S"
            )
            rows_processed = random.randint(50000, 200000)

            if day_offset >= 23 and pipe_id == "PL-001":
                status = "FAILED"
                error = "'Invalid enum value for column customer_region'"
                completed = "NULL"
                rows_processed = 0

            rows.append(
                f"('{pipe_id}', '{pipe_name}', '{status}', "
                f"'{date.strftime('%Y-%m-%d %H:%M:%S')}', "
                f"{'NULL' if completed == 'NULL' else repr(completed)}, "
                f"{error}, {rows_processed})"
            )

    values = ", ".join(rows)
    execute_query(
        f"INSERT INTO pipeline_events (pipeline_id, pipeline_name, status, "
        f"started_at, completed_at, error_message, rows_processed) VALUES {values}"
    )
    print(f"Seeded {len(rows)} pipeline_events rows")


def seed_data_quality_metrics() -> None:
    """Seed data quality metrics showing degradation in incident window."""
    rows = []
    base_date = datetime(2026, 8, 1)

    tables_columns = [
        ("customer_orders", "customer_region"),
        ("customer_orders", "amount"),
        ("customer_orders", "status"),
        ("revenue_daily", "revenue"),
        ("revenue_daily", "region"),
    ]

    for day_offset in range(25):
        date = base_date + timedelta(days=day_offset)
        date_str = date.strftime("%Y-%m-%d")

        for table, column in tables_columns:
            null_rate = 0.002
            uniqueness = 0.998
            completeness = 0.999
            volume = random.randint(4000, 5000)

            if day_offset >= 23 and column == "customer_region":
                null_rate = 0.187
                uniqueness = 0.85
                completeness = 0.813
                volume = int(volume * 0.55)

            rows.append(
                f"('{date_str}', '{table}', '{column}', "
                f"{null_rate}, {uniqueness}, {completeness}, {volume})"
            )

    values = ", ".join(rows)
    execute_query(
        f"INSERT INTO data_quality_metrics (metric_date, table_name, column_name, "
        f"null_rate, uniqueness, completeness, volume) VALUES {values}"
    )
    print(f"Seeded {len(rows)} data_quality_metrics rows")


def main() -> None:
    print("Seeding ClickHouse...")
    create_tables()
    seed_revenue_daily()
    seed_customer_orders()
    seed_pipeline_events()
    seed_data_quality_metrics()
    print("ClickHouse seeding complete!")


if __name__ == "__main__":
    main()
