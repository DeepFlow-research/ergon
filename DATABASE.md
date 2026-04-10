# Database

Arcane uses **PostgreSQL 15** for all environments. Schema is managed by
[Alembic](https://alembic.sqlalchemy.org/) migrations in `h_arcane/migrations/`.

## Quick reference

| Task | Command |
|------|---------|
| Start Postgres | `docker compose up postgres -d` |
| Apply migrations | `cd h_arcane && alembic upgrade head` |
| Auto-generate a migration | `cd h_arcane && alembic revision --autogenerate -m "describe change"` |
| Check current revision | `cd h_arcane && alembic current` |
| Show migration history | `cd h_arcane && alembic history` |

## Connection

The database URL is configured via `ARCANE_DATABASE_URL` or `DATABASE_URL`
environment variable (checked in that order). The default points at the
docker-compose Postgres:

```
postgresql://h_arcane:h_arcane_dev@localhost:5433/h_arcane
```

Override the port in `.env` if 5433 conflicts with another project.

## How migrations work

Every entry point — CLI commands, the FastAPI API server, and GPU training
scripts — calls `ensure_db()` on startup. This runs `alembic upgrade head`
programmatically, applying any pending migrations. It's idempotent.

For development, the typical flow is:

1. Edit a SQLModel class in `h_arcane/core/persistence/`
2. Run `cd h_arcane && alembic revision --autogenerate -m "add column X to Y"`
3. Review the generated file in `h_arcane/migrations/versions/`
4. Apply it: `cd h_arcane && alembic upgrade head`

Alembic's `env.py` imports all model packages (definitions, graph, saved_specs,
telemetry) so `--autogenerate` always sees the full schema.

## Adding a new model package

If you add a new persistence subpackage under `h_arcane/core/persistence/`,
add a corresponding import to `h_arcane/migrations/env.py` so Alembic can
detect its tables.

## Tests

Integration tests call `ensure_db()` and run against a Postgres instance.
Set `ARCANE_DATABASE_URL` to a test database before running them.

The unit tests in `tests/state/` use an in-memory SQLite engine directly
(not via `ensure_db`) for fast, isolated state-machine testing.
