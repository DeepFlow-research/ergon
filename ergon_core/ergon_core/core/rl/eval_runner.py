"""Eval watcher: score checkpoints on Ergon benchmarks.

Watches a checkpoint directory, detects new checkpoints, runs
``ergon benchmark run`` against each, and optionally reports results.

The watcher runs on CPU.  For vLLM-based evaluation, use
``--on-checkpoint`` to spawn a SkyPilot GPU job per checkpoint.
"""

import asyncio
import logging
import shlex
import subprocess

from ergon_core.core.rl.checkpoint import CheckpointInfo, discover_checkpoints

logger = logging.getLogger(__name__)


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
    """Run benchmark evaluation locally via the CLI.  Returns exit code.

    Uses the checkpoint path as the vLLM model target so each checkpoint
    is actually evaluated (not just the base model).
    """
    model_target = f"vllm:{ckpt.path}"

    cmd = [
        "ergon",
        "benchmark",
        "run",
        "--benchmark",
        benchmark_type,
        "--evaluator",
        evaluator_type,
        "--model",
        model_target,
    ]

    if eval_limit:
        cmd.extend(["--limit", str(eval_limit)])

    logger.info("Running local eval for step %d: %s", ckpt.step, " ".join(cmd))

    env = dict(__import__("os").environ)
    env["ERGON_CHECKPOINT_STEP"] = str(ckpt.step)
    env["ERGON_CHECKPOINT_PATH"] = ckpt.path

    try:
        proc = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
            env=env,
        )
        _stdout, stderr = await proc.communicate()

        exit_code = 0 if proc.returncode is None else proc.returncode
        if exit_code == 0:
            logger.info("Eval complete for step %d", ckpt.step)
        else:
            logger.warning(
                "Eval failed for step %d (exit %d): %s",
                ckpt.step,
                exit_code,
                stderr.decode()[:500],
            )
        return exit_code
    except Exception:  # slopcop: ignore[no-broad-except]
        logger.exception("Eval crashed for step %d", ckpt.step)
        return 1


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
