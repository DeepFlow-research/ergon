"""Vendor the pinned Manager Agent Gym (MAG) sources into ``manager_gym/_vendor/mag``.

Usage::

    git clone https://github.com/DeepFlow-research/manager_agent_gym /tmp/mag
    git -C /tmp/mag checkout <REVISION>
    uv run python scripts/vendor_mag.py /tmp/mag          # rewrite the vendored tree
    uv run python scripts/vendor_mag.py /tmp/mag --check  # fail if the tree is stale

Upstream files are copied byte-for-byte except for their import statements.
Three mechanical rules are applied to imports, and nothing else is edited:

1. Absolute imports of ``manager_agent_gym`` and ``examples`` gain the vendor
   package prefix.
2. Imports from an upstream package whose ``__init__`` is not vendored are
   redirected to the submodule that defines each name.
3. The per-file overrides in ``IMPORT_OVERRIDES``.

Upstream modules that belong to MAG's own runtime (agents, engine, services)
are replaced by the hand-written shims listed in ``SHIMS``; the shims live in
the vendored tree and are recorded, not generated, by this script.
"""

from __future__ import annotations

import argparse
import ast
import filecmp
import hashlib
import json
import shutil
import subprocess
import sys
import tempfile
from dataclasses import dataclass
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_URL = "https://github.com/DeepFlow-research/manager_agent_gym"
REVISION = "3f7a5d4af1d31abaedbedd525a0090452926fef4"
VENDOR_PACKAGE = "ergon_builtins.benchmarks.manager_gym._vendor.mag"
VENDOR_ROOT = REPO_ROOT / "ergon_builtins/ergon_builtins/benchmarks/manager_gym/_vendor/mag"
UPSTREAM_TOP_LEVEL = ("manager_agent_gym", "examples")

# Upstream modules Ergon imports directly; everything they import is vendored too.
SEEDS = (
    "examples/scenarios.py",
    "examples/common_stakeholders.py",
    "manager_agent_gym/core/evaluation/common_evaluators.py",
    "manager_agent_gym/core/evaluation/scenario_constraints.py",
    "manager_agent_gym/schemas/evaluation/success_criteria.py",
    "manager_agent_gym/core/workflow_agents/prompts/ai_agent_prompts.py",
    "manager_agent_gym/core/workflow_agents/prompts/human_agent_prompts.py",
    "manager_agent_gym/core/manager_agent/prompts/structured_manager_prompts.py",
    "manager_agent_gym/core/decomposition/prompts.py",
)

# Upstream runtime modules replaced by hand-written shims in the vendored tree.
SHIMS = (
    "manager_agent_gym/core/common/logging.py",
    "manager_agent_gym/core/communication/service.py",
    "manager_agent_gym/core/workflow_agents/interface.py",
    "manager_agent_gym/core/workflow_agents/stakeholder_agent.py",
    "manager_agent_gym/schemas/execution/manager_actions.py",
)

# Ergon stores agent configs, not live agents, in ``Workflow.agents``.
IMPORT_OVERRIDES = {
    "manager_agent_gym/core/evaluation/stakeholder_evaluator.py": {
        "..workflow_agents.stakeholder_agent": (
            "from ...schemas.workflow_agents.stakeholder import "
            "StakeholderConfig as StakeholderAgent"
        ),
    },
}

# Upstream sources that native Ergon modules port rather than vendor.
REFERENCES = (
    "manager_agent_gym/core/decomposition/__init__.py",
    "manager_agent_gym/core/evaluation/validation_rules.py",
    "manager_agent_gym/core/execution/engine.py",
    "manager_agent_gym/core/manager_agent/random_manager.py",
    "manager_agent_gym/core/manager_agent/structured_manager.py",
    "manager_agent_gym/core/workflow_agents/ai_agent.py",
    "manager_agent_gym/core/workflow_agents/human_agent.py",
    "manager_agent_gym/core/workflow_agents/stakeholder_agent.py",
    "manager_agent_gym/core/communication/service.py",
    "manager_agent_gym/schemas/execution/manager_actions.py",
)


@dataclass(frozen=True)
class Upstream:
    root: Path

    def path(self, rel: str) -> Path:
        return self.root / rel

    def is_package(self, directory: Path) -> bool:
        return (directory / "__init__.py").is_file()

    def module_file(self, dotted: Path) -> Path | None:
        """Return the ``.py`` file for a module path, matching case exactly."""
        candidate = dotted.with_suffix(".py")
        if candidate.parent.is_dir() and candidate.name in _listdir(candidate.parent):
            return candidate
        return None


def _listdir(directory: Path) -> set[str]:
    return {entry.name for entry in directory.iterdir()}


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _rel(upstream: Upstream, path: Path) -> str:
    return path.relative_to(upstream.root).as_posix()


