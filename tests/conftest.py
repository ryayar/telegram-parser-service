"""Shared fixtures for database tests.

Uses in-memory SQLite for speed and isolation.
"""
from __future__ import annotations

import pytest_asyncio
import aiosqlite

from shared.database import SQL_CREATE_TABLES, SQL_CREATE_INDEXES


@pytest_asyncio.fixture
async def db():
    """Yield an initialized in-memory database connection."""
    async with aiosqlite.connect(":memory:") as conn:
        conn.row_factory = aiosqlite.Row
        await conn.execute("PRAGMA foreign_keys=ON")
        await conn.executescript(SQL_CREATE_TABLES)
        await conn.executescript(SQL_CREATE_INDEXES)
        await conn.commit()
        yield conn
