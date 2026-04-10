# Database

Ergon uses **PostgreSQL 15** for all environments. Schema is managed by
[Alembic](https://alembic.sqlalchemy.org/) migrations in `ergon_core/migrations/`.

## Quick reference

| Task | Command |
|------|---------|
| Start Postgres | `docker compose up postgres -d` |
| Apply migrations | `cd ergon_core && alembic upgrade head` |
| Auto-generate a migration | `cd ergon_core && alembic revision --autogenerate -m "describe change"` |
| Check current revision | `cd ergon_core && alembic current` |
| Show migration history | `cd ergon_core && alembic history` |

## Connection

The database URL is configured via `ERGON_DATABASE_URL` or `DATABASE_URL`
environment variable (checked in that order). The default points at the
docker-compose Postgres:

```
postgresql://ergon:ergon_dev@localhost:5433/ergon
```

Override the port in `.env` if 5433 conflicts with another project.

## How migrations work

Every entry point — CLI commands, the FastAPI API server, and GPU training
scripts — calls `ensure_db()` on startup. This runs `alembic upgrade head`
programmatically, applying any pending migrations. It's idempotent.

For development, the typical flow is:

1. Edit a SQLModel class in `ergon_core/core/persistence/`
2. Run `cd ergon_core && alembic revision --autogenerate -m "add column X to Y"`
3. Review the generated file in `ergon_core/migrations/versions/`
4. Apply it: `cd ergon_core && alembic upgrade head`

Alembic's `env.py` imports all model packages (definitions, graph, saved_specs,
telemetry) so `--autogenerate` always sees the full schema.

## Adding a new model package

If you add a new persistence subpackage under `ergon_core/core/persistence/`,
add a corresponding import to `ergon_core/migrations/env.py` so Alembic can
detect its tables.

## Tests

Integration tests call `ensure_db()` and run against a Postgres instance.
Set `ERGON_DATABASE_URL` to a test database before running them.

The unit tests in `tests/state/` use an in-memory SQLite engine directly
(not via `ensure_db`) for fast, isolated state-machine testing.
