import json
from pathlib import Path

from pydantic import BaseModel


class DialogRegistryItem(BaseModel):
    title: str
    entity_id: str
    entity_type: str


def get_project_root() -> Path:
    return Path(__file__).resolve().parent.parent


def get_scan_cache_path() -> Path:
    return get_project_root() / "scanned_dialogs.json"


def get_saved_dialogs_path() -> Path:
    return get_project_root() / "selected_dialogs.json"


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


def _deserialize_rows(data: str) -> list[tuple[str, str, str]]:
    raw_items = json.loads(data)
    rows: list[tuple[str, str, str]] = []

    for raw_item in raw_items:
        item = DialogRegistryItem.model_validate(raw_item)
        rows.append((item.title, item.entity_id, item.entity_type))

    return rows


def save_scan_cache(rows: list[tuple[str, str, str]]) -> Path:
    path = get_scan_cache_path()
    path.write_text(
        json.dumps(_serialize_rows(rows), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_scan_cache() -> list[tuple[str, str, str]]:
    path = get_scan_cache_path()
    if not path.exists():
        return []
    return _deserialize_rows(path.read_text(encoding="utf-8"))


def save_saved_dialogs(rows: list[tuple[str, str, str]]) -> Path:
    path = get_saved_dialogs_path()
    path.write_text(
        json.dumps(_serialize_rows(rows), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    return path


def load_saved_dialogs() -> list[tuple[str, str, str]]:
    path = get_saved_dialogs_path()
    if not path.exists():
        return []
    return _deserialize_rows(path.read_text(encoding="utf-8"))


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
