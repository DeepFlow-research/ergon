# Adapted from pinned MAG source; see NOTICE and source-manifest.json.
"""
Brand Crisis Management & Reputation Recovery Demo
Real-world use case: Mid-market consumer goods company social media-driven reputation crisis.
Demonstrates:
- Crisis response coordination under extreme time pressure with incomplete information
- Multi-stakeholder communication orchestration across diverse groups
- Real-time adaptive strategy adjustment based on evolving situation dynamics
- Resource allocation prioritization during time-critical scenarios
- Cross-functional team coordination with varying expertise levels
- Timeline management with hard deadlines and cascading dependencies
"""

from ergon_builtins.benchmarks.manager_gym.scenarios.standard_rules import speed_rubric, cost_rubric
from math import exp
from ergon_builtins.benchmarks.manager_gym.source_types import Preference, PreferenceWeights
from ergon_builtins.benchmarks.manager_gym.source_types import Workflow
from ergon_builtins.benchmarks.manager_gym.source_types import WorkflowRubric, RunCondition
from ergon_builtins.benchmarks.manager_gym.source_types import Evaluator, AggregationStrategy
from ergon_builtins.benchmarks.manager_gym.source_types import PreferenceWeightUpdateRequest


def create_brand_crisis_management_preferences() -> PreferenceWeights:

    def _safe_hours(delta_seconds: float) -> float:
        return max(0.0, float(delta_seconds)) / 3600.0

    def _validate_cost_realism(workflow: Workflow, context) -> float:
        """Penalize unrealistic cost discrepancies for brand crisis management."""
        expected_min_cost = 50000.0
        total_estimated = sum(
            (task.estimated_cost for task in workflow.tasks.values() if task.estimated_cost)
        )
        total_actual = sum(
            (task.actual_cost for task in workflow.tasks.values() if task.actual_cost)
        )
        if total_estimated == 0:
            return 0.0
        if total_actual < expected_min_cost:
            return 0.0
        cost_variance = abs(total_actual - total_estimated) / total_estimated
        if cost_variance > 0.4:
            return 0.2
        elif cost_variance > 0.2:
            return 0.6
        else:
            return 1.0

    def _brand_crisis_adversarial_pressure_score(workflow: Workflow) -> float:
        """Score based on handling brand crisis adversarial pressure."""
        pressure_indicators = [
            "media attack",
            "viral criticism",
            "boycott threat",
            "influencer backlash",
            "regulatory scrutiny",
            "competitor exploitation",
            "employee revolt",
            "customer exodus",
            "legal action",
            "stakeholder pressure",
            "activist campaign",
            "reputation damage",
        ]
        pressure_handled = 0
        for indicator in pressure_indicators:
            for res in workflow.resources.values():
                if indicator.lower() in str(res.content or "").lower():
                    if any(
                        (
                            resolution.lower() in str(res.content or "").lower()
                            for resolution in [
                                "countered",
                                "addressed",
                                "managed",
                                "contained",
                                "neutralized",
                            ]
                        )
                    ):
                        pressure_handled += 1
                    break
        return min(1.0, pressure_handled / max(1, len(pressure_indicators) * 0.3))

    def crisis_response_timeliness(workflow: Workflow) -> float:
        """Reward rapid initial crisis response within critical 2-hour window (0..1)."""
        if workflow.started_at is None:
            return 0.0
        first_response_time = None
        for task in workflow.tasks.values():
            if any(
                (
                    keyword in task.name.lower()
                    for keyword in ["communication", "response", "assessment"]
                )
            ):
                if task.completed_at is not None:
                    if first_response_time is None or task.completed_at < first_response_time:
                        first_response_time = task.completed_at
        if first_response_time is None:
            return 0.0
        elapsed_h = _safe_hours((first_response_time - workflow.started_at).total_seconds())
        if elapsed_h <= 2.0:
            return 1.0
        elif elapsed_h <= 24.0:
            return exp(-0.5 * (elapsed_h - 2.0))
        else:
            return 0.1

    def stakeholder_engagement_coverage(workflow: Workflow) -> float:
        """Reward comprehensive stakeholder engagement across all key groups (0..1)."""
        stakeholder_keywords = {
            "customer": ["customer", "client", "consumer"],
            "media": ["media", "press", "journalist", "reporter"],
            "employee": ["employee", "staff", "internal", "workforce"],
            "investor": ["investor", "shareholder", "financial"],
            "partner": ["partner", "vendor", "supplier"],
            "regulator": ["regulatory", "compliance", "legal"],
        }
        engaged_groups = set()
        for res in workflow.resources.values():
            try:
                content = (res.content or "").lower()
                for group, keywords in stakeholder_keywords.items():
                    if any((keyword in content for keyword in keywords)):
                        engaged_groups.add(group)
            except Exception:
                continue
        return min(1.0, len(engaged_groups) / len(stakeholder_keywords))

    def message_consistency_tracking(workflow: Workflow) -> float:
        """Check for consistent messaging across channels by detecting contradictions (0..1)."""
        contradiction_flags = ["contradiction", "inconsistent", "conflicting", "different message"]
        total_messages = 0
        contradiction_count = 0
        for msg in workflow.messages:
            total_messages += 1
            try:
                content = msg.content.lower()
                if any((flag in content for flag in contradiction_flags)):
                    contradiction_count += 1
            except Exception:
                continue
        if total_messages == 0:
            return 0.5
        contradiction_ratio = contradiction_count / total_messages
        return exp(-3.0 * contradiction_ratio)

    def sentiment_recovery_progress(workflow: Workflow) -> float:
        """Track sentiment recovery through monitoring and improvement indicators (0..1)."""
        positive_indicators = [
            "sentiment improved",
            "positive feedback",
            "trust restored",
            "reputation recovery",
        ]
        negative_indicators = [
            "sentiment declined",
            "negative reaction",
            "backlash",
            "criticism increased",
        ]
        positive_count = 0
        negative_count = 0
        for res in workflow.resources.values():
            try:
                content = (res.content or "").lower()
                for indicator in positive_indicators:
                    if indicator in content:
                        positive_count += 1
                for indicator in negative_indicators:
                    if indicator in content:
                        negative_count += 1
            except Exception:
                continue
        total_sentiment_signals = positive_count + negative_count
        if total_sentiment_signals == 0:
            return 0.5
        return max(0.0, min(1.0, positive_count / total_sentiment_signals))

    def crisis_coordination_efficiency(workflow: Workflow) -> float:
        """Measure crisis team coordination through communication frequency and decision speed (0..1)."""
        coordination_keywords = [
            "team meeting",
            "decision made",
            "escalation",
            "coordination",
            "aligned",
        ]
        recent_messages = workflow.messages[-20:]
        if not recent_messages:
            return 0.0
        coordination_signals = 0
        for msg in recent_messages:
            try:
                content = msg.content.lower()
                if any((keyword in content for keyword in coordination_keywords)):
                    coordination_signals += 1
            except Exception:
                continue
        return min(1.0, coordination_signals / max(1, len(recent_messages)))

    def crisis_artifact_density(workflow: Workflow) -> float:
        """Reward having crisis response artifacts for completed tasks (0..1)."""
        completed = [t for t in workflow.tasks.values() if t.status.value == "completed"]
        if not completed:
            return 0.0
        total_outputs = 0
        for t in completed:
            total_outputs += len(t.output_resource_ids)
        avg_outputs = total_outputs / max(1, len(completed))
        return max(0.0, min(1.0, avg_outputs / 2.0))

    def legal_documentation_presence(workflow: Workflow) -> float:
        """Ensure legal documentation and risk mitigation measures are tracked (0..1)."""
        legal_keywords = [
            "legal review",
            "documentation",
            "compliance check",
            "risk assessment",
            "audit trail",
        ]
        total_legal_tasks = 0
        documented_tasks = 0
        for task in workflow.tasks.values():
            if any((keyword in task.name.lower() for keyword in legal_keywords)):
                total_legal_tasks += 1
                if len(task.output_resource_ids) > 0:
                    documented_tasks += 1
        if total_legal_tasks == 0:
            return 0.5
        return max(0.0, min(1.0, documented_tasks / total_legal_tasks))

    quality_rubrics = [
        WorkflowRubric(
            name="crisis_assessment_thoroughness",
            llm_prompt="Evaluate crisis assessment thoroughness. Award partial credit for:\n                (a) comprehensive situation analysis including scope and scale,\n                (b) stakeholder impact mapping with specific affected groups,\n                (c) financial impact quantification with projections,\n                (d) competitive and market positioning analysis.\n                Cite specific workflow resources/messages for evidence. Output a numeric score in [0, MAX].",
            max_score=10.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="messaging_framework_quality",
            llm_prompt="Assess messaging framework quality: (1) brand value alignment, (2) legal compliance,\n                (3) audience segmentation appropriateness, (4) consistency across channels.\n                Award equal partial credit. Cite evidence. Output numeric score [0, MAX].",
            max_score=8.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="stakeholder_communication_effectiveness",
            llm_prompt="Evaluate stakeholder communication effectiveness across customers, employees, media, investors, and partners.\n                Award partial credit for coverage, messaging appropriateness, and response quality. Output numeric score [0, MAX].",
            max_score=10.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="crisis_response_timeliness_measure",
            evaluator_function=crisis_response_timeliness,
            max_score=1.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="digital_reputation_recovery_depth",
            llm_prompt="Assess digital reputation recovery strategy depth: SEO optimization, positive content creation,\n                influencer engagement, review management, and social media presence improvement.\n                Partial credit across all dimensions. Output numeric score [0, MAX].",
            max_score=10.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="stakeholder_engagement_coverage_measure",
            evaluator_function=stakeholder_engagement_coverage,
            max_score=1.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="crisis_artifact_density_measure",
            evaluator_function=crisis_artifact_density,
            max_score=1.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
    ]
    compliance_rubrics = [
        WorkflowRubric(
            name="legal_risk_assessment_completeness",
            llm_prompt="Evaluate legal risk assessment completeness: litigation risk analysis, regulatory compliance review,\n                documentation requirements, and liability mitigation strategies. Award partial credit with citations.\n                Output numeric score [0, MAX].",
            max_score=10.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="regulatory_notification_compliance",
            llm_prompt="Assess regulatory notification compliance: required disclosures, timely filing, regulatory relationship management,\n                and compliance with industry-specific requirements. Output numeric score [0, MAX].",
            max_score=8.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="documentation_preservation_quality",
            llm_prompt="Evaluate documentation preservation quality: audit trail maintenance, evidence collection,\n                communication records, and litigation preparedness documentation. Output numeric score [0, MAX].",
            max_score=8.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="message_consistency_compliance",
            llm_prompt="Assess message consistency across all communication channels: social media, press releases, internal communications.\n                Penalize contradictions, reward alignment with brand values and crisis messaging framework. Output numeric score [0, MAX].",
            max_score=10.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="brand_voice_preservation",
            llm_prompt="Evaluate preservation of brand voice and values throughout crisis communications.\n                Assess authenticity, tone appropriateness, and alignment with established brand identity.\n                Output numeric score [0, MAX].",
            max_score=8.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="legal_documentation_presence_measure",
            evaluator_function=legal_documentation_presence,
            max_score=1.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="message_consistency_tracking_measure",
            evaluator_function=message_consistency_tracking,
            max_score=1.0,
            run_condition=RunCondition.EACH_TIMESTEP,
        ),
    ]
    governance_rubrics = [
        WorkflowRubric(
            name="crisis_team_activation_effectiveness",
            llm_prompt="Evaluate crisis team activation effectiveness: team assembly speed, role clarity, decision-making authority establishment,\n                and 24/7 response capability setup. Award partial credit across components. Output numeric score [0, MAX].",
            max_score=10.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="cross_functional_coordination_quality",
            llm_prompt="Assess cross-functional coordination quality: department integration, information flow,\n                decision synchronization, and conflict resolution effectiveness. Output numeric score [0, MAX].",
            max_score=8.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="escalation_management_effectiveness",
            llm_prompt="Evaluate escalation management effectiveness: clear escalation paths, timely decision-making,\n                authority delegation, and issue resolution tracking. Output numeric score [0, MAX].",
            max_score=8.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="stakeholder_relationship_preservation",
            llm_prompt="Assess stakeholder relationship preservation during crisis: customer retention efforts, employee morale management,\n                investor confidence maintenance, and partner relationship continuity. Output numeric score [0, MAX].",
            max_score=10.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="decision_documentation_quality",
            llm_prompt="Evaluate decision documentation quality and traceability: major decisions documented with rationale and approver,\n                linked to artifacts, and crisis response justification. Output numeric score [0, MAX].",
            max_score=6.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="crisis_coordination_efficiency_measure",
            evaluator_function=crisis_coordination_efficiency,
            max_score=1.0,
            run_condition=RunCondition.EACH_TIMESTEP,
        ),
    ]
    speed_rubrics = [
        WorkflowRubric(
            name="critical_timeline_adherence",
            llm_prompt="Evaluate adherence to critical crisis response timelines: 2-hour acknowledgment, 24-hour comprehensive response,\n                1-week strategy implementation. Award partial credit based on timeline compliance. Output numeric score [0, MAX].",
            max_score=10.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="decision_making_speed",
            llm_prompt="Assess decision-making speed under pressure: rapid assessment, quick approvals, \n                fast implementation, and agile strategy adjustments. Output numeric score [0, MAX].",
            max_score=8.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="speed_efficiency",
            evaluator_function=speed_rubric,
            max_score=1.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="crisis_response_timeliness_tracking",
            evaluator_function=crisis_response_timeliness,
            max_score=1.0,
            run_condition=RunCondition.EACH_TIMESTEP,
        ),
    ]
    cost_rubrics = [
        WorkflowRubric(
            name="cost_efficiency",
            evaluator_function=cost_rubric,
            max_score=1.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="crisis_budget_management",
            llm_prompt="Evaluate crisis budget management: cost containment within ±15% of annual marketing budget,\n                justification for expenses, and ROI optimization for crisis response investments.\n                Output numeric score [0, MAX].",
            max_score=8.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="compensation_program_cost_effectiveness",
            llm_prompt="Assess compensation program cost-effectiveness: program design efficiency, customer impact per dollar,\n                retention value optimization, and long-term ROI. Output numeric score [0, MAX].",
            max_score=6.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="resource_allocation_efficiency",
            llm_prompt="Evaluate resource allocation efficiency during crisis: priority-based allocation, expertise matching,\n                workload balancing, and capacity management. Output numeric score [0, MAX].",
            max_score=4.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="crisis_adversarial_scenarios",
            llm_prompt="Evaluate handling of brand crisis adversarial scenarios and escalations:\n                - shows preparation for media attacks and viral criticism campaigns\n                - demonstrates response to boycott threats and influencer backlash\n                - shows handling of regulatory scrutiny and competitor exploitation\n                - demonstrates preparation for employee revolt and customer exodus scenarios\n                - shows crisis escalation management and reputation damage containment\n                Score 0 if no adversarial scenarios addressed. Return score [0, 10].",
            max_score=10.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="cost_realism_validation",
            evaluator_function=_validate_cost_realism,
            max_score=1.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
    ]
    reputation_recovery_rubrics = [
        WorkflowRubric(
            name="sentiment_monitoring_system_quality",
            llm_prompt="Evaluate sentiment monitoring system quality: real-time tracking capability, platform coverage,\n                alert mechanisms, and response integration. Assess monitoring comprehensiveness and accuracy.\n                Output numeric score [0, MAX].",
            max_score=8.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="trust_rebuilding_strategy_depth",
            llm_prompt="Assess trust rebuilding strategy depth: community engagement initiatives, corporate responsibility programs,\n                transparency measures, and third-party validation efforts. Award partial credit across components.\n                Output numeric score [0, MAX].",
            max_score=10.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="brand_recovery_measurement_framework",
            llm_prompt="Evaluate brand recovery measurement framework: key metrics definition, tracking mechanisms,\n                third-party validation, and progress reporting systems. Output numeric score [0, MAX].",
            max_score=8.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="sentiment_recovery_progress_measure",
            evaluator_function=sentiment_recovery_progress,
            max_score=1.0,
            run_condition=RunCondition.EACH_TIMESTEP,
        ),
        WorkflowRubric(
            name="long_term_prevention_strategy",
            llm_prompt="Assess long-term crisis prevention strategy: lessons learned documentation, protocol updates,\n                training programs, and early warning systems. Evaluate preparedness improvement measures.\n                Output numeric score [0, MAX].",
            max_score=6.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
    ]
    return PreferenceWeights(
        preferences=[
            Preference(
                name="quality",
                weight=0.25,
                evaluator=Evaluator(
                    name="quality",
                    description="Measures the quality of the crisis response",
                    aggregation=AggregationStrategy.WEIGHTED_AVERAGE,
                    rubrics=quality_rubrics,
                ),
            ),
            Preference(
                name="compliance",
                weight=0.2,
                evaluator=Evaluator(
                    name="compliance",
                    description="Measures the compliance of the crisis response",
                    aggregation=AggregationStrategy.WEIGHTED_AVERAGE,
                    rubrics=compliance_rubrics,
                ),
            ),
            Preference(
                name="governance",
                weight=0.2,
                evaluator=Evaluator(
                    name="governance",
                    description="Measures the governance of the crisis response",
                    aggregation=AggregationStrategy.WEIGHTED_AVERAGE,
                    rubrics=governance_rubrics,
                ),
            ),
            Preference(
                name="speed",
                weight=0.15,
                evaluator=Evaluator(
                    name="speed",
                    description="Measures the speed of the crisis response",
                    aggregation=AggregationStrategy.WEIGHTED_AVERAGE,
                    rubrics=speed_rubrics,
                ),
            ),
            Preference(
                name="cost",
                weight=0.1,
                evaluator=Evaluator(
                    name="cost",
                    description="Measures the cost of the crisis response",
                    aggregation=AggregationStrategy.WEIGHTED_AVERAGE,
                    rubrics=cost_rubrics,
                ),
            ),
            Preference(
                name="reputation_recovery",
                weight=0.1,
                evaluator=Evaluator(
                    name="reputation_recovery",
                    description="Measures the reputation recovery of the crisis response",
                    aggregation=AggregationStrategy.WEIGHTED_AVERAGE,
                    rubrics=reputation_recovery_rubrics,
                ),
            ),
        ]
    )


def create_preference_update_requests() -> list[PreferenceWeightUpdateRequest]:
    """Return weight update requests for crisis → recovery dynamics."""
    timeline: dict[int, PreferenceWeights] = {
        0: PreferenceWeights(
            preferences=[
                Preference(name="quality", weight=0.3),
                Preference(name="compliance", weight=0.25),
                Preference(name="governance", weight=0.15),
                Preference(name="speed", weight=0.2),
                Preference(name="cost", weight=0.05),
                Preference(name="reputation_recovery", weight=0.05),
            ]
        ),
        5: PreferenceWeights(
            preferences=[
                Preference(name="quality", weight=0.25),
                Preference(name="compliance", weight=0.2),
                Preference(name="governance", weight=0.2),
                Preference(name="speed", weight=0.15),
                Preference(name="cost", weight=0.1),
                Preference(name="reputation_recovery", weight=0.1),
            ]
        ),
        15: PreferenceWeights(
            preferences=[
                Preference(name="quality", weight=0.2),
                Preference(name="compliance", weight=0.15),
                Preference(name="governance", weight=0.2),
                Preference(name="speed", weight=0.1),
                Preference(name="cost", weight=0.1),
                Preference(name="reputation_recovery", weight=0.25),
            ]
        ),
        25: PreferenceWeights(
            preferences=[
                Preference(name="quality", weight=0.15),
                Preference(name="compliance", weight=0.1),
                Preference(name="governance", weight=0.15),
                Preference(name="speed", weight=0.05),
                Preference(name="cost", weight=0.15),
                Preference(name="reputation_recovery", weight=0.4),
            ]
        ),
    }
    requests: list[PreferenceWeightUpdateRequest] = []
    for ts, weights in sorted(timeline.items(), key=lambda kv: kv[0]):
        changes = weights.get_preference_dict()
        if not changes:
            continue
        requests.append(
            PreferenceWeightUpdateRequest(
                timestep=ts,
                changes=changes,
                mode="absolute",
                normalize=True,
                clamp_zero=True,
                missing="create_zero",
                redistribution="proportional",
            )
        )
    return requests


def create_evaluator_to_measure_goal_achievement() -> Evaluator:
    """Create goal achievement evaluator for brand crisis management and reputation recovery."""
    goal_achievement_rubrics = [
        WorkflowRubric(
            name="crisis_assessment_completed",
            llm_prompt="Does comprehensive crisis assessment exist with: situation evaluation completed, stakeholder impact mapping documented, financial impact quantified, and real-time monitoring dashboard operational? Return true if crisis assessment is comprehensive and operational, false otherwise.",
            max_score=15.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="public_communication_launched",
            llm_prompt="Does launched public communication strategy exist with: coordinated messaging framework deployed, social media response active, press releases issued, and customer service protocols implemented? Return true if public communication is actively launched, false otherwise.",
            max_score=15.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="customer_sentiment_recovery_achieved",
            llm_prompt="Does customer sentiment recovery exist with: sentiment analysis showing >75% recovery to pre-crisis levels, social media sentiment shifted to neutral/positive, customer feedback trending positive, and engagement metrics improved? Return true if customer sentiment recovery is achieved, false otherwise.",
            max_score=12.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="media_coverage_balance_restored",
            llm_prompt="Does restored media coverage balance exist with: >60% neutral-to-positive articles achieved, factual inaccuracies corrected in major media, journalist relationships maintained, and narrative control established? Return true if media coverage balance is restored, false otherwise.",
            max_score=12.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="brand_trust_metrics_restored",
            llm_prompt="Do restored brand trust metrics exist with: independent third-party measurement showing >80% of pre-crisis baseline, trust tracking dashboard operational, customer confidence indicators positive, and reputation scores improved? Return true if brand trust metrics are restored, false otherwise.",
            max_score=10.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="customer_retention_maintained",
            llm_prompt="Does maintained customer retention exist with: >90% customer retention rate achieved, customer churn analysis completed, retention strategies implemented, and loyalty programs effective? Return true if customer retention is maintained, false otherwise.",
            max_score=10.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="digital_reputation_recovery_campaign",
            llm_prompt="Does digital reputation recovery campaign exist with: SEO optimization implemented, positive content created and published, influencer engagement active, and online review management operational? Return true if digital reputation recovery campaign is active, false otherwise.",
            max_score=8.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="internal_stakeholder_confidence_maintained",
            llm_prompt="Does maintained internal stakeholder confidence exist with: <5% employee turnover during crisis, internal communication program active, leadership messaging aligned, and morale monitoring positive? Return true if internal stakeholder confidence is maintained, false otherwise.",
            max_score=8.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="customer_service_enhancement",
            llm_prompt="Does customer service enhancement exist with: <24 hour resolution time for crisis-related inquiries, enhanced customer service protocols implemented, complaint management system operational, and satisfaction scores improved? Return true if customer service enhancement is operational, false otherwise.",
            max_score=8.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="crisis_team_activation_successful",
            llm_prompt="Does successful crisis team activation exist with: cross-functional team deployed, executive leadership engaged, 24/7 response capability established, and clear roles defined? Return true if crisis team activation is successful, false otherwise.",
            max_score=7.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="legal_regulatory_compliance_maintained",
            llm_prompt="Does maintained legal and regulatory compliance exist with: zero regulatory violations, legal risk assessment completed, documentation properly preserved, and regulatory notifications made? Return true if legal and regulatory compliance is maintained, false otherwise.",
            max_score=7.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="media_relations_strategy_executed",
            llm_prompt="Does executed media relations strategy exist with: interview preparation completed, journalist relationships managed, message consistency maintained, and proactive media engagement active? Return true if media relations strategy is executed, false otherwise.",
            max_score=6.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="compensation_program_implemented",
            llm_prompt="Does implemented compensation program exist with: customer compensation framework developed, affected customers identified and contacted, compensation disbursed, and satisfaction tracking active? Return true if compensation program is implemented, false otherwise.",
            max_score=6.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="community_engagement_initiatives",
            llm_prompt="Do community engagement initiatives exist with: corporate responsibility initiatives launched, community outreach programs active, trust rebuilding activities implemented, and stakeholder engagement positive? Return true if community engagement initiatives are active, false otherwise.",
            max_score=5.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="investor_relations_maintained",
            llm_prompt="Does maintained investor relations exist with: transparent communication provided, investor confidence preserved, board reporting completed, and financial impact communicated? Return true if investor relations are maintained, false otherwise.",
            max_score=5.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="crisis_response_protocols_updated",
            llm_prompt="Do updated crisis response protocols exist with: lessons learned documented, response effectiveness analyzed, improvement areas identified, and protocols updated for future preparedness? Return true if crisis response protocols are updated, false otherwise.",
            max_score=4.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="social_media_monitoring_operational",
            llm_prompt="Does operational social media monitoring exist with: real-time monitoring tools active, sentiment tracking implemented, platform-specific responses deployed, and engagement metrics tracked? Return true if social media monitoring is operational, false otherwise.",
            max_score=4.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
        WorkflowRubric(
            name="partner_stakeholder_coordination",
            llm_prompt="Does partner stakeholder coordination exist with: key partners notified and aligned, vendor relationships maintained, supplier communications managed, and business continuity ensured? Return true if partner stakeholder coordination is effective, false otherwise.",
            max_score=3.0,
            run_condition=RunCondition.ON_COMPLETION,
        ),
    ]
    return Evaluator(
        name="brand_crisis_goal_achievement_eval",
        description="Brand crisis management and reputation recovery deliverable achievement measurement",
        aggregation=AggregationStrategy.WEIGHTED_AVERAGE,
        rubrics=goal_achievement_rubrics,
    )
