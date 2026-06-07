PYTHON_UNIT_COMMANDS = {
    "core": ("uv", "run", "pytest", "ergon_core/tests/unit", "-q", "-n", "auto", "--durations=20"),
    "builtins": (
        "uv",
        "run",
        "pytest",
        "ergon_builtins/tests/unit",
        "-q",
        "-n",
        "auto",
        "--durations=20",
    ),
    "cli": ("uv", "run", "pytest", "ergon_cli/tests/unit", "-q", "-n", "auto", "--durations=20"),
    "ingestion": (
        "uv",
        "run",
        "pytest",
        "ergon_ingestion/tests/unit",
        "-q",
        "-n",
        "auto",
        "--durations=20",
    ),
}

PYTHON_UNIT_ALL = (
    "uv",
    "run",
    "pytest",
    "ergon_core/tests/unit",
    "ergon_builtins/tests/unit",
    "ergon_cli/tests/unit",
    "ergon_ingestion/tests/unit",
    "-q",
    "-n",
    "auto",
    "--durations=20",
)

DASHBOARD_UNIT = ("pnpm", "-C", "ergon-dashboard", "run", "test:unit")
DASHBOARD_CONTRACTS = ("pnpm", "-C", "ergon-dashboard", "run", "test:contracts")
BACKEND_INTEGRATION = ("uv", "run", "pytest", "tests/integration", "-v", "--timeout=300")
BACKEND_SMOKE = ("uv", "run", "pytest", "tests/integration/smokes", "-v", "--timeout=300")
BACKEND_E2E = ("uv", "run", "pytest", "tests/e2e", "-v")
REAL_LLM = ("uv", "run", "pytest", "tests/real_llm", "-v")
DASHBOARD_SMOKE = ("pnpm", "-C", "ergon-dashboard", "run", "e2e:live")
ENVIRONMENT_SMOKE_COMMANDS = {
    "researchrubrics": ("uv", "run", "pytest", "tests/e2e/test_researchrubrics_smoke.py", "-v"),
    "minif2f": ("uv", "run", "pytest", "tests/e2e/test_minif2f_smoke.py", "-v"),
    "swebench-verified": ("uv", "run", "pytest", "tests/e2e/test_swebench_smoke.py", "-v"),
}
ENVIRONMENT_SMOKE_ALL = (
    "uv",
    "run",
    "pytest",
    "tests/e2e/test_researchrubrics_smoke.py",
    "tests/e2e/test_minif2f_smoke.py",
    "tests/e2e/test_swebench_smoke.py",
    "-v",
)
