"""Rubric version 2 corrects three upstream rubrics; version 1 leaves them as upstream wrote them."""

from ergon_builtins.benchmarks.manager_gym.rubric import definitions
from ergon_builtins.benchmarks.manager_gym.upstream import AdditionalContextItem


def _named(scenario: str, rubric_version: int) -> dict[str, list]:
    named: dict[str, list] = {}
    for d in definitions(scenario, rubric_version=rubric_version):
        named.setdefault(d.rubric.name, []).append(d)
    return named


def test_icaap_seeking_sourcing_is_dropped_only_in_version_2():
    assert "seeking_sourcing" in _named("icaap", 1)
    assert "seeking_sourcing" not in _named("icaap", 2)
    kept = {d.slug for d in definitions("icaap", rubric_version=2)}
    assert kept < {d.slug for d in definitions("icaap", rubric_version=1)}


def test_response_latency_maximum_matches_its_function_in_version_2():
    (v1,) = _named("orsa", 1)["response_latency_adherence"]
    (v2,) = _named("orsa", 2)["response_latency_adherence"]
    assert v1.rubric.max_score == 20 and v2.rubric.max_score == 8
    assert v1.slug == v2.slug


def test_agent_utilization_requests_agent_states_in_version_2():
    (v1,) = _named("orsa", 1)["agent_utilization_efficiency"]
    (v2,) = _named("orsa", 2)["agent_utilization_efficiency"]
    assert not v1.rubric.required_context
    assert v2.rubric.required_context == {AdditionalContextItem.AGENT_PUBLIC_STATES}
    assert "utilisation" in v2.rubric.description


def test_other_scenarios_keep_every_rubric_in_version_2():
    for scenario in ("orsa", "marketing_campaign", "legal_m_and_a"):
        assert {d.slug for d in definitions(scenario, rubric_version=1)} == {
            d.slug for d in definitions(scenario, rubric_version=2)
        }
