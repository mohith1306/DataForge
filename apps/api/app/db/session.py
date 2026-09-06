"""DataForge API — Database session."""
import logging
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from apps.api.app.core.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, echo=False)
async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

MIGRATIONS_DIR = Path(__file__).parent / "migrations"


async def ensure_schema():
    """Run database migrations on startup."""
    async with engine.begin() as conn:
        # Run migration files in order
        if MIGRATIONS_DIR.exists():
            migration_files = sorted(MIGRATIONS_DIR.glob("*.sql"))
            for migration_file in migration_files:
                try:
                    sql = migration_file.read_text()
                    # Split by semicolons and execute each statement
                    for statement in sql.split(";"):
                        # Strip comment-only lines before checking
                        lines = statement.strip().split("\n")
                        non_comment_lines = [
                            line for line in lines
                            if not line.strip().startswith("--")
                        ]
                        cleaned = "\n".join(non_comment_lines).strip()
                        
                        if cleaned:
                            await conn.execute(text(cleaned))
                    logger.info("Migration applied: %s", migration_file.name)
                except Exception as e:
                    # Some migrations may fail if already applied
                    logger.debug("Migration %s skipped: %s", migration_file.name, e)

        # Legacy migrations for existing deployments
        try:
            await conn.execute(text(
                "ALTER TABLE incidents "
                "ADD COLUMN IF NOT EXISTS trueforge_session_id VARCHAR(100)"
            ))
        except Exception:
            pass
        try:
            await conn.execute(text(
                "ALTER TABLE incidents "
                "ADD COLUMN IF NOT EXISTS verification_result TEXT"
            ))
        except Exception:
            pass
        try:
            await conn.execute(text(
                "ALTER TABLE incident_events "
                "ALTER COLUMN metadata TYPE JSONB USING metadata::JSONB"
            ))
        except Exception:
            pass
        try:
            await conn.execute(text(
                "ALTER TABLE incidents "
                "ADD COLUMN IF NOT EXISTS connector_id VARCHAR(100)"
            ))
        except Exception:
            pass


async def get_db():  # type: ignore[no-untyped-def]
    async with async_session_factory() as session:
        yield session
