"""DataForge API — Database session."""
import logging

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from apps.api.app.core.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(settings.database_url, echo=False)
async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def ensure_schema():
    """Add missing columns to existing tables on startup."""
    async with engine.begin() as conn:
        try:
            await conn.execute(text(
                "ALTER TABLE incidents "
                "ADD COLUMN IF NOT EXISTS trueforge_session_id VARCHAR(100)"
            ))
            logger.info("Schema migration: ensured trueforge_session_id column")
        except Exception as e:
            logger.warning(f"Schema migration skipped: {e}")
        try:
            await conn.execute(text(
                "ALTER TABLE incidents "
                "ADD COLUMN IF NOT EXISTS verification_result TEXT"
            ))
            logger.info("Schema migration: ensured verification_result column")
        except Exception as e:
            logger.warning(f"Schema migration skipped: {e}")


async def get_db():  # type: ignore[no-untyped-def]
    async with async_session_factory() as session:
        yield session
