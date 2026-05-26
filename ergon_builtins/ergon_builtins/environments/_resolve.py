"""Typed component resolution helpers for builtin environments."""

from __future__ import annotations

from collections.abc import Callable, Sequence
from typing import TypeVar, cast

from ergon_core.api.rubric import Evaluator
from ergon_core.api.sandbox import Sandbox
from ergon_core.api.worker import Worker

RowT = TypeVar("RowT")


def resolve_worker(value: Worker | Callable[[RowT], Worker], row: RowT) -> Worker:
    if isinstance(value, Worker):
        return value
    return cast(Callable[[RowT], Worker], value)(row)


def resolve_sandbox(value: Sandbox | Callable[[RowT], Sandbox], row: RowT) -> Sandbox:
    if isinstance(value, Sandbox):
        return value
    return cast(Callable[[RowT], Sandbox], value)(row)


def resolve_evaluators(
    value: Sequence[Evaluator] | Callable[[RowT], Sequence[Evaluator]],
    row: RowT,
) -> tuple[Evaluator, ...]:
    if callable(value):
        return tuple(cast(Callable[[RowT], Sequence[Evaluator]], value)(row))
    return tuple(value)
