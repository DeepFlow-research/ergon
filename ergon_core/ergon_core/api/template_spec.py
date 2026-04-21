"""Template-setup descriptor for Benchmark subclasses."""

from pathlib import Path
from typing import TypeAlias

from pydantic import BaseModel


class TemplateSpec(BaseModel, frozen=True):
    """Declarative description of a benchmark's sandbox-template setup.

    A Benchmark subclass sets ``template_spec`` to either a ``TemplateSpec``
    describing how its sandbox is prepared, or to the ``NoSetup`` sentinel to
    declare intentionally that no template setup is required.

    Fields are intentionally additive: a benchmark may set ``e2b_template_id``
    (pre-built), ``build_recipe_path`` (buildable), ``runtime_install``
    (installed at sandbox-prep time), or any combination.
    """

    e2b_template_id: str | None = None
    """Pre-built E2B template name or pinned template_id.

    When set, ``ergon benchmark setup <slug>`` verifies the template exists in
    the user's E2B account and prints rebuild instructions if absent.

    Example: ``"ergon-minif2f-v1"``
    """

    build_recipe_path: Path | None = None
    """Path to the Dockerfile or setup directory that ``ergon benchmark setup``
    uses to build the E2B template.

    Typically ``Path(__file__).parent / "sandbox"`` pointing to the
    per-benchmark ``sandbox/`` folder (which must contain a ``Dockerfile`` and
    an ``e2b.toml.template``).

    When set alongside ``e2b_template_id``, the setup command can rebuild the
    template from this recipe.
    """

    runtime_install: tuple[str, ...] = ()
    """pip package specifiers installed at sandbox-prep time.

    Strings are passed verbatim to ``pip install``; extras markers such as
    ``"foo[bar]==1.2.3"`` are supported.

    When non-empty and ``build_recipe_path`` is None, ``ergon benchmark setup``
    prints a note that setup is deferred to sandbox prep (no build step is
    needed).
    """


class _NoSetupType:
    """Singleton sentinel: this benchmark has no template setup requirements.

    Use the pre-constructed ``NoSetup`` instance, not this class directly.
    """

    _instance: "_NoSetupType | None" = None

    def __new__(cls) -> "_NoSetupType":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self) -> str:
        return "NoSetup"


NoSetup: _NoSetupType = _NoSetupType()
NoSetupSentinel: TypeAlias = _NoSetupType
