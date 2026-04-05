"""Shared Exa client for all Exa-based skills.

Uses environment variable for API key to work both in host and in E2B sandbox.
"""

import os

from exa_py import Exa


def get_exa_client() -> Exa:
    """Get Exa client from environment variable.

    Works both in host (where EXA_API_KEY is from .env) and
    in VM (where it's passed via sandbox envs parameter).
    """
    api_key = os.environ.get("EXA_API_KEY", "")
    if not api_key:
        raise ValueError("EXA_API_KEY environment variable is not set")

    return Exa(api_key=api_key)
