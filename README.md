# DialogMiner

CLI tool for exporting Telegram chat history via a user session (not a bot). Saves conversations as structured archives and splits them into text chunks sized for LLM context windows.

---

## What it does

- Connects to Telegram via a user session (Telethon)
- Scans dialog list and lets you select the ones you need
- Exports chat history with optional date filtering (`--since`, `--until`)
- Saves three output formats:
  - `raw_messages.json` — full archive in JSON for reuse
  - `full_archive.txt` — entire history as readable plain text
  - `chunks/` — history split into monthly parts, respecting LLM context limits
- Generates `summary.json` — chat statistics (authors, media, forwards, chunk count)
- Allows rebuilding chunks from an existing archive without re-fetching from Telegram

---

## Stack

- **Python 3.11+**
- [Telethon](https://github.com/LonamiWebs/Telethon) — Telegram MTProto client
- [Typer](https://typer.tiangolo.com/) — CLI
- [Rich](https://github.com/Textualize/rich) — terminal output
- [Pydantic](https://docs.pydantic.dev/) + [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) — models and `.env` config
- [uv](https://github.com/astral-sh/uv) — dependency management

---

## Installation

```bash
git clone https://github.com/Evil2997/DialogMiner.git
cd DialogMiner
uv sync
```

---

## Configuration

Copy `.env.example` to `.env` and fill in your credentials:

```bash
cp .env.example .env
```

```env
TG_API_ID=123456
TG_API_HASH=0123456789abcdef0123456789abcdef
TG_PHONE=+79001234567
TG_SESSION_NAME=my_session   # optional, default: telegram_export_session
```

`TG_API_ID` and `TG_API_HASH` are available at [my.telegram.org](https://my.telegram.org/apps).

On first run Telethon will prompt for a confirmation code and create a session file.

---

## Usage

### 1. Scan available dialogs

```bash
uv run python main.py scan-dialogs
uv run python main.py scan-dialogs --limit 200
```

Prints a table with dialog numbers, titles, and IDs. Result is cached locally.

### 2. Save dialogs by number

```bash
uv run python main.py save-dialogs 1 5 12
```

### 3. List saved dialogs

```bash
uv run python main.py list-saved
```

### 4. Export a specific chat

```bash
uv run python main.py export-chat --chat @username
uv run python main.py export-chat --chat 123456789
uv run python main.py export-chat --chat @username --since 2024-01-01 --until 2024-06-30
```

### 5. Export all saved dialogs

```bash
uv run python main.py export-saved
```

### 6. Rebuild chunks without fetching from Telegram

```bash
uv run python main.py build-chunks --raw-json output/chatname/raw_messages.json
uv run python main.py build-chunks
```

---

## Output structure

```
output/
└── chat-slug/
    ├── raw_messages.json
    ├── full_archive.txt
    ├── summary.json
    └── chunks/
        ├── 01.2024-02.2024.txt
        ├── 03.2024-03.2024_part1.txt
        ├── 03.2024-03.2024_part2.txt
        └── ...
```

Chunks are split by month. Large months are divided into parts; small adjacent months are merged. Soft minimum: 90,000 characters. Hard maximum: 180,000 characters per chunk.

---

## Why

The primary use case is preparing chat history for LLM analysis (ChatGPT, Claude, etc.). Chunks are sized to fit standard context windows, and `summary.json` helps navigate the archive quickly.