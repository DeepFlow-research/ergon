from pathlib import Path

from ergon_core.core.persistence.telemetry.models import RolloutBatch


ROOT = Path(__file__).resolve().parents[4]

DISALLOWED_ROLLOUT_RUN_SYMBOLS = [
    "RolloutBatchRun",
    "rollout_batch_runs",
    "batch_run",
    "run_ids",
]


def test_rollout_batch_sample_membership_no_longer_uses_runs() -> None:
    offenders: list[str] = []
    for root in [
        ROOT / "ergon_core" / "ergon_core" / "core" / "rl",
        ROOT / "ergon_core" / "ergon_core" / "core" / "infrastructure" / "http" / "routes",
    ]:
        for path in root.rglob("*.py"):
            text = path.read_text(encoding="utf-8")
            for symbol in DISALLOWED_ROLLOUT_RUN_SYMBOLS:
                if symbol in text:
                    offenders.append(f"{path.relative_to(ROOT)} contains {symbol!r}")

    assert offenders == []


def test_rollout_batch_definition_id_is_documented_as_temporary_bridge() -> None:
    field = RolloutBatch.model_fields["definition_id"]

    assert field.description is not None
    assert "Temporary compatibility bridge" in field.description
    assert "experiment-backed" in field.description
