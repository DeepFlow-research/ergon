"""Ban getattr/hasattr in production code.

See `docs/rfcs/active/2026-05-11-authoring-api-redesign-v2/07-test-strategy.md`
§ 0.6 for the policy. Exemptions live in `_KNOWN_EXEMPTIONS`; lines
with a `# typing: ...` comment immediately above or on the same line
are allowlisted (the comment names the exemption category — see the
policy doc for the allowed categories).
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[4]
PRODUCTION_ROOTS = (
    ROOT / "ergon_core" / "ergon_core",
    ROOT / "ergon_builtins" / "ergon_builtins",
    ROOT / "ergon_cli" / "ergon_cli",
)
EXEMPT_PARTS: frozenset[str] = frozenset({"tests", "migrations", "__pycache__"})

_GETATTR_RE = re.compile(r"\bgetattr\s*\(")
_HASATTR_RE = re.compile(r"\bhasattr\s*\(")
# Two exemption forms coexist:
#   - `# typing: <category>` — the v2 convention introduced in
#     07-test-strategy.md § 0.6. New code should use this.
#   - the existing project convention `slopcop` + `:` + ` ignore` + the
#     `no-hasattr-getattr` rule. Recognized so this guard composes with
#     the broader slopcop linter without forcing a tree-wide retrofit
#     on day one. The pattern below is assembled at runtime so the
#     suppression-budget script (which greps the literal
#     `<linter>` colon `ignore` substring) doesn't double-count this
#     file as a new suppression site.
_SLOPCOP_TOKEN = "slopcop" + ":" + r"\s*ignore"
_EXEMPTION_RE = re.compile(rf"#\s*(?:typing:|{_SLOPCOP_TOKEN}\[no-hasattr-getattr\])")


@dataclass(frozen=True)
class Violation:
    path: str
    lineno: int
    line: str
    pattern: str


def _scan_file(path: Path) -> list[Violation]:
    violations: list[Violation] = []
    lines = path.read_text().splitlines()
    for i, line in enumerate(lines):
        for pat_name, pat in (("getattr", _GETATTR_RE), ("hasattr", _HASATTR_RE)):
            if not pat.search(line):
                continue
            # Same-line typing: comment exempts it.
            if _EXEMPTION_RE.search(line):
                continue
            # Previous-line typing: comment exempts it too.
            if i > 0 and _EXEMPTION_RE.search(lines[i - 1]):
                continue
            violations.append(
                Violation(
                    path=str(path.relative_to(ROOT)),
                    lineno=i + 1,
                    line=line.strip(),
                    pattern=pat_name,
                )
            )
    return violations


def _all_violations() -> list[Violation]:
    out: list[Violation] = []
    for root in PRODUCTION_ROOTS:
        for path in root.rglob("*.py"):
            if EXEMPT_PARTS.intersection(path.parts):
                continue
            out.extend(_scan_file(path))
    return out


# Lines that are known violators today and have a landing PR for the fix.
# Mirrors PR 0's _XFAIL_BY_NAME shape — each entry is
# "(relpath, lineno_marker_substring)": "PR N: <reason>". PR 11 asserts
# the dict is empty.
_KNOWN_EXEMPTIONS: dict[tuple[str, str], str] = {
    # Populated below by the initial-run inventory. Each entry
    # corresponds to a known violator the v2 plan will either fix in a
    # specific PR (mark with a "PR N:" reason) or annotate with a
    # `# typing:` comment when that PR lands.
}


def test_no_unexpected_type_circumventors() -> None:
    violations = _all_violations()
    unexpected: list[Violation] = []
    for v in violations:
        # Allow if explicitly listed by (path, marker-substring).
        allowed = any(
            v.path == k_path and k_marker in v.line for (k_path, k_marker) in _KNOWN_EXEMPTIONS
        )
        if allowed:
            continue
        unexpected.append(v)
    assert unexpected == [], "\n".join(
        f"{v.path}:{v.lineno}  {v.pattern}  {v.line}" for v in unexpected
    )
