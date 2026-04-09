"""Tests for shared/database.py — schema, CRUD, foreign keys, deduplication."""
from __future__ import annotations

from datetime import datetime, timedelta

import pytest
import aiosqlite

from shared.database import (
    get_or_create_user,
    get_user_by_telegram_id,
    update_user,
    create_group,
    get_group_by_id,
    get_group_by_link,
    get_groups_by_status,
    update_group,
    delete_group,
    add_user_to_group,
    remove_user_from_group,
    get_user_groups,
    get_group_users,
    get_users_for_telegram_group,
    create_pattern,
    get_user_patterns,
    delete_pattern,
    create_match,
    check_duplicate,
    get_unsent_matches,
    mark_match_sent,
    get_user_matches,
    count_user_matches,
    create_pending_join,
    get_pending_joins,
    update_pending_join,
    add_pattern_to_group,
    remove_pattern_from_group,
    set_all_patterns_for_group,
    clear_all_patterns_for_group,
    get_active_pattern_ids_for_group,
    get_patterns_for_user_in_group,
    add_pattern_to_all_groups,
)
from shared.models import GroupStatus, PatternType, PendingJoinStatus


# ─── Schema Tests ────────────────────────────────────────────────────


class TestSchema:
    async def test_tables_exist(self, db):
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
        )
        tables = [row["name"] for row in await cursor.fetchall()]
        for table in ["groups", "matches", "pattern_groups", "patterns", "pending_joins", "user_groups", "users"]:
            assert table in tables

    async def test_indexes_exist(self, db):
        cursor = await db.execute(
            "SELECT name FROM sqlite_master WHERE type='index' AND name LIKE 'idx_%'"
        )
        indexes = {row["name"] for row in await cursor.fetchall()}
        expected = {
            "idx_users_telegram_id",
            "idx_groups_telegram_id",
            "idx_groups_status",
            "idx_patterns_user_id",
            "idx_matches_user_id",
            "idx_matches_text_hash",
            "idx_matches_sent_at",
            "idx_matches_user_hash",
            "idx_matches_created_at",
            "idx_pending_joins_status",
        }
        assert expected.issubset(indexes)


# ─── Users CRUD ──────────────────────────────────────────────────────


class TestUsersCRUD:
    async def test_get_or_create_user_creates_new(self, db):
        user = await get_or_create_user(db, telegram_id=111)
        assert user.telegram_id == 111
        assert user.timezone == 3
        assert user.is_active is True
        assert user.id is not None

    async def test_get_or_create_user_returns_existing(self, db):
        user1 = await get_or_create_user(db, telegram_id=222)
        user2 = await get_or_create_user(db, telegram_id=222)
        assert user1.id == user2.id

    async def test_get_user_by_telegram_id(self, db):
        await get_or_create_user(db, telegram_id=333)
        user = await get_user_by_telegram_id(db, 333)
        assert user is not None
        assert user.telegram_id == 333

    async def test_get_user_by_telegram_id_not_found(self, db):
        user = await get_user_by_telegram_id(db, 999999)
        assert user is None

    async def test_update_user_timezone(self, db):
        user = await get_or_create_user(db, telegram_id=444)
        await update_user(db, user.id, timezone=5)
        updated = await get_user_by_telegram_id(db, 444)
        assert updated.timezone == 5

    async def test_update_user_quiet_hours(self, db):
        user = await get_or_create_user(db, telegram_id=555)
        await update_user(db, user.id, quiet_hours_start="23:00", quiet_hours_end="08:00")
        updated = await get_user_by_telegram_id(db, 555)
        assert updated.quiet_hours_start == "23:00"
        assert updated.quiet_hours_end == "08:00"

    async def test_update_user_is_active(self, db):
        user = await get_or_create_user(db, telegram_id=666)
        await update_user(db, user.id, is_active=0)
        updated = await get_user_by_telegram_id(db, 666)
        assert updated.is_active is False


# ─── Groups CRUD ─────────────────────────────────────────────────────


