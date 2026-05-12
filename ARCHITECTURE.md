# Architecture

## Overview

DialogMiner is a CLI tool for exporting Telegram chat history. The codebase is organized around a single responsibility per module: each file does one thing and delegates everything else.

---

## Module Responsibilities

**`telegram_api.py`** — all Telegram interaction. Connects the client, resolves chat entities, iterates message history. Raises typed exceptions (`TelegramAuthError`, `TelegramEntityResolveError`, `TelegramHistoryReadError`) so the CLI can handle errors cleanly without catching broad exceptions.

**`formatting.py`** — message conversion and text rendering. Converts raw Telethon `Message` objects into `ArchiveMessage` models, resolves author names, handles forwarded messages, normalizes text (whitespace, line endings). Also renders messages to human-readable strings and groups them by month.

**`chunking.py`** — the core splitting algorithm. Takes a flat list of messages and produces sized chunks respecting monthly boundaries. Small adjacent months are merged up; large months are split into numbered parts. The algorithm operates in two passes: split first, then merge where possible.

**`storage.py`** — all file I/O. Writes raw JSON, full text archive, chunk files, and summary. Reads raw archives back for rebuilding. Raises typed storage exceptions to separate I/O failures from business logic.

**`dialog_registry.py`** — local state management. Persists scan cache and saved dialog selections to JSON files in the state directory. Validates data on read with Pydantic to catch corruption early.

**`models.py`** — data structures. All domain objects are Pydantic models: `ArchiveMessage`, `ChatInfo`, `RawArchive`, `ChunkInfo`, `ChunkDraft`, `Summary`.

**`config.py`** — settings from `.env` with `TG_` prefix via pydantic-settings. Cached with `lru_cache`.

**`paths.py`** — single source of truth for directory layout. `MAIN_DIR` is anchored to the package root via `Path(__file__).resolve().parents[1]`.

**`cli.py`** — Typer commands. Orchestrates the above modules. No business logic here — only wiring and user-facing output via Rich.

---

## Key Design Decisions

### Typed exceptions per layer
Every module defines its own exception hierarchy. The CLI catches specific types and exits with meaningful codes. No bare `except Exception` in user-facing paths.

### Chunking algorithm
Messages are sorted chronologically, grouped by month, then processed in two stages. First pass: split any month that exceeds the hard maximum into parts. Second pass: merge consecutive small months if the combined size stays under the maximum and the left side is below the soft minimum. This produces chunks that are neither too small nor too large without hardcoding boundaries.

### No mutations after export
`RawArchive` stores the original messages. Chunks and the full text archive are always derived from it. If chunking parameters change, `build-chunks` regenerates everything from the stored JSON without touching Telegram.

### Pydantic everywhere
All data that crosses a boundary (Telegram → domain, disk → domain) is validated through Pydantic models. Invalid data raises `StorageValidationError` or `DialogRegistryValidationError` early, before it can cause silent corruption.

---

## Data Flow

```
Telegram API
  → telegram_api.py: fetch raw messages
  → formatting.py: convert to ArchiveMessage list
  → storage.py: write raw_messages.json + full_archive.txt
  → chunking.py: build chunk drafts
  → storage.py: write chunks/ + summary.json
```

Rebuild path (no Telegram):
```
raw_messages.json
  → storage.py: load RawArchive
  → chunking.py: rebuild drafts
  → storage.py: overwrite chunks/ + summary.json
```

---

## Output Layout

```
output/
└── <chat-slug>/
    ├── raw_messages.json   # source of truth, never regenerated
    ├── full_archive.txt    # derived, can be rebuilt
    ├── summary.json        # derived, can be rebuilt
    └── chunks/             # derived, can be rebuilt
        ├── 01.2024-03.2024.txt
        └── 04.2024-04.2024_part1.txt
```

---

## Potential Extensions

- **Incremental export** — fetch only messages newer than the last export date stored in `summary.json`
- **Multiple export formats** — markdown, HTML in addition to plain text
- **Media metadata** — include file names and types for messages with attachments