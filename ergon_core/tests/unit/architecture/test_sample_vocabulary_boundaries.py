from pathlib import Path


ROOT = Path(__file__).resolve().parents[4]

CHECKED_ROOTS = [
    ROOT / "ergon_core" / "ergon_core",
    ROOT / "ergon_cli" / "ergon_cli",
    ROOT / "ergon-dashboard" / "src",
    ROOT / "ergon-dashboard" / "tests",
    ROOT / "examples",
]

DISALLOWED_RUNTIME_NOUNS = [
    "run_id",
    "runId",
    "RunRecord",
    "RunTask",
    "RunGraph",
    "RunResource",
    "WorkflowRunState",
    "/run/",
    "/runs/",
    'data-testid="run-',
    ".run-",
    "--run-",
    "RUNS",
]

ALLOWED_VERB_SNIPPETS = [
    "uv run",
    "pnpm run",
    "subprocess.run(",
    '"run"',
    "'run'",
    "examples run",
]


def test_runtime_surfaces_do_not_keep_run_as_identity_noun() -> None:
    offenders: list[str] = []
    for root in CHECKED_ROOTS:
        for path in root.rglob("*"):
            if path.suffix not in {".py", ".ts", ".tsx", ".json", ".md"}:
                continue
            if "generated" in path.parts:
                continue
            if path.parts[-2:] == ("rl", "rollout_types.py") or path.parts[-2:] == (
                "rl",
                "rollout_service.py",
            ):
                continue
            for line_number, line in enumerate(
                path.read_text(encoding="utf-8").splitlines(), start=1
            ):
                if any(allowed in line for allowed in ALLOWED_VERB_SNIPPETS):
                    continue
                for needle in DISALLOWED_RUNTIME_NOUNS:
                    if needle in line:
                        offenders.append(
                            f"{path.relative_to(ROOT)}:{line_number} contains {needle!r}"
                        )

    assert offenders == []
