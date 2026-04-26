"""Sentinel helpers for test-support sandbox IDs."""

STUB_SANDBOX_PREFIX = "stub-sandbox-"


def is_stub_sandbox_id(
    sandbox_id: object,  # slopcop: ignore[no-typing-any] -- sentinel check accepts arbitrary persisted JSON values.
) -> bool:
    return isinstance(sandbox_id, str) and sandbox_id.startswith(STUB_SANDBOX_PREFIX)
