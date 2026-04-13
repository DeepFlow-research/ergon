"""Shared type aliases for stringly-typed identifiers.

NewType aliases are erased at runtime but catch cross-field
misassignment in type checkers (e.g., passing a benchmark slug
where a worker binding key is expected).
"""

from typing import NewType

WorkerBindingKey = NewType("WorkerBindingKey", str)
BenchmarkSlug = NewType("BenchmarkSlug", str)
