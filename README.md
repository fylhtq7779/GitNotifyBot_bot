# GitNotifyBot_bot

Telegram bot for tracking public GitHub repository updates and sending concise LLM-generated summaries.

## Architecture

The app is a modular monolith with two runtime processes:

- `bot`: Telegram UI, commands, buttons, and settings flows.
- `worker`: scheduled GitHub checks, LLM summaries, and notifications.

Both processes share PostgreSQL.

## Local Development

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
