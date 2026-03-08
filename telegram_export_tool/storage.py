import json
from pathlib import Path

from pydantic import ValidationError
from telegram_export_tool.constants import FALLBACK_CHUNK_FILE_NAME
from telegram_export_tool.paths import build_chunks_dir, build_full_archive_path, build_raw_messages_path, \
    build_summary_path

from telegram_export_tool.chunking import build_chunk_drafts, build_chunk_summary, sort_messages_chronologically
from telegram_export_tool.formatting import render_full_archive
from telegram_export_tool.models import ChunkInfo, RawArchive, Summary


class StorageError(Exception):
    pass


class StorageReadError(StorageError):
    pass


class StorageWriteError(StorageError):
    pass


class StorageValidationError(StorageError):
    pass


def ensure_output_chat_paths(chat_dir: Path) -> tuple[Path, Path]:
    chunks_dir = build_chunks_dir(chat_dir)

    try:
        chat_dir.mkdir(parents=True, exist_ok=True)
        chunks_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise StorageWriteError(f"Failed to create output directories: {chat_dir}") from exc

    return chat_dir, chunks_dir


def ensure_output_paths(chat_dir: Path) -> tuple[Path, Path]:
    return ensure_output_chat_paths(chat_dir)


def save_raw_archive(chat_dir: Path, archive: RawArchive) -> Path:
    chat_dir, _ = ensure_output_chat_paths(chat_dir)
    path = build_raw_messages_path(chat_dir)

    try:
        path.write_text(
            json.dumps(archive.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        raise StorageWriteError(f"Failed to write raw archive: {path}") from exc

    return path


def load_raw_archive(path: Path) -> RawArchive:
    try:
        raw_data = path.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise StorageReadError(f"Archive file not found: {path}") from exc
    except OSError as exc:
        raise StorageReadError(f"Failed to read archive file: {path}") from exc

    try:
        return RawArchive.model_validate_json(raw_data)
    except ValidationError as exc:
        raise StorageValidationError(f"Archive file has invalid structure: {path}") from exc
    except ValueError as exc:
        raise StorageValidationError(f"Archive file is not valid JSON: {path}") from exc


def save_full_archive(chat_dir: Path, archive: RawArchive) -> Path:
    chat_dir, _ = ensure_output_chat_paths(chat_dir)
    path = build_full_archive_path(chat_dir)

    try:
        path.write_text(render_full_archive(archive.messages), encoding="utf-8")
    except OSError as exc:
        raise StorageWriteError(f"Failed to write full archive text file: {path}") from exc

    return path


def plan_chunks(archive: RawArchive, max_chars: int, soft_min_chars: int) -> list[ChunkInfo]:
    drafts = build_chunk_drafts(
        messages=archive.messages,
        max_chars=max_chars,
        soft_min_chars=soft_min_chars,
    )
    return build_chunk_summary(drafts)


def save_chunks(
        chat_dir: Path,
        archive: RawArchive,
        max_chars: int,
        soft_min_chars: int,
) -> tuple[Path, list[ChunkInfo]]:
    _, chunks_dir = ensure_output_chat_paths(chat_dir)

    try:
        for existing in chunks_dir.glob("*.txt"):
            existing.unlink()
    except OSError as exc:
        raise StorageWriteError(f"Failed to clean chunks directory: {chunks_dir}") from exc

    drafts = build_chunk_drafts(
        messages=archive.messages,
        max_chars=max_chars,
        soft_min_chars=soft_min_chars,
    )

    try:
        for draft in drafts:
            file_name = draft.file_name or FALLBACK_CHUNK_FILE_NAME
            (chunks_dir / file_name).write_text(draft.text, encoding="utf-8")
    except OSError as exc:
        raise StorageWriteError(f"Failed to write chunk files into: {chunks_dir}") from exc

    return chunks_dir, build_chunk_summary(drafts)


def build_summary(archive: RawArchive, chunks_info: list[ChunkInfo]) -> Summary:
    ordered_messages = sort_messages_chronologically(archive.messages)
    authors = {message.author for message in archive.messages if message.author}
    text_messages = sum(1 for message in archive.messages if
                        message.text != FALLBACK_CHUNK_FILE_NAME.replace("chunk.txt", "[empty message]"))
    service_messages = sum(1 for message in archive.messages if message.is_service)
    media_messages = sum(1 for message in archive.messages if message.has_media)
    forwarded_messages = sum(1 for message in archive.messages if message.forwarded_from is not None)

    return Summary(
        chat=archive.chat,
        exported_at_utc=archive.exported_at_utc,
        total_messages=archive.total_messages,
        first_message_date_utc=ordered_messages[0].date_utc if ordered_messages else None,
        last_message_date_utc=ordered_messages[-1].date_utc if ordered_messages else None,
        authors_count=len(authors),
        text_messages=text_messages,
        service_messages=service_messages,
        media_messages=media_messages,
        forwarded_messages=forwarded_messages,
        chunks_count=len(chunks_info),
        chunks=chunks_info,
    )


def save_summary(chat_dir: Path, summary: Summary) -> Path:
    chat_dir, _ = ensure_output_chat_paths(chat_dir)
    path = build_summary_path(chat_dir)

    try:
        path.write_text(
            json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        raise StorageWriteError(f"Failed to write summary file: {path}") from exc

    return path
