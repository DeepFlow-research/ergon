"""Stub backend: resolves ``stub:constant`` (and any ``stub:*``) to a fixed marker.

Used by zero-cost canary tests that want a syntactically valid, registered
``model_target`` but never call out to a real model. The returned
``ResolvedModel`` wraps a constant marker string so that any downstream
consumer (provenance, telemetry) has a total, deterministic value to observe
instead of leaking the raw ``stub:...`` string through to PydanticAI's
``infer_model`` (which would reject it).

Workers using this backend are expected not to pass ``.model`` to
``Agent(model=...)``; the stub path is a fixture, not a real inference path.
"""

from ergon_core.core.providers.generation.model_resolution import ResolvedModel

STUB_CONSTANT_RESPONSE = "CONSTANT_STUB_RESPONSE"
"""Fixed marker string returned as the resolved model.

Workers that ignore the resolved model (the canary case) never observe this;
it exists purely so that introspection of ``ResolvedModel.model`` returns a
stable, grep-able sentinel instead of the raw ``stub:...`` target.
"""


def resolve_stub(
    target: str,
    *,
    model_name: str | None = None,
    policy_version: str | None = None,
    api_key: str | None = None,
) -> ResolvedModel:
    """Resolve any ``stub:*`` target to a fixed-response stub marker.

    The ``target`` suffix is accepted and ignored — ``stub:constant``,
    ``stub:anything`` all resolve identically. ``supports_logprobs`` is
    ``False`` because no real generation takes place.
    """
    return ResolvedModel(
        model=STUB_CONSTANT_RESPONSE,
        policy_version=policy_version,
        supports_logprobs=False,
    )
