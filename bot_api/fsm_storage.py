"""Persistent SQLite-based FSM storage for aiogram 3.

Survives bot restarts — state is written to the same database file.
"""
from __future__ import annotations

import json
from typing import Any, Dict, Optional

import aiosqlite
from aiogram.fsm.storage.base import BaseStorage, StorageKey, StateType

CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS fsm_state (
    bot_id   INTEGER NOT NULL,
    chat_id  INTEGER NOT NULL,
    user_id  INTEGER NOT NULL,
    destiny  TEXT    NOT NULL DEFAULT 'default',
    state    TEXT,
    data     TEXT    NOT NULL DEFAULT '{}',
    PRIMARY KEY (bot_id, chat_id, user_id, destiny)
);
"""

UPSERT_STATE_SQL = """
INSERT INTO fsm_state (bot_id, chat_id, user_id, destiny, state, data)
VALUES (?, ?, ?, ?, ?, '{}')
ON CONFLICT (bot_id, chat_id, user_id, destiny)
DO UPDATE SET state = excluded.state;
"""

UPSERT_DATA_SQL = """
INSERT INTO fsm_state (bot_id, chat_id, user_id, destiny, data)
VALUES (?, ?, ?, ?, ?)
ON CONFLICT (bot_id, chat_id, user_id, destiny)
DO UPDATE SET data = excluded.data;
"""

SELECT_ROW_SQL = """
SELECT state, data FROM fsm_state
WHERE bot_id=? AND chat_id=? AND user_id=? AND destiny=?;
"""


class SQLiteStorage(BaseStorage):
    """FSM storage backed by SQLite — state survives bot restarts."""

    def __init__(self, db_path: str) -> None:
        self._db_path = db_path
        self._db: Optional[aiosqlite.Connection] = None

    async def _conn(self) -> aiosqlite.Connection:
        if self._db is None:
            self._db = await aiosqlite.connect(self._db_path)
            self._db.row_factory = aiosqlite.Row
            await self._db.execute(CREATE_TABLE_SQL)
            await self._db.commit()
        return self._db

    def _key(self, key: StorageKey) -> tuple:
        return (key.bot_id, key.chat_id, key.user_id, key.destiny)

    async def set_state(self, key: StorageKey, state: StateType = None) -> None:
        state_str: Optional[str] = None
        if state is not None:
            state_str = state.state if hasattr(state, "state") else str(state)
        db = await self._conn()
        await db.execute(UPSERT_STATE_SQL, (*self._key(key), state_str))
        await db.commit()

    async def get_state(self, key: StorageKey) -> Optional[str]:
        db = await self._conn()
        async with db.execute(SELECT_ROW_SQL, self._key(key)) as cur:
            row = await cur.fetchone()
        return row["state"] if row else None

    async def set_data(self, key: StorageKey, data: Dict[str, Any]) -> None:
        db = await self._conn()
        await db.execute(UPSERT_DATA_SQL, (*self._key(key), json.dumps(data)))
        await db.commit()

    async def get_data(self, key: StorageKey) -> Dict[str, Any]:
        db = await self._conn()
        async with db.execute(SELECT_ROW_SQL, self._key(key)) as cur:
            row = await cur.fetchone()
        if row and row["data"]:
            return json.loads(row["data"])
        return {}

    async def close(self) -> None:
        if self._db is not None:
            await self._db.close()
            self._db = None