class TestGroupsCRUD:
    async def test_create_group(self, db):
        group = await create_group(db, link="https://t.me/test_group", title="Test")
        assert group.link == "https://t.me/test_group"
        assert group.title == "Test"
        assert group.status == GroupStatus.PENDING

    async def test_get_group_by_id(self, db):
        group = await create_group(db, link="https://t.me/g1")
        fetched = await get_group_by_id(db, group.id)
        assert fetched is not None
        assert fetched.link == "https://t.me/g1"

    async def test_get_group_by_id_not_found(self, db):
        fetched = await get_group_by_id(db, 999)
        assert fetched is None

    async def test_get_group_by_link(self, db):
        await create_group(db, link="https://t.me/g2")
        fetched = await get_group_by_link(db, "https://t.me/g2")
        assert fetched is not None

    async def test_get_groups_by_status(self, db):
        await create_group(db, link="https://t.me/g3")
        await create_group(db, link="https://t.me/g4")
        groups = await get_groups_by_status(db, GroupStatus.PENDING)
        assert len(groups) == 2

    async def test_update_group_status(self, db):
        group = await create_group(db, link="https://t.me/g5")
        await update_group(db, group.id, status="active", telegram_id=-100123)
        updated = await get_group_by_id(db, group.id)
        assert updated.status == GroupStatus.ACTIVE
        assert updated.telegram_id == -100123

    async def test_delete_group(self, db):
        group = await create_group(db, link="https://t.me/g6")
        await delete_group(db, group.id)
        fetched = await get_group_by_id(db, group.id)
        assert fetched is None


# ─── User-Groups ─────────────────────────────────────────────────────


class TestUserGroups:
    async def test_add_user_to_group(self, db):
        user = await get_or_create_user(db, 1001)
        group = await create_group(db, link="https://t.me/ug1")
        await add_user_to_group(db, user.id, group.id)
        groups = await get_user_groups(db, user.id)
        assert len(groups) == 1
        assert groups[0].id == group.id

    async def test_add_user_to_group_idempotent(self, db):
        user = await get_or_create_user(db, 1002)
        group = await create_group(db, link="https://t.me/ug2")
        await add_user_to_group(db, user.id, group.id)
        await add_user_to_group(db, user.id, group.id)  # duplicate
        groups = await get_user_groups(db, user.id)
        assert len(groups) == 1

    async def test_remove_user_from_group(self, db):
        user = await get_or_create_user(db, 1003)
        group = await create_group(db, link="https://t.me/ug3")
        await add_user_to_group(db, user.id, group.id)
        await remove_user_from_group(db, user.id, group.id)
        groups = await get_user_groups(db, user.id)
        assert len(groups) == 0

    async def test_get_group_users(self, db):
        user1 = await get_or_create_user(db, 1004)
        user2 = await get_or_create_user(db, 1005)
        group = await create_group(db, link="https://t.me/ug4")
        await add_user_to_group(db, user1.id, group.id)
        await add_user_to_group(db, user2.id, group.id)
        users = await get_group_users(db, group.id)
        assert len(users) == 2

    async def test_get_group_users_only_active(self, db):
        user1 = await get_or_create_user(db, 1006)
        user2 = await get_or_create_user(db, 1007)
        await update_user(db, user2.id, is_active=0)
        group = await create_group(db, link="https://t.me/ug5")
        await add_user_to_group(db, user1.id, group.id)
        await add_user_to_group(db, user2.id, group.id)
        users = await get_group_users(db, group.id)
        assert len(users) == 1
        assert users[0].telegram_id == 1006

    async def test_get_users_for_telegram_group(self, db):
        user = await get_or_create_user(db, 1008)
        group = await create_group(db, link="https://t.me/ug6")
        await update_group(db, group.id, telegram_id=-100999)
        await add_user_to_group(db, user.id, group.id)
        users = await get_users_for_telegram_group(db, -100999)
        assert len(users) == 1
        assert users[0].telegram_id == 1008


# ─── Patterns CRUD ──────────────────────────────────────────────────


