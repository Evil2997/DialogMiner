import asyncio
from datetime import datetime, timedelta, timezone
from pathlib import Path

import typer
from pydantic import ValidationError
from rich.console import Console
from rich.table import Table

from telegram_export_tool.config import Settings, load_settings
from telegram_export_tool.dialog_registry import (
    load_saved_dialogs,
    load_scan_cache,
    save_saved_dialogs_from_indexes,
    save_scan_cache,
)
from telegram_export_tool.models import RawArchive
from telegram_export_tool.storage import (
    build_summary,
    ensure_output_paths,
    load_raw_archive,
    save_chunks,
    save_full_archive,
    save_raw_archive,
    save_summary,
)
from telegram_export_tool.telegram_api import (
    TelegramAuthError,
    TelegramEntityResolveError,
    TelegramHistoryReadError,
    export_chat_archive,
    list_dialog_rows,
    make_client,
)

app = typer.Typer(add_completion=False)
console = Console()


def parse_bound_date(value: str | None, *, is_end: bool) -> datetime | None:
    if value is None:
        return None

    try:
        dt = datetime.strptime(value, "%Y-%m-%d").replace(tzinfo=timezone.utc)
    except ValueError as exc:
        raise typer.BadParameter("Date must be in YYYY-MM-DD format.") from exc

    if is_end:
        return dt + timedelta(days=1) - timedelta(seconds=1)
    return dt


def get_settings_or_exit() -> Settings:
    try:
        return load_settings()
    except ValidationError as exc:
        console.print("[red]Invalid configuration.[/red]")
        for error in exc.errors():
            field = ".".join(str(part) for part in error.get("loc", []))
            message = error.get("msg", "Invalid value")
            console.print(f"- {field}: {message}")
        raise typer.Exit(code=1) from exc


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


def export_archive(archive: RawArchive) -> Path:
    settings = get_settings_or_exit()
    chat_dir = settings.chat_output_dir(archive.chat.slug)

    ensure_output_paths(chat_dir)

    raw_path = save_raw_archive(chat_dir, archive)
    full_path = save_full_archive(chat_dir, archive)

    chunks_dir, chunks_info = save_chunks(
        chat_dir,
        archive,
        max_chars=180_000,
        soft_min_chars=90_000,
    )

    summary_path = save_summary(chat_dir, build_summary(archive, chunks_info))

    console.print(f"[green]Export complete[/green]: {chat_dir}")
    console.print(f"Messages: {archive.total_messages}")
    console.print(f"Raw JSON: {raw_path}")
    console.print(f"Full TXT: {full_path}")
    console.print(f"Summary: {summary_path}")
    console.print(f"Chunks: {chunks_dir}")

    return chat_dir


def find_chat_dir_for_archive(settings: Settings, archive: RawArchive) -> Path:
    return settings.chat_output_dir(archive.chat.slug)


def find_saved_archive_path(settings: Settings, entity_id: str, fallback_title: str) -> Path | None:
    for raw_json_path in sorted(settings.output_dir.glob("*/raw_messages.json")):
        try:
            archive = load_raw_archive(raw_json_path)
        except Exception:
            continue

        if str(archive.chat.id) == entity_id:
            return raw_json_path

    fallback_chat_dir = settings.chat_output_dir(fallback_title)
    fallback_raw_json = fallback_chat_dir / "raw_messages.json"
    if fallback_raw_json.exists():
        return fallback_raw_json

    return None


def print_telegram_error(exc: Exception) -> None:
    console.print(f"[red]{exc}[/red]")


@app.command("scan-dialogs")
def scan_dialogs(
    limit: int = typer.Option(100, help="How many dialogs to scan"),
) -> None:
    async def run() -> None:
        settings = get_settings_or_exit()
        client = await make_client(settings)

        try:
            rows = await list_dialog_rows(client, limit=limit)
        finally:
            await client.disconnect()

        cache_path = save_scan_cache(rows)

        console.print(render_dialogs_table(f"Dialogs (limit={limit})", rows))
        console.print(f"Scan cache saved: {cache_path}")

    try:
        asyncio.run(run())
    except (TelegramAuthError, TelegramHistoryReadError) as exc:
        print_telegram_error(exc)
        raise typer.Exit(code=1) from exc


@app.command("save-dialogs")
def save_dialogs(
    indexes: list[int] = typer.Argument(...),
) -> None:
    scan_rows = load_scan_cache()

    if not scan_rows:
        console.print("[red]No scan cache found. Run scan-dialogs first.[/red]")
        raise typer.Exit(code=1)

    try:
        saved_rows = save_saved_dialogs_from_indexes(scan_rows, indexes)
    except ValueError as exc:
        console.print(f"[red]{exc}[/red]")
        raise typer.Exit(code=1) from exc

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
        settings = get_settings_or_exit()
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

    try:
        asyncio.run(run())
    except (TelegramAuthError, TelegramEntityResolveError, TelegramHistoryReadError) as exc:
        print_telegram_error(exc)
        raise typer.Exit(code=1) from exc


@app.command("export-saved")
def export_saved() -> None:
    async def run() -> None:
        rows = load_saved_dialogs()

        if not rows:
            console.print("[red]No saved dialogs. Run save-dialogs first.[/red]")
            raise typer.Exit(code=1)

        settings = get_settings_or_exit()
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

    try:
        asyncio.run(run())
    except (TelegramAuthError, TelegramEntityResolveError, TelegramHistoryReadError) as exc:
        print_telegram_error(exc)
        raise typer.Exit(code=1) from exc


@app.command("build-chunks")
def build_chunks(
    raw_json: Path | None = typer.Option(None, "--raw-json"),
) -> None:
    settings = get_settings_or_exit()

    if raw_json is not None:
        if not raw_json.exists():
            console.print(f"[red]File not found: {raw_json}[/red]")
            raise typer.Exit(code=1)

        archive = load_raw_archive(raw_json)
        chat_dir = raw_json.parent

        chunks_dir, chunks_info = save_chunks(
            chat_dir,
            archive,
            max_chars=180_000,
            soft_min_chars=90_000,
        )

        console.print(f"[green]Chunks rebuilt[/green]: {chunks_dir}")
        console.print(f"Files: {len(chunks_info)}")
        return

    rows = load_saved_dialogs()

    if not rows:
        console.print("[red]No saved dialogs[/red]")
        raise typer.Exit(code=1)

    for title, entity_id, _ in rows:
        raw_json_path = find_saved_archive_path(settings, entity_id=entity_id, fallback_title=title)

        if raw_json_path is None:
            console.print(f"[yellow]Skipping {title}: raw_messages.json not found[/yellow]")
            continue

        archive = load_raw_archive(raw_json_path)
        chat_dir = find_chat_dir_for_archive(settings, archive)

        chunks_dir, chunks_info = save_chunks(
            chat_dir,
            archive,
            max_chars=180_000,
            soft_min_chars=90_000,
        )

        console.print(f"[green]Chunks rebuilt[/green]: {chunks_dir}")
        console.print(f"Files: {len(chunks_info)}")