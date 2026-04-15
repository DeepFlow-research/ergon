"""MiniF2F-specific sandbox manager.

Thin subclass of :class:`BaseSandboxManager` that provisions sandboxes from
the pre-built ``ergon-minif2f-v1`` E2B template (elan + Lean 4 + mathlib4 +
pre-cached oleans).  Because the template has everything baked in, the
``_install_dependencies`` hook is a no-op — the verify step just smoke-tests
that ``lake env lean --version`` returns cleanly.
"""

import json
import logging
from pathlib import Path
from uuid import UUID

from ergon_core.core.providers.sandbox.event_sink import SandboxEventSink
from ergon_core.core.providers.sandbox.manager import BaseSandboxManager

try:
    from e2b_code_interpreter import AsyncSandbox  # type: ignore[import-untyped]
except ImportError:
    AsyncSandbox = object  # type: ignore[assignment,misc]

logger = logging.getLogger(__name__)

# Fallback template name.  `ergon benchmark setup minif2f` persists the
# resolved template_id to ~/.ergon/sandbox_templates.json; when that exists
# we prefer the pinned build_id over the mutable name so reruns are
# reproducible across rebuilds of the same template name.
_DEFAULT_TEMPLATE_NAME = "ergon-minif2f-v1"
_REGISTRY_PATH = Path.home() / ".ergon" / "sandbox_templates.json"
_REGISTRY_SLUG = "minif2f"


def _resolve_template() -> str:
    """Return the pinned template_id from ~/.ergon registry, else the name."""
    if _REGISTRY_PATH.exists():
        try:
            with _REGISTRY_PATH.open() as f:
                data = json.load(f)
            entry = data.get(_REGISTRY_SLUG, {})
            template_id = entry.get("template_id")
            if template_id:
                return template_id
        except (OSError, json.JSONDecodeError) as exc:
            logger.warning(
                "Failed to read sandbox template registry at %s (%s); "
                "falling back to template name %r.",
                _REGISTRY_PATH,
                exc,
                _DEFAULT_TEMPLATE_NAME,
            )
    return _DEFAULT_TEMPLATE_NAME


class MiniF2FSandboxManager(BaseSandboxManager):
    """Sandbox manager for the MiniF2F Lean-4 benchmark.

    Resolves its template on first instantiation: prefers the pinned
    template_id written by ``ergon benchmark setup minif2f``, falling back
    to the mutable template name ``ergon-minif2f-v1``.
    """

    def __init__(self, event_sink: SandboxEventSink | None = None) -> None:
        super().__init__(event_sink=event_sink)
        # Instance-level override of BaseSandboxManager.template (ClassVar).
        # Resolved at construction time so registry changes take effect on
        # the next manager re-instantiation.
        self.template = _resolve_template()

    async def _create_directory_structure(self, sandbox: AsyncSandbox, sandbox_key: UUID) -> None:
        """Ensure workspace dirs exist and are writable by the sandbox user.

        The base class uses ``sandbox.run_code`` (the E2B code-interpreter
        Jupyter endpoint) which our bare-Dockerfile template does not
        expose. We use plain shell commands. The template's Dockerfile
        pre-creates ``/workspace/{scratchpad,final_output}`` and
        ``/inputs`` chowned to the sandbox user (uid 1000); we fall back
        to ``mkdir -p`` so this also works on older template builds.
        """
        # Template-version-agnostic: use -p so no-op if dirs already exist,
        # and run with /bin/sh -c so the shell handles nonexistent paths.
        result = await sandbox.commands.run(
            "mkdir -p /tmp/minif2f_probe /workspace/scratchpad "
            "/workspace/final_output /inputs 2>/dev/null || true",
            timeout=30,
        )
        # Writability smoke test — the criterion writes to
        # /tools/mathlib_project/src/verify.lean, which the Dockerfile
        # chowns to the sandbox user.
        try:
            await sandbox.files.write("/tools/mathlib_project/src/.ergon_probe", b"ok")
        except Exception as exc:  # slopcop: ignore[no-broad-except]
            await self.terminate(sandbox_key)
            raise RuntimeError(
                f"MiniF2F sandbox /tools/mathlib_project/src not writable "
                f"for sandbox_key={sandbox_key}: {exc}"
            ) from exc
        logger.debug(
            "MiniF2F dir setup for sandbox_key=%s: mkdir exit=%d",
            sandbox_key,
            result.exit_code,
        )

    async def _install_dependencies(self, sandbox: AsyncSandbox, task_id: UUID) -> None:
        # Pre-built template already contains elan, Lean toolchain, mathlib4
        # and decompressed oleans.  Nothing to do here.
        logger.debug(
            "MiniF2F sandbox %s provisioned from template %s (no install step).",
            task_id,
            self.template,
        )

    async def _verify_setup(self, sandbox: AsyncSandbox, task_id: UUID) -> None:
        logger.info("Verifying Lean toolchain in sandbox (task_id=%s) …", task_id)
        # `lake env lean --version` exercises both the Lean binary and the
        # mathlib project resolution — if either is broken this will fail.
        result = await sandbox.commands.run(
            "lake env lean --version",
            cwd="/tools/mathlib_project",
            timeout=60,
        )
        if result.exit_code != 0:
            stdout = result.stdout or ""
            stderr = result.stderr or ""
            raise RuntimeError(
                f"MiniF2F sandbox verification failed for task_id={task_id}. "
                f"`lake env lean --version` exit={result.exit_code}. "
                f"stdout={stdout!r} stderr={stderr!r}"
            )
        logger.info(
            "MiniF2F sandbox verified (task_id=%s): %s",
            task_id,
            (result.stdout or "").strip(),
        )
