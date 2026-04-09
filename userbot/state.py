"""Shared in-memory state for the userbot process."""
from __future__ import annotations

from datetime import datetime

# chat_id → time when the userbot successfully joined the group
recently_joined: dict[int, datetime] = {}
