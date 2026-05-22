from __future__ import annotations

from pathlib import Path

from ergon_core.core.application.testing import suppression_budget as budget


def test_counts_inline_suppressions_in_python_files(tmp_path: Path) -> None:
    source = tmp_path / "pkg" / "module.py"
    source.parent.mkdir()
    source.write_text(
        "\n".join(
            [
                "value = 1  # noqa: F401",
                "other = 2  # type: ignore[arg-type]",
                "try:",
                "    pass",
                "except Exception:  # slopcop: ignore[no-broad-except]",
                "    pass",
            ]
        ),
        encoding="utf-8",
    )

    counts = budget.count_suppressions([tmp_path / "pkg"])

    assert counts.slopcop_ignore == 1
    assert counts.noqa == 1
    assert counts.type_ignore == 1


def test_excludes_docs_and_non_python_files(tmp_path: Path) -> None:
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "notes.md").write_text(
        "# noqa\n# type: ignore\n# slopcop: ignore[x]\n", encoding="utf-8"
    )
    package = tmp_path / "pkg"
    package.mkdir()
    (package / "data.txt").write_text("# noqa\n", encoding="utf-8")

    counts = budget.count_suppressions([tmp_path])

    assert counts.slopcop_ignore == 0
    assert counts.noqa == 0
    assert counts.type_ignore == 0


def test_budget_fails_only_when_counts_increase() -> None:
    assert (
        budget.budget_failures(
            budget.SuppressionCounts(slopcop_ignore=1, noqa=2, type_ignore=3),
            budget.SuppressionCounts(slopcop_ignore=1, noqa=2, type_ignore=3),
        )
        == []
    )
    assert budget.budget_failures(
        budget.SuppressionCounts(slopcop_ignore=2, noqa=2, type_ignore=3),
        budget.SuppressionCounts(slopcop_ignore=1, noqa=2, type_ignore=3),
    ) == ["slopcop_ignore: 2 > 1"]
