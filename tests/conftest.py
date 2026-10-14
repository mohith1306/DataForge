"""Shared test fixtures for DataForge test suite."""

import pytest


@pytest.fixture(autouse=True)
async def _dispose_engine_between_tests():
    """Dispose the async engine around each test so connections are not
    bound to a previous event loop (pytest-asyncio creates a fresh loop
    per test)."""
    from apps.api.app.db.session import engine

    await engine.dispose()
    yield
    await engine.dispose()
