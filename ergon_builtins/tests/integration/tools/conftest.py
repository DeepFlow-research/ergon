import importlib.util
import sys
from pathlib import Path

import pytest

_FIXTURE_PATH = Path(__file__).parents[2] / "fixtures" / "toy_workflow.py"
_SPEC = importlib.util.spec_from_file_location("toy_workflow_fixture", _FIXTURE_PATH)
if _SPEC is None or _SPEC.loader is None:
    raise RuntimeError(f"could not load fixture module at {_FIXTURE_PATH}")
_TOY_WORKFLOW = importlib.util.module_from_spec(_SPEC)
sys.modules[_SPEC.name] = _TOY_WORKFLOW
_SPEC.loader.exec_module(_TOY_WORKFLOW)


@pytest.fixture
def toy_workflow_harness(monkeypatch: pytest.MonkeyPatch):
    return _TOY_WORKFLOW.make_toy_workflow_harness(monkeypatch)