def _target_dir(upstream: Upstream, current: Path, node: ast.ImportFrom) -> Path | None:
    """Directory-or-module path an ``ImportFrom`` refers to, or ``None`` if external."""
    module = node.module or ""
    if node.level:
        base = current.parent
        for _ in range(node.level - 1):
            base = base.parent
        return base.joinpath(*module.split(".")) if module else base
    if module.split(".")[0] not in UPSTREAM_TOP_LEVEL:
        return None
    return upstream.root.joinpath(*module.split("."))


def _defining_module(upstream: Upstream, package: Path, name: str) -> Path:
    """Follow a package ``__init__`` re-export chain to the file defining ``name``."""
    if upstream.module_file(package / name):
        return package / f"{name}.py"
    init = package / "__init__.py"
    for node in ast.parse(init.read_text()).body:
        if isinstance(node, ast.ImportFrom) and any(
            (alias.asname or alias.name) == name for alias in node.names
        ):
            target = _target_dir(upstream, init, node)
            if target is None:
                break
            if upstream.is_package(target):
                return _defining_module(upstream, target, name)
            return target.with_suffix(".py")
    raise LookupError(f"cannot resolve {name!r} through {init}")


class Vendor:
    def __init__(self, upstream: Upstream) -> None:
        self.upstream = upstream
        self.files: set[str] = set()

    # ── Closure ──────────────────────────────────────────────────────────────

    def collect(self) -> None:
        stack = [self.upstream.path(seed) for seed in SEEDS]
        while stack:
            path = stack.pop()
            rel = _rel(self.upstream, path)
            if rel in self.files or rel in SHIMS:
                continue
            self.files.add(rel)
            for node in ast.walk(ast.parse(path.read_text())):
                if isinstance(node, ast.Import):
                    top = {alias.name.split(".")[0] for alias in node.names}
                    if top & set(UPSTREAM_TOP_LEVEL):
                        raise ValueError(f"{rel}: plain `import` of upstream code is unsupported")
                if isinstance(node, ast.ImportFrom):
                    stack.extend(self._dependencies(path, node))

    def _dependencies(self, current: Path, node: ast.ImportFrom) -> list[Path]:
        target = _target_dir(self.upstream, current, node)
        if target is None:
            return []
        if self.upstream.is_package(target):
            if self._keeps_package_import(target):
                return [target / "__init__.py"]
            return [_defining_module(self.upstream, target, alias.name) for alias in node.names]
        return [target.with_suffix(".py")]

    def _keeps_package_import(self, package: Path) -> bool:
        """Scenario packages are imported as packages; keep their ``__init__``."""
        rel = _rel(self.upstream, package)
        return rel.startswith("examples/end_to_end_examples/") and rel.count("/") == 2

    # ── Import rewriting ─────────────────────────────────────────────────────

    def rewrite(self, rel: str) -> str:
        """Return the upstream file with its imports rewritten for the vendor package."""
        path = self.upstream.path(rel)
        source = path.read_text()
        lines = source.splitlines(keepends=True)
        edits: list[tuple[int, int, list[str]]] = []
        for node in ast.walk(ast.parse(source)):
            if isinstance(node, ast.ImportFrom):
                new = self._rewrite_import(rel, path, node, lines)
                if new is not None:
                    edits.append((node.lineno - 1, node.end_lineno or node.lineno, new))
        for start, end, new in sorted(edits, reverse=True):
            lines[start:end] = new
        return "".join(lines)

    def _rewrite_import(
        self, rel: str, current: Path, node: ast.ImportFrom, lines: list[str]
    ) -> list[str] | None:
        original = lines[node.lineno - 1 : node.end_lineno or node.lineno]
        indent = original[0][: len(original[0]) - len(original[0].lstrip())]
        if not original[0].lstrip().startswith("from ") or ";" in "".join(original):
            raise ValueError(f"{rel}:{node.lineno}: import must occupy whole lines")
        module = "." * node.level + (node.module or "")
        override = IMPORT_OVERRIDES.get(rel, {}).get(module)
        if override is not None:
            return [f"{indent}{override}\n"]
        target = _target_dir(self.upstream, current, node)
        if target is None:
            return None
        if not self.upstream.is_package(target) or self._keeps_package_import(target):
            if node.level:
                return None
            head = f"{indent}from {node.module} "
            if not original[0].startswith(head):
                raise ValueError(f"{rel}:{node.lineno}: unexpected import layout")
            prefixed = f"{indent}from {VENDOR_PACKAGE}.{node.module} "
            return [prefixed + original[0][len(head) :], *original[1:]]
        groups: dict[str, list[ast.alias]] = {}
        for alias in node.names:
            defining = _defining_module(self.upstream, target, alias.name)
            groups.setdefault(self._module_name(node, target, defining), []).append(alias)
        multiline = len(original) > 1
        return [
            f"{indent}{line}\n"
            for name, aliases in groups.items()
            for line in _format_import(name, aliases, multiline=multiline)
        ]

    def _module_name(self, node: ast.ImportFrom, target: Path, defining: Path) -> str:
        suffix = defining.relative_to(target).with_suffix("")
        parts = [part for part in suffix.parts if part != "__init__"]
        if node.level:
            return "." * node.level + ".".join([node.module or "", *parts]).strip(".")
        return f"{VENDOR_PACKAGE}." + ".".join([node.module or "", *parts])

    # ── Output ───────────────────────────────────────────────────────────────

    def write(self, destination: Path) -> dict[str, dict[str, str]]:
        manifest: dict[str, dict[str, str]] = {}
        for rel in sorted(self.files):
            raw = self.upstream.path(rel).read_bytes()
            text = self.rewrite(rel)
            out = destination / rel
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_text(text)
            manifest[rel] = {
                "kind": "verbatim" if text.encode() == raw else "imports_rewritten",
                "upstream_sha256": _sha256(raw),
                "sha256": _sha256(text.encode()),
            }
        return manifest


