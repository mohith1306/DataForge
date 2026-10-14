#!/usr/bin/env python3
"""Database schema repair script.

Handles databases that were created before Alembic versioning was in place,
or that have drifted from the expected schema. Safe to run multiple times.

Usage:
    uv run python scripts/repair_schema.py
    uv run python scripts/repair_schema.py --dry-run
"""

from __future__ import annotations

import argparse
import asyncio
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine

from apps.api.app.core.config import settings
from apps.api.app.db.models import Base


async def get_existing_tables(conn) -> set[str]:
    res = await conn.execute(
        text("SELECT table_name FROM information_schema.tables WHERE table_schema='public'")
    )
    return {r[0] for r in res}


async def get_existing_columns(conn, table_name: str) -> set[str]:
    res = await conn.execute(
        text(
            "SELECT column_name FROM information_schema.columns "
            "WHERE table_name=:t AND table_schema='public'"
        ),
        {"t": table_name},
    )
    return {r[0] for r in res}


async def repair(dry_run: bool = False) -> None:
    engine = create_async_engine(settings.database_url, echo=False)

    created_tables: list[str] = []
    added_columns: list[str] = []
    skipped: list[str] = []

    async with engine.begin() as conn:
        existing = await get_existing_tables(conn)

        # 1. Create missing tables
        for table in Base.metadata.sorted_tables:
            if table.name in existing:
                continue
            if dry_run:
                created_tables.append(table.name)
                continue
            table.create(bind=conn.sync_connection, checkfirst=True)
            created_tables.append(table.name)

        # 2. Add missing columns
        for table in Base.metadata.sorted_tables:
            if table.name not in existing and not dry_run:
                pass  # table was just created, columns exist
            db_cols = await get_existing_columns(conn, table.name)
            for col in table.columns:
                if col.name in db_cols:
                    continue
                col_type = col.type.compile(conn.sync_connection.dialect)
                nullable = "NULL" if col.nullable else "NOT NULL"
                if dry_run:
                    added_columns.append(f"{table.name}.{col.name}")
                    continue
                try:
                    await conn.execute(
                        text(f'ALTER TABLE {table.name} ADD COLUMN "{col.name}" {col_type} {nullable}')
                    )
                    added_columns.append(f"{table.name}.{col.name}")
                except Exception as e:
                    skipped.append(f"{table.name}.{col.name}: {type(e).__name__}")

        # 3. Ensure alembic_version exists and is stamped
        if not dry_run:
            await conn.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS alembic_version "
                    "(version_num VARCHAR(32) NOT NULL, PRIMARY KEY (version_num))"
                )
            )
            res = await conn.execute(text("SELECT version_num FROM alembic_version"))
            current = res.scalar_one_or_none()
            if current is None:
                await conn.execute(
                    text("INSERT INTO alembic_version (version_num) VALUES ('003')")
                )
                print("Stamped alembic_version at 003")
            else:
                print(f"alembic_version already at {current}")

    await engine.dispose()

    # Report
    mode = "[DRY RUN] " if dry_run else ""
    print(f"\n{mode}Schema repair complete:")
    if created_tables:
        print(f"  Created tables ({len(created_tables)}): {', '.join(created_tables)}")
    if added_columns:
        print(f"  Added columns ({len(added_columns)}):")
        for c in added_columns:
            print(f"    + {c}")
    if skipped:
        print(f"  Skipped ({len(skipped)}):")
        for s in skipped:
            print(f"    ~ {s}")
    if not created_tables and not added_columns and not skipped:
        print("  No changes needed — schema is up to date")


def main() -> None:
    parser = argparse.ArgumentParser(description="Repair database schema")
    parser.add_argument("--dry-run", action="store_true", help="Show what would change without applying")
    args = parser.parse_args()
    asyncio.run(repair(dry_run=args.dry_run))


if __name__ == "__main__":
    main()
