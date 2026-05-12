# DialogMiner

CLI-инструмент для экспорта истории Telegram-чатов через пользовательскую сессию (не бот). Сохраняет переписку в виде структурированного архива и нарезает её на текстовые чанки, удобные для подачи в LLM.

---

## Что умеет

- Подключается к Telegram через пользовательскую сессию (Telethon)
- Сканирует список диалогов и позволяет выбрать нужные
- Экспортирует историю чата с фильтрацией по дате (`--since`, `--until`)
- Сохраняет три формата вывода:
  - `raw_messages.json` — полный архив в JSON для переиспользования
  - `full_archive.txt` — вся история в читаемом текстовом виде
  - `chunks/` — история, разбитая на части по месяцам, с учётом лимитов LLM-контекста
- Формирует `summary.json` — статистика по чату (авторы, медиа, форварды, количество чанков)
- Позволяет перестроить чанки из уже сохранённого архива без повторных запросов к Telegram

---

## Стек

- **Python 3.11+**
- [Telethon](https://github.com/LonamiWebs/Telethon) — Telegram MTProto клиент
- [Typer](https://typer.tiangolo.com/) — CLI
- [Rich](https://github.com/Textualize/rich) — красивый вывод в терминале
- [Pydantic](https://docs.pydantic.dev/) + [pydantic-settings](https://docs.pydantic.dev/latest/concepts/pydantic_settings/) — модели и конфиг из `.env`
- [uv](https://github.com/astral-sh/uv) — управление зависимостями

---

## Установка

```bash
git clone https://github.com/Evil2997/DialogMiner.git
cd DialogMiner

# Установить зависимости через uv
uv sync
```

---

## Настройка

Скопируй `.env.example` в `.env` и заполни:

```bash
cp .env.example .env
```

```env
TG_API_ID=123456
TG_API_HASH=0123456789abcdef0123456789abcdef
TG_PHONE=+79001234567
TG_SESSION_NAME=my_session   # опционально, по умолчанию telegram_export_session
```

`TG_API_ID` и `TG_API_HASH` можно получить на [my.telegram.org](https://my.telegram.org/apps).

При первом запуске Telethon запросит код подтверждения и создаст файл сессии рядом с проектом.

---

## Использование

### 1. Просмотр доступных диалогов

```bash
uv run python main.py scan-dialogs
uv run python main.py scan-dialogs --limit 200
```

Выводит таблицу диалогов с номерами, названиями и ID. Результат кешируется локально.

### 2. Сохранить нужные диалоги по номеру из таблицы

```bash
uv run python main.py save-dialogs 1 5 12
```

### 3. Посмотреть сохранённые диалоги

```bash
uv run python main.py list-saved
```

### 4. Экспортировать конкретный чат

```bash
# По username или ID
uv run python main.py export-chat --chat @username
uv run python main.py export-chat --chat 123456789

# С фильтром по дате
uv run python main.py export-chat --chat @username --since 2024-01-01 --until 2024-06-30
```

### 5. Экспортировать все сохранённые диалоги

```bash
uv run python main.py export-saved
```

### 6. Перестроить чанки без обращения к Telegram

```bash
# Из конкретного архива
uv run python main.py build-chunks --raw-json output/chatname/raw_messages.json

# По всем сохранённым диалогам (если архивы уже есть)
uv run python main.py build-chunks
```

---

## Структура вывода

```
output/
└── chat-slug/
    ├── raw_messages.json      # полный архив (JSON)
    ├── full_archive.txt       # вся история (текст)
    ├── summary.json           # статистика
    └── chunks/
        ├── 01.2024-02.2024.txt
        ├── 03.2024-03.2024_part1.txt
        ├── 03.2024-03.2024_part2.txt
        └── ...
```

Чанки нарезаются по месяцам. Если месяц слишком большой — делится на части. Маленькие соседние месяцы объединяются. Лимиты: мягкий минимум 90 000 символов, жёсткий максимум 180 000 символов на чанк.

---

## Зачем это нужно

Основной сценарий — подготовка истории переписки для анализа через LLM (ChatGPT, Claude и др.). Чанки по размеру подогнаны под стандартные контекстные окна, а `summary.json` позволяет быстро ориентироваться в архиве.

---

## Лицензия

MIT
