from pathlib import Path


ROOT = Path(__file__).resolve().parents[3]
CORE = ROOT / "ergon_core" / "ergon_core" / "core"

ALLOWED_FILES = {
    CORE / "api" / "test_harness.py",
    CORE / "settings.py",
}

FORBIDDEN_IMPORT_SNIPPETS = (
    "ergon_core.test_support",
    "tests.",
)

FORBIDDEN_CORE_TEST_DOUBLE_TERMS = (
    "StubSandboxManager",
    "is_stub_sandbox_id",
    "stub-sandbox-",
)


def _core_python_files() -> list[Path]:
    return [
        path
        for path in CORE.rglob("*.py")
        if path not in ALLOWED_FILES and "__pycache__" not in path.parts
    ]


def test_core_does_not_import_test_support_or_tests() -> None:
    offenders: list[str] = []
    for path in _core_python_files():
        text = path.read_text()
        for snippet in FORBIDDEN_IMPORT_SNIPPETS:
            if snippet in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {snippet!r}")

    assert offenders == []


def test_core_does_not_define_or_branch_on_stub_sandbox_terms() -> None:
    offenders: list[str] = []
    for path in _core_python_files():
        text = path.read_text()
        for term in FORBIDDEN_CORE_TEST_DOUBLE_TERMS:
            if term in text:
                offenders.append(f"{path.relative_to(ROOT)} contains {term!r}")

    assert offenders == []


def test_core_task_execution_does_not_mint_placeholder_sandbox_ids() -> None:
    path = CORE / "runtime" / "inngest" / "execute_task.py"
    text = path.read_text()

    assert "StubSandboxManager" not in text
    assert "make_noop_sandbox_id" not in text
    assert "stub_sandbox_id" not in text
