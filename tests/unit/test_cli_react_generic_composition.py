"""Smoke: build_experiment(worker=react-generic, toolkit_benchmark=...) puts
the slug into BenchmarkTask task_payload so ReActGenericWorker can read it."""

from ergon_cli.composition import build_experiment


def test_react_generic_toolkit_benchmark_propagates_into_task_metadata() -> None:
    exp = build_experiment(
        benchmark_slug="smoke-test",
        model="stub:constant",
        worker_slug="react-generic",
        evaluator_slug="stub-rubric",
        toolkit_benchmark="swebench-verified",
        limit=1,
    )
    instances = exp.benchmark.build_instances()
    tasks = [t for tasks_for_cohort in instances.values() for t in tasks_for_cohort]
    assert tasks, "benchmark produced no tasks"
    assert all(t.task_payload.get("toolkit_benchmark") == "swebench-verified" for t in tasks)