class TestPatternsCRUD:
    async def test_create_exact_pattern(self, db):
        user = await get_or_create_user(db, 2001)
        pattern = await create_pattern(db, user.id, "iphone")
        assert pattern.value == "iphone"
        assert pattern.pattern_type == PatternType.EXACT

    async def test_create_smart_pattern(self, db):
        user = await get_or_create_user(db, 2002)
        pattern = await create_pattern(db, user.id, "macbook", PatternType.SMART)
        assert pattern.pattern_type == PatternType.SMART

    async def test_get_user_patterns(self, db):
        user = await get_or_create_user(db, 2003)
        await create_pattern(db, user.id, "iphone")
        await create_pattern(db, user.id, "macbook", PatternType.SMART)
        patterns = await get_user_patterns(db, user.id)
        assert len(patterns) == 2

    async def test_delete_pattern(self, db):
        user = await get_or_create_user(db, 2004)
        pattern = await create_pattern(db, user.id, "airpods")
        await delete_pattern(db, pattern.id)
        patterns = await get_user_patterns(db, user.id)
        assert len(patterns) == 0


# ─── Foreign Keys ────────────────────────────────────────────────────


class TestForeignKeys:
    async def test_cannot_insert_pattern_for_nonexistent_user(self, db):
        with pytest.raises(aiosqlite.IntegrityError):
            await db.execute(
                "INSERT INTO patterns (user_id, value) VALUES (?, ?)",
                (99999, "test"),
            )

    async def test_cascade_delete_user_removes_patterns(self, db):
        user = await get_or_create_user(db, 3001)
        await create_pattern(db, user.id, "test_pattern")
        await db.execute("DELETE FROM users WHERE id = ?", (user.id,))
        await db.commit()
        patterns = await get_user_patterns(db, user.id)
        assert len(patterns) == 0

    async def test_cascade_delete_user_removes_user_groups(self, db):
        user = await get_or_create_user(db, 3002)
        group = await create_group(db, link="https://t.me/fk1")
        await add_user_to_group(db, user.id, group.id)
        await db.execute("DELETE FROM users WHERE id = ?", (user.id,))
        await db.commit()
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM user_groups WHERE user_id = ?", (user.id,)
        )
        row = await cursor.fetchone()
        assert row["cnt"] == 0

    async def test_cascade_delete_user_removes_matches(self, db):
        user = await get_or_create_user(db, 3003)
        group = await create_group(db, link="https://t.me/fk2")
        await create_match(db, user.id, group.id, "test", "hash1")
        await db.execute("DELETE FROM users WHERE id = ?", (user.id,))
        await db.commit()
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM matches WHERE user_id = ?", (user.id,)
        )
        row = await cursor.fetchone()
        assert row["cnt"] == 0

    async def test_pattern_delete_sets_null_on_matches(self, db):
        user = await get_or_create_user(db, 3004)
        group = await create_group(db, link="https://t.me/fk3")
        pattern = await create_pattern(db, user.id, "iphone")
        match = await create_match(
            db, user.id, group.id, "iPhone 15 Pro", "hash2", pattern_id=pattern.id
        )
        await delete_pattern(db, pattern.id)
        cursor = await db.execute(
            "SELECT pattern_id FROM matches WHERE id = ?", (match.id,)
        )
        row = await cursor.fetchone()
        assert row["pattern_id"] is None

    async def test_cascade_delete_group_removes_matches(self, db):
        user = await get_or_create_user(db, 3005)
        group = await create_group(db, link="https://t.me/fk4")
        await create_match(db, user.id, group.id, "test msg", "hash3")
        await delete_group(db, group.id)
        cursor = await db.execute(
            "SELECT COUNT(*) as cnt FROM matches WHERE group_id = ?", (group.id,)
        )
        row = await cursor.fetchone()
        assert row["cnt"] == 0


# ─── Deduplication ──────────────────────────────────────────────────


