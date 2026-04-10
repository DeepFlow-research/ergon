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
            task_key="root",
            instance_key=instance_key,
            description="Single smoke test task",
            evaluator_binding_keys=("default",),
        ),
    ]


def linear_tasks(instance_key: str = "default") -> list[BenchmarkTask]:
    return [
        BenchmarkTask(
            task_key="step_1",
            instance_key=instance_key,
            description="First step",
            evaluator_binding_keys=("default",),
        ),
        BenchmarkTask(
            task_key="step_2",
            instance_key=instance_key,
            description="Second step",
            dependency_task_keys=("step_1",),
            evaluator_binding_keys=("default",),
        ),
        BenchmarkTask(
            task_key="step_3",
            instance_key=instance_key,
            description="Third step",
            dependency_task_keys=("step_2",),
            evaluator_binding_keys=("default",),
        ),
    ]


def parallel_tasks(instance_key: str = "default") -> list[BenchmarkTask]:
    return [
        BenchmarkTask(
            task_key="task_a",
            instance_key=instance_key,
            description="Parallel task A",
            evaluator_binding_keys=("default",),
        ),
        BenchmarkTask(
            task_key="task_b",
            instance_key=instance_key,
            description="Parallel task B",
            evaluator_binding_keys=("default",),
        ),
        BenchmarkTask(
            task_key="task_c",
            instance_key=instance_key,
            description="Parallel task C",
            evaluator_binding_keys=("default",),
        ),
    ]


def diamond_tasks(instance_key: str = "default") -> list[BenchmarkTask]:
    return [
        BenchmarkTask(
            task_key="start",
            instance_key=instance_key,
            description="Diamond start",
        ),
        BenchmarkTask(
            task_key="left",
            instance_key=instance_key,
            description="Left branch",
            dependency_task_keys=("start",),
        ),
        BenchmarkTask(
            task_key="right",
            instance_key=instance_key,
            description="Right branch",
            dependency_task_keys=("start",),
        ),
        BenchmarkTask(
            task_key="join",
            instance_key=instance_key,
            description="Diamond join",
            dependency_task_keys=("left", "right"),
            evaluator_binding_keys=("default",),
        ),
    ]