def _format_import(module: str, aliases: list[ast.alias], *, multiline: bool) -> list[str]:
    names = [f"{a.name} as {a.asname}" if a.asname else a.name for a in aliases]
    if not multiline:
        return [f"from {module} import {', '.join(names)}"]
    return [f"from {module} import (", *[f"    {name}," for name in names], ")"]


def _upstream_revision(root: Path) -> str:
    return subprocess.check_output(["git", "-C", str(root), "rev-parse", "HEAD"], text=True).strip()


def build(upstream: Upstream, destination: Path) -> dict[str, object]:
    """Write the vendored tree into ``destination`` and return its manifest."""
    vendor = Vendor(upstream)
    vendor.collect()
    files = vendor.write(destination)
    for rel in SHIMS:
        target = destination / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(VENDOR_ROOT / rel, target)
        files[rel] = {"kind": "shim", "sha256": _sha256(target.read_bytes())}
    # Upstream package __init__ files pull in MAG's runtime, so only the scenario
    # packages keep theirs; every other package gets an empty __init__.
    for directory in sorted({p.parent for p in destination.rglob("*.py")}):
        for package in [directory, *directory.parents]:
            if package == destination.parent:
                break
            init = package / "__init__.py"
            if not init.exists():
                init.write_text("")
                files[init.relative_to(destination).as_posix()] = {
                    "kind": "package_init",
                    "sha256": _sha256(b""),
                }
    return {
        "upstream": UPSTREAM_URL,
        "revision": REVISION,
        "files": dict(sorted(files.items())),
        "references": {rel: _sha256(upstream.path(rel).read_bytes()) for rel in REFERENCES},
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("upstream", type=Path, help="Checkout of the upstream MAG repository")
    parser.add_argument("--check", action="store_true", help="Fail if the vendored tree is stale")
    args = parser.parse_args()

    root = args.upstream.resolve()
    if _upstream_revision(root) != REVISION:
        parser.error(f"{root} is not at revision {REVISION}")
    upstream = Upstream(root)

    with tempfile.TemporaryDirectory() as scratch:
        staging = Path(scratch) / "mag"
        staging.mkdir()
        manifest = build(upstream, staging)
        (staging / "MANIFEST.json").write_text(json.dumps(manifest, indent=2) + "\n")
        for extra in ("README.md", "NOTICE"):
            if (VENDOR_ROOT / extra).exists():
                shutil.copyfile(VENDOR_ROOT / extra, staging / extra)
        if args.check:
            stale = _diff(staging, VENDOR_ROOT)
            for rel in stale:
                print(f"stale: {rel}", file=sys.stderr)
            return 1 if stale else 0
        shutil.rmtree(VENDOR_ROOT, ignore_errors=True)
        shutil.copytree(staging, VENDOR_ROOT)
    print(f"vendored {len(manifest['files'])} files into {VENDOR_ROOT.relative_to(REPO_ROOT)}")
    return 0


def _diff(left: Path, right: Path) -> list[str]:
    ignore = {"__pycache__"}
    names = {
        p.relative_to(root).as_posix()
        for root in (left, right)
        for p in root.rglob("*")
        if p.is_file() and not ignore & set(p.parts)
    }
    return sorted(
        rel
        for rel in names
        if not ((left / rel).is_file() and (right / rel).is_file())
        or not filecmp.cmp(left / rel, right / rel, shallow=False)
    )


if __name__ == "__main__":
    sys.exit(main())
