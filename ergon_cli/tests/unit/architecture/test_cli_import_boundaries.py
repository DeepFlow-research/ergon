import ast
from pathlib import Path

REPO_ROOT = Path(__file__).parents[4]
CLI_ROOT = REPO_ROOT / "ergon_cli" / "ergon_cli"
DOMAIN_ROOT = CLI_ROOT / "domains"
BUILTINS_ROOT = REPO_ROOT / "ergon_builtins" / "ergon_builtins"


def _python_files(root: Path) -> list[Path]:
    return [path for path in sorted(root.rglob("*.py")) if "__pycache__" not in path.parts]


def _imports(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(), filename=str(path))
    modules: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            modules.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            modules.append(node.module)
    return modules


def test_deleted_cli_compatibility_packages_stay_deleted() -> None:
    for package in ("commands", "composition", "discovery", "onboarding", "rendering"):
        assert not (CLI_ROOT / package).exists()


def test_cli_domains_do_not_import_core_persistence() -> None:
    allowed = {DOMAIN_ROOT / "workflow" / "commands.py"}
    for path in _python_files(DOMAIN_ROOT):
        if path in allowed:
            continue
        offenders = [
            module for module in _imports(path) if module.startswith("ergon_core.core.persistence")
        ]
        assert offenders == [], f"{path}: {offenders}"


def test_builtins_production_code_does_not_import_cli() -> None:
    for path in _python_files(BUILTINS_ROOT):
        offenders = [module for module in _imports(path) if module.startswith("ergon_cli")]
        assert offenders == [], f"{path}: {offenders}"


def test_cli_production_code_does_not_import_deleted_compatibility_paths() -> None:
    deleted_prefixes = (
        "ergon_cli.commands",
        "ergon_cli.composition",
        "ergon_cli.discovery",
        "ergon_cli.onboarding",
        "ergon_cli.rendering",
    )
    for path in _python_files(CLI_ROOT):
        offenders = [
            module
            for module in _imports(path)
            if any(module.startswith(prefix) for prefix in deleted_prefixes)
        ]
        assert offenders == [], f"{path}: {offenders}"


def test_generic_cli_code_does_not_hardcode_benchmark_metadata() -> None:
    allowed = {
        CLI_ROOT / "domains" / "benchmarks" / "templates.py",
        CLI_ROOT / "domains" / "benchmarks" / "service.py",
    }
    forbidden_fragments = (
        "sandbox_template",
        "swebench_verified",
        "ergon-builtins[data]",
    )

    for path in _python_files(CLI_ROOT):
        if path in allowed:
            continue
        text = path.read_text()
        offenders = [fragment for fragment in forbidden_fragments if fragment in text]
        assert offenders == [], f"{path}: {offenders}"
