CREATE DATABASE IF NOT EXISTS dataforge;

CREATE TABLE IF NOT EXISTS dataforge.revenue_daily (
    date Date,
    region String,
    product_line String,
    revenue Float64,
    orders UInt32,
    avg_order_value Float64
) ENGINE = MergeTree()
ORDER BY (date, region, product_line);

CREATE TABLE IF NOT EXISTS dataforge.customer_orders (
    order_id String,
    customer_id String,
    customer_region String,
    product_line String,
    order_date DateTime,
    amount Float64,
    status String
) ENGINE = MergeTree()
ORDER BY (order_date, order_id);

CREATE TABLE IF NOT EXISTS dataforge.pipeline_events (
    pipeline_id String,
    pipeline_name String,
    status String,
    started_at DateTime,
    completed_at Nullable(DateTime),
    error_message Nullable(String),
    rows_processed UInt32
) ENGINE = MergeTree()
ORDER BY (started_at, pipeline_id);

CREATE TABLE IF NOT EXISTS dataforge.data_quality_metrics (
    metric_date Date,
    table_name String,
    column_name String,
    null_rate Float64,
    uniqueness Float64,
    completeness Float64,
    volume UInt32
) ENGINE = MergeTree()
ORDER BY (metric_date, table_name, column_name);
