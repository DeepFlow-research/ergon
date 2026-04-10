"""Checkpoint discovery for the eval watcher.

Scans a directory for HuggingFace-format checkpoints and returns
metadata for each one found.
"""

import logging
import re
from pathlib import Path

from pydantic import BaseModel

logger = logging.getLogger(__name__)

_STEP_PATTERN = re.compile(r"checkpoint-(\d+)")


class CheckpointInfo(BaseModel):
    """Metadata about one discovered checkpoint."""

    model_config = {"frozen": True}

    path: str
    step: int
    has_config: bool
    has_model: bool

    @property
    def is_valid(self) -> bool:
        return self.has_config or self.has_model


def discover_checkpoints(checkpoint_dir: str | Path) -> list[CheckpointInfo]:
    """Scan a directory for HuggingFace-format checkpoints.

    Expects the standard layout::

        checkpoint_dir/
          checkpoint-100/
            config.json
            model.safetensors (or adapter_model.safetensors, pytorch_model.bin)
          checkpoint-200/
            ...

    Returns checkpoints sorted by step number (ascending).
    """
    root = Path(checkpoint_dir)
    if not root.is_dir():
        logger.warning("Checkpoint directory does not exist: %s", root)
        return []

    checkpoints: list[CheckpointInfo] = []

    for child in sorted(root.iterdir()):
        if not child.is_dir():
            continue

        match = _STEP_PATTERN.match(child.name)
        if match is None:
            continue

        step = int(match.group(1))
        has_config = (child / "config.json").exists()
        has_model = any(
            (child / name).exists()
            for name in [
                "model.safetensors",
                "adapter_model.safetensors",
                "pytorch_model.bin",
                "adapter_model.bin",
            ]
        )

        info = CheckpointInfo(
            path=str(child),
            step=step,
            has_config=has_config,
            has_model=has_model,
        )

        if info.is_valid:
            checkpoints.append(info)

    checkpoints.sort(key=lambda c: c.step)
    return checkpoints
