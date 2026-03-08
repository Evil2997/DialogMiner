import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from telegram_export_tool.config import settings
from telegram_export_tool.dialog_registry import (
    get_saved_dialogs_path,
    get_scan_cache_path,
    load_saved_dialogs,
    load_scan_cache,
    save_saved_dialogs_from_indexes,
    save_scan_cache,
)
from telegram_export_tool.storage import (
    build_summary,
    ensure_output_paths,
    load_raw_archive,
    save_chunks,
    save_full_archive,
    save_raw_archive,
    save_summary,
)
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


def render_dialogs_table(title: str, rows: list[tuple[str, str, str]]) -> Table:
    table = Table(title=title)
    table.add_column("#", justify="right")
    table.add_column("Title")
    table.add_column("ID", justify="right")
    table.add_column("Type")

    for index, row in enumerate(rows, start=1):
        dialog_title, entity_id, entity_type = row
        table.add_row(str(index), dialog_title, entity_id, entity_type)

    return table


def export_archive_to_storage(
        archive,
        output_root: Path,
        max_chunk_chars: int,
        soft_min_chunk_chars: int,
) -> Path:
    chat_dir = resolve_chat_dir(output_root, archive.chat.slug)
    ensure_output_paths(chat_dir)
    save_raw_archive(chat_dir, archive)
    save_full_archive(chat_dir, archive)
    _, chunks_info = save_chunks(chat_dir, archive, max_chunk_chars, soft_min_chunk_chars)
    save_summary(chat_dir, build_summary(archive, chunks_info))
    return chat_dir


@app.command("scan-dialogs")
def scan_dialogs(
        limit: int = typer.Option(100, help="How many dialogs to scan"),
) -> None:
    async def run() -> None:
        client = await make_client(settings)
        try:
            rows = await list_dialog_rows(client, limit=limit)
        finally:
            await client.disconnect()

        save_scan_cache(rows)
        console.print(render_dialogs_table(f"Dialogs (limit={limit})", rows))
        console.print(f"Scan cache saved: {get_scan_cache_path()}")

    asyncio.run(run())


@app.command("save-dialogs")
def save_dialogs(
        indexes: list[int] = typer.Argument(..., help="Dialog numbers from the latest scan"),
) -> None:
    scan_rows = load_scan_cache()
    if not scan_rows:
        console.print("[red]No scan cache found.[/red] Run scan-dialogs first.")
        raise typer.Exit(code=1)

    try:
        saved_rows = save_saved_dialogs_from_indexes(scan_rows, indexes)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

    console.print(render_dialogs_table("Saved dialogs", saved_rows))
    console.print(f"Saved dialogs file: {get_saved_dialogs_path()}")


@app.command("list-saved")
def list_saved() -> None:
    saved_rows = load_saved_dialogs()
    if not saved_rows:
        console.print("[yellow]No saved dialogs.[/yellow]")
        console.print(f"Expected file: {get_saved_dialogs_path()}")
        return

    console.print(render_dialogs_table("Saved dialogs", saved_rows))
    console.print(f"Saved dialogs file: {get_saved_dialogs_path()}")


@app.command("export-chat")
def export_chat(
        chat: str = typer.Option(..., "--chat", help="Chat ID, username, or other valid Telegram chat reference"),
        since: str | None = typer.Option(None, "--since", help="Start date YYYY-MM-DD"),
        until: str | None = typer.Option(None, "--until", help="End date YYYY-MM-DD"),
        max_chunk_chars: int = typer.Option(180000, "--max-chunk-chars", min=1000),
        soft_min_chunk_chars: int = typer.Option(90000, "--soft-min-chunk-chars", min=0),
) -> None:
    async def run() -> None:
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

        chat_dir = export_archive_to_storage(
            archive=archive,
            output_root=settings.output_dir,
            max_chunk_chars=max_chunk_chars,
            soft_min_chunk_chars=soft_min_chunk_chars,
        )

        console.print(f"[green]Export complete[/green]: {chat_dir}")
        console.print(f"Messages: {archive.total_messages}")

    asyncio.run(run())


@app.command("export-saved")
def export_saved(
        since: str | None = typer.Option(None, "--since", help="Start date YYYY-MM-DD"),
        until: str | None = typer.Option(None, "--until", help="End date YYYY-MM-DD"),
        max_chunk_chars: int = typer.Option(180000, "--max-chunk-chars", min=1000),
        soft_min_chunk_chars: int = typer.Option(90000, "--soft-min-chunk-chars", min=0),
) -> None:
    async def run() -> None:
        saved_rows = load_saved_dialogs()
        if not saved_rows:
            console.print("[red]No saved dialogs.[/red] Run save-dialogs first.")
            raise typer.Exit(code=1)

        client = await make_client(settings)
        try:
            for index, row in enumerate(saved_rows, start=1):
                title, entity_id, entity_type = row
                console.print(f"[cyan]Exporting[/cyan] {index}/{len(saved_rows)}: {title} ({entity_type}, {entity_id})")

                archive = await export_chat_archive(
                    client=client,
                    chat_ref=entity_id,
                    since=parse_bound_date(since, is_end=False),
                    until=parse_bound_date(until, is_end=True),
                )

                chat_dir = export_archive_to_storage(
                    archive=archive,
                    output_root=settings.output_dir,
                    max_chunk_chars=max_chunk_chars,
                    soft_min_chunk_chars=soft_min_chunk_chars,
                )

                console.print(f"[green]Done[/green]: {chat_dir}")
        finally:
            await client.disconnect()

    asyncio.run(run())


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
