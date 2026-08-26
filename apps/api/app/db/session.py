"""DataForge API — Database session."""
from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine
from sqlalchemy.orm import sessionmaker

from apps.api.app.core.config import settings

engine = create_async_engine(settings.database_url, echo=False)
async_session_factory = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db():  # type: ignore[no-untyped-def]
    async with async_session_factory() as session:
        yield session
