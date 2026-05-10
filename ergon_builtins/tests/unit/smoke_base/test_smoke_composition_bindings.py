from ergon_cli.composition import build_experiment
from tests.fixtures.smoke_components import register_smoke_fixtures


def test_happy_smoke_experiment_binds_recursive_worker() -> None:
    register_smoke_fixtures()

    experiment = build_experiment(
        benchmark_slug="researchrubrics",
        model="stub:constant",
        worker_slug="researchrubrics-smoke-worker",
        evaluator_slug="researchrubrics-smoke-criterion",
        limit=1,
    )

    task = experiment.benchmark.build_instances()["default"][0]
    assert task.worker.type_slug == "researchrubrics-smoke-worker"
    assert {evaluator.name for evaluator in task.evaluators} >= {"default", "post-root"}


def test_sad_smoke_experiment_does_not_bind_recursive_worker() -> None:
    register_smoke_fixtures()

    experiment = build_experiment(
        benchmark_slug="researchrubrics",
        model="stub:constant",
        worker_slug="researchrubrics-sadpath-smoke-worker",
        evaluator_slug="researchrubrics-smoke-criterion",
        limit=1,
    )

    task = experiment.benchmark.build_instances()["default"][0]
    assert task.worker.type_slug == "researchrubrics-sadpath-smoke-worker"
    assert {evaluator.name for evaluator in task.evaluators} >= {"default", "post-root"}
