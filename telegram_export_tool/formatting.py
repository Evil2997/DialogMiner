import re
from collections import defaultdict
from datetime import datetime, timezone

from telethon.tl.custom.message import Message

from telegram_export_tool.models import ArchiveMessage, ChatInfo

DATE_UTC_FORMAT = "%Y-%m-%d %H:%M:%S UTC"


def normalize_text(text: str) -> str:
    value = text.replace("\r\n", "\n").replace("\r", "\n")
    value = re.sub(r"[ \t]+", " ", value)
    value = re.sub(r"\n{3,}", "\n\n", value)
    return value.strip()


def to_utc_string(value: datetime) -> str:
    dt = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).strftime(DATE_UTC_FORMAT)


def month_key_from_utc_string(value: str) -> str:
    dt = datetime.strptime(value, DATE_UTC_FORMAT)
    return dt.strftime("%m.%Y")


def slugify(value: str) -> str:
    lowered = value.lower().strip()
    lowered = re.sub(r"[^a-z0-9а-яё]+", "-", lowered, flags=re.IGNORECASE)
    lowered = lowered.strip("-")
    return lowered or "chat"


def build_chat_info(entity) -> ChatInfo:
    title = getattr(entity, "title", None) or getattr(entity, "first_name", None) or str(getattr(entity, "id", "chat"))
    username = getattr(entity, "username", None)
    slug_source = username or title or str(getattr(entity, "id", "chat"))
    slug = slugify(slug_source)
    return ChatInfo(
        id=int(getattr(entity, "id")),
        title=title,
        username=username,
        entity_type=entity.__class__.__name__,
        slug=slug,
    )


def resolve_author_name(message: Message) -> str:
    sender = getattr(message, "sender", None)

    if sender is not None:
        username = getattr(sender, "username", None)
        if username:
            return f"@{username}"

        first_name = getattr(sender, "first_name", "") or ""
        last_name = getattr(sender, "last_name", "") or ""
        full_name = f"{first_name} {last_name}".strip()
        if full_name:
            return normalize_text(full_name)

        title = getattr(sender, "title", None)
        if title:
            return normalize_text(str(title))

    if getattr(message, "post_author", None):
        return normalize_text(str(message.post_author))

    if getattr(message, "sender_id", None) is not None:
        return f"sender:{message.sender_id}"

    return "unknown"


def resolve_forwarded_from(message: Message) -> str | None:
    forward = getattr(message, "fwd_from", None)
    if forward is None:
        return None

    if getattr(forward, "from_name", None):
        return normalize_text(str(forward.from_name))

    if getattr(forward, "from_id", None) is not None:
        return str(forward.from_id)

    return "forwarded"


def resolve_text(message: Message) -> str:
    raw_text = getattr(message, "message", None) or getattr(message, "raw_text", None) or ""
    normalized = normalize_text(raw_text)
    if normalized:
        return normalized

    return "[empty message]"


def convert_message(message: Message) -> ArchiveMessage:
    return ArchiveMessage(
        id=int(message.id),
        date_utc=to_utc_string(message.date),
        author=resolve_author_name(message),
        text=resolve_text(message),
        sender_id=int(message.sender_id) if getattr(message, "sender_id", None) is not None else None,
        reply_to_msg_id=getattr(getattr(message, "reply_to", None), "reply_to_msg_id", None),
        forwarded_from=resolve_forwarded_from(message),
        has_media=getattr(message, "media", None) is not None,
        is_service=getattr(message, "action", None) is not None,
    )


def render_archive_message(message: ArchiveMessage) -> str:
    return f"[{message.date_utc}] {message.author}\n{message.text}\n"


def render_full_archive(messages: list[ArchiveMessage]) -> str:
    if not messages:
        return ""

    ordered_messages = sorted(
        messages,
        key=lambda message: (
            datetime.strptime(message.date_utc, DATE_UTC_FORMAT),
            message.id,
        ),
    )

    return "\n".join(render_archive_message(message).rstrip() for message in ordered_messages).strip() + "\n"


def group_messages_by_month(messages: list[ArchiveMessage]) -> dict[str, list[ArchiveMessage]]:
    buckets: dict[str, list[ArchiveMessage]] = defaultdict(list)
    for message in messages:
        buckets[month_key_from_utc_string(message.date_utc)].append(message)
    return dict(buckets)
