# GitNotifyBot_bot

Telegram bot for tracking public GitHub repository updates and sending concise LLM-generated summaries.

## Architecture

The app is a modular monolith with two runtime processes:

- `bot`: Telegram UI, commands, buttons, and settings flows.
- `worker`: scheduled GitHub checks, LLM summaries, and notifications.

Both processes share PostgreSQL.

## Local Development

This section describes the completed foundation setup. During staged implementation, some
commands become available only after later foundation tasks add the app modules, Alembic
configuration, and Docker Compose services.

Install dependencies:

```bash
uv sync
```

Copy environment:

```bash
cp .env.example .env
```

Run tests:

```bash
uv run pytest
```

Run lint:

```bash
uv run ruff check .
```

Start local services:

```bash
docker compose up postgres
```

Run migrations:

```bash
uv run alembic upgrade head
```

Run bot process:

```bash
uv run python -m app.bot
```

Run worker process:

```bash
uv run python -m app.worker
```

## Status

End-to-end MVP complete: Telegram add/list/delete subscription flows,
manual "check now", per-chat language/style/preferences, Releases and
File modes with LLM-generated Russian/English summaries.
