"""Dataclass models representing database rows.

Pure data containers with no database logic.
Used as return types from database.py and as typed input to CRUD operations.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum


class GroupStatus(str, Enum):
    PENDING = "pending"
    ACTIVE = "active"
    ERROR = "error"
    LEFT = "left"


class PatternType(str, Enum):
    EXACT = "exact"
    SMART = "smart"


class PendingJoinStatus(str, Enum):
    PENDING = "pending"
    JOINING = "joining"
    CAPTCHA = "captcha"
    DONE = "done"
    ERROR = "error"


@dataclass
class User:
    id: int
    telegram_id: int
    timezone: int = 3
    quiet_hours_start: str | None = None
    quiet_hours_end: str | None = None
    is_active: bool = True
    new_group_patterns: bool = False  # auto-activate all patterns for a new group
    new_pattern_groups: bool = False  # auto-activate new pattern for all groups
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Group:
    id: int
    telegram_id: int | None = None
    link: str = ""
    title: str = ""
    status: GroupStatus = GroupStatus.PENDING
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class UserGroup:
    user_id: int
    group_id: int
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Pattern:
    id: int
    user_id: int
    pattern_type: PatternType = PatternType.EXACT
    value: str = ""
    created_at: datetime = field(default_factory=datetime.utcnow)


@dataclass
class Match:
    id: int
    user_id: int
    group_id: int
    pattern_id: int | None = None
    message_text: str = ""
    text_hash: str = ""
    message_link: str | None = None
    media_path: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    sent_at: datetime | None = None


@dataclass
class PendingJoin:
    id: int
    link: str = ""
    status: PendingJoinStatus = PendingJoinStatus.PENDING
    error_message: str | None = None
    created_at: datetime = field(default_factory=datetime.utcnow)
    updated_at: datetime = field(default_factory=datetime.utcnow)
