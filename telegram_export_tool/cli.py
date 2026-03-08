import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import typer
from rich.console import Console
from rich.table import Table

from telegram_export_tool.config import settings
from telegram_export_tool.dialog_registry import (
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


def render_dialogs_table(title: str, rows: list[tuple[str, str, str]]) -> Table:
    table = Table(title=title)
    table.add_column("#", justify="right")
    table.add_column("Title")
    table.add_column("ID", justify="right")
    table.add_column("Type")

    for index, row in enumerate(rows, start=1):
        title_, entity_id, entity_type = row
        table.add_row(str(index), title_, entity_id, entity_type)

    return table


def export_archive(archive) -> Path:
    chat_dir = settings.chat_output_dir(archive.chat.slug)

    ensure_output_paths(chat_dir)

    raw_path = save_raw_archive(chat_dir, archive)
    full_path = save_full_archive(chat_dir, archive)

    chunks_dir, chunks_info = save_chunks(
        chat_dir,
        archive,
        max_chars=180000,
        soft_min_chars=90000,
    )

    summary_path = save_summary(chat_dir, build_summary(archive, chunks_info))

    console.print(f"[green]Export complete[/green]: {chat_dir}")
    console.print(f"Messages: {archive.total_messages}")
    console.print(f"Raw JSON: {raw_path}")
    console.print(f"Full TXT: {full_path}")
    console.print(f"Summary: {summary_path}")
    console.print(f"Chunks: {chunks_dir}")

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
        console.print(f"Scan cache saved: {settings.scan_cache_path()}")

    asyncio.run(run())


@app.command("save-dialogs")
def save_dialogs(
        indexes: list[int] = typer.Argument(...),
) -> None:
    scan_rows = load_scan_cache()

    if not scan_rows:
        console.print("[red]No scan cache found. Run scan-dialogs first.[/red]")
        raise typer.Exit(code=1)

    saved_rows = save_saved_dialogs_from_indexes(scan_rows, indexes)

    console.print(render_dialogs_table("Saved dialogs", saved_rows))


@app.command("list-saved")
def list_saved() -> None:
    rows = load_saved_dialogs()

    if not rows:
        console.print("[yellow]No saved dialogs[/yellow]")
        return

    console.print(render_dialogs_table("Saved dialogs", rows))


@app.command("export-chat")
def export_chat(
        chat: str = typer.Option(..., "--chat"),
        since: str | None = typer.Option(None),
        until: str | None = typer.Option(None),
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

        export_archive(archive)

    asyncio.run(run())


@app.command("export-saved")
def export_saved() -> None:
    async def run() -> None:
        rows = load_saved_dialogs()

        if not rows:
            console.print("[red]No saved dialogs. Run save-dialogs first.[/red]")
            raise typer.Exit(code=1)

        client = await make_client(settings)

        try:
            for title, entity_id, entity_type in rows:
                console.print(f"[cyan]Exporting[/cyan] {title} ({entity_type})")

                archive = await export_chat_archive(
                    client=client,
                    chat_ref=entity_id,
                )

                export_archive(archive)

        finally:
            await client.disconnect()

    asyncio.run(run())


@app.command("build-chunks")
def build_chunks(
        raw_json: Path | None = typer.Option(None, "--raw-json"),
) -> None:
    if raw_json is not None:
        archive = load_raw_archive(raw_json)
        chat_dir = raw_json.parent
        chunks_dir, chunks_info = save_chunks(chat_dir, archive, 180000, 90000)

        console.print(f"[green]Chunks rebuilt[/green]: {chunks_dir}")
        console.print(f"Files: {len(chunks_info)}")
        return

    rows = load_saved_dialogs()

    if not rows:
        console.print("[red]No saved dialogs[/red]")
        raise typer.Exit(code=1)

    for title, entity_id, _ in rows:
        slug = title.lower().replace(" ", "_")
        chat_dir = settings.chat_output_dir(slug)
        raw_json_path = chat_dir / "raw_messages.json"

        if not raw_json_path.exists():
            console.print(f"[yellow]Skipping {title}: raw_messages.json not found[/yellow]")
            continue

        archive = load_raw_archive(raw_json_path)
        chunks_dir, chunks_info = save_chunks(chat_dir, archive, 180000, 90000)

        console.print(f"[green]Chunks rebuilt[/green]: {chunks_dir}")
        console.print(f"Files: {len(chunks_info)}")
