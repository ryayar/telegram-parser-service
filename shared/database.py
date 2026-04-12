"""Async SQLite database layer.

Provides:
- init_db()          -- create tables and indexes
- get_connection()   -- async context manager for aiosqlite connection
- CRUD functions grouped by table
"""
from __future__ import annotations

from contextlib import asynccontextmanager
from collections.abc import AsyncGenerator
from datetime import datetime, timedelta

import aiosqlite

from shared.config import settings
from shared.models import (
    User,
    Group,
    UserGroup,
    Pattern,
    Match,
    PendingJoin,
    GroupStatus,
    PatternType,
    PendingJoinStatus,
)


# ─── Connection Management ───────────────────────────────────────────


@asynccontextmanager
async def get_connection() -> AsyncGenerator[aiosqlite.Connection, None]:
    """Yield an aiosqlite connection with WAL mode and foreign keys enabled."""
    db_path = settings.db_full_path
    db_path.parent.mkdir(parents=True, exist_ok=True)

    async with aiosqlite.connect(str(db_path)) as db:
        db.row_factory = aiosqlite.Row
        await db.execute("PRAGMA journal_mode=WAL")
        await db.execute("PRAGMA foreign_keys=ON")
        yield db


# ─── Schema ──────────────────────────────────────────────────────────


