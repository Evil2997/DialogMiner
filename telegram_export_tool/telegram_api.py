from datetime import datetime, timezone

from telethon import TelegramClient
from telethon.errors import RPCError, SessionPasswordNeededError
from telethon.tl.custom.dialog import Dialog

from telegram_export_tool.config import Settings
from telegram_export_tool.formatting import build_chat_info, convert_message, to_utc_string
from telegram_export_tool.models import RawArchive


class TelegramError(Exception):
    pass


class TelegramAuthError(TelegramError):
    pass


class TelegramEntityResolveError(TelegramError):
    pass


class TelegramHistoryReadError(TelegramError):
    pass


async def make_client(settings: Settings) -> TelegramClient:
    client = TelegramClient(
        str(settings.session_name),
        settings.api_id,
        settings.api_hash,
    )

    try:
        await client.connect()

        if not await client.is_user_authorized():
            if not settings.phone:
                raise TelegramAuthError(
                    "Telegram session is not authorized. Add TG_PHONE to .env or create the local session first."
                )

            try:
                await client.start(phone=settings.phone)
            except SessionPasswordNeededError as exc:
                raise TelegramAuthError(
                    "Two-factor authentication is enabled. Complete login in the local session first."
                ) from exc

        if not await client.is_user_authorized():
            raise TelegramAuthError(
                "Telegram session is not authorized. Create or restore the local user session first."
            )

        return client
    except TelegramAuthError:
        await client.disconnect()
        raise
    except Exception as exc:
        await client.disconnect()
        raise TelegramAuthError(f"Failed to initialize Telegram client: {exc}") from exc


async def list_dialog_rows(client: TelegramClient, limit: int = 100) -> list[tuple[str, str, str]]:
    rows: list[tuple[str, str, str]] = []

    try:
        async for dialog in client.iter_dialogs(limit=limit):
            rows.append(_dialog_to_row(dialog))
    except RPCError as exc:
        raise TelegramHistoryReadError(f"Failed to load dialogs from Telegram: {exc}") from exc
    except Exception as exc:
        raise TelegramHistoryReadError(f"Failed to read Telegram dialogs: {exc}") from exc

    return rows


async def resolve_chat_entity(client: TelegramClient, chat_ref: str):
    normalized_ref = chat_ref.strip()

    try:
        return await client.get_entity(normalized_ref)
    except Exception:
        pass

    numeric_ref = normalized_ref.removeprefix("+")
    if numeric_ref.isdigit():
        target_id = int(numeric_ref)

        try:
            async for dialog in client.iter_dialogs():
                entity = dialog.entity
                if getattr(entity, "id", None) == target_id:
                    return entity
        except RPCError as exc:
            raise TelegramEntityResolveError(
                f"Failed to scan dialogs while resolving chat '{chat_ref}': {exc}") from exc
        except Exception as exc:
            raise TelegramEntityResolveError(f"Failed to resolve chat '{chat_ref}' from dialogs: {exc}") from exc

    raise TelegramEntityResolveError(
        f"Failed to resolve chat '{chat_ref}'. Use a username/link or rescan dialogs and try again."
    )


async def export_chat_archive(
        client: TelegramClient,
        chat_ref: str,
        since: datetime | None = None,
        until: datetime | None = None,
) -> RawArchive:
    entity = await resolve_chat_entity(client, chat_ref)

    messages = []

    try:
        async for message in client.iter_messages(entity, reverse=True):
            if message is None or getattr(message, "id", None) is None or getattr(message, "date", None) is None:
                continue

            message_date = message.date
            if message_date.tzinfo is None:
                message_date = message_date.replace(tzinfo=timezone.utc)

            if since is not None and message_date < since:
                continue
            if until is not None and message_date > until:
                continue

            messages.append(convert_message(message))
    except RPCError as exc:
        raise TelegramHistoryReadError(f"Failed to read chat history for '{chat_ref}': {exc}") from exc
    except Exception as exc:
        raise TelegramHistoryReadError(f"Failed to export chat history for '{chat_ref}': {exc}") from exc

    return RawArchive(
        chat=build_chat_info(entity),
        exported_at_utc=to_utc_string(datetime.now(timezone.utc)),
        total_messages=len(messages),
        messages=messages,
    )


def _dialog_to_row(dialog: Dialog) -> tuple[str, str, str]:
    entity = dialog.entity
    title = dialog.name or getattr(entity, "title", None) or getattr(entity, "first_name", None) or str(
        getattr(entity, "id", "unknown")
    )
    entity_id = str(getattr(entity, "id", ""))
    entity_type = entity.__class__.__name__
    return title, entity_id, entity_type
