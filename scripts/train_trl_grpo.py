#!/usr/bin/env python3
"""On-VM entry point for TRL GRPO training with Ergon environments.

Parses CLI args into a TrainingConfig and delegates to ergon_infra.
This is the script that SkyPilot YAMLs call on the GPU node.

For local development, prefer ``ergon train local`` which handles
definition creation and service checks automatically.

Example::

    python scripts/train_trl_grpo.py \\
        --benchmark smoke-test \\
        --definition-id <uuid> \\
        --model Qwen/Qwen2.5-1.5B \\
        --vllm-mode colocate \\
        --output-dir /checkpoints/test
"""

import logging
import sys

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)

from ergon_core.core.persistence.shared.db import ensure_db  # noqa: E402

from ergon_infra.training.config import training_config_from_args  # noqa: E402
from ergon_infra.training.trl_runner import run_trl_training  # noqa: E402


def main() -> int:
    ensure_db()
    config = training_config_from_args()
    return run_trl_training(config)


if __name__ == "__main__":
    sys.exit(main())
