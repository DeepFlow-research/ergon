from pathlib import Path


def test_ergon_core_does_not_import_builtins_registry() -> None:
    root = Path("ergon_core/ergon_core")
    offenders: list[str] = []

    for path in root.rglob("*.py"):
        text = path.read_text()
        if "ergon_builtins.registry" in text:
            offenders.append(str(path))

    assert offenders == []


def test_ergon_core_process_local_registry_is_deleted() -> None:
    assert not Path("ergon_core/ergon_core/api/registry.py").exists()


def test_core_package_has_no_smoke_fixture_registration_package() -> None:
    assert not Path("ergon_core/ergon_core/test_support/smoke_fixtures").exists()
