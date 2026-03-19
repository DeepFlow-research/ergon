# Benchmark Setup CLI

This document specifies a first-class local setup and benchmark preparation CLI for Arcane.

The goal is to make local onboarding and benchmark readiness feel like a product, not a scavenger hunt through docs, env vars, and one-off commands.

## Goal

Provide a single user-facing CLI that lets a new user:

1. start required local services
2. validate environment and dependency readiness
3. choose which benchmarks they want to work with
4. prepare benchmark-specific assets
5. seed selected benchmark data into Postgres
6. inspect readiness later without guessing what is already set up

The intended top-level command is:

```bash
magym
```

with the first-run entrypoint:

```bash
magym init
```

## Why This Is Needed

Current benchmark setup ergonomics are inconsistent:

- `GDPEval` currently expects local data copied from another repository
- `MiniF2F` clones a repository on demand
- `ResearchRubrics` depends on Hugging Face auth and a user-derived dataset name
- database connection defaults and docs are inconsistent
- the README contains stale command references
- there is no single "am I ready?" command

This is bad for:

- new human contributors
- agent-driven implementation
- reliable benchmark-backed testing

## Product Principles

### 1. One obvious entrypoint

Users should not need to know:

- which docker compose commands to run
- which benchmark loader module to call
- which dataset needs Hugging Face login
- which DB to seed

The CLI should make those decisions or guide the user through them.

### 2. Interactive by default, scriptable by design

`magym init` should be interactive for humans.

But every operation should also support non-interactive flags for:

- agents
- CI
- shell automation

### 3. Benchmark-specific logic lives in services, not in the CLI command body

The CLI should orchestrate.

Benchmark preparation and seeding logic should live behind service boundaries.

### 4. Readiness and mutation are separate concepts

The CLI should clearly distinguish:

- checking what is ready
- preparing missing pieces
- seeding data into Postgres

### 5. Safe by default

The CLI should not surprise users by:

- wiping the wrong database
- loading huge datasets without confirmation
- seeding benchmarks they did not ask for

### 6. Prefer Hosted Benchmark Assets Over Manual Copy Steps

Wherever possible, benchmark assets should be hosted in a stable remote location rather than requiring users to manually copy files from another local repository.

For this project, the preferred distribution mechanism is:

- Hugging Face datasets for benchmark assets and benchmark metadata

This is already true in practice for ResearchRubrics and should become true for GDPEval as well.

That would let `magym init` and `magym benchmark prepare` pull benchmark assets directly instead of depending on undocumented local file copying.

## Preferred Dataset Distribution Strategy

The long-term benchmark setup story should be:

- `ResearchRubrics` loads from Hugging Face
- `GDPEval` also loads from Hugging Face
- `MiniF2F` continues to clone or download its upstream source unless we later decide to mirror a reduced version

### ResearchRubrics

The existing ablated dataset is already hosted on Hugging Face:

