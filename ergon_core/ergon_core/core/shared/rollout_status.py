"""Shared rollout batch status vocabulary."""

from enum import StrEnum


class RolloutStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    COMPLETE = "complete"
    FAILED = "failed"
    CANCELLED = "cancelled"
