"""Base interface for framework transcript adapters."""

from typing import Protocol, TypeVar

from ergon_core.api.generation import GenerationTurn
from ergon_core.core.persistence.context.models import RunContextEvent

TranscriptT = TypeVar("TranscriptT")
ReplayT = TypeVar("ReplayT")


class TranscriptAdapter(Protocol[TranscriptT, ReplayT]):
    """Convert between framework-native transcripts and Ergon context events."""

    def build_turns(self, transcript: TranscriptT) -> list[GenerationTurn]:
        """Return ordered turns extracted from a complete transcript."""
        ...

    def assemble_replay(self, events: list[RunContextEvent]) -> ReplayT:
        """Return framework-native replay context from ordered context events."""
        ...
