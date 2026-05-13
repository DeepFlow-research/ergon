"""Base interface for framework transcript adapters."""

from typing import Protocol, TypeVar

from ergon_core.core.domain.generation.context_parts import ContextPartChunk

TranscriptT = TypeVar("TranscriptT")
ReplayT = TypeVar("ReplayT")


class TranscriptAdapter(Protocol[TranscriptT, ReplayT]):
    """Convert between framework-native transcripts and Ergon context events."""

    def build_chunks(self, transcript: TranscriptT) -> list[ContextPartChunk]:
        """Return ordered chunks extracted from a complete transcript."""
        ...