- [cm2435cm2435cm2435/researchrubrics-ablated](https://huggingface.co/datasets/cm2435cm2435cm2435/researchrubrics-ablated)

The CLI should treat this as the preferred source of truth rather than assuming the user has pre-populated local files.

### GDPEval

The preferred next step is to publish the GDPEval benchmark assets required by Arcane to a Hugging Face dataset as well.

TODO for the first CLI implementation:

- leave `GDPEval` out of the supported `magym` benchmark list until those assets are hosted cleanly
- re-enable it once the Hugging Face-backed distribution path exists

That dataset should contain, at minimum:

- the parquet or equivalent task metadata
- the staged rubric JSONL
- the reference files needed for benchmark tasks

Once hosted, the CLI should prefer pulling GDPEval assets from Hugging Face over manual copy-based setup.

### Authentication Model

The CLI should support:

- public dataset access when a dataset is public
- Hugging Face token-based access when a dataset is private or gated

Recommended input mechanisms:

- `HF_TOKEN` environment variable
- or a prompt during interactive setup when the user chooses a benchmark requiring auth

The CLI should never require a token for a public dataset.

## Command Surface

## Top-Level Commands

### `magym init`

Primary onboarding flow.

Responsibilities:

- ensure docker compose services are up
- run readiness checks
- let the user choose which benchmarks to prepare
- let the user choose which benchmarks to seed
- print a final summary of what is ready

### `magym doctor`

Read-only readiness report.

Responsibilities:

- check env vars
- check docker compose services
- check DB connectivity
- check benchmark-specific prerequisites
- report actionable missing items

### `magym compose up`

Bring up required services.

### `magym compose down`

Stop local services.

### `magym compose logs`

Show compose logs, optionally scoped to one service.

### `magym benchmark list`

List supported benchmarks and readiness state.

### `magym benchmark prepare <benchmark>`

Prepare one benchmark's assets without seeding.

### `magym benchmark seed <benchmark>`

Seed one benchmark's selected tasks into Postgres.

### `magym benchmark status <benchmark>`

Show benchmark-specific readiness and seed state.

## Recommended Initial Subset

The first implementation does not need the entire command surface on day one.

The minimal high-value subset is:

- `magym init`
- `magym doctor`
- `magym benchmark list`
- `magym benchmark prepare <benchmark>`
- `magym benchmark seed <benchmark>`

## Example UX

### Interactive init flow

Example:

```bash
$ magym init

Checking Docker services...
- postgres: not running
- api: not running
- inngest-dev: not running
- dashboard: not running

Start required services now? [Y/n]

Checking environment...
- OPENAI_API_KEY: present
- E2B_API_KEY: present
- EXA_API_KEY: missing
- Hugging Face auth: missing

Select benchmarks to prepare:
[x] gdpeval
[x] minif2f
[ ] researchrubrics

Prepare selected benchmarks now? [Y/n]

GDPEval:
- data directory missing
- prompt user for source location or documented manual step

MiniF2F:
- repository missing
- clone now? [Y/n]

Select benchmarks to seed into Postgres:
[ ] gdpeval
[x] minif2f
[ ] researchrubrics

How many examples per selected benchmark?
minif2f: 5

Summary:
- compose services: running
- gdpeval: not prepared
- minif2f: prepared and seeded
- researchrubrics: not prepared
```

### Scriptable flows

Examples:

```bash
magym doctor
magym init --yes --benchmark minif2f --seed --limit 5
magym benchmark prepare gdpeval
magym benchmark seed researchrubrics --limit 3
```

## Benchmark-Specific Preparation Logic

### GDPEval

Preparation should check:

- whether the configured GDPEval Hugging Face dataset is reachable
- whether required files have already been cached locally
- whether the local extracted asset set contains:
  - `data/raw/gdpeval.parquet`
  - `data/generated/staged_v2/staged_rubrics.jsonl`
  - `data/raw/reference_files/`

Preparation UX should support:

- downloading from Hugging Face as the preferred path
- showing cache or extraction status
- optionally accepting a local `--source-dir` import path as a fallback path
- giving a precise remediation message if neither hosted nor local import is available

Seeding should support:

- selecting a limit
- selecting the target database
- showing how many experiments were created

### MiniF2F

Preparation should check:

- local clone at the expected data path
- Lean source files exist
- the local checkout is readable

Preparation UX should support:

- cloning the repo if missing
- skipping clone if already present

Seeding should support:

- selecting split or default subset if the loader supports it later
- selecting a limit
- selecting the target database

### ResearchRubrics

Preparation should check:

- Hugging Face authentication
- ability to resolve the ablated dataset name or use the configured dataset name directly
- ability to download or access the dataset
- `EXA_API_KEY` only if the benchmark runtime truly requires it for the paths being prepared

Preparation UX should support:

- validating login
- showing the resolved dataset name
- downloading or caching the dataset

Seeding should support:

- selecting a limit
- selecting the target database

## Hugging Face Configuration

The CLI should support benchmark dataset configuration through explicit settings rather than hidden conventions.

Recommended settings:

- `hf_token`
- `gdpeval_dataset_name`
- `researchrubrics_dataset_name`

If these are not configured, the CLI should:

- use project defaults where safe
- otherwise prompt interactively or print a precise remediation message

The first implementation can keep the configuration simple.

Example behavior:

- ResearchRubrics defaults to the existing hosted ablated dataset
- GDPEval defaults to a configured Hugging Face dataset once published
- private datasets can be accessed via `HF_TOKEN`

## Database UX

The CLI should make database targeting explicit.

Recommended options:

- default database
- test database

`magym init` should report:

- whether the main DB is reachable
- whether the test DB is reachable
- whether schema exists

It should never silently seed the wrong database.

## Docker Compose UX

The CLI should wrap the most common compose actions so users do not need to remember service names.

Required service checks:

- postgres
- api
- inngest-dev
- dashboard

The first implementation can shell out to `docker compose`.

That is acceptable as long as:

- output is readable
- failures are surfaced clearly
- service health is summarized in CLI-friendly terms

## Suggested Implementation Layout

```text
h_arcane/
└── cli/
    ├── __init__.py
    ├── main.py
    ├── compose.py
    ├── doctor.py
    ├── benchmark.py
    └── prompts.py

h_arcane/
└── services/
    └── setup/
        ├── compose_service.py
        ├── readiness_service.py
        ├── benchmark_preparation_service.py
        ├── benchmark_seed_service.py
        └── schemas.py
```

The exact module paths may differ, but the separation of responsibilities should remain.

## Pyproject Integration

The CLI should be exposed through a console script in `pyproject.toml`.

Example shape:

```toml
[project.scripts]
magym = "h_arcane.cli.main:app"
```

The exact callable can vary based on the CLI framework used.

## Framework Recommendation

A small CLI framework like `typer` is a good fit because:

- the repo already uses Python-first patterns
- it supports nested commands cleanly
- it works well for both human and agent use

The first implementation should avoid overengineering.

## Service Boundaries

### `ComposeService`

Responsibilities:

- start services
- stop services
- inspect service status
- read logs if needed

### `ReadinessService`

Responsibilities:

- validate env vars
- validate database reachability
- validate benchmark-specific prerequisites
- aggregate readiness into a structured result

### `BenchmarkPreparationService`

Responsibilities:

- prepare assets for one benchmark
- download, clone, cache, or validate local files as needed
- prefer Hugging Face-hosted benchmark assets where available

### `BenchmarkSeedService`

Responsibilities:

- seed selected benchmark data into the chosen database
- report counts and IDs

## Suggested Pydantic Schemas

The CLI plan should use structured results rather than ad hoc print logic.

Example shapes:

```python
from pydantic import BaseModel


class ServiceStatus(BaseModel):
    name: str
    ready: bool
    detail: str | None = None


class BenchmarkReadiness(BaseModel):
    benchmark_name: str
    ready: bool
    missing_items: list[str] = []
    detail: str | None = None


class DoctorReport(BaseModel):
    services: list[ServiceStatus]
    benchmarks: list[BenchmarkReadiness]
    env_ok: bool
    database_ok: bool
```

## Connection To Testing

This CLI is not only an onboarding convenience.

It is also an enabling layer for:

- benchmark-backed local development
- benchmark-backed integration testing
- deterministic fixture development
- future agent workflows

However:

- the deterministic golden-fixture test suite should not depend on full benchmark setup being complete

The fixture-backed `02` and `03` test slices should still work with minimal local prerequisites.

This CLI is about:

- benchmark readiness
- fuller local workflows
- better ergonomics

not about making deterministic test fixtures depend on external datasets.

## Open Product Decision

To fully realize this design, GDPEval should be published to a Hugging Face dataset.

Implementation of that publication step requires:

- the desired dataset repo name
- whether it should be public or private
- Hugging Face credentials or token where required

The CLI itself can be built before that publication happens, but the best end-state is for both ResearchRubrics and GDPEval to be pullable directly from Hugging Face.

## Acceptance Criteria

This effort is complete when:

- a new user can run `magym init`
- the CLI can start required compose services
- the CLI can tell the user exactly which benchmarks are ready or not ready
- the CLI can prepare at least one benchmark automatically
- the CLI can seed selected benchmark data into Postgres
- the CLI can report whether the main DB and test DB are ready
- the README can be simplified to point to this CLI rather than scattered setup steps

## Recommended First Slice

Implement this in the following order:

1. `magym doctor`
2. `magym compose up`
3. `magym benchmark list`
4. `magym benchmark prepare minif2f`
5. `magym benchmark seed minif2f --limit 5`
6. `magym init` interactive wrapper around the above

MiniF2F is the best first benchmark for the setup CLI because:

- it has fewer local file-format complications than GDPEval
- it does not depend on Hugging Face user resolution like ResearchRubrics
- it exercises a realistic prepare-plus-seed flow