class TestDeduplication:
    async def test_duplicate_detected_within_window(self, db):
        user = await get_or_create_user(db, 4001)
        group = await create_group(db, link="https://t.me/dd1")
        await create_match(db, user.id, group.id, "Продам iPhone", "abc123")
        is_dup = await check_duplicate(db, user.id, "abc123", hours=2)
        assert is_dup is True

    async def test_no_duplicate_for_different_hash(self, db):
        user = await get_or_create_user(db, 4002)
        group = await create_group(db, link="https://t.me/dd2")
        await create_match(db, user.id, group.id, "Продам iPhone", "abc123")
        is_dup = await check_duplicate(db, user.id, "xyz789", hours=2)
        assert is_dup is False

    async def test_no_duplicate_for_different_user(self, db):
        user1 = await get_or_create_user(db, 4003)
        user2 = await get_or_create_user(db, 4004)
        group = await create_group(db, link="https://t.me/dd3")
        await create_match(db, user1.id, group.id, "Продам iPhone", "abc123")
        is_dup = await check_duplicate(db, user2.id, "abc123", hours=2)
        assert is_dup is False

    async def test_no_duplicate_outside_time_window(self, db):
        user = await get_or_create_user(db, 4005)
        group = await create_group(db, link="https://t.me/dd4")
        # Insert match with old timestamp using SQLite datetime format
        old_time = (datetime.utcnow() - timedelta(hours=3)).strftime("%Y-%m-%d %H:%M:%S")
        await db.execute(
            """
            INSERT INTO matches (user_id, group_id, message_text, text_hash, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user.id, group.id, "Old message", "old_hash", old_time),
        )
        await db.commit()
        is_dup = await check_duplicate(db, user.id, "old_hash", hours=2)
        assert is_dup is False


# ─── Matches Sender ─────────────────────────────────────────────────


class TestMatchesSender:
    async def test_unsent_matches_returned(self, db):
        user = await get_or_create_user(db, 5001)
        group = await create_group(db, link="https://t.me/ms1")
        await create_match(db, user.id, group.id, "msg1", "h1")
        await create_match(db, user.id, group.id, "msg2", "h2")
        unsent = await get_unsent_matches(db)
        assert len(unsent) == 2

    async def test_mark_sent_removes_from_unsent(self, db):
        user = await get_or_create_user(db, 5002)
        group = await create_group(db, link="https://t.me/ms2")
        match = await create_match(db, user.id, group.id, "msg", "h3")
        await mark_match_sent(db, match.id)
        unsent = await get_unsent_matches(db)
        assert len(unsent) == 0

    async def test_get_user_matches_ordered(self, db):
        user = await get_or_create_user(db, 5003)
        group = await create_group(db, link="https://t.me/ms3")
        await create_match(db, user.id, group.id, "first", "h4")
        await create_match(db, user.id, group.id, "second", "h5")
        matches = await get_user_matches(db, user.id)
        assert len(matches) == 2
        # Newest first
        assert matches[0].message_text == "second"

    async def test_count_user_matches(self, db):
        user = await get_or_create_user(db, 5004)
        group = await create_group(db, link="https://t.me/ms4")
        await create_match(db, user.id, group.id, "m1", "h6")
        await create_match(db, user.id, group.id, "m2", "h7")
        count = await count_user_matches(db, user.id)
        assert count == 2

    async def test_count_user_matches_since(self, db):
        user = await get_or_create_user(db, 5005)
        group = await create_group(db, link="https://t.me/ms5")
        # Insert old match using SQLite datetime format
        old_time = (datetime.utcnow() - timedelta(days=10)).strftime("%Y-%m-%d %H:%M:%S")
        await db.execute(
            """
            INSERT INTO matches (user_id, group_id, message_text, text_hash, created_at)
            VALUES (?, ?, ?, ?, ?)
            """,
            (user.id, group.id, "old", "h_old", old_time),
        )
        await db.commit()
        # Insert recent match
        await create_match(db, user.id, group.id, "new", "h_new")
        since = datetime.utcnow() - timedelta(days=7)
        count = await count_user_matches(db, user.id, since=since)
        assert count == 1


# ─── Pending Joins ──────────────────────────────────────────────────


class TestPendingJoins:
    async def test_create_pending_join(self, db):
        pj = await create_pending_join(db, "https://t.me/+abc123")
        assert pj.link == "https://t.me/+abc123"
        assert pj.status == PendingJoinStatus.PENDING

    async def test_get_pending_joins_by_status(self, db):
        await create_pending_join(db, "https://t.me/+a")
        await create_pending_join(db, "https://t.me/+b")
        pending = await get_pending_joins(db, PendingJoinStatus.PENDING)
        assert len(pending) == 2

    async def test_update_pending_join_status(self, db):
        pj = await create_pending_join(db, "https://t.me/+c")
        await update_pending_join(db, pj.id, status="done")
        pending = await get_pending_joins(db, PendingJoinStatus.PENDING)
        done = await get_pending_joins(db, PendingJoinStatus.DONE)
        assert len(pending) == 0
        assert len(done) == 1

    async def test_update_pending_join_error(self, db):
        pj = await create_pending_join(db, "https://t.me/+d")
        await update_pending_join(db, pj.id, status="error", error_message="Invite expired")
        errors = await get_pending_joins(db, PendingJoinStatus.ERROR)
        assert len(errors) == 1
        assert errors[0].error_message == "Invite expired"


# ─── Pattern-Groups Tests ────────────────────────────────────────────


class TestPatternGroups:
    async def _setup(self, db):
        user = await get_or_create_user(db, 111)
        group = await create_group(db, link="@test_group")
        await add_user_to_group(db, user.id, group.id)
        p1 = await create_pattern(db, user.id, "iphone", PatternType.EXACT)
        p2 = await create_pattern(db, user.id, "samsung", PatternType.SMART)
        return user, group, p1, p2

    async def test_add_and_get_active(self, db):
        user, group, p1, p2 = await self._setup(db)
        await add_pattern_to_group(db, user.id, p1.id, group.id)
        active = await get_active_pattern_ids_for_group(db, user.id, group.id)
        assert p1.id in active
        assert p2.id not in active

    async def test_remove_pattern(self, db):
        user, group, p1, p2 = await self._setup(db)
        await add_pattern_to_group(db, user.id, p1.id, group.id)
        await remove_pattern_from_group(db, user.id, p1.id, group.id)
        active = await get_active_pattern_ids_for_group(db, user.id, group.id)
        assert p1.id not in active

    async def test_set_all_patterns_for_group(self, db):
        user, group, p1, p2 = await self._setup(db)
        await set_all_patterns_for_group(db, user.id, group.id)
        active = await get_active_pattern_ids_for_group(db, user.id, group.id)
        assert p1.id in active
        assert p2.id in active

    async def test_clear_all_patterns_for_group(self, db):
        user, group, p1, p2 = await self._setup(db)
        await set_all_patterns_for_group(db, user.id, group.id)
        await clear_all_patterns_for_group(db, user.id, group.id)
        active = await get_active_pattern_ids_for_group(db, user.id, group.id)
        assert len(active) == 0

    async def test_get_patterns_for_user_in_group(self, db):
        user, group, p1, p2 = await self._setup(db)
        await add_user_to_group(db, user.id, group.id)
        await add_pattern_to_group(db, user.id, p1.id, group.id)
        # Нужен telegram_id у группы для горячего пути
        await db.execute("UPDATE groups SET telegram_id=-100123 WHERE id=?", (group.id,))
        await db.commit()
        patterns = await get_patterns_for_user_in_group(db, user.id, -100123)
        assert len(patterns) == 1
        assert patterns[0].value == "iphone"

    async def test_add_pattern_to_all_groups(self, db):
        user, group, p1, p2 = await self._setup(db)
        # p1 уже привязан к группе через setup? нет — setup не вызывает add_pattern_to_group
        await add_pattern_to_all_groups(db, user.id, p1.id)
        active = await get_active_pattern_ids_for_group(db, user.id, group.id)
        assert p1.id in active

    async def test_idempotent_add(self, db):
        user, group, p1, _ = await self._setup(db)
        await add_pattern_to_group(db, user.id, p1.id, group.id)
        await add_pattern_to_group(db, user.id, p1.id, group.id)  # no error
        active = await get_active_pattern_ids_for_group(db, user.id, group.id)
        assert len(active) == 1

    async def test_cascade_delete_pattern(self, db):
        user, group, p1, _ = await self._setup(db)
        await add_pattern_to_group(db, user.id, p1.id, group.id)
        await delete_pattern(db, p1.id)
        active = await get_active_pattern_ids_for_group(db, user.id, group.id)
        assert p1.id not in active
