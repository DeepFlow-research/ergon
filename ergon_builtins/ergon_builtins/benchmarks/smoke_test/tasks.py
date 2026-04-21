"""Pre-defined DAG workflow patterns for the smoke-test benchmark.

Factory functions return flat task lists (with dependency edges) that
``SmokeTestBenchmark.build_instances`` maps into instance dictionaries.

Patterns
--------
- single:   one atomic task
- linear:   A -> B -> C  (sequential)
- parallel: [A, B, C]   (independent)
- diamond:  start -> [left, right] -> join  (fan-out / fan-in)
"""

from ergon_core.api.task_types import BenchmarkTask


def single_task(instance_key: str = "default") -> list[BenchmarkTask]:
    return [
        BenchmarkTask(
            task_slug="root",
            instance_key=instance_key,
            description="Single smoke test task",
            evaluator_binding_keys=("default",),
        ),
    ]


def linear_tasks(instance_key: str = "default") -> list[BenchmarkTask]:
    return [
        BenchmarkTask(
            task_slug="step_1",
            instance_key=instance_key,
            description="First step",
            evaluator_binding_keys=("default",),
        ),
        BenchmarkTask(
            task_slug="step_2",
            instance_key=instance_key,
            description="Second step",
            dependency_task_slugs=("step_1",),
            evaluator_binding_keys=("default",),
        ),
        BenchmarkTask(
            task_slug="step_3",
            instance_key=instance_key,
            description="Third step",
            dependency_task_slugs=("step_2",),
            evaluator_binding_keys=("default",),
        ),
    ]


def parallel_tasks(instance_key: str = "default") -> list[BenchmarkTask]:
    return [
        BenchmarkTask(
            task_slug="task_a",
            instance_key=instance_key,
            description="Parallel task A",
            evaluator_binding_keys=("default",),
        ),
        BenchmarkTask(
            task_slug="task_b",
            instance_key=instance_key,
            description="Parallel task B",
            evaluator_binding_keys=("default",),
        ),
        BenchmarkTask(
            task_slug="task_c",
            instance_key=instance_key,
            description="Parallel task C",
            evaluator_binding_keys=("default",),
        ),
    ]


def diamond_tasks(instance_key: str = "default") -> list[BenchmarkTask]:
    return [
        BenchmarkTask(
            task_slug="start",
            instance_key=instance_key,
            description="Diamond start",
        ),
        BenchmarkTask(
            task_slug="left",
            instance_key=instance_key,
            description="Left branch",
            dependency_task_slugs=("start",),
        ),
        BenchmarkTask(
            task_slug="right",
            instance_key=instance_key,
            description="Right branch",
            dependency_task_slugs=("start",),
        ),
        BenchmarkTask(
            task_slug="join",
            instance_key=instance_key,
            description="Diamond join",
            dependency_task_slugs=("left", "right"),
            evaluator_binding_keys=("default",),
        ),
    ]
