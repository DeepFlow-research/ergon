PYTHON_UNIT_COMMANDS = {
    "core": ("pnpm", "run", "test:core:unit"),
    "builtins": ("pnpm", "run", "test:builtins:unit"),
    "cli": ("pnpm", "run", "test:cli:unit"),
    "ingestion": ("pnpm", "run", "test:ingestion:unit"),
}

PYTHON_UNIT_ALL = ("pnpm", "run", "test:full:unit")

DASHBOARD_UNIT = ("pnpm", "-C", "ergon-dashboard", "run", "test:unit")
DASHBOARD_CONTRACTS = ("pnpm", "-C", "ergon-dashboard", "run", "test:contracts")
BACKEND_INTEGRATION = ("uv", "run", "pytest", "tests/integration", "-v", "--timeout=300")
BACKEND_SMOKE = ("uv", "run", "pytest", "tests/integration/smokes", "-v", "--timeout=300")
BACKEND_E2E = ("uv", "run", "pytest", "tests/e2e", "-v")
REAL_LLM = ("uv", "run", "pytest", "tests/real_llm", "-v")
DASHBOARD_SMOKE = ("pnpm", "-C", "ergon-dashboard", "run", "e2e:live")
BENCHMARK_SMOKE_COMMANDS = {
    "researchrubrics": ("uv", "run", "pytest", "tests/e2e/test_researchrubrics_smoke.py", "-v"),
    "minif2f": ("uv", "run", "pytest", "tests/e2e/test_minif2f_smoke.py", "-v"),
    "swebench-verified": ("uv", "run", "pytest", "tests/e2e/test_swebench_smoke.py", "-v"),
}
BENCHMARK_SMOKE_ALL = (
    "uv",
    "run",
    "pytest",
    "tests/e2e/test_researchrubrics_smoke.py",
    "tests/e2e/test_minif2f_smoke.py",
    "tests/e2e/test_swebench_smoke.py",
    "-v",
)
