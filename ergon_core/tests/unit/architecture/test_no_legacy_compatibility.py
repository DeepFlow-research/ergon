import importlib

import pytest


def test_legacy_extractor_symbols_are_not_importable() -> None:
    module_name = "ergon_core.core.rl." + "extraction"

    with pytest.raises(ImportError):
        importlib.import_module(module_name)

    import ergon_core.core.rl.rollout_types as rollout_types

    assert not hasattr(rollout_types, "Traj" + "ectory")
