from datetime import datetime, timezone

from telethon import TelegramClient

from telegram_export_tool.config import Settings
from telegram_export_tool.formatting import build_chat_info, convert_message, to_utc_string
from telegram_export_tool.models import RawArchive


async def make_client(settings: Settings) -> TelegramClient:
    client = TelegramClient(settings.session_name, settings.api_id, settings.api_hash)
    await client.connect()

    if not await client.is_user_authorized():
        await client.start(phone=settings.phone)

    return client


async def list_dialog_rows(client: TelegramClient, limit: int) -> list[tuple[str, str, str]]:
    dialogs = await client.get_dialogs(limit=limit)
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
    entity = await client.get_entity(chat_ref)
    chat_info = build_chat_info(entity)
    messages = []

    async for message in client.iter_messages(entity, reverse=True):
        if message.date is None:
            continue

        message_dt = message.date if message.date.tzinfo else message.date.replace(tzinfo=timezone.utc)

        if since is not None and message_dt < since:
            continue
        if until is not None and message_dt > until:
            continue

        messages.append(convert_message(message))

    return RawArchive(
        chat=chat_info,
        exported_at_utc=to_utc_string(datetime.now(timezone.utc)),
        total_messages=len(messages),
        messages=messages,
    )