"""Keep a failed acceptance gate from admitting further model work."""

import json
import sys
from hashlib import sha256
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from examples.manager_gym import acceptance


def test_frozen_checkpoint_does_not_substitute_for_named_report(monkeypatch):
    content = '{"fixture":true}'
    digest = sha256(content.encode()).hexdigest()
    monkeypatch.setattr(acceptance, "definitions", lambda scenario: [SimpleNamespace(slug="a")])
    evidence = {
        "nodes": [{"task_id": "root", "parent_task_id": None}],
        "attempts": [
            {"id": "root-attempt", "task_id": "root", "worker_output_json": {"output": content}}
        ],
        "evaluations": [
            {
                "score": 0,
                "summary_json": {
                    "criterion_results": [
                        {"criterion_slug": "a", "metadata": {"snapshot_hash": digest}}
                    ]
                },
            }
        ],
        "resources": [
            {
                "task_attempt_id": "root-attempt",
                "kind": "artifact",
                "name": ".checkpoints/episode-final-snapshot.json",
                "content_hash": digest,
            }
        ],
    }
    assert not acceptance.score_checks(evidence, "fixture")["snapshot_report_saved"]
    report = dict(evidence["resources"][0], kind="report", name="manager-gym-snapshot.json")
    evidence["resources"].append(report)
    assert acceptance.score_checks(evidence, "fixture")["snapshot_report_saved"]
    report["content_hash"] = "wrong bytes"
    assert not acceptance.score_checks(evidence, "fixture")["snapshot_report_saved"]
    report["content_hash"] = digest
    report["task_attempt_id"] = "unrelated-worker"
    assert not acceptance.score_checks(evidence, "fixture")["snapshot_report_saved"]


def test_native_failed_sample_is_accepted_only_for_accounted_work_failures():
    evidence = {
        "sample": {"status": "failed"},
        "nodes": [
            {"task_id": "manager", "parent_task_id": None, "status": "completed"},
            {"task_id": "work", "parent_task_id": "manager", "status": "failed"},
        ],
        "attempts": [
            {
                "id": "attempt",
                "created_at": "2026-09-14",
                "task_id": "work",
                "worker_output_json": {
                    "success": False,
                    "metadata": {"model_failure": {"kind": "request_limit"}},
                },
            }
        ],
    }
    assert all(acceptance.execution_checks(evidence).values())
    evidence["attempts"][0]["worker_output_json"] = None
    assert not acceptance.execution_checks(evidence)["native_failures_accounted"]
    evidence["nodes"][0]["status"] = "failed"
    assert not acceptance.execution_checks(evidence)["manager_completed"]
    evidence["nodes"][1]["status"] = "blocked"
    assert not acceptance.execution_checks(evidence)["all_tasks_terminal"]


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["pilot", "catalog"])
async def test_failed_gate_drains_admitted_samples_without_launching_more(
    tmp_path, monkeypatch, stage
):
    monkeypatch.setattr(
        sys,
        "argv",
        ["acceptance.py", "--stage", stage, "--output", str(tmp_path), "--model", "test:model"],
    )
    monkeypatch.setattr(acceptance, "SCENARIOS", acceptance.PILOTS)
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
        acceptance,
        "inspect_sample",
        lambda key: {"sample": {"status": "completed"}, "nodes": [], "attempts": []},
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


@pytest.mark.asyncio
@pytest.mark.parametrize("stage", ["pilot", "catalog"])
async def test_unaccounted_failure_stops_admission_before_slow_sample_finishes(
    tmp_path, monkeypatch, stage
):
    monkeypatch.setattr(
        sys,
        "argv",
        ["acceptance.py", "--stage", stage, "--output", str(tmp_path), "--model", "test:model"],
    )
    monkeypatch.setattr(acceptance, "SCENARIOS", acceptance.PILOTS)
    monkeypatch.setattr(acceptance, "code_digest", lambda: "test-build")
    submit = AsyncMock(side_effect=["slow", "quick"])
    finish = AsyncMock(
        side_effect=[
            {"sample_id": "quick", "accepted": True},
            {"sample_id": "slow", "accepted": False},
        ]
    )
    slow_reads = 0

    def inspect(key):
        nonlocal slow_reads
        if key == "slow":
            slow_reads += 1
            return {
                "sample": {"status": "executing" if slow_reads == 1 else "failed"},
                "nodes": [{"task_id": "work", "parent_task_id": "manager", "status": "failed"}],
                "attempts": [],
            }
        return {"sample": {"status": "completed"}, "nodes": [], "attempts": []}

    monkeypatch.setattr(acceptance, "submit", submit)
    monkeypatch.setattr(acceptance, "finish", finish)
    monkeypatch.setattr(acceptance, "inspect_sample", inspect)
    monkeypatch.setattr(acceptance.asyncio, "sleep", AsyncMock())
    with pytest.raises(SystemExit):
        await acceptance.main()
    assert submit.await_count == finish.await_count == 2
    ledger = json.loads((tmp_path / "acceptance.json").read_text())
    assert ledger["admission_failure"] == "slow"
