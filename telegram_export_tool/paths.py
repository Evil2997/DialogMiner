from pathlib import Path

from telegram_export_tool.constants import (
    CHUNKS_DIR_NAME,
    FULL_ARCHIVE_FILE_NAME,
    RAW_MESSAGES_FILE_NAME,
    SCANNED_DIALOGS_FILE_NAME,
    SELECTED_DIALOGS_FILE_NAME,
    SUMMARY_FILE_NAME,
)


def build_chat_output_dir(output_dir: Path, slug: str) -> Path:
    return output_dir / slug


def build_chunks_dir(chat_dir: Path) -> Path:
    return chat_dir / CHUNKS_DIR_NAME


def build_raw_messages_path(chat_dir: Path) -> Path:
    return chat_dir / RAW_MESSAGES_FILE_NAME


def build_full_archive_path(chat_dir: Path) -> Path:
    return chat_dir / FULL_ARCHIVE_FILE_NAME


def build_summary_path(chat_dir: Path) -> Path:
    return chat_dir / SUMMARY_FILE_NAME


def build_selected_dialogs_path(state_dir: Path) -> Path:
    return state_dir / SELECTED_DIALOGS_FILE_NAME


def build_scanned_dialogs_path(state_dir: Path) -> Path:
    return state_dir / SCANNED_DIALOGS_FILE_NAME
