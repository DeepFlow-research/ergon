from pathlib import Path

ROOT = Path(__file__).resolve().parents[3]


def test_graph_status_literals_are_defined_only_in_status_conventions() -> None:
    offenders: list[str] = []
    duplicate_snippets = (
        'Literal["pending", "ready", "running", "completed", "failed", "cancelled", "blocked"]',
        'Literal["pending", "ready", "running", "completed", "failed", "blocked", "cancelled"]',
        'Literal["pending", "satisfied", "invalidated"]',
    )
    allowed = {
        ROOT / "ergon_core/ergon_core/core/persistence/graph/status_conventions.py",
    }

    for path in (ROOT / "ergon_core/ergon_core/core").rglob("*.py"):
        if path in allowed:
            continue
        text = path.read_text()
        compact_text = "".join(text.split()).replace(",]", "]")
        for snippet in duplicate_snippets:
            if snippet in text or "".join(snippet.split()) in compact_text:
                offenders.append(f"{path.relative_to(ROOT)} duplicates {snippet}")

    assert offenders == []


def test_eval_criterion_status_literal_is_defined_only_in_evaluation_summary() -> None:
    offenders: list[str] = []
    snippet = 'EvalCriterionStatus=Literal["passed","failed","errored","skipped"]'
    allowed = {
        ROOT / "ergon_core/ergon_core/core/persistence/telemetry/evaluation_summary.py",
    }

    for path in (ROOT / "ergon_core/ergon_core/core").rglob("*.py"):
        if path in allowed:
            continue
        compact_text = "".join(path.read_text().split()).replace(",]", "]")
        if snippet in compact_text:
            offenders.append(str(path.relative_to(ROOT)))

    assert offenders == []


def test_run_task_dto_does_not_label_worker_slug_as_name() -> None:
    path = ROOT / "ergon_core/ergon_core/core/api/schemas.py"
    text = path.read_text()
    assert "assigned_worker_name" not in text
    assert "assigned_worker_slug" in text


def test_workflow_task_ref_does_not_duplicate_graph_task_ref() -> None:
    path = ROOT / "ergon_core/ergon_core/core/runtime/services/workflow_dto.py"
    assert "class WorkflowTaskRef" not in path.read_text()
