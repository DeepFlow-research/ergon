"""Validators for structured output returned by model tool calls."""

import json

from pydantic import BeforeValidator


def _decode_json_string(value: object) -> object:
    return json.loads(value) if isinstance(value, str) else value


# Some OpenAI-compatible tool parsers return nested objects and lists as JSON
# strings. Decoding them first leaves normal validation unchanged: malformed
# JSON and invalid structures still fail.
JsonDecoded = BeforeValidator(_decode_json_string)
