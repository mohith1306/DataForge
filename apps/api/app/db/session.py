"""DataForge API — Database session."""
import logging

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from apps.api.app.core.config import settings

logger = logging.getLogger(__name__)

engine = create_async_engine(
    settings.database_url,
    echo=False,
    pool_size=5,
    max_overflow=10,
    pool_pre_ping=True,
)
async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def ensure_schema():
    """Run database migrations on startup using Alembic."""
    import asyncio
    from alembic.config import Config
    from alembic import command

    alembic_cfg = Config("alembic.ini")
    alembic_cfg.set_main_option("sqlalchemy.url", settings.database_url)

    def _run_upgrade():
        command.upgrade(alembic_cfg, "head")

    try:
        await asyncio.to_thread(_run_upgrade)
        logger.info("Database migrations applied successfully")
    except Exception as e:
        logger.error("Migration failed: %s", e)
        raise


async def get_db():
    """Dependency that provides a database session."""
    async with async_session_factory() as session:
        yield session
