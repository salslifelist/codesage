"""Focused tests for the deterministic maintainability-improvement gate."""

from __future__ import annotations

from codesage.comparison import (
    DescriptiveStatus,
    DirectionalStatus,
    MetricComparison,
    ScriptComparison,
    evaluate_maintainability_improvement,
)

TARGET = "focused"


def directional(metric, before, after, status):
    return MetricComparison(TARGET, metric, before, after, status)


def descriptive(metric, before, after, status):
    return MetricComparison(TARGET, metric, before, after, status)


def comparison(
    *,
    directional_items=(),
    descriptive_items=(),
    smells_introduced=(),
    smells_removed=(),
):
    return ScriptComparison(
        directional=tuple(directional_items),
        descriptive=tuple(descriptive_items),
        structural=(),
        smells_introduced=tuple(smells_introduced),
        smells_removed=tuple(smells_removed),
        warnings=(),
    )


def resolved_smell_metric(code, *, before=1, after=0, status=DirectionalStatus.IMPROVED):
    return directional(f"smell.{code}", before, after, status)


def unresolved_reviewed_smell(reviewed):
    """A baseline comparison where every listed reviewed smell is fully resolved."""
    return comparison(
        directional_items=[resolved_smell_metric(code) for _, code in reviewed],
    )


def test_accepted_when_reviewed_smell_is_resolved_and_nothing_regresses():
    reviewed = ((TARGET, "deep_nesting"),)
    decision = evaluate_maintainability_improvement(
        unresolved_reviewed_smell(reviewed), (TARGET,), reviewed
    )
    assert decision.accepted
    assert decision.failure_codes == ()
    assert any("deep nesting" in item for item in decision.improvements)


def test_accepted_when_nesting_improves_and_reviewed_smell_resolves():
    reviewed = ((TARGET, "deep_nesting"),)
    base = comparison(
        directional_items=[
            resolved_smell_metric("deep_nesting"),
            directional("nesting_depth", 5, 2, DirectionalStatus.IMPROVED),
            directional("complexity", 5, 5, DirectionalStatus.UNCHANGED),
        ]
    )
    decision = evaluate_maintainability_improvement(base, (TARGET,), reviewed)
    assert decision.accepted
    assert any("Nesting depth decreased" in item for item in decision.improvements)


def test_rejects_when_a_reviewed_smell_remains():
    reviewed = ((TARGET, "deep_nesting"),)
    base = comparison(
        directional_items=[directional("smell.deep_nesting", 1, 1, DirectionalStatus.UNCHANGED)]
    )
    decision = evaluate_maintainability_improvement(base, (TARGET,), reviewed)
    assert not decision.accepted
    assert "reviewed_finding_remaining" in decision.failure_codes


def test_rejects_when_complexity_increases():
    reviewed = ((TARGET, "deep_nesting"),)
    base = comparison(
        directional_items=[
            resolved_smell_metric("deep_nesting"),
            directional("complexity", 5, 6, DirectionalStatus.REGRESSED),
        ]
    )
    decision = evaluate_maintainability_improvement(base, (TARGET,), reviewed)
    assert not decision.accepted
    assert "complexity_regressed" in decision.failure_codes
    assert any("increased from 5 to 6" in item for item in decision.regressions)


def test_rejects_when_nesting_increases():
    reviewed = ((TARGET, "deep_nesting"),)
    base = comparison(
        directional_items=[
            resolved_smell_metric("deep_nesting"),
            directional("nesting_depth", 4, 5, DirectionalStatus.REGRESSED),
        ]
    )
    decision = evaluate_maintainability_improvement(base, (TARGET,), reviewed)
    assert not decision.accepted
    assert "nesting_regressed" in decision.failure_codes


def test_rejects_when_parameter_count_increases():
    reviewed = ((TARGET, "too_many_parameters"),)
    base = comparison(
        directional_items=[resolved_smell_metric("too_many_parameters")],
        descriptive_items=[descriptive("parameter_count", 5, 6, DescriptiveStatus.INCREASED)],
    )
    decision = evaluate_maintainability_improvement(base, (TARGET,), reviewed)
    assert not decision.accepted
    assert "parameter_count_increased" in decision.failure_codes


