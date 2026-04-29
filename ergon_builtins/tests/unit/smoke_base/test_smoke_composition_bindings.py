from ergon_cli.composition import build_experiment


def test_happy_smoke_experiment_binds_recursive_worker(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_TEST_HARNESS", "1")

    experiment = build_experiment(
        benchmark_slug="researchrubrics",
        model="stub:constant",
        worker_slug="researchrubrics-smoke-worker",
        evaluator_slug="researchrubrics-smoke-criterion",
        limit=1,
    )

    assert set(experiment.workers) >= {
        "parent",
        "researchrubrics-smoke-leaf",
        "researchrubrics-smoke-recursive-worker",
    }
    assert set(experiment.evaluators) >= {"default", "post-root"}


def test_sad_smoke_experiment_does_not_bind_recursive_worker(monkeypatch) -> None:
    monkeypatch.setenv("ENABLE_TEST_HARNESS", "1")

    experiment = build_experiment(
        benchmark_slug="researchrubrics",
        model="stub:constant",
        worker_slug="researchrubrics-sadpath-smoke-worker",
        evaluator_slug="researchrubrics-smoke-criterion",
        limit=1,
    )

    assert "researchrubrics-smoke-recursive-worker" not in experiment.workers
    assert set(experiment.workers) >= {
        "parent",
        "researchrubrics-smoke-leaf",
        "researchrubrics-smoke-leaf-failing",
    }
    assert set(experiment.evaluators) >= {"default", "post-root"}
