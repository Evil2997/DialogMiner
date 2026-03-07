import asyncio
import os
import re
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Optional

import typer
from dotenv import load_dotenv
from rich import print
from rich.console import Console
from rich.table import Table
from telethon import TelegramClient
from telethon.errors import FloodWaitError, RPCError
from telethon.tl.types import Message

app = typer.Typer(add_completion=False)
console = Console()


# ----------------------------
# Helpers
# ----------------------------

def month_key(dt: datetime) -> str:
    # "02.2026"
    return dt.strftime("%m.%Y")


def normalize_ws(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def safe_sender_name(msg: Message) -> str:
    # In groups it may be None sometimes (anonymous admin, service msg, etc.)
    sender = getattr(msg, "sender", None)
    if sender:
        fn = getattr(sender, "first_name", "") or ""
        ln = getattr(sender, "last_name", "") or ""
        un = getattr(sender, "username", "") or ""
        name = (fn + " " + ln).strip()
        if not name and un:
            name = f"@{un}"
        return name or "unknown"
    return "unknown"


def fmt_msg(msg: Message) -> Optional[str]:
    if not msg:
        return None
    if not getattr(msg, "message", None):
        return None

    dt = msg.date
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    dt_str = dt.astimezone(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

    sender = safe_sender_name(msg)
    text = normalize_ws(msg.message)

    # Можно добавить ссылку на сообщение, если это публичный канал/чат с username.
    # Для приватных групп ссылки может не быть — оставим только ID.
    return f"[{dt_str}] {sender}\n{text}\n"


@dataclass
class Chunk:
    start_month: str
    end_month: str
    text: str
    msg_count: int


def build_chunks(
        messages: list[Message],
        max_chars: int,
        min_chars: int,
        header_prefix: str,
) -> list[Chunk]:
    """
    Алгоритм:
    - Идем по сообщениям (старые -> новые)
    - Собираем текущий чанк пока не упремся в max_chars
    - При этом "диапазон месяцев" определяется по первому/последнему сообщению в чанке
    - min_chars используется, чтобы не отправлять слишком маленькие чанки: если вышли меньше min_chars,
      пытаемся добрать следующими сообщениями (если это возможно).
    """
    chunks: list[Chunk] = []

    cur_lines: list[str] = []
    cur_len = 0
    cur_start_month: Optional[str] = None
    cur_end_month: Optional[str] = None
    cur_count = 0

    def current_text_preview_len() -> int:
        # учитываем шапку, которую добавим при отправке
        if cur_start_month and cur_end_month:
            title = f"{header_prefix} {cur_start_month}-{cur_end_month}\n\n"
        else:
            title = f"{header_prefix}\n\n"
        return len(title) + cur_len

    def flush():
        nonlocal cur_lines, cur_len, cur_start_month, cur_end_month, cur_count
        if not cur_lines:
            return
        text_body = "".join(cur_lines).strip() + "\n"
        chunks.append(Chunk(
            start_month=cur_start_month or "??.????",
            end_month=cur_end_month or "??.????",
            text=text_body,
            msg_count=cur_count
        ))
        cur_lines = []
        cur_len = 0
        cur_start_month = None
        cur_end_month = None
        cur_count = 0

    for msg in messages:
        line = fmt_msg(msg)
        if not line:
            continue

        mkey = month_key(msg.date)
        if cur_start_month is None:
            cur_start_month = mkey
        cur_end_month = mkey

        # если добавление строки превысит max_chars — отправляем текущий чанк
        # но сначала проверим: не пустой ли он (иначе придется резать даже один пост)
        projected = current_text_preview_len() + len(line)

        if cur_lines and projected > max_chars:
            # если текущий чанк слишком маленький — попробуем все равно принять,
            # потому что иначе будем бесконечно пытаться "добрать".
            flush()

            # после flush начнем новый
            cur_start_month = mkey
            cur_end_month = mkey

        # Если один пост сам по себе больше max_chars — режем его по частям
        # (Telegram и LLM лимиты бывают жесткие; лучше резать безопасно)
        if len(line) > max_chars:
            # сначала отправим накопленное, если есть
            if cur_lines:
                flush()
                cur_start_month = mkey
                cur_end_month = mkey

            # режем line на куски
            start = 0
            while start < len(line):
                part = line[start:start + (max_chars - 200)]  # запас под заголовок/маркировку
                part = part.strip()
                if part:
                    chunks.append(Chunk(
                        start_month=mkey,
                        end_month=mkey,
                        text=part + "\n",
                        msg_count=1
                    ))
                start += (max_chars - 200)
            # сбрасываем состояние
            cur_lines = []
            cur_len = 0
            cur_start_month = None
            cur_end_month = None
            cur_count = 0
            continue

        # обычное добавление
        cur_lines.append(line)
        cur_len += len(line)
        cur_count += 1

    # финальный flush
    flush()

    # Пост-обработка min_chars: склеиваем слишком маленькие чанки с последующим, если можем
    if min_chars > 0 and len(chunks) > 1:
        merged: list[Chunk] = []
        i = 0
        while i < len(chunks):
            c = chunks[i]
            # приблизительная длина с заголовком:
            title_len = len(f"{header_prefix} {c.start_month}-{c.end_month}\n\n")
            total_len = title_len + len(c.text)

            if total_len < min_chars and i + 1 < len(chunks):
                nxt = chunks[i + 1]
                # пробуем склеить, если не превысим max_chars
                merged_title_len = len(f"{header_prefix} {c.start_month}-{nxt.end_month}\n\n")
                merged_total = merged_title_len + len(c.text) + len(nxt.text)
                if merged_total <= max_chars:
                    merged.append(Chunk(
                        start_month=c.start_month,
                        end_month=nxt.end_month,
                        text=(c.text + "\n" + nxt.text).strip() + "\n",
                        msg_count=c.msg_count + nxt.msg_count
                    ))
                    i += 2
                    continue

            merged.append(c)
            i += 1
        chunks = merged

    return chunks


async def safe_send(client: TelegramClient, entity, text: str, delay_s: float) -> None:
    while True:
        try:
            await client.send_message(entity, text)
            await asyncio.sleep(delay_s)
            return
        except FloodWaitError as e:
            wait_s = int(getattr(e, "seconds", 0) or 0)
            print(f"[yellow]FloodWait: нужно подождать {wait_s} секунд...[/yellow]")
            await asyncio.sleep(wait_s + 1)
        except RPCError as e:
            # На практике можно логировать детальнее, но тут CLI — просто покажем и стопнем.
            raise RuntimeError(f"Telegram RPC error: {e.__class__.__name__}: {e}") from e


def load_cfg():
    load_dotenv()
    api_id = os.getenv("TG_API_ID")
    api_hash = os.getenv("TG_API_HASH")
    phone = os.getenv("TG_PHONE")
    session = os.getenv("TG_SESSION", "pdfnik_sender")

    if not api_id or not api_hash:
        raise RuntimeError("Не найдены TG_API_ID / TG_API_HASH в .env")

    return int(api_id), api_hash, phone, session


async def make_client() -> TelegramClient:
    api_id, api_hash, _, session = load_cfg()
    client = TelegramClient(session, api_id, api_hash)
    await client.connect()
    if not await client.is_user_authorized():
        print("[cyan]Первый вход: Telethon попросит код подтверждения из Telegram.[/cyan]")
        # Telethon сам интерактивно запросит phone/code через input() при start()
        # Но start() требует phone, иначе спросит.
        _, _, phone, _ = load_cfg()
        await client.start(phone=phone)
    return client


# ----------------------------
# CLI Commands
# ----------------------------

@app.command("list-chats")
def list_chats(limit: int = typer.Option(200, help="Сколько диалогов показать")):
    """
    Вывести список диалогов (группы/каналы/лички) с их ID.
    """

    async def run():
        client = await make_client()
        try:
            dialogs = await client.get_dialogs(limit=limit)
            table = Table(title=f"Dialogs (limit={limit})")
            table.add_column("№", justify="right")
            table.add_column("Title")
            table.add_column("ID", justify="right")
            table.add_column("Type")

            for i, d in enumerate(dialogs, start=1):
                ent = d.entity
                # type hints: Chat / Channel / User
                t = ent.__class__.__name__
                table.add_row(str(i), str(d.name), str(d.id), t)
            console.print(table)
        finally:
            await client.disconnect()

    asyncio.run(run())


@app.command("send")
def send(
        chat: str = typer.Option(..., help="ID чата (например -100123...) или username/название"),
        bot: str = typer.Option(..., help="Username бота (например @PDFnikBot) или его ID"),
        max_chars: int = typer.Option(3200, help="Максимум символов в одном сообщении боту"),
        min_chars: int = typer.Option(1200, help="Желаемый минимум (если меньше — попробуем слить со следующим)"),
        delay_s: float = typer.Option(1.2, help="Задержка между отправками, секунд"),
        header: str = typer.Option("PDFnik export:", help="Префикс заголовка чанка"),
        since: Optional[str] = typer.Option(None, help="Начало периода YYYY-MM-DD (включительно)"),
        until: Optional[str] = typer.Option(None, help="Конец периода YYYY-MM-DD (включительно)"),
        hard_limit: int = typer.Option(2000, help="Жесткий лимит сообщений на выгрузку (на всякий)"),
        dry_run: bool = typer.Option(False, help="Не отправлять, только показать план"),
):
    """
    Выгрузить сообщения из чата, нарезать на чанки и отправить боту.
    """

    def parse_date(s: Optional[str]) -> Optional[datetime]:
        if not s:
            return None
        dt = datetime.strptime(s, "%Y-%m-%d")
        return dt.replace(tzinfo=timezone.utc)

    since_dt = parse_date(since)
    until_dt = parse_date(until)

    async def run():
        client = await make_client()
        try:
            chat_entity = await client.get_entity(chat)
            bot_entity = await client.get_entity(bot)

            # Забираем сообщения. Telethon iter_messages по умолчанию от новых к старым.
            # Нам надо старые -> новые, поэтому соберем и перевернем.
            msgs: list[Message] = []
            async for m in client.iter_messages(chat_entity, limit=hard_limit):
                # фильтр по дате
                if m.date and m.date.tzinfo is None:
                    m.date = m.date.replace(tzinfo=timezone.utc)

                if since_dt and m.date and m.date < since_dt:
                    # так как идем от новых к старым, можно заканчивать
                    break
                if until_dt and m.date and m.date > until_dt:
                    continue
                msgs.append(m)

            msgs.reverse()

            # Убираем совсем пустое и сервисное в fmt_msg()
            chunks = build_chunks(
                messages=msgs,
                max_chars=max_chars,
                min_chars=min_chars,
                header_prefix=header,
            )

            print(f"[green]Сообщений (сырьё): {len(msgs)}[/green]")
            print(f"[green]Чанков к отправке: {len(chunks)}[/green]")

            # Покажем план
            for idx, c in enumerate(chunks, start=1):
                title = f"{header} {c.start_month}-{c.end_month}"
                approx_len = len(title) + 2 + len(c.text)
                print(f"[cyan]#{idx}[/cyan] {c.start_month}-{c.end_month} | msgs={c.msg_count} | chars~={approx_len}")

            if dry_run:
                print("[yellow]dry-run включен: ничего не отправляем.[/yellow]")
                return

            # Отправка
            for idx, c in enumerate(chunks, start=1):
                title = f"{header} {c.start_month}-{c.end_month}"
                payload = f"{title}\n\n{c.text}".strip()

                # Telegram лимит на одно сообщение ~4096 символов (зависит), поэтому max_chars лучше держать <= 3500.
                if len(payload) > max_chars + 500:
                    # на всякий, если заголовок/склейка дала перелет
                    payload = payload[:max_chars]

                print(f"[blue]Sending #{idx}/{len(chunks)}[/blue] ({c.start_month}-{c.end_month}) ...")
                await safe_send(client, bot_entity, payload, delay_s=delay_s)

            print("[green]Готово: все чанки отправлены.[/green]")

        finally:
            await client.disconnect()

    asyncio.run(run())


if __name__ == "__main__":
    app()


# │  20 │ Егор Пыриков                                                             │ -1001613236732 │ Channel │
# │  22 │ [PYTHON:TODAY]                                                           │ -1001125084041 │ Channel │
# │  24 │ сбежавшая нейросеть                                                      │ -1002343435951 │ Channel │
# │  26 │ Твой пет проект                                                          │ -1002025880809 │ Channel │
# │  30 │ Профессор Клинков                                                        │ -1001435570463 │ Channel │