SQL_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS users (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id       INTEGER NOT NULL UNIQUE,
    timezone          INTEGER NOT NULL DEFAULT 3,
    quiet_hours_start TEXT,
    quiet_hours_end   TEXT,
    is_active             INTEGER NOT NULL DEFAULT 1,
    new_group_patterns    INTEGER NOT NULL DEFAULT 0,
    new_pattern_groups    INTEGER NOT NULL DEFAULT 0,
    group_duplicates      INTEGER NOT NULL DEFAULT 0,
    created_at            TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS groups (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    telegram_id INTEGER,
    link        TEXT NOT NULL,
    title       TEXT NOT NULL DEFAULT '',
    status      TEXT NOT NULL DEFAULT 'pending',
    created_at  TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS user_groups (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    group_id   INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    created_at TEXT NOT NULL DEFAULT (datetime('now')),
    PRIMARY KEY (user_id, group_id)
);

CREATE TABLE IF NOT EXISTS patterns (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    pattern_type TEXT NOT NULL DEFAULT 'exact',
    value        TEXT NOT NULL,
    created_at   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS matches (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id      INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    group_id     INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    pattern_id   INTEGER REFERENCES patterns(id) ON DELETE SET NULL,
    message_text TEXT NOT NULL,
    text_hash    TEXT NOT NULL,
    message_link TEXT,
    media_path   TEXT,
    send_after   TEXT,
    created_at   TEXT NOT NULL DEFAULT (datetime('now')),
    sent_at      TEXT
);

CREATE TABLE IF NOT EXISTS pending_joins (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    link          TEXT NOT NULL,
    status        TEXT NOT NULL DEFAULT 'pending',
    error_message TEXT,
    created_at    TEXT NOT NULL DEFAULT (datetime('now')),
    updated_at    TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS pattern_groups (
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    pattern_id INTEGER NOT NULL REFERENCES patterns(id) ON DELETE CASCADE,
    group_id   INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    PRIMARY KEY (user_id, pattern_id, group_id)
);

CREATE TABLE IF NOT EXISTS link_clicks (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    match_id   INTEGER REFERENCES matches(id) ON DELETE SET NULL,
    group_id   INTEGER NOT NULL REFERENCES groups(id) ON DELETE CASCADE,
    user_id    INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
    clicked_at TEXT NOT NULL DEFAULT (datetime('now'))
);
"""

SQL_CREATE_INDEXES = """
CREATE INDEX IF NOT EXISTS idx_users_telegram_id
    ON users(telegram_id);
CREATE INDEX IF NOT EXISTS idx_groups_telegram_id
    ON groups(telegram_id);
CREATE INDEX IF NOT EXISTS idx_groups_status
    ON groups(status);
CREATE INDEX IF NOT EXISTS idx_patterns_user_id
    ON patterns(user_id);
CREATE INDEX IF NOT EXISTS idx_matches_user_id
    ON matches(user_id);
CREATE INDEX IF NOT EXISTS idx_matches_text_hash
    ON matches(text_hash);
CREATE INDEX IF NOT EXISTS idx_matches_sent_at
    ON matches(sent_at);
CREATE INDEX IF NOT EXISTS idx_matches_user_hash
    ON matches(user_id, text_hash);
CREATE INDEX IF NOT EXISTS idx_matches_created_at
    ON matches(created_at);
CREATE INDEX IF NOT EXISTS idx_pending_joins_status
    ON pending_joins(status);
CREATE INDEX IF NOT EXISTS idx_pattern_groups_group
    ON pattern_groups(group_id, user_id);
CREATE INDEX IF NOT EXISTS idx_pattern_groups_pattern
    ON pattern_groups(pattern_id);
CREATE INDEX IF NOT EXISTS idx_link_clicks_group_id
    ON link_clicks(group_id);
CREATE INDEX IF NOT EXISTS idx_link_clicks_clicked_at
    ON link_clicks(clicked_at);
CREATE INDEX IF NOT EXISTS idx_link_clicks_user_id
    ON link_clicks(user_id);
"""


async def _run_migrations(db: aiosqlite.Connection) -> None:
    """Apply incremental schema migrations (idempotent)."""
    for sql in [
        "ALTER TABLE matches ADD COLUMN media_path TEXT",
        "ALTER TABLE matches ADD COLUMN send_after TEXT",
        "ALTER TABLE users ADD COLUMN new_group_patterns INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE users ADD COLUMN new_pattern_groups INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE users ADD COLUMN group_duplicates INTEGER NOT NULL DEFAULT 0",
    ]:
        try:
            await db.execute(sql)
            await db.commit()
        except Exception:
            pass  # Column already exists


async def init_db() -> None:
    """Create all tables and indexes. Safe to call multiple times."""
    async with get_connection() as db:
        await db.executescript(SQL_CREATE_TABLES)
        await db.executescript(SQL_CREATE_INDEXES)
        await db.commit()
        await _run_migrations(db)


async def init_db_with_connection(db: aiosqlite.Connection) -> None:
    """Create tables and indexes using an existing connection (for testing)."""
    await db.executescript(SQL_CREATE_TABLES)
    await db.executescript(SQL_CREATE_INDEXES)
    await db.commit()


# ─── Row → Dataclass Converters ──────────────────────────────────────


def _row_to_user(row: aiosqlite.Row) -> User:
    keys = row.keys()
    return User(
        id=row["id"],
        telegram_id=row["telegram_id"],
        timezone=row["timezone"],
        quiet_hours_start=row["quiet_hours_start"],
        quiet_hours_end=row["quiet_hours_end"],
        is_active=bool(row["is_active"]),
        new_group_patterns=bool(row["new_group_patterns"]) if "new_group_patterns" in keys else False,
        new_pattern_groups=bool(row["new_pattern_groups"]) if "new_pattern_groups" in keys else False,
        group_duplicates=bool(row["group_duplicates"]) if "group_duplicates" in keys else False,
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _row_to_group(row: aiosqlite.Row) -> Group:
    return Group(
        id=row["id"],
        telegram_id=row["telegram_id"],
        link=row["link"],
        title=row["title"],
        status=GroupStatus(row["status"]),
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _row_to_pattern(row: aiosqlite.Row) -> Pattern:
    return Pattern(
        id=row["id"],
        user_id=row["user_id"],
        pattern_type=PatternType(row["pattern_type"]),
        value=row["value"],
        created_at=datetime.fromisoformat(row["created_at"]),
    )


def _row_to_match(row: aiosqlite.Row) -> Match:
    return Match(
        id=row["id"],
        user_id=row["user_id"],
        group_id=row["group_id"],
        pattern_id=row["pattern_id"],
        message_text=row["message_text"],
        text_hash=row["text_hash"],
        message_link=row["message_link"],
        media_path=row["media_path"] if "media_path" in row.keys() else None,
        send_after=datetime.fromisoformat(row["send_after"]) if row["send_after"] else None,
        created_at=datetime.fromisoformat(row["created_at"]),
        sent_at=datetime.fromisoformat(row["sent_at"]) if row["sent_at"] else None,
    )


def _row_to_pending_join(row: aiosqlite.Row) -> PendingJoin:
    return PendingJoin(
        id=row["id"],
        link=row["link"],
        status=PendingJoinStatus(row["status"]),
        error_message=row["error_message"],
        created_at=datetime.fromisoformat(row["created_at"]),
        updated_at=datetime.fromisoformat(row["updated_at"]),
    )


# ─── Users CRUD ──────────────────────────────────────────────────────


async def get_or_create_user(db: aiosqlite.Connection, telegram_id: int) -> User:
    """Get existing user or create a new one."""
    cursor = await db.execute(
        "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
    )
    row = await cursor.fetchone()
    if row:
        return _row_to_user(row)

    cursor = await db.execute(
        "INSERT INTO users (telegram_id) VALUES (?)", (telegram_id,)
    )
    await db.commit()
    cursor = await db.execute("SELECT * FROM users WHERE id = ?", (cursor.lastrowid,))
    row = await cursor.fetchone()
    return _row_to_user(row)


async def get_user_by_telegram_id(
    db: aiosqlite.Connection, telegram_id: int
) -> User | None:
    cursor = await db.execute(
        "SELECT * FROM users WHERE telegram_id = ?", (telegram_id,)
    )
    row = await cursor.fetchone()
    return _row_to_user(row) if row else None


async def update_user(db: aiosqlite.Connection, user_id: int, **fields) -> None:
    """Update arbitrary user fields. E.g. update_user(db, 1, timezone=5)."""
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values())
    values.append(user_id)
    await db.execute(f"UPDATE users SET {set_clause} WHERE id = ?", values)
    await db.commit()


# ─── Groups CRUD ─────────────────────────────────────────────────────


async def create_group(
    db: aiosqlite.Connection, link: str, title: str = ""
) -> Group:
    cursor = await db.execute(
        "INSERT INTO groups (link, title) VALUES (?, ?)", (link, title)
    )
    await db.commit()
    cursor = await db.execute("SELECT * FROM groups WHERE id = ?", (cursor.lastrowid,))
    row = await cursor.fetchone()
    return _row_to_group(row)


async def get_group_by_id(db: aiosqlite.Connection, group_id: int) -> Group | None:
    cursor = await db.execute("SELECT * FROM groups WHERE id = ?", (group_id,))
    row = await cursor.fetchone()
    return _row_to_group(row) if row else None


async def get_group_by_telegram_id(
    db: aiosqlite.Connection, telegram_id: int
) -> Group | None:
    cursor = await db.execute(
        "SELECT * FROM groups WHERE telegram_id = ?", (telegram_id,)
    )
    row = await cursor.fetchone()
    return _row_to_group(row) if row else None


async def get_group_by_link(db: aiosqlite.Connection, link: str) -> Group | None:
    cursor = await db.execute("SELECT * FROM groups WHERE link = ?", (link,))
    row = await cursor.fetchone()
    return _row_to_group(row) if row else None


async def get_groups_by_status(
    db: aiosqlite.Connection, status: GroupStatus
) -> list[Group]:
    cursor = await db.execute(
        "SELECT * FROM groups WHERE status = ?", (status.value,)
    )
    rows = await cursor.fetchall()
    return [_row_to_group(r) for r in rows]


async def update_group(db: aiosqlite.Connection, group_id: int, **fields) -> None:
    if not fields:
        return
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values())
    values.append(group_id)
    await db.execute(f"UPDATE groups SET {set_clause} WHERE id = ?", values)
    await db.commit()


async def delete_group(db: aiosqlite.Connection, group_id: int) -> None:
    await db.execute("DELETE FROM groups WHERE id = ?", (group_id,))
    await db.commit()


# ─── User-Groups (many-to-many) ─────────────────────────────────────


async def add_user_to_group(
    db: aiosqlite.Connection, user_id: int, group_id: int
) -> None:
    await db.execute(
        "INSERT OR IGNORE INTO user_groups (user_id, group_id) VALUES (?, ?)",
        (user_id, group_id),
    )
    await db.commit()


async def remove_user_from_group(
    db: aiosqlite.Connection, user_id: int, group_id: int
) -> None:
    await db.execute(
        "DELETE FROM user_groups WHERE user_id = ? AND group_id = ?",
        (user_id, group_id),
    )
    await db.commit()


async def get_user_groups(db: aiosqlite.Connection, user_id: int) -> list[Group]:
    cursor = await db.execute(
        """
        SELECT g.* FROM groups g
        JOIN user_groups ug ON g.id = ug.group_id
        WHERE ug.user_id = ?
        ORDER BY g.title
        """,
        (user_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_group(r) for r in rows]


async def get_group_users(db: aiosqlite.Connection, group_id: int) -> list[User]:
    cursor = await db.execute(
        """
        SELECT u.* FROM users u
        JOIN user_groups ug ON u.id = ug.user_id
        WHERE ug.group_id = ? AND u.is_active = 1
        ORDER BY u.id
        """,
        (group_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_user(r) for r in rows]


async def get_users_for_telegram_group(
    db: aiosqlite.Connection, group_telegram_id: int
) -> list[User]:
    """Get all active users subscribed to a group by its Telegram chat ID.

    This is the hot-path query used by the userbot monitor.
    """
    cursor = await db.execute(
        """
        SELECT u.* FROM users u
        JOIN user_groups ug ON u.id = ug.user_id
        JOIN groups g ON g.id = ug.group_id
        WHERE g.telegram_id = ? AND u.is_active = 1
        """,
        (group_telegram_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_user(r) for r in rows]


# ─── Patterns CRUD ──────────────────────────────────────────────────


async def create_pattern(
    db: aiosqlite.Connection,
    user_id: int,
    value: str,
    pattern_type: PatternType = PatternType.EXACT,
) -> Pattern:
    cursor = await db.execute(
        "INSERT INTO patterns (user_id, value, pattern_type) VALUES (?, ?, ?)",
        (user_id, value, pattern_type.value),
    )
    await db.commit()
    cursor = await db.execute(
        "SELECT * FROM patterns WHERE id = ?", (cursor.lastrowid,)
    )
    row = await cursor.fetchone()
    return _row_to_pattern(row)


async def get_user_patterns(
    db: aiosqlite.Connection, user_id: int
) -> list[Pattern]:
    cursor = await db.execute(
        "SELECT * FROM patterns WHERE user_id = ? ORDER BY created_at",
        (user_id,),
    )
    rows = await cursor.fetchall()
    return [_row_to_pattern(r) for r in rows]


async def delete_pattern(db: aiosqlite.Connection, pattern_id: int) -> None:
    await db.execute("DELETE FROM patterns WHERE id = ?", (pattern_id,))
    await db.commit()


# ─── Matches CRUD ───────────────────────────────────────────────────


async def create_match(
    db: aiosqlite.Connection,
    user_id: int,
    group_id: int,
    message_text: str,
    text_hash: str,
    pattern_id: int | None = None,
    message_link: str | None = None,
    send_after: str | None = None,
) -> Match:
    cursor = await db.execute(
        """
        INSERT INTO matches (user_id, group_id, pattern_id, message_text, text_hash, message_link, send_after)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (user_id, group_id, pattern_id, message_text, text_hash, message_link, send_after),
    )
    await db.commit()
    cursor = await db.execute(
        "SELECT * FROM matches WHERE id = ?", (cursor.lastrowid,)
    )
    row = await cursor.fetchone()
    return _row_to_match(row)


async def check_duplicate(
    db: aiosqlite.Connection,
    user_id: int,
    text_hash: str,
    hours: int = 2,
) -> bool:
    """Check if a match with same hash exists for this user within N hours."""
    cursor = await db.execute(
        """
        SELECT 1 FROM matches
        WHERE user_id = ? AND text_hash = ?
              AND created_at > datetime('now', ?)
        LIMIT 1
        """,
        (user_id, text_hash, f"-{hours} hours"),
    )
    row = await cursor.fetchone()
    return row is not None


async def get_unsent_matches(
    db: aiosqlite.Connection, limit: int = 50
) -> list[Match]:
    """Return unsent matches that are ready to deliver (send_after has passed or is NULL)."""
    cursor = await db.execute(
        """
        SELECT * FROM matches
        WHERE sent_at IS NULL
          AND (send_after IS NULL OR send_after <= datetime('now'))
        ORDER BY created_at
        LIMIT ?
        """,
        (limit,),
    )
    rows = await cursor.fetchall()
    return [_row_to_match(r) for r in rows]


async def get_grouped_matches(
    db: aiosqlite.Connection,
    user_id: int,
    text_hash: str,
) -> list[Match]:
    """Return all unsent ready matches for a user with the same text hash (for grouping)."""
    cursor = await db.execute(
        """
        SELECT * FROM matches
        WHERE user_id = ? AND text_hash = ? AND sent_at IS NULL
          AND (send_after IS NULL OR send_after <= datetime('now'))
        ORDER BY created_at
        """,
        (user_id, text_hash),
    )
    rows = await cursor.fetchall()
    return [_row_to_match(r) for r in rows]


async def mark_matches_sent_batch(db: aiosqlite.Connection, match_ids: list[int]) -> None:
    """Mark multiple matches as sent in a single query."""
    if not match_ids:
        return
    placeholders = ",".join("?" * len(match_ids))
    await db.execute(
        f"UPDATE matches SET sent_at = datetime('now') WHERE id IN ({placeholders})",
        match_ids,
    )
    await db.commit()


async def mark_match_sent(db: aiosqlite.Connection, match_id: int) -> None:
    await db.execute(
        "UPDATE matches SET sent_at = datetime('now') WHERE id = ?", (match_id,)
    )
    await db.commit()


async def update_match_media(db: aiosqlite.Connection, match_id: int, media_path: str) -> None:
    await db.execute(
        "UPDATE matches SET media_path = ? WHERE id = ?", (media_path, match_id)
    )
    await db.commit()


async def get_user_matches(
    db: aiosqlite.Connection,
    user_id: int,
    limit: int = 20,
    offset: int = 0,
) -> list[Match]:
    cursor = await db.execute(
        """
        SELECT * FROM matches
        WHERE user_id = ?
        ORDER BY id DESC
        LIMIT ? OFFSET ?
        """,
        (user_id, limit, offset),
    )
    rows = await cursor.fetchall()
    return [_row_to_match(r) for r in rows]


async def count_user_matches(
    db: aiosqlite.Connection,
    user_id: int,
    since: datetime | None = None,
) -> int:
    if since:
        since_str = since.strftime("%Y-%m-%d %H:%M:%S")
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM matches WHERE user_id = ? AND created_at > ?",
            (user_id, since_str),
        )
    else:
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM matches WHERE user_id = ?",
            (user_id,),
        )
    row = await cursor.fetchone()
    return row["cnt"]


# ─── Pending Joins CRUD ─────────────────────────────────────────────


async def create_pending_join(db: aiosqlite.Connection, link: str) -> PendingJoin:
    cursor = await db.execute(
        "INSERT INTO pending_joins (link) VALUES (?)", (link,)
    )
    await db.commit()
    cursor = await db.execute(
        "SELECT * FROM pending_joins WHERE id = ?", (cursor.lastrowid,)
    )
    row = await cursor.fetchone()
    return _row_to_pending_join(row)


async def get_pending_joins(
    db: aiosqlite.Connection,
    status: PendingJoinStatus = PendingJoinStatus.PENDING,
) -> list[PendingJoin]:
    cursor = await db.execute(
        "SELECT * FROM pending_joins WHERE status = ? ORDER BY created_at",
        (status.value,),
    )
    rows = await cursor.fetchall()
    return [_row_to_pending_join(r) for r in rows]


async def update_pending_join(
    db: aiosqlite.Connection, join_id: int, **fields
) -> None:
    if not fields:
        return
    fields["updated_at"] = datetime.utcnow().isoformat()
    set_clause = ", ".join(f"{k} = ?" for k in fields)
    values = list(fields.values())
    values.append(join_id)
    await db.execute(
        f"UPDATE pending_joins SET {set_clause} WHERE id = ?", values
    )
    await db.commit()


# ─── Pattern-Groups CRUD ─────────────────────────────────────────────


async def add_pattern_to_group(
    db: aiosqlite.Connection, user_id: int, pattern_id: int, group_id: int
) -> None:
    """Activate a pattern for a specific group (idempotent)."""
    await db.execute(
        "INSERT OR IGNORE INTO pattern_groups (user_id, pattern_id, group_id) VALUES (?, ?, ?)",
        (user_id, pattern_id, group_id),
    )
    await db.commit()


async def remove_pattern_from_group(
    db: aiosqlite.Connection, user_id: int, pattern_id: int, group_id: int
) -> None:
    """Deactivate a pattern for a specific group."""
    await db.execute(
        "DELETE FROM pattern_groups WHERE user_id = ? AND pattern_id = ? AND group_id = ?",
        (user_id, pattern_id, group_id),
    )
    await db.commit()


async def set_all_patterns_for_group(
    db: aiosqlite.Connection, user_id: int, group_id: int
) -> None:
    """Activate ALL user patterns for a group (used on group add and 'select all')."""
    cursor = await db.execute(
        "SELECT id FROM patterns WHERE user_id = ?", (user_id,)
    )
    rows = await cursor.fetchall()
    for row in rows:
        await db.execute(
            "INSERT OR IGNORE INTO pattern_groups (user_id, pattern_id, group_id) VALUES (?, ?, ?)",
            (user_id, row["id"], group_id),
        )
    await db.commit()


async def clear_all_patterns_for_group(
    db: aiosqlite.Connection, user_id: int, group_id: int
) -> None:
    """Deactivate ALL patterns for a group ('deselect all')."""
    await db.execute(
        "DELETE FROM pattern_groups WHERE user_id = ? AND group_id = ?",
        (user_id, group_id),
    )
    await db.commit()


async def get_active_pattern_ids_for_group(
    db: aiosqlite.Connection, user_id: int, group_id: int
) -> set[int]:
    """Return set of pattern IDs active for this group."""
    cursor = await db.execute(
        "SELECT pattern_id FROM pattern_groups WHERE user_id = ? AND group_id = ?",
        (user_id, group_id),
    )
    rows = await cursor.fetchall()
    return {row["pattern_id"] for row in rows}


async def get_patterns_for_user_in_group(
    db: aiosqlite.Connection, user_id: int, group_telegram_id: int
) -> list[Pattern]:
    """Return patterns active for a user in a specific Telegram group.

    This is the hot-path query used by the userbot monitor.
    """
    cursor = await db.execute(
        """
        SELECT p.* FROM patterns p
        JOIN pattern_groups pg ON pg.pattern_id = p.id
        JOIN groups g ON g.id = pg.group_id
        WHERE pg.user_id = ? AND g.telegram_id = ?
        """,
        (user_id, group_telegram_id),
    )
    rows = await cursor.fetchall()
    return [_row_to_pattern(r) for r in rows]


# ─── Link Clicks CRUD ───────────────────────────────────────────────


async def create_link_click(
    db: aiosqlite.Connection,
    match_id: int | None,
    group_id: int,
    user_id: int,
) -> None:
    await db.execute(
        "INSERT INTO link_clicks (match_id, group_id, user_id) VALUES (?, ?, ?)",
        (match_id, group_id, user_id),
    )
    await db.commit()


async def get_click_stats(
    db: aiosqlite.Connection,
    days: int = 30,
    limit: int = 15,
) -> list[aiosqlite.Row]:
    """Return top groups by click count over the last N days."""
    cursor = await db.execute(
        """
        SELECT g.title, g.link, COUNT(lc.id) AS clicks
        FROM link_clicks lc
        JOIN groups g ON g.id = lc.group_id
        WHERE lc.clicked_at > datetime('now', ?)
        GROUP BY lc.group_id
        ORDER BY clicks DESC
        LIMIT ?
        """,
        (f"-{days} days", limit),
    )
    return await cursor.fetchall()


async def get_total_clicks(db: aiosqlite.Connection, days: int = 30) -> int:
    cursor = await db.execute(
        "SELECT COUNT(*) AS cnt FROM link_clicks WHERE clicked_at > datetime('now', ?)",
        (f"-{days} days",),
    )
    row = await cursor.fetchone()
    return row["cnt"]


# ─── Pattern-Groups CRUD ─────────────────────────────────────────────


async def add_pattern_to_all_groups(
    db: aiosqlite.Connection, user_id: int, pattern_id: int
) -> None:
    """Activate a new pattern for ALL groups the user is subscribed to (used on pattern add)."""
    cursor = await db.execute(
        "SELECT group_id FROM user_groups WHERE user_id = ?", (user_id,)
    )
    rows = await cursor.fetchall()
    for row in rows:
        await db.execute(
            "INSERT OR IGNORE INTO pattern_groups (user_id, pattern_id, group_id) VALUES (?, ?, ?)",
            (user_id, pattern_id, row["group_id"]),
        )
    await db.commit()
