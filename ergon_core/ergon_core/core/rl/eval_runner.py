"""Eval watcher: score checkpoints through Pythonic experiment submit scripts.

Watches a checkpoint directory, detects new checkpoints, and delegates each
checkpoint to an explicit command supplied by the caller. The CLI no longer
constructs or submits experiment work itself; benchmark/environment composition
stays in Python authoring code.

The watcher runs on CPU.  For vLLM-based evaluation, use
``--on-checkpoint`` to spawn a SkyPilot GPU job per checkpoint.
"""

import asyncio
import logging
import shlex
import subprocess

from ergon_core.core.rl.checkpoint import CheckpointInfo, discover_checkpoints

logger = logging.getLogger(__name__)
LOCAL_EVAL_UNSUPPORTED_EXIT_CODE = 2


async def watch_and_evaluate(
    checkpoint_dir: str,
    benchmark_type: str,
    *,
    evaluator_type: str,
    model_base: str,
    poll_interval_s: int = 60,
    eval_limit: int | None = None,
    on_checkpoint_cmd: str | None = None,
    external_cmd_timeout_s: int = 600,
) -> None:
    """Watch for new checkpoints and evaluate each one.

    Args:
        checkpoint_dir: directory to watch for ``checkpoint-NNN/`` dirs.
        benchmark_type: Ergon benchmark slug.
        evaluator_type: evaluator slug.
        model_base: base model for local evaluation (when not using ``on_checkpoint_cmd``).
        poll_interval_s: seconds between directory scans.
        eval_limit: max tasks to evaluate per checkpoint.
        on_checkpoint_cmd: shell command template to run per checkpoint.
            ``{path}`` is replaced with the checkpoint path, ``{step}``
            with the step number.  Use this to spawn SkyPilot GPU jobs.
        external_cmd_timeout_s: seconds before killing an external eval command.
    """
    seen: set[str] = set()

    logger.info("Starting eval watcher on %s (poll every %ds)", checkpoint_dir, poll_interval_s)

    while True:
        checkpoints = discover_checkpoints(checkpoint_dir)
        new_checkpoints = [c for c in checkpoints if c.path not in seen]

        for ckpt in new_checkpoints:
            logger.info("New checkpoint: %s (step %d)", ckpt.path, ckpt.step)

            if on_checkpoint_cmd:
                _run_external_eval(ckpt, on_checkpoint_cmd, timeout_s=external_cmd_timeout_s)
            else:
                await _run_local_eval(
                    ckpt,
                    benchmark_type=benchmark_type,
                    evaluator_type=evaluator_type,
                    model_base=model_base,
                    eval_limit=eval_limit,
                )

            seen.add(ckpt.path)

        await asyncio.sleep(poll_interval_s)


def _run_external_eval(ckpt: CheckpointInfo, cmd_template: str, *, timeout_s: int = 600) -> None:
    """Spawn an external command (e.g. SkyPilot) for checkpoint evaluation."""
    rendered = cmd_template.replace("{path}", ckpt.path).replace("{step}", str(ckpt.step))
    cmd = shlex.split(rendered)
    logger.info("Running external eval: %s", cmd)

    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=timeout_s)
        if result.returncode != 0:
            logger.warning(
                "External eval failed (exit %d): %s", result.returncode, result.stderr[:500]
            )
        else:
            logger.info("External eval launched for step %d", ckpt.step)
    except subprocess.TimeoutExpired:
        logger.warning(
            "External eval command timed out after %ds for step %d", timeout_s, ckpt.step
        )


async def _run_local_eval(
    ckpt: CheckpointInfo,
    *,
    benchmark_type: str,
    evaluator_type: str,
    model_base: str,
    eval_limit: int | None,
) -> int:
    """Reject local CLI-launched evaluation.

    The removed CLI launch path used to hide benchmark composition inside the
    eval CLI. Callers should use ``--on-checkpoint`` with
    a Python entrypoint that builds the desired Experiment/Environment/Sampler
    objects and submits them directly.
    """
    logger.error(
        "Local checkpoint evaluation is no longer supported by the CLI. "
        "Use --on-checkpoint with a Python experiment submission command "
        "(checkpoint=%s benchmark=%s evaluator=%s model_base=%s eval_limit=%s).",
        ckpt.path,
        benchmark_type,
        evaluator_type,
        model_base,
        eval_limit,
    )
    return LOCAL_EVAL_UNSUPPORTED_EXIT_CODE


async def evaluate_checkpoint(
    checkpoint_path: str,
    benchmark_type: str,
    *,
    evaluator_type: str,
    model_base: str,
    eval_limit: int | None = None,
) -> int:
    """One-shot checkpoint evaluation.  Returns exit code."""
    ckpt = CheckpointInfo(
        path=checkpoint_path,
        step=0,
        has_config=True,
        has_model=True,
    )

    return await _run_local_eval(
        ckpt,
        benchmark_type=benchmark_type,
        evaluator_type=evaluator_type,
        model_base=model_base,
        eval_limit=eval_limit,
    )
