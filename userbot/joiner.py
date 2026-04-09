"""Group joining logic — processes pending_joins queue.

Background task that periodically checks pending_joins table and
attempts to join groups via invite links or usernames.
"""
from __future__ import annotations

import asyncio
import logging
import re

from telethon import TelegramClient, utils
from telethon.errors import (
    FloodWaitError,
    InviteHashExpiredError,
    InviteHashInvalidError,
    UserAlreadyParticipantError,
    ChannelPrivateError,
    ChatAdminRequiredError,
)
from telethon.tl.functions.messages import ImportChatInviteRequest
from telethon.tl.functions.channels import JoinChannelRequest

from shared.database import (
    get_connection,
    get_pending_joins,
    update_pending_join,
    get_group_by_link,
    update_group,
)
from shared.models import PendingJoinStatus

logger = logging.getLogger(__name__)

# Match invite hash from links like https://t.me/+AbCdEfG or https://t.me/joinchat/AbCdEfG
INVITE_HASH_RE = re.compile(r"t\.me/(?:\+|joinchat/)([a-zA-Z0-9_-]+)")
# Match public username from links like https://t.me/group_name or @group_name
USERNAME_RE = re.compile(r"(?:t\.me/|@)([a-zA-Z]\w{3,})")

JOIN_DELAY_SECONDS = 30  # delay between join attempts to avoid flood
CHECK_INTERVAL_SECONDS = 60  # how often to check for new pending_joins


async def _join_by_invite(client: TelegramClient, invite_hash: str):
    """Join a private group via invite hash."""
    return await client(ImportChatInviteRequest(invite_hash))


async def _join_by_username(client: TelegramClient, username: str):
    """Join a public group/channel by username."""
    return await client(JoinChannelRequest(username))


async def _process_join(client: TelegramClient, link: str) -> tuple[int | None, str]:
    """Attempt to join a group. Returns (chat_id, title) on success.

    Raises on failure.
    """
    # Try invite hash first
    invite_match = INVITE_HASH_RE.search(link)
    if invite_match:
        invite_hash = invite_match.group(1)
        result = await _join_by_invite(client, invite_hash)
        chat = result.chats[0] if result.chats else None
        if chat:
            return utils.get_peer_id(chat), getattr(chat, "title", "")
        return None, ""

    # Try public username
    username_match = USERNAME_RE.search(link)
    if username_match:
        username = username_match.group(1)
        result = await _join_by_username(client, username)
        chat = result.chats[0] if result.chats else None
        if chat:
            return utils.get_peer_id(chat), getattr(chat, "title", "")
        return None, ""

    raise ValueError(f"Cannot parse link: {link}")


async def _resolve_chat_id(client: TelegramClient, link: str) -> tuple[int | None, str]:
    """Resolve chat_id for an existing group without joining again."""
    username_match = USERNAME_RE.search(link)
    if not username_match:
        return None, ""
    username = username_match.group(1)
    entity = await client.get_entity(username)
    return utils.get_peer_id(entity), getattr(entity, "title", "")


async def process_pending_joins(client: TelegramClient) -> None:
    """Process all pending join requests once."""
    async with get_connection() as db:
        pending = await get_pending_joins(db, PendingJoinStatus.PENDING)

    for pj in pending:
        async with get_connection() as db:
            await update_pending_join(db, pj.id, status=PendingJoinStatus.JOINING.value)

        try:
            chat_id, title = await _process_join(client, pj.link)

            async with get_connection() as db:
                # Update pending_join status
                await update_pending_join(db, pj.id, status=PendingJoinStatus.DONE.value)

                # Update the group record
                group = await get_group_by_link(db, pj.link)
                if group and chat_id:
                    updates = {"telegram_id": chat_id, "status": "active"}
                    if title:
                        updates["title"] = title
                    await update_group(db, group.id, **updates)

            logger.info("Joined group: %s (chat_id=%s)", pj.link, chat_id)

        except UserAlreadyParticipantError:
            logger.info("Already in group: %s", pj.link)
            async with get_connection() as db:
                await update_pending_join(db, pj.id, status=PendingJoinStatus.DONE.value)
                group = await get_group_by_link(db, pj.link)
                if group:
                    updates = {"status": "active"}
                    chat_id, title = await _resolve_chat_id(client, pj.link)
                    if chat_id:
                        updates["telegram_id"] = chat_id
                    if title:
                        updates["title"] = title
                    await update_group(db, group.id, **updates)

        except FloodWaitError as e:
            logger.warning("Flood wait %d seconds for %s", e.seconds, pj.link)
            async with get_connection() as db:
                await update_pending_join(
                    db, pj.id,
                    status=PendingJoinStatus.PENDING.value,
                    error_message=f"Flood wait: {e.seconds}s",
                )
            await asyncio.sleep(e.seconds)

        except (InviteHashExpiredError, InviteHashInvalidError) as e:
            logger.error("Invalid invite for %s: %s", pj.link, e)
            async with get_connection() as db:
                await update_pending_join(
                    db, pj.id,
                    status=PendingJoinStatus.ERROR.value,
                    error_message=f"Invalid invite: {type(e).__name__}",
                )
                group = await get_group_by_link(db, pj.link)
                if group:
                    await update_group(db, group.id, status="error")

        except (ChannelPrivateError, ChatAdminRequiredError) as e:
            logger.error("Access denied for %s: %s", pj.link, e)
            async with get_connection() as db:
                await update_pending_join(
                    db, pj.id,
                    status=PendingJoinStatus.ERROR.value,
                    error_message=f"Access denied: {type(e).__name__}",
                )
                group = await get_group_by_link(db, pj.link)
                if group:
                    await update_group(db, group.id, status="error")

        except Exception as e:
            logger.exception("Failed to join %s: %s", pj.link, e)
            async with get_connection() as db:
                await update_pending_join(
                    db, pj.id,
                    status=PendingJoinStatus.ERROR.value,
                    error_message=str(e)[:500],
                )
                group = await get_group_by_link(db, pj.link)
                if group:
                    await update_group(db, group.id, status="error")

        # Delay between join attempts
        await asyncio.sleep(JOIN_DELAY_SECONDS)


async def joiner_loop(client: TelegramClient) -> None:
    """Background loop that periodically processes pending joins."""
    while True:
        try:
            await process_pending_joins(client)
        except Exception:
            logger.exception("Error in joiner loop")
        await asyncio.sleep(CHECK_INTERVAL_SECONDS)
