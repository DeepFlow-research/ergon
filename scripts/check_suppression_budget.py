"""Fail CI when inline lint/type suppressions increase.

The goal is not to pretend the current baseline is clean. It is to stop new
``noqa``, ``type: ignore``, and ``slopcop: ignore`` comments from quietly
appearing without an explicit budget update.
"""

import argparse
import io
import re
import sys
import tokenize
from pathlib import Path
from typing import NamedTuple

DEFAULT_PATHS = (
    "ergon_core",
    "ergon_builtins",
    "ergon_cli",
    "ergon_infra",
    "tests",
    "scripts",
)


class SuppressionCounts(NamedTuple):
    slopcop_ignore: int
    noqa: int
    type_ignore: int


# Keep this baseline equal to the current repository count. Lower it as cleanup
# lands; raise it only when a new suppression is explicitly reviewed.
BUDGET = SuppressionCounts(
    # +1 for ergon_core/api/benchmark/task.py:_import_component qualname
    # walk introduced by PR 2 of the v2 authoring redesign. The getattr
    # is genuinely dynamic (resolves a class from a user-controlled
    # discriminator string); no static alternative exists.
    # +3 for MiniF2FToolkit.__init__ parameters (sandbox, sandbox_run_skill,
    # ask_stakeholder_fn): the v1 benchmark surface deliberately accepts
    # heterogeneous sandbox/skill types — typed as `Any` matching the
    # existing `_minif2f_run_skill` pattern. Reviewed in PR 4.5.
    # +13 (PR 6): MiniF2FToolkit.tools sandbox/task args typed Any (genuine
    # circular import prevents static types); benchmarks/minif2f/_tools.py
    # build_tools sandbox/task Any + 4×no-broad-except (tool fns must return
    # error responses, not propagate); benchmarks/minif2f/_legacy_workers.py
    # _minif2f_run_skill / MiniF2FReactWorker Any args (v1 legacy surface);
    # ReActWorker.execute return Any + no-broad-except (pydantic_ai agent
    # output is dynamic).
    # +1 noqa: C901 for build_tools: closure-heavy tool builder, complexity
    # is structural not incidental; refactoring into sub-functions would
    # obscure the sandbox binding.
    # TODO(PR 11): when `_minif2f_run_skill` and `MiniF2FReactWorker` are
    # deleted with `_legacy_workers.py`, decrement `slopcop_ignore` by ~3
    # (the v1 legacy `Any` annotations) and update this comment to reflect
    # the post-PR-11 baseline.
    # +1 (PR 6.5): persist_benchmark module-level function adds 1×no-typing-any
    # (resolved_metadata dict[str,Any]) in definition_writer.py and
    # 1×guarded-function-import in service.py (run_experiment lazy-imports
    # launch.py); net +1 after the deleted api/experiment.py contributed -1
    # and the post-cleanup removal of ExperimentService.persist_benchmark
    # dropped 1×no-typing-any + 1×guarded-function-import.
    # +1 noqa (PR 6.5): noqa: C901 on persist_benchmark (complex by design,
    # same as the persist_definition it supplements).
    slopcop_ignore=238,
    noqa=4,
    type_ignore=64,
)

_SLOPCOP_IGNORE = re.compile(r"\bslopcop:\s*ignore\b")
_NOQA = re.compile(r"#\s*noqa\b")
_TYPE_IGNORE = re.compile(r"#\s*type:\s*ignore\b")


def iter_python_files(paths: list[Path]) -> list[Path]:
    files: list[Path] = []
    for path in paths:
        if not path.exists():
            continue
        if path.is_file():
            if _is_counted_python_file(path):
                files.append(path)
            continue
        for child in path.rglob("*.py"):
            if _is_counted_python_file(child):
                files.append(child)
    return sorted(files)


def _is_counted_python_file(path: Path) -> bool:
    parts = set(path.parts)
    return path.suffix == ".py" and "docs" not in parts and ".venv" not in parts


def count_suppressions(paths: list[Path]) -> SuppressionCounts:
    slopcop_ignore = 0
    noqa = 0
    type_ignore = 0

    for path in iter_python_files(paths):
        for comment in _comment_tokens(path):
            if _SLOPCOP_IGNORE.search(comment):
                slopcop_ignore += 1
            if _NOQA.search(comment):
                noqa += 1
            if _TYPE_IGNORE.search(comment):
                type_ignore += 1

    return SuppressionCounts(
        slopcop_ignore=slopcop_ignore,
        noqa=noqa,
        type_ignore=type_ignore,
    )


def _comment_tokens(path: Path) -> list[str]:
    try:
        source = path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        source = path.read_text()

    comments: list[str] = []
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
    except tokenize.TokenError:
        return comments

    for token in tokens:
        if token.type == tokenize.COMMENT:
            comments.append(token.string)
    return comments


def budget_failures(counts: SuppressionCounts, budget: SuppressionCounts) -> list[str]:
    failures: list[str] = []
    for field in SuppressionCounts._fields:
        count = getattr(counts, field)
        allowed = getattr(budget, field)
        if count > allowed:
            failures.append(f"{field}: {count} > {allowed}")
    return failures


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "paths",
        nargs="*",
        default=list(DEFAULT_PATHS),
        help="Files or directories to scan",
    )
    parser.add_argument(
        "--show-current",
        action="store_true",
        help="Print current counts and exit successfully",
    )
    args = parser.parse_args(argv)

    counts = count_suppressions([Path(path) for path in args.paths])
    print(
        "suppression counts: "
        f"slopcop_ignore={counts.slopcop_ignore}, "
        f"noqa={counts.noqa}, "
        f"type_ignore={counts.type_ignore}"
    )

    if args.show_current:
        return 0

    failures = budget_failures(counts, BUDGET)
    if failures:
        print("Suppression budget exceeded:", file=sys.stderr)
        for failure in failures:
            print(f"  - {failure}", file=sys.stderr)
        print("Lower the count or explicitly update BUDGET after review.", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
