"""The vendored MAG tree matches its manifest, and native prompts keep the upstream text."""

import hashlib
import importlib
import json
import pkgutil
from pathlib import Path

from ergon_builtins.benchmarks.manager_gym._vendor import mag
from ergon_builtins.benchmarks.manager_gym.prompts import judge_prompt
from ergon_builtins.benchmarks.manager_gym.upstream import WorkflowRubric

VENDOR_ROOT = Path(mag.__file__).parent
MANIFEST = json.loads((VENDOR_ROOT / "MANIFEST.json").read_text())
FIXTURES = Path(__file__).parent / "fixtures"


def test_every_vendored_file_matches_the_manifest():
    on_disk = {
        path.relative_to(VENDOR_ROOT).as_posix()
        for path in VENDOR_ROOT.rglob("*.py")
        if "__pycache__" not in path.parts
    }
    assert on_disk == set(MANIFEST["files"])
    for rel, entry in MANIFEST["files"].items():
        digest = hashlib.sha256((VENDOR_ROOT / rel).read_bytes()).hexdigest()
        assert digest == entry["sha256"], f"{rel} was edited; re-run scripts/vendor_mag.py"


def test_every_vendored_module_imports():
    for module in pkgutil.walk_packages(mag.__path__, prefix=f"{mag.__name__}."):
        importlib.import_module(module.name)


def test_judge_prompt_renders_the_upstream_text():
    rubric = WorkflowRubric(
        name="golden",
        llm_prompt="Award credit for:\n(a) {braces} kept\n(b) unicode – ok",
        max_score=7.5,
    )
    rendered = judge_prompt(rubric, "WORKFLOW: demo\n- task A {x}\n")
    assert rendered == (FIXTURES / "judge_prompt.txt").read_text()
