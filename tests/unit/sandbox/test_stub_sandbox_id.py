"""Tests for is_stub_sandbox_id() sentinel check."""

import pytest
from ergon_core.core.providers.sandbox.manager import is_stub_sandbox_id


@pytest.mark.parametrize(
    "sandbox_id,expected",
    [
        ("stub-sandbox-abc123", True),  # canonical stub id
        ("stub-sandbox-", True),  # prefix only still matches
        ("sbx-real-123", False),  # real E2B sandbox id
        ("", False),  # empty string
        (None, False),  # None (function accepts object)
        (42, False),  # non-string
        ("STUB-SANDBOX-abc", False),  # wrong case
        ("not-a-stub", False),  # random string
    ],
)
def test_is_stub_sandbox_id(sandbox_id, expected):
    assert is_stub_sandbox_id(sandbox_id) is expected