def test_accepts_when_parameter_count_is_unchanged():
    reviewed = ((TARGET, "deep_nesting"),)
    base = comparison(
        directional_items=[resolved_smell_metric("deep_nesting")],
        descriptive_items=[descriptive("parameter_count", 2, 2, DescriptiveStatus.UNCHANGED)],
    )
    decision = evaluate_maintainability_improvement(base, (TARGET,), reviewed)
    assert decision.accepted


def test_rejects_when_a_new_smell_is_introduced():
    reviewed = ((TARGET, "deep_nesting"),)
    base = comparison(
        directional_items=[resolved_smell_metric("deep_nesting")],
        smells_introduced=(f"{TARGET}:bare_exception",),
    )
    decision = evaluate_maintainability_improvement(base, (TARGET,), reviewed)
    assert not decision.accepted
    assert "new_smell_introduced" in decision.failure_codes
    assert any("bare_exception" in item for item in decision.regressions)


def test_accepts_when_no_new_smell_appears():
    reviewed = ((TARGET, "deep_nesting"),)
    base = comparison(directional_items=[resolved_smell_metric("deep_nesting")])
    decision = evaluate_maintainability_improvement(base, (TARGET,), reviewed)
    assert decision.accepted
    assert decision.failure_codes == ()


def test_rejects_when_severity_smell_count_increases():
    reviewed = ((TARGET, "deep_nesting"),)
    base = comparison(
        directional_items=[
            resolved_smell_metric("deep_nesting"),
            directional("high_severity_smell_count", 1, 2, DirectionalStatus.REGRESSED),
        ]
    )
    decision = evaluate_maintainability_improvement(base, (TARGET,), reviewed)
    assert not decision.accepted
    assert "severity_count_regressed" in decision.failure_codes


def test_rejects_when_no_measurable_improvement_is_recorded():
    base = comparison(
        directional_items=[
            directional("complexity", 3, 3, DirectionalStatus.UNCHANGED),
            directional("nesting_depth", 2, 2, DirectionalStatus.UNCHANGED),
        ]
    )
    decision = evaluate_maintainability_improvement(base, (TARGET,), ())
    assert not decision.accepted
    assert "no_measurable_improvement" in decision.failure_codes


def test_rejects_when_a_target_comparison_is_unresolved():
    reviewed = ((TARGET, "deep_nesting"),)
    base = comparison(
        directional_items=[
            resolved_smell_metric("deep_nesting"),
            directional("complexity", 5, None, DirectionalStatus.UNRESOLVED),
        ]
    )
    decision = evaluate_maintainability_improvement(base, (TARGET,), reviewed)
    assert not decision.accepted
    assert "target_comparison_unresolved" in decision.failure_codes


def test_no_target_metric_is_unresolved_is_a_requirement_for_acceptance():
    reviewed = ((TARGET, "deep_nesting"),)
    base = comparison(
        directional_items=[
            resolved_smell_metric("deep_nesting"),
            directional("nesting_depth", 5, 3, DirectionalStatus.IMPROVED),
        ]
    )
    decision = evaluate_maintainability_improvement(base, (TARGET,), reviewed)
    assert decision.accepted


def test_rejects_when_one_of_multiple_reviewed_findings_remains():
    reviewed = ((TARGET, "deep_nesting"), (TARGET, "mutable_default"))
    base = comparison(
        directional_items=[
            resolved_smell_metric("deep_nesting"),
            directional("smell.mutable_default", 1, 1, DirectionalStatus.UNCHANGED),
        ]
    )
    decision = evaluate_maintainability_improvement(base, (TARGET,), reviewed)
    assert not decision.accepted
    assert "reviewed_finding_remaining" in decision.failure_codes
    assert any("deep nesting" in item for item in decision.improvements)
    assert any("mutable default" in item for item in decision.regressions)


def test_decision_never_exposes_a_proprietary_aggregate_score():
    decision = evaluate_maintainability_improvement(comparison(), (TARGET,), ())
    assert not hasattr(decision, "score")
    assert not hasattr(decision, "overall_verdict")
