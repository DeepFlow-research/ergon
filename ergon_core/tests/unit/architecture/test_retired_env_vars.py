from pathlib import Path


RETIRED = {
    "ERGON_STARTUP_PLUGINS",
    "ENABLE_SMOKE_FIXTURES",
    "ENABLE_TEST_HARNESS",
    "ERGON_SKIP_INFRA_CHECK",
    "TEST_HARNESS_SECRET",
}


def test_retired_plugin_and_smoke_env_vars_are_not_used_in_code() -> None:
    offenders: list[str] = []
    this_file = Path(__file__).resolve()
    roots = [
        Path("ergon_core"),
        Path("ergon_cli"),
        Path("ergon_builtins"),
        Path("tests"),
        Path("scripts"),
    ]
    for root in roots:
        for path in root.rglob("*"):
            if path.resolve() == this_file:
                continue
            if path.is_dir() or path.suffix not in {".py", ".sh", ".yml", ".yaml"}:
                continue
            text = path.read_text(errors="ignore")
            for name in RETIRED:
                if name in text:
                    offenders.append(f"{path}: {name}")

    assert offenders == []
