import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from telegram_export_tool.config import load_settings
from telegram_export_tool.storage import build_summary, ensure_output_paths, load_raw_archive, plan_chunks, save_chunks, save_full_archive, save_raw_archive, save_summary
from telegram_export_tool.telegram_api import export_chat_archive, list_dialog_rows, make_client

app = typer.Typer(add_completion=False)
console = Console()


def parse_bound_date(value: str | None, *, is_end: bool) -> datetime | None:
    if value is None:
        return None
    dt = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    if is_end:
        return dt + timedelta(days=1) - timedelta(seconds=1)
    return dt


def resolve_chat_dir(output_root: Path, slug: str) -> Path:
    return output_root / slug


@app.command("list-chats")
def list_chats(limit: int = typer.Option(100, help="How many dialogs to display")) -> None:
    async def run() -> None:
        settings = load_settings()
        client = await make_client(settings)
        try:
            rows = await list_dialog_rows(client, limit=limit)
            table = Table(title=f"Dialogs (limit={limit})")
            table.add_column("#", justify="right")
            table.add_column("Title")
            table.add_column("ID", justify="right")
            table.add_column("Type")
            for index, row in enumerate(rows, start=1):
                title, entity_id, entity_type = row
                table.add_row(str(index), title, entity_id, entity_type)
            console.print(table)
        finally:
            await client.disconnect()

    asyncio.run(run())


@app.command("export-chat")
def export_chat(
    chat: str = typer.Option(..., "--chat", help="Chat ID, username, or invite-resolved entity"),
    since: str | None = typer.Option(None, "--since", help="Start date YYYY-MM-DD"),
    until: str | None = typer.Option(None, "--until", help="End date YYYY-MM-DD"),
    max_chunk_chars: int = typer.Option(180000, "--max-chunk-chars", min=1000),
    soft_min_chunk_chars: int = typer.Option(90000, "--soft-min-chunk-chars", min=0),
) -> None:
    async def run() -> None:
        settings = load_settings()
        client = await make_client(settings)
        try:
            archive = await export_chat_archive(
                client=client,
                chat_ref=chat,
                since=parse_bound_date(since, is_end=False),
                until=parse_bound_date(until, is_end=True),
            )
        finally:
            await client.disconnect()

        chat_dir = resolve_chat_dir(settings.output_dir, archive.chat.slug)
        ensure_output_paths(chat_dir)
        raw_path = save_raw_archive(chat_dir, archive)
        full_archive_path = save_full_archive(chat_dir, archive)
        _, chunks_info = save_chunks(chat_dir, archive, max_chunk_chars, soft_min_chunk_chars)
        summary_path = save_summary(chat_dir, build_summary(archive, chunks_info))

        console.print(f"[green]Export complete[/green]: {chat_dir}")
        console.print(f"Messages: {archive.total_messages}")
        console.print(f"Raw JSON: {raw_path}")
        console.print(f"Full TXT: {full_archive_path}")
        console.print(f"Summary: {summary_path}")
        console.print(f"Chunks: {chat_dir / 'chunks'}")

    asyncio.run(run())


@app.command("build-archive")
def build_archive(
    raw_json: Path = typer.Option(..., "--raw-json", exists=True, file_okay=True, dir_okay=False),
) -> None:
    archive = load_raw_archive(raw_json)
    chat_dir = raw_json.parent
    path = save_full_archive(chat_dir, archive)
    console.print(f"[green]Full archive rebuilt[/green]: {path}")


@app.command("build-summary")
def build_summary_command(
    raw_json: Path = typer.Option(..., "--raw-json", exists=True, file_okay=True, dir_okay=False),
    max_chunk_chars: int = typer.Option(180000, "--max-chunk-chars", min=1000),
    soft_min_chunk_chars: int = typer.Option(90000, "--soft-min-chunk-chars", min=0),
) -> None:
    archive = load_raw_archive(raw_json)
    chat_dir = raw_json.parent
    chunks_info = plan_chunks(archive, max_chunk_chars, soft_min_chunk_chars)
    path = save_summary(chat_dir, build_summary(archive, chunks_info))
    console.print(f"[green]Summary rebuilt[/green]: {path}")


@app.command("build-chunks")
def build_chunks_command(
    raw_json: Path = typer.Option(..., "--raw-json", exists=True, file_okay=True, dir_okay=False),
    max_chunk_chars: int = typer.Option(180000, "--max-chunk-chars", min=1000),
    soft_min_chunk_chars: int = typer.Option(90000, "--soft-min-chunk-chars", min=0),
) -> None:
    archive = load_raw_archive(raw_json)
    chat_dir = raw_json.parent
    chunks_dir, chunks_info = save_chunks(chat_dir, archive, max_chunk_chars, soft_min_chunk_chars)
    console.print(f"[green]Chunks rebuilt[/green]: {chunks_dir}")
    console.print(f"Files: {len(chunks_info)}")