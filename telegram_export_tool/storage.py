import json
from datetime import datetime, timezone
from pathlib import Path

from pydantic import BaseModel

from telegram_export_tool.chunking import build_chunk_drafts, build_chunk_summary
from telegram_export_tool.formatting import render_full_archive
from telegram_export_tool.models import RawArchive, Summary


class ScannedDialogState(BaseModel):
    title: str
    id: int
    type: str
    slug: str
    source_index: int | None = None
    display_index: int | None = None
    username: str | None = None
    scanned_at: str | None = None


class SelectedDialogState(BaseModel):
    title: str
    id: int
    type: str
    slug: str
    source_index: int | None = None
    display_index: int | None = None
    username: str | None = None
    selected_at: str | None = None


def _utc_now_string() -> str:
    return datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")


def ensure_output_paths(chat_dir: Path) -> tuple[Path, Path]:
    chunks_dir = chat_dir / "chunks"

    chat_dir.mkdir(parents=True, exist_ok=True)
    chunks_dir.mkdir(parents=True, exist_ok=True)

    return chat_dir, chunks_dir


def ensure_state_paths(state_dir: Path) -> tuple[Path, Path]:
    state_dir.mkdir(parents=True, exist_ok=True)
    scanned_path = state_dir / "scanned_dialogs.json"
    selected_path = state_dir / "selected_dialogs.json"
    return scanned_path, selected_path


def ensure_state_path(state_dir: Path) -> Path:
    _, selected_path = ensure_state_paths(state_dir)
    return selected_path


def save_raw_archive(chat_dir: Path, archive: RawArchive) -> Path:
    chat_dir, _ = ensure_output_paths(chat_dir)

    path = chat_dir / "raw_messages.json"
    path.write_text(
        json.dumps(archive.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_raw_archive(path: Path) -> RawArchive:
    return RawArchive.model_validate_json(path.read_text(encoding="utf-8"))


def save_full_archive(chat_dir: Path, archive: RawArchive) -> Path:
    chat_dir, _ = ensure_output_paths(chat_dir)

    path = chat_dir / "full_archive.txt"
    path.write_text(render_full_archive(archive.messages), encoding="utf-8")
    return path


def plan_chunks(archive: RawArchive, max_chars: int, soft_min_chars: int) -> list:
    drafts = build_chunk_drafts(
        messages=archive.messages,
        max_chars=max_chars,
        soft_min_chars=soft_min_chars,
    )
    return build_chunk_summary(drafts)


def save_chunks(chat_dir: Path, archive: RawArchive, max_chars: int, soft_min_chars: int) -> tuple[Path, list]:
    _, chunks_dir = ensure_output_paths(chat_dir)

    for existing in chunks_dir.glob("*.txt"):
        existing.unlink()

    drafts = build_chunk_drafts(
        messages=archive.messages,
        max_chars=max_chars,
        soft_min_chars=soft_min_chars,
    )

    for draft in drafts:
        (chunks_dir / (draft.file_name or "chunk.txt")).write_text(draft.text, encoding="utf-8")

    return chunks_dir, build_chunk_summary(drafts)


def build_summary(archive: RawArchive, chunks_info: list) -> Summary:
    authors = {message.author for message in archive.messages}
    text_messages = sum(
        1 for message in archive.messages
        if message.text != "[empty message]"
    )
    service_messages = sum(1 for message in archive.messages if message.is_service)
    media_messages = sum(1 for message in archive.messages if message.has_media)
    forwarded_messages = sum(1 for message in archive.messages if message.forwarded_from is not None)

    return Summary(
        chat=archive.chat,
        exported_at_utc=archive.exported_at_utc,
        total_messages=archive.total_messages,
        first_message_date_utc=archive.messages[0].date_utc if archive.messages else None,
        last_message_date_utc=archive.messages[-1].date_utc if archive.messages else None,
        authors_count=len(authors),
        text_messages=text_messages,
        service_messages=service_messages,
        media_messages=media_messages,
        forwarded_messages=forwarded_messages,
        chunks_count=len(chunks_info),
        chunks=chunks_info,
    )


def save_summary(chat_dir: Path, summary: Summary) -> Path:
    chat_dir, _ = ensure_output_paths(chat_dir)

    path = chat_dir / "summary.json"
    path.write_text(
        json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def save_scanned_dialogs(state_dir: Path, dialogs: list[ScannedDialogState]) -> Path:
    scanned_path, _ = ensure_state_paths(state_dir)

    payload = {
        "saved_at": _utc_now_string(),
        "dialogs": [dialog.model_dump(mode="json") for dialog in dialogs],
    }

    scanned_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return scanned_path


def load_scanned_dialogs(state_dir: Path) -> list[ScannedDialogState]:
    scanned_path, _ = ensure_state_paths(state_dir)

    if not scanned_path.exists():
        return []

    data = json.loads(scanned_path.read_text(encoding="utf-8"))
    dialogs = data.get("dialogs", [])
    return [ScannedDialogState.model_validate(item) for item in dialogs]


def save_selected_dialogs(state_dir: Path, dialogs: list[SelectedDialogState]) -> Path:
    _, selected_path = ensure_state_paths(state_dir)

    payload = {
        "saved_at": _utc_now_string(),
        "dialogs": [dialog.model_dump(mode="json") for dialog in dialogs],
    }

    selected_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return selected_path


def load_selected_dialogs(state_dir: Path) -> list[SelectedDialogState]:
    _, selected_path = ensure_state_paths(state_dir)

    if not selected_path.exists():
        return []

    data = json.loads(selected_path.read_text(encoding="utf-8"))
    dialogs = data.get("dialogs", [])
    return [SelectedDialogState.model_validate(item) for item in dialogs]