import re
from datetime import datetime, timezone

from telethon import TelegramClient
from telethon.errors import FloodWaitError, RPCError
from telethon.tl.types import Channel, Chat, User

from telegram_export_tool.config import Settings
from telegram_export_tool.models import ArchiveMessage, ChatInfo, RawArchive


class TelegramLayerError(Exception):
    pass


class TelegramAuthError(TelegramLayerError):
    pass


class TelegramEntityResolveError(TelegramLayerError):
    pass


class TelegramHistoryReadError(TelegramLayerError):
    pass


def to_utc_string(value: datetime) -> str:
    dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    dt = dt.astimezone(timezone.utc).replace(microsecond=0)
    return dt.strftime("%Y-%m-%d %H:%M:%S UTC")


def _slugify(value: str) -> str:
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", value.strip().lower()).strip("-")
    return slug or "chat"


def _entity_title(entity: object) -> str:
    if isinstance(entity, User):
        parts = [entity.first_name or "", entity.last_name or ""]
        full_name = " ".join(part for part in parts if part).strip()
        if full_name:
            return full_name
        if entity.username:
            return entity.username
        if entity.deleted:
            return "Deleted Account"
        return f"user-{entity.id}"

    if isinstance(entity, (Chat, Channel)):
        title = getattr(entity, "title", None)
        if title:
            return str(title)
        username = getattr(entity, "username", None)
        if username:
            return str(username)
        return f"chat-{entity.id}"

    entity_id = getattr(entity, "id", None)
    if entity_id is not None:
        return f"entity-{entity_id}"
    return "Unknown Chat"


def _entity_type(entity: object) -> str:
    if isinstance(entity, User):
        return "user"
    if isinstance(entity, Channel):
        return "channel"
    if isinstance(entity, Chat):
        return "chat"
    return entity.__class__.__name__.lower()


def build_chat_info(entity: object) -> ChatInfo:
    entity_id = getattr(entity, "id", None)
    if entity_id is None:
        raise TelegramEntityResolveError("Telegram entity was resolved, but it does not contain an id.")

    title = _entity_title(entity)
    username = getattr(entity, "username", None)

    return ChatInfo(
        id=int(entity_id),
        title=title,
        username=str(username) if username else None,
        entity_type=_entity_type(entity),
        slug=_slugify(title),
    )


def _user_author(sender: User) -> str:
    if sender.deleted:
        return "deleted_account"
    if sender.username:
        return sender.username

    parts = [sender.first_name or "", sender.last_name or ""]
    full_name = " ".join(part for part in parts if part).strip()
    if full_name:
        return full_name

    if sender.id is not None:
        return f"user_{sender.id}"

    return "unknown"


def _entity_author(sender: object) -> str:
    if isinstance(sender, User):
        return _user_author(sender)

    if isinstance(sender, Channel):
        if sender.title:
            return str(sender.title)
        if sender.username:
            return str(sender.username)
        return "channel"

    if isinstance(sender, Chat):
        if sender.title:
            return str(sender.title)
        return "chat"

    sender_id = getattr(sender, "id", None)
    if sender_id is not None:
        return f"entity_{sender_id}"

    return "unknown"


async def _resolve_author(message) -> str:
    if getattr(message, "action", None) is not None:
        return "service"

    post_author = getattr(message, "post_author", None)
    if post_author:
        return str(post_author)

    try:
        sender = await message.get_sender()
    except (RPCError, ValueError):
        sender = None

    if sender is not None:
        return _entity_author(sender)

    sender_id = getattr(message, "sender_id", None)
    if sender_id is not None:
        return f"user_{sender_id}"

    if getattr(message, "post", False):
        return "channel"

    return "unknown"


def _message_text(message) -> str:
    raw_text = getattr(message, "message", None)
    if raw_text is None:
        raw_text = getattr(message, "raw_text", None)

    if raw_text is None:
        return "[empty message]"

    text = str(raw_text)
    if text == "":
        return "[empty message]"

    return text


async def _convert_message(message) -> ArchiveMessage:
    message_date = message.date if message.date.tzinfo else message.date.replace(tzinfo=timezone.utc)
    forwarded_from = getattr(message, "fwd_from", None)

    return ArchiveMessage(
        id=int(message.id),
        date_utc=to_utc_string(message_date),
        author=await _resolve_author(message),
        text=_message_text(message),
        sender_id=getattr(message, "sender_id", None),
        reply_to_msg_id=getattr(message, "reply_to_msg_id", None),
        forwarded_from=str(forwarded_from) if forwarded_from is not None else None,
        has_media=message.media is not None,
        is_service=getattr(message, "action", None) is not None,
    )


async def make_client(settings: Settings) -> TelegramClient:
    client = TelegramClient(settings.session_name, settings.api_id, settings.api_hash)
    await client.connect()

    if not await client.is_user_authorized():
        if not settings.phone:
            await client.disconnect()
            raise TelegramAuthError(
                "Telegram session is not authorized. Set TG_PHONE in your environment or authorize the session first."
            )

        try:
            await client.start(phone=settings.phone)
        except (RPCError, ValueError) as exc:
            await client.disconnect()
            raise TelegramAuthError("Failed to authorize Telegram client session.") from exc

    return client


async def list_dialog_rows(client: TelegramClient, limit: int) -> list[tuple[str, str, str]]:
    try:
        dialogs = await client.get_dialogs(limit=limit)
    except FloodWaitError as exc:
        raise TelegramHistoryReadError(
            f"Telegram rate limit was reached while loading dialogs. Retry after {exc.seconds} seconds."
        ) from exc
    except (RPCError, ValueError) as exc:
        raise TelegramHistoryReadError("Failed to load Telegram dialogs.") from exc

    rows: list[tuple[str, str, str]] = []
    for dialog in dialogs:
        entity = dialog.entity
        rows.append((str(dialog.name), str(dialog.id), entity.__class__.__name__))
    return rows


async def export_chat_archive(
        client: TelegramClient,
        chat_ref: str,
        since: datetime | None = None,
        until: datetime | None = None,
) -> RawArchive:
    try:
        entity = await client.get_entity(chat_ref)
    except (ValueError, RPCError) as exc:
        raise TelegramEntityResolveError(
            f"Failed to resolve chat '{chat_ref}'. Check chat id, username, access rights, or session permissions."
        ) from exc

    chat_info = build_chat_info(entity)
    messages: list[ArchiveMessage] = []

    try:
        async for message in client.iter_messages(entity, reverse=True):
            if message.date is None:
                continue

            message_dt = message.date if message.date.tzinfo else message.date.replace(tzinfo=timezone.utc)

            if since is not None and message_dt < since:
                continue
            if until is not None and message_dt > until:
                continue

            messages.append(await _convert_message(message))
    except FloodWaitError as exc:
        raise TelegramHistoryReadError(
            f"Telegram rate limit was reached while reading chat '{chat_ref}'. Retry after {exc.seconds} seconds."
        ) from exc
    except (RPCError, ValueError) as exc:
        raise TelegramHistoryReadError(
            f"Failed to read message history for chat '{chat_ref}'."
        ) from exc

    return RawArchive(
        chat=chat_info,
        exported_at_utc=to_utc_string(datetime.now(timezone.utc)),
        total_messages=len(messages),
        messages=messages,
    )
