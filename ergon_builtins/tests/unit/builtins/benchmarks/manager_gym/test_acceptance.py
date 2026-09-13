"""Keep a failed pilot gate from admitting further model work."""

import json
import sys
from unittest.mock import AsyncMock

import pytest

from examples.manager_gym import acceptance


@pytest.mark.asyncio
async def test_failed_pilot_drains_admitted_samples_without_launching_more(tmp_path, monkeypatch):
    monkeypatch.setattr(
        sys, "argv", ["acceptance.py", "--stage", "pilot", "--output", str(tmp_path)]
    )
    monkeypatch.setattr(acceptance, "code_digest", lambda: "test-build")
    submit = AsyncMock(side_effect=["first", "second"])
    finish = AsyncMock(
        side_effect=[
            {"sample_id": "first", "accepted": False},
            {"sample_id": "second", "accepted": True},
        ]
    )
    monkeypatch.setattr(acceptance, "submit", submit)
    monkeypatch.setattr(
        acceptance, "inspect_sample", lambda key: {"sample": {"status": "completed"}}
    )
    monkeypatch.setattr(acceptance, "finish", finish)
    with pytest.raises(SystemExit) as stopped:
        await acceptance.main()
    assert stopped.value.code == 1
    assert submit.await_count == finish.await_count == 2
    ledger = json.loads((tmp_path / "acceptance.json").read_text())
    assert set(ledger["samples"]) == set(acceptance.PILOTS[:2])
    submit.reset_mock()
    finish.reset_mock()
    with pytest.raises(SystemExit):
        await acceptance.main()
    submit.assert_not_awaited()
    finish.assert_not_awaited()
