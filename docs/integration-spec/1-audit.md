# Integration Tier Audit

## Directory Structure

```
tests/integration/
├── conftest.py
├── smokes/
│   └── test_smoke_harness.py
├── swebench_verified/
│   ├── test_benchmark.py
│   ├── test_criterion.py
│   ├── test_rubric.py
│   ├── test_sandbox_manager.py
│   ├── test_smoke_e2e.py
│   ├── test_task_schemas.py
│   └── test_toolkit.py
└── minif2f/
    ├── test_sandbox_manager.py
    └── test_verification_integration.py
```

---

## What Is Actually Covered

| File | What it tests | Live infra required |
|------|--------------|-------------------|
| `smokes/test_smoke_harness.py` | seed → read → reset HTTP round-trip against a real server + Postgres | Server + Postgres |
| `swebench_verified/test_criterion.py` | `SWEBenchTestCriterion.evaluate()` with a mock `CriterionRuntime` | None |
| `swebench_verified/test_benchmark.py` | `build_instances()` with mocked `_load_rows` | None |
| `swebench_verified/test_task_schemas.py` | `SWEBenchInstance`, `SWEBenchTaskPayload` parsing, `_parse_test_list` | None |
| `swebench_verified/test_toolkit.py` | bash and str_replace_editor tools with a mock sandbox | None |
| `swebench_verified/test_rubric.py` | Rubric has one criterion named "test-resolution" with weight 1.0 | None |
| `swebench_verified/test_sandbox_manager.py` | Template resolution + `AsyncSandbox.create` call shape (mocked) | None |
| `swebench_verified/test_smoke_e2e.py` | Dockerfile and `e2b.toml.template` exist on disk | None |
| `minif2f/test_sandbox_manager.py` | Template resolution + sandbox create/verify lifecycle (mocked) — **3 tests uncollected** | None |
| `minif2f/test_verification_integration.py` | `ProofVerificationCriterion` — live test skipped without E2B key; static 'sorry' rejection test | Optional E2B |

**There are no Postgres persistence round-trip tests for `RunRecord`, `RunTaskExecution`, `RunResource`, or `RunGraphNode`. There are no Inngest event schema or propagation tests. The single test that exercises real infrastructure is `test_smoke_harness.py::test_seed_then_read_then_reset_roundtrip`, and it only asserts HTTP response codes — not Postgres state.**

---

## Existing Issues

### Critical

#### 1. Three tests have never been collected — `minif2f/test_sandbox_manager.py`

Three functions are named `testresolve_*` instead of `test_*`. pytest never collects them. They have passed in CI since they were written only because they are invisible to the runner.

```python
# Current — never collected:
def testresolve_template_falls_back_to_name_when_registry_missing(...): ...
def testresolve_template_prefers_registry_template_id(...): ...
def testresolve_template_falls_back_on_malformed_registry(...): ...

# Should be:
def test_resolve_template_falls_back_to_name_when_registry_missing(...): ...
def test_resolve_template_prefers_registry_template_id(...): ...
def test_resolve_template_falls_back_on_malformed_registry(...): ...
```

**Fix:** Rename the three functions. Zero-risk, one commit.

---

### High

#### 2. The Inngest preflight gates tests that do not use Inngest

`conftest.py` probes Inngest TCP connectivity at session start and calls `pytest.exit()` if it is unreachable. This applies to every file in `tests/integration/` regardless of whether the test needs Inngest.

Eight of the ten test files require no live infrastructure at all — they are fully mocked unit tests sitting behind the integration preflight for no reason. A ten-line rubric test that checks a list length cannot run in any environment without a running Inngest server.

**Fix:** Move the fully-mocked files to `tests/unit/` where they belong, or introduce a sub-conftest scoped only to the files that actually need Inngest.

#### 3. Eight of ten files are misclassified unit tests

Every file below needs no live infrastructure and is currently blocked behind the integration preflight:

- `swebench_verified/test_benchmark.py` — mocks `_load_rows`
- `swebench_verified/test_criterion.py` — mocks `CriterionRuntime`
- `swebench_verified/test_rubric.py` — instantiates a local object
- `swebench_verified/test_sandbox_manager.py` — mocks `AsyncSandbox`
- `swebench_verified/test_smoke_e2e.py` — filesystem stat only
- `swebench_verified/test_task_schemas.py` — pure data parsing
- `swebench_verified/test_toolkit.py` — mocks `AsyncSandbox`
- `minif2f/test_sandbox_manager.py` — mocks `AsyncSandbox`

These should live in `tests/unit/` and run under `pnpm run test:be:fast`.

---

### Medium

#### 4. `_reset_sandbox_singleton` fixture is duplicated

The fixture that resets `BaseSandboxManager` class-level state is defined independently in both `minif2f/test_sandbox_manager.py` and `minif2f/test_verification_integration.py`. It is identical in both files.

**Fix:** Extract to `tests/integration/minif2f/conftest.py`.

#### 5. The one real integration test covers a narrow happy path

`test_smoke_harness.py` has a single test: seed → read → reset, ending in a 404. It asserts HTTP status codes only. It does not assert Postgres state, does not test non-happy-path statuses, and does not verify that reset actually cascades to child rows.
