from datetime import datetime

from telegram_export_tool.formatting import group_messages_by_month, render_archive_message
from telegram_export_tool.models import ArchiveMessage, ChunkDraft, ChunkInfo


DATE_UTC_FORMAT = "%Y-%m-%d %H:%M:%S UTC"
MONTH_KEY_FORMAT = "%m.%Y"


def parse_date_utc(value: str) -> datetime:
    return datetime.strptime(value, DATE_UTC_FORMAT)


def parse_month_key(value: str) -> datetime:
    return datetime.strptime(value, MONTH_KEY_FORMAT)


def split_month_into_parts(month: str, messages: list[ArchiveMessage], max_chars: int) -> list[ChunkDraft]:
    parts: list[ChunkDraft] = []
    current_messages: list[ArchiveMessage] = []
    current_blocks: list[str] = []
    current_chars = 0

    for message in messages:
        block = render_archive_message(message) + "\n"
        block_len = len(block)

        if current_blocks and current_chars + block_len > max_chars:
            text = "".join(current_blocks).strip() + "\n"
            parts.append(
                ChunkDraft(
                    start_month=month,
                    end_month=month,
                    message_count=len(current_messages),
                    char_count=len(text),
                    first_message_date_utc=current_messages[0].date_utc,
                    last_message_date_utc=current_messages[-1].date_utc,
                    text=text,
                )
            )
            current_messages = []
            current_blocks = []
            current_chars = 0

        if block_len > max_chars and not current_blocks:
            text = block.strip() + "\n"
            parts.append(
                ChunkDraft(
                    start_month=month,
                    end_month=month,
                    message_count=1,
                    char_count=len(text),
                    first_message_date_utc=message.date_utc,
                    last_message_date_utc=message.date_utc,
                    text=text,
                )
            )
            continue

        current_messages.append(message)
        current_blocks.append(block)
        current_chars += block_len

    if current_blocks:
        text = "".join(current_blocks).strip() + "\n"
        parts.append(
            ChunkDraft(
                start_month=month,
                end_month=month,
                message_count=len(current_messages),
                char_count=len(text),
                first_message_date_utc=current_messages[0].date_utc,
                last_message_date_utc=current_messages[-1].date_utc,
                text=text,
            )
        )

    return parts


def merge_chunk_pair(left: ChunkDraft, right: ChunkDraft) -> ChunkDraft:
    text = f"{left.text.rstrip()}\n\n{right.text.lstrip()}".strip() + "\n"
    return ChunkDraft(
        start_month=left.start_month,
        end_month=right.end_month,
        message_count=left.message_count + right.message_count,
        char_count=len(text),
        first_message_date_utc=left.first_message_date_utc,
        last_message_date_utc=right.last_message_date_utc,
        text=text,
    )


def sort_messages_chronologically(messages: list[ArchiveMessage]) -> list[ArchiveMessage]:
    return sorted(
        messages,
        key=lambda message: (
            parse_date_utc(message.date_utc),
            message.id,
        ),
    )


def build_chunk_drafts(
    messages: list[ArchiveMessage],
    max_chars: int = 180000,
    soft_min_chars: int = 90000,
) -> list[ChunkDraft]:
    if not messages:
        return []

    ordered_messages = sort_messages_chronologically(messages)
    month_groups = group_messages_by_month(ordered_messages)
    month_order = sorted(month_groups.keys(), key=parse_month_key)

    raw_drafts: list[ChunkDraft] = []
    split_month_totals: dict[str, int] = {}

    for month in month_order:
        month_parts = split_month_into_parts(
            month=month,
            messages=month_groups[month],
            max_chars=max_chars,
        )
        raw_drafts.extend(month_parts)
        if len(month_parts) > 1:
            split_month_totals[month] = len(month_parts)

    merged: list[ChunkDraft] = []
    accumulator: ChunkDraft | None = None

    for draft in raw_drafts:
        is_real_split_month_part = split_month_totals.get(draft.start_month, 0) > 1

        if is_real_split_month_part:
            if accumulator is not None:
                merged.append(accumulator)
                accumulator = None
            merged.append(draft)
            continue

        if accumulator is None:
            accumulator = draft
            continue

        combined = merge_chunk_pair(accumulator, draft)
        if combined.char_count <= max_chars and accumulator.char_count < soft_min_chars:
            accumulator = combined
            continue

        merged.append(accumulator)
        accumulator = draft

    if accumulator is not None:
        merged.append(accumulator)

    split_month_seen: dict[str, int] = {}
    finalized: list[ChunkDraft] = []

    for draft in merged:
        file_name: str
        part_index: int | None = None
        part_total: int | None = None

        is_real_split_month_part = (
            draft.start_month == draft.end_month
            and split_month_totals.get(draft.start_month, 0) > 1
        )

        if is_real_split_month_part:
            part_total = split_month_totals[draft.start_month]
            part_index = split_month_seen.get(draft.start_month, 0) + 1
            split_month_seen[draft.start_month] = part_index
            file_name = f"{draft.start_month}-{draft.end_month}_part{part_index}.txt"
        else:
            file_name = f"{draft.start_month}-{draft.end_month}.txt"

        finalized.append(
            draft.model_copy(
                update={
                    "file_name": file_name,
                    "part_index": part_index,
                    "part_total": part_total,
                }
            )
        )

    return finalized


def build_chunk_summary(drafts: list[ChunkDraft]) -> list[ChunkInfo]:
    return [
        ChunkInfo(
            file_name=draft.file_name or "chunk.txt",
            start_month=draft.start_month,
            end_month=draft.end_month,
            part_index=draft.part_index,
            part_total=draft.part_total,
            message_count=draft.message_count,
            char_count=draft.char_count,
            first_message_date_utc=draft.first_message_date_utc,
            last_message_date_utc=draft.last_message_date_utc,
        )
        for draft in drafts
    ]
