"""Config-time descriptor for a worker binding.

A ``WorkerSpec`` records *what kind of worker* an experiment wants and
*how it should be named / targeted at a model* — without requiring any of
the runtime identity (``task_id`` / ``sandbox_id``) that a live
``Worker`` instance needs to actually execute.

Rationale (RFC 2026-04-22, Open Question 1 resolution):

* ``Experiment`` is built once at config time, long before any task
  exists and any sandbox has been provisioned. Asking users to hand us a
  fully-constructed ``Worker`` there forces us to either make the
  identity fields optional (sentinel values like ``UUID(int=0)`` / ``""``
  leak into the runtime) or construct ``Worker`` instances twice (once
  config-side for the Experiment graph, once exec-side with real IDs).
* ``WorkerSpec`` is the honest type for the config layer: three fields,
  no runtime state, trivially serialisable, no registry plumbing. The
  registry factory is invoked exactly once — at ``worker_execute`` time,
  with the real ``task_id`` and ``sandbox_id`` — and the fresh ``Worker``
  lives only for the duration of that execution.

See also: ``ergon_core/api/worker.py`` for the execution-time ``Worker``
ABC (now requires ``task_id`` / ``sandbox_id`` at construction).
"""

from pydantic import BaseModel, ConfigDict


class WorkerSpec(BaseModel):
    """Immutable descriptor for a worker binding in an ``Experiment``.

    Attributes
    ----------
    worker_slug
        Registry key — must be present in ``ergon_builtins.registry.WORKERS``.
        Used at execute time to resolve the concrete ``Worker`` class or
        benchmark factory.
    name
        Binding key / instance name for the worker. Persisted into the
        definition snapshot and used as the binding key if the Experiment
        is constructed via ``Experiment.from_single_worker``.
    model
        Model target identifier (provider-qualified, e.g.
        ``"openai:gpt-4o"``). This is required at the experiment composition
        boundary so persisted definitions are fully explicit. Workers that
        do not call an LLM still receive the configured model target; they
        can ignore it at execution time.
    """

    # reason: project standard (slopcop `no-dataclass`) is Pydantic BaseModel;
    # frozen=True preserves the dataclass-style immutability we want.
    model_config = ConfigDict(frozen=True)

    worker_slug: str
    name: str
    model: str

    def validate_spec(self) -> None:
        """Check that ``worker_slug`` refers to a known registry entry.

        Kept deliberately lightweight — model-target validation happens
        at execution time inside the generation providers, and name
        validation is structural (any non-empty string works).

        Named ``validate_spec`` (not ``validate``) to avoid shadowing
        ``pydantic.BaseModel.validate`` (deprecated but still present).
        """
        # Deferred: avoid import cycle — ergon_builtins imports ergon_core.api.
        from ergon_builtins.registry import WORKERS

        if self.worker_slug not in WORKERS:
            known = ", ".join(sorted(WORKERS))
            raise ValueError(
                f"Unknown worker slug {self.worker_slug!r}; registered workers: {known}"
            )
        if not self.name:
            raise ValueError("WorkerSpec.name must be a non-empty string")
        if not self.model:
            raise ValueError("WorkerSpec.model must be a non-empty string")
