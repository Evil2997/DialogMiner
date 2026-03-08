import json
from pathlib import Path

from pydantic import BaseModel, ValidationError

from telegram_export_tool.config import load_settings


class DialogRegistryError(Exception):
    pass


class DialogRegistryReadError(DialogRegistryError):
    pass


class DialogRegistryWriteError(DialogRegistryError):
    pass


class DialogRegistryValidationError(DialogRegistryError):
    pass


class DialogRegistryItem(BaseModel):
    title: str
    entity_id: str
    entity_type: str


def get_scan_cache_path() -> Path:
    settings = load_settings()
    path = settings.scanned_dialogs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def get_saved_dialogs_path() -> Path:
    settings = load_settings()
    path = settings.selected_dialogs_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _serialize_rows(rows: list[tuple[str, str, str]]) -> list[dict]:
    items = [
        DialogRegistryItem(
            title=title,
            entity_id=entity_id,
            entity_type=entity_type,
        )
        for title, entity_id, entity_type in rows
    ]
    return [item.model_dump(mode="json") for item in items]


def _deserialize_rows(data: str, source: Path) -> list[tuple[str, str, str]]:
    try:
        raw_items = json.loads(data)
    except json.JSONDecodeError as exc:
        raise DialogRegistryReadError(f"Registry file is not valid JSON: {source}") from exc

    if not isinstance(raw_items, list):
        raise DialogRegistryValidationError(f"Registry file must contain a JSON list: {source}")

    rows: list[tuple[str, str, str]] = []

    for raw_item in raw_items:
        try:
            item = DialogRegistryItem.model_validate(raw_item)
        except ValidationError as exc:
            raise DialogRegistryValidationError(
                f"Registry file contains invalid dialog item data: {source}"
            ) from exc

        rows.append((item.title, item.entity_id, item.entity_type))

    return rows


def save_scan_cache(rows: list[tuple[str, str, str]]) -> Path:
    path = get_scan_cache_path()

    try:
        path.write_text(
            json.dumps(_serialize_rows(rows), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        raise DialogRegistryWriteError(f"Failed to write scan cache: {path}") from exc

    return path


def load_scan_cache() -> list[tuple[str, str, str]]:
    path = get_scan_cache_path()

    if not path.exists():
        return []

    try:
        data = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DialogRegistryReadError(f"Failed to read scan cache: {path}") from exc

    return _deserialize_rows(data, path)


def save_saved_dialogs(rows: list[tuple[str, str, str]]) -> Path:
    path = get_saved_dialogs_path()

    try:
        path.write_text(
            json.dumps(_serialize_rows(rows), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    except OSError as exc:
        raise DialogRegistryWriteError(f"Failed to write saved dialogs registry: {path}") from exc

    return path


def load_saved_dialogs() -> list[tuple[str, str, str]]:
    path = get_saved_dialogs_path()

    if not path.exists():
        return []

    try:
        data = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise DialogRegistryReadError(f"Failed to read saved dialogs registry: {path}") from exc

    return _deserialize_rows(data, path)


def save_saved_dialogs_from_indexes(
        scan_rows: list[tuple[str, str, str]],
        indexes: list[int],
) -> list[tuple[str, str, str]]:
    if not indexes:
        raise ValueError("At least one dialog number must be provided.")

    unique_indexes: list[int] = []
    seen: set[int] = set()

    for index in indexes:
        if index < 1 or index > len(scan_rows):
            raise ValueError(f"Dialog number out of range: {index}")
        if index not in seen:
            unique_indexes.append(index)
            seen.add(index)

    selected_rows = [scan_rows[index - 1] for index in unique_indexes]
    save_saved_dialogs(selected_rows)
    return selected_rows
