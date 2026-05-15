"""Sandbox template resolution utilities for MiniF2F."""

import json
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Fallback template name.  `ergon benchmark setup minif2f` persists the
# resolved template_id to ~/.ergon/sandbox_templates.json; when that exists
# we prefer the pinned build_id over the mutable name so reruns are
# reproducible across rebuilds of the same template name.
DEFAULT_TEMPLATE_NAME = "ergon-minif2f-v1"
REGISTRY_PATH = Path.home() / ".ergon" / "sandbox_templates.json"
REGISTRY_SLUG = "minif2f"


def resolve_template() -> str:
    """Return the pinned template_id from ~/.ergon registry, else the name."""
    if REGISTRY_PATH.exists():
        try:
            with REGISTRY_PATH.open() as f:
                data = json.load(f)
            entry = data.get(REGISTRY_SLUG, {})
            template_id = entry.get("template_id")
            if template_id:
                return template_id
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "Failed to read sandbox template registry at %s (%s); "
                "falling back to template name %r.",
                REGISTRY_PATH,
                exc,
                DEFAULT_TEMPLATE_NAME,
            )
    return DEFAULT_TEMPLATE_NAME
