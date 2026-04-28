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
