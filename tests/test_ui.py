from __future__ import annotations

import inspect
import tomllib
from dataclasses import asdict, replace
from datetime import datetime, timezone
from pathlib import Path

import pytest

import app
from codesage.ai import (
    ApiErrorDetail,
    CandidateVerification,
    CoachMessage,
    CoachResult,
    CorrectionStatus,
    Finding,
    GroundingCorrectionStatus,
    RefactorAvailabilityStatus,
    RefactorResult,
    ReviewOutcome,
    ReviewResponse,
    ReviewResult,
    refactor_availability,
)
from codesage.analysis import analyse_script
from codesage.comparison import compare_scripts
from codesage.config import COACH_MESSAGE_CHARACTER_LIMIT, PRINT_COMPLETE_SOURCE_CHARACTER_LIMIT
from codesage.evidence import THRESHOLDS, build_evidence_package
from codesage.models import Severity, Smell
from codesage.source import (
    SourceOrigin,
    normalise_example_source,
    normalise_pasted_source,
)
from codesage.ui import (
    ALTERNATIVE_REFACTOR_ERROR_KEY,
    ANALYSIS_KEY,
    COACH_CHAT_CONTEXT_KEY,
    COACH_CHAT_ERROR_KEY,
    COACH_CHAT_KEY,
    EXAMPLE_MODE,
    FAILURE_MESSAGES,
    REFACTOR_ERROR_KEY,
    REFACTOR_KEY,
    RefactorResultState,
    REVIEW_ERROR_KEY,
    REVIEW_KEY,
    SOURCE_MODE_KEY,
    SOURCE_KEY,
    analysis_summary,
    clear_coach_chat,
    classify_refactor_result,
    coach_starter_questions,
    failure_message,
    handle_actions,
    handle_coach_chat_action,
    handle_refactor_action,
    invalidate_stale_state,
    load_example,
    readable_outcome,
    readable_smell,
    readable_source_reference,
    refactor_action_label,
    refactor_outcome_summary,
    source_summary,
    unit_inventory_rows,
    workflow_statuses,
)


@pytest.fixture(autouse=True)
def _authorise_existing_ui_scenarios(monkeypatch):
    """Keep established UI tests focused on behaviour beyond the separately tested gate."""
    monkeypatch.setattr(app, "render_judge_ai_access", lambda state, configuration=None: True)
    monkeypatch.setattr(app, "ai_access_is_granted", lambda state, configuration=None: True)


def hotspot_source(name="focused"):
    return f"def {name}(value=[]):\n    return value\n"


def successful_review(source, outcome=ReviewOutcome.REFACTOR_RECOMMENDED):
    analysis = analyse_script(source)
    evidence = build_evidence_package(analysis)
    item = next(
        (item for item in evidence.items if item.fact.startswith("smell.")),
        evidence.items[0],
    )
    findings = []
    if outcome is ReviewOutcome.REFACTOR_RECOMMENDED:
        findings = [
            Finding(
                title="Mutable default",
                category="maintainability",
                priority="medium",
                source_reference=item.source_reference,
                evidence_ids=[item.evidence_id],
                explanation="The measured result identifies a mutable default.",
                recommendation="Initialise a new list inside the function.",
                learning_takeaway="Defaults are created once.",
                uncertainty="Runtime use was not observed.",
            )
        ]
    response = ReviewResponse(
        outcome=outcome,
        summary="Evidence-based review.",
        findings=findings,
        suggested_tests=["Run existing tests."],
    )
    return ReviewResult(analysis, evidence, response, None, None, True)


def choose_priority_item_review(outcome=ReviewOutcome.REFACTOR_RECOMMENDED):
    source = """def choose_priority_item(values=[]):
    for value in values:
        if value:
            if isinstance(value, int):
                if value > 0:
                    if value % 2:
                        return value
    return None
"""
    analysis = analyse_script(source)
    unit = next(item for item in analysis.units if item.qualified_name == "choose_priority_item")
    unit = replace(
        unit,
        sloc=10,
        nesting_depth=5,
        complexity=6,
        complexity_rank="B",
        smells=(
            Smell("deep_nesting", Severity.HIGH, "Measured nesting depth 5."),
            Smell("mutable_default", Severity.MEDIUM, "Measured mutable default."),
        ),
    )
    analysis = replace(
        analysis,
        units=tuple(
            unit if item.qualified_name == "choose_priority_item" else item
            for item in analysis.units
        ),
        hotspots=(unit,),
    )
    evidence = build_evidence_package(analysis)
    smell_items = [
        item
        for item in evidence.items
        if item.source_reference == f"{unit.key}@L{unit.line}-L{unit.end_line}"
        and item.fact in {"smell.deep_nesting", "smell.mutable_default"}
    ]
    findings = []
    if outcome is ReviewOutcome.REFACTOR_RECOMMENDED:
        findings = [
            Finding(
                title="Nested selection with shared mutable state",
                category="maintainability",
                priority="high",
                source_reference=smell_items[0].source_reference,
                evidence_ids=[item.evidence_id for item in smell_items],
                explanation="The measured nesting and mutable default obscure the flow.",
                recommendation="Use a sentinel default and simplify the nested conditions.",
                learning_takeaway="Focused changes can make control flow easier to inspect.",
                uncertainty="Runtime behaviour was not observed.",
            )
        ]
    response = ReviewResponse(
        outcome=outcome,
        summary=(
            "Refactoring is recommended."
            if outcome is ReviewOutcome.REFACTOR_RECOMMENDED
            else "No targeted refactor is recommended."
        ),
        findings=findings,
        suggested_tests=["Exercise empty, odd and even input values."],
    )
    return source, ReviewResult(analysis, evidence, response, None, None, True)


def valid_refactor(source, review, replacement):
    candidate_analysis = analyse_script(replacement)
    verification = CandidateVerification(
        character_limit=5000,
        character_count=len(replacement),
        syntax_valid=True,
        syntax_error=None,
        analysis=candidate_analysis,
        comparison=compare_scripts(review.original_analysis, candidate_analysis),
        non_equivalence_notice="Static comparison does not establish behavioural equivalence.",
    )
    return RefactorResult(
        review.original_analysis,
        review.evidence,
        review.response,
        replacement,
        verification,
        None,
        None,
        CorrectionStatus.NOT_NEEDED,
        True,
        False,
    )


def reviewed_issue_refactor(*, addressed: int, unresolved: bool = False):
    original_source = "def focused(values=[]):\n    return values\n"
    original = analyse_script(original_source)
    original_unit = next(unit for unit in original.units if unit.qualified_name == "focused")
    original_unit = replace(
        original_unit,
        complexity=6,
        nesting_depth=5,
        smells=(
            Smell("deep_nesting", Severity.HIGH, "Measured deep nesting."),
            Smell("mutable_default", Severity.MEDIUM, "Measured mutable default."),
        ),
    )
    original = replace(
        original,
        units=tuple(
            original_unit if unit.qualified_name == "focused" else unit for unit in original.units
        ),
        hotspots=(original_unit,),
    )
    evidence = build_evidence_package(original)
    target_reference = next(
        item.source_reference for item in evidence.items if item.fact == "smell.deep_nesting"
    )
    evidence_ids = [
        item.evidence_id
        for item in evidence.items
        if item.source_reference == target_reference and item.fact.startswith("smell.")
    ]
    finding = Finding(
        title="Reviewed issues",
        category="maintainability",
        priority="high",
        source_reference=target_reference,
        evidence_ids=evidence_ids,
        explanation="Two measured issues were reviewed.",
        recommendation="Make a focused change.",
        learning_takeaway="Compare each issue separately.",
        uncertainty="Static evidence only.",
    )
    response = ReviewResponse(
        outcome=ReviewOutcome.REFACTOR_RECOMMENDED,
        summary="Review summary.",
        findings=[finding],
    )
    candidate_source = "def focused(values=None):\n    return values\n"
    candidate = analyse_script(candidate_source)
    candidate_unit = next(unit for unit in candidate.units if unit.qualified_name == "focused")
    remaining_smells = (
        original_unit.smells
        if addressed == 0
        else (original_unit.smells[0],)
        if addressed == 1
        else ()
    )
    candidate_unit = replace(
        candidate_unit,
        complexity=7,
        nesting_depth=None if unresolved else (4 if addressed < 2 else 3),
        smells=remaining_smells,
    )
    candidate = replace(
        candidate,
        units=tuple(
            candidate_unit if unit.qualified_name == "focused" else unit for unit in candidate.units
        ),
    )
    comparison = compare_scripts(original, candidate)
    verification = CandidateVerification(
        character_limit=5_000,
        character_count=len(candidate_source),
        syntax_valid=True,
        syntax_error=None,
        analysis=candidate,
        comparison=comparison,
        non_equivalence_notice="Static comparison does not establish behavioural equivalence.",
        target_names=("focused",),
    )
    return RefactorResult(
        original,
        evidence,
        response,
        candidate_source,
        verification,
        None,
        None,
    )


def failed_refactor(review):
    return RefactorResult(
        review.original_analysis,
        review.evidence,
        review.response,
        None,
        None,
        "refactor_verification_failed",
        "Could not verify.",
        CorrectionStatus.FAILED,
        True,
        True,
    )


def abstained_refactor(review, reason="No better targeted option was identified."):
    return RefactorResult(
        review.original_analysis,
        review.evidence,
        review.response,
        None,
        None,
        None,
        None,
        abstained=True,
        decision_reason=reason,
    )


def test_review_requires_explicit_action_and_is_cached():
    source = hotspot_source()
    state = {}
    calls = []

    def reviewer(current_source, analysis):
        calls.append(current_source)
        return successful_review(current_source)

    handle_actions(state, source, analyse_clicked=True, review_clicked=False, reviewer=reviewer)
    handle_actions(state, source, analyse_clicked=False, review_clicked=False, reviewer=reviewer)
    assert calls == []
    handle_actions(state, source, analyse_clicked=False, review_clicked=True, reviewer=reviewer)
    handle_actions(state, source, analyse_clicked=False, review_clicked=True, reviewer=reviewer)
    assert calls == [source]
    assert REVIEW_KEY in state


def test_ten_distinct_sources_are_not_blocked_by_session_quota():
    state = {}
    calls = []

    def reviewer(current_source, analysis):
        calls.append(current_source)
        return successful_review(current_source)

    for number in range(10):
        source = hotspot_source(f"focused_{number}")
        handle_actions(state, source, analyse_clicked=True, review_clicked=False, reviewer=reviewer)
        assert (
            handle_actions(
                state, source, analyse_clicked=False, review_clicked=True, reviewer=reviewer
            )
            is None
        )
    assert len(calls) == 10


def test_multiple_sources_can_each_generate_refactors_without_a_session_limit():
    state = {}
    review_calls = []
    refactor_calls = []

    def reviewer(current_source, analysis):
        review_calls.append(current_source)
        return successful_review(current_source)

    def refactorer(current_source, analysis, review, **kwargs):
        refactor_calls.append(current_source)
        name = next(
            unit.qualified_name for unit in analysis.units if unit.qualified_name != "<module>"
        )
        replacement = f"def {name}(value=None):\n    return value\n"
        return valid_refactor(current_source, review, replacement)

    for number in range(4):
        source = hotspot_source(f"refactor_{number}")
        handle_actions(state, source, analyse_clicked=True, review_clicked=False, reviewer=reviewer)
        handle_actions(state, source, analyse_clicked=False, review_clicked=True, reviewer=reviewer)
        handle_refactor_action(
            state,
            source,
            refactor_clicked=True,
            optional_instructions="",
            refactorer=refactorer,
        )

    assert len(review_calls) == 4
    assert len(refactor_calls) == 4


def test_source_change_invalidates_analysis_review_and_refactor():
    source = hotspot_source()
    review = successful_review(source)
    state = {
        ANALYSIS_KEY: review.original_analysis,
        REVIEW_KEY: review,
        REFACTOR_KEY: valid_refactor(
            source, review, "def focused(value=None):\n    return value\n"
        ),
    }
    invalidate_stale_state(state, normalise_pasted_source(hotspot_source("changed")))
    assert ANALYSIS_KEY not in state
    assert REVIEW_KEY not in state
    assert REFACTOR_KEY not in state


def test_source_origin_change_invalidates_results_even_when_text_is_identical():
    source = hotspot_source()
    review = successful_review(source)
    pasted = normalise_pasted_source(source)
    uploaded = replace(
        pasted,
        origin=__import__("codesage.source", fromlist=["SourceOrigin"]).SourceOrigin.UPLOADED,
        display_name="module.py",
    )
    state = {ANALYSIS_KEY: review.original_analysis, REVIEW_KEY: review}
    state["active_source_document"] = pasted
    invalidate_stale_state(state, uploaded)
    assert ANALYSIS_KEY not in state
    assert REVIEW_KEY not in state


def test_loading_and_analysing_example_invalidates_stale_state_without_ai_call():
    previous = hotspot_source("previous")
    previous_review = successful_review(previous)
    state = {
        ANALYSIS_KEY: previous_review.original_analysis,
        REVIEW_KEY: previous_review,
    }
    calls = []

    document = load_example(state)

    assert document == normalise_example_source()
    assert state[SOURCE_KEY] == document
    assert SOURCE_MODE_KEY not in state
    assert ANALYSIS_KEY not in state
    assert REVIEW_KEY not in state
    handle_actions(
        state,
        document,
        analyse_clicked=True,
        review_clicked=False,
        reviewer=lambda *args, **kwargs: calls.append(True),
    )
    assert state[ANALYSIS_KEY].syntax_valid
    assert state[ANALYSIS_KEY].hotspots[0].qualified_name == "choose_next_delivery"
    assert calls == []


def test_refactor_is_explicit_and_identical_completed_request_is_cached():
    source = hotspot_source()
    review = successful_review(source)
    state = {ANALYSIS_KEY: review.original_analysis, REVIEW_KEY: review}
    calls = []

    def refactorer(current_source, analysis, current_review, **kwargs):
        calls.append((current_source, kwargs["optional_instructions"]))
        return valid_refactor(source, review, "def focused(value=None):\n    return value\n")

    handle_refactor_action(
        state,
        source,
        refactor_clicked=False,
        optional_instructions="",
        refactorer=refactorer,
    )
    assert calls == []
    for _ in range(2):
        handle_refactor_action(
            state,
            source,
            refactor_clicked=True,
            optional_instructions="small change",
            refactorer=refactorer,
        )
    assert calls == [(source, "small change")]


def test_changed_instructions_replace_only_refactor_and_do_not_rerun_review():
    source = hotspot_source()
    review = successful_review(source)
    old = valid_refactor(source, review, "def focused(value=None):\n    return value\n")
    state = {ANALYSIS_KEY: review.original_analysis, REVIEW_KEY: review, REFACTOR_KEY: old}
    calls = []

    def refactorer(*args, **kwargs):
        calls.append(kwargs["optional_instructions"])
        return valid_refactor(
            source, review, "def focused(value=None):\n    return list(value or [])\n"
        )

    handle_refactor_action(
        state,
        source,
        refactor_clicked=True,
        optional_instructions="Prefer a small expression.",
        refactorer=refactorer,
    )
    assert calls == ["Prefer a small expression."]
    assert state[REVIEW_KEY] is review
    assert state[REFACTOR_KEY] is not old


def test_failed_alternative_preserves_previous_valid_refactor():
    source = hotspot_source()
    review = successful_review(source)
    old = valid_refactor(source, review, "def focused(value=None):\n    return value\n")
    state = {ANALYSIS_KEY: review.original_analysis, REVIEW_KEY: review, REFACTOR_KEY: old}
    handle_refactor_action(
        state,
        source,
        refactor_clicked=True,
        optional_instructions="Different approach.",
        refactorer=lambda *args, **kwargs: failed_refactor(review),
    )
    assert state[REFACTOR_KEY] is old
    assert REFACTOR_ERROR_KEY not in state
    assert state[ALTERNATIVE_REFACTOR_ERROR_KEY].error_code == "refactor_verification_failed"


def test_failed_initial_refactor_stores_error_key_with_no_refactor_key():
    source = hotspot_source()
    review = successful_review(source)
    state = {ANALYSIS_KEY: review.original_analysis, REVIEW_KEY: review}

    handle_refactor_action(
        state,
        source,
        refactor_clicked=True,
        optional_instructions="",
        refactorer=lambda *args, **kwargs: failed_refactor(review),
    )

    assert REFACTOR_KEY not in state
    assert state[REFACTOR_ERROR_KEY].error_code == "refactor_verification_failed"
    assert ALTERNATIVE_REFACTOR_ERROR_KEY not in state


def test_successful_alternative_replaces_refactor_key_and_clears_both_error_keys():
    source = hotspot_source()
    review = successful_review(source)
    old = valid_refactor(source, review, "def focused(value=None):\n    return value\n")
    new = valid_refactor(source, review, "def focused(value=None):\n    return list(value or [])\n")
    state = {
        ANALYSIS_KEY: review.original_analysis,
        REVIEW_KEY: review,
        REFACTOR_KEY: old,
        REFACTOR_ERROR_KEY: object(),
        ALTERNATIVE_REFACTOR_ERROR_KEY: object(),
    }

    handle_refactor_action(
        state,
        source,
        refactor_clicked=True,
        optional_instructions="A distinct approach.",
        refactorer=lambda *args, **kwargs: new,
    )

    assert state[REFACTOR_KEY] is new
    assert REFACTOR_ERROR_KEY not in state
    assert ALTERNATIVE_REFACTOR_ERROR_KEY not in state


def test_alternative_request_receives_the_previous_suggested_refactor():
    source = hotspot_source()
    review = successful_review(source)
    old = valid_refactor(source, review, "def focused(value=None):\n    return value\n")
    state = {ANALYSIS_KEY: review.original_analysis, REVIEW_KEY: review, REFACTOR_KEY: old}
    received = {}

    def refactorer(current_source, analysis, current_review, **kwargs):
        received.update(kwargs)
        return valid_refactor(
            current_source, current_review, "def focused(value=None):\n    return []\n"
        )

    handle_refactor_action(
        state,
        source,
        refactor_clicked=True,
        optional_instructions="A distinct approach.",
        refactorer=refactorer,
    )

    assert received.get("previous_suggestion") == old.suggested_refactor


def test_source_change_and_reanalysis_clear_both_error_keys():
    source = hotspot_source()
    review = successful_review(source)
    state = {
        SOURCE_KEY: normalise_pasted_source(source),
        ANALYSIS_KEY: review.original_analysis,
        REVIEW_KEY: review,
        REFACTOR_KEY: valid_refactor(
            source, review, "def focused(value=None):\n    return value\n"
        ),
        REFACTOR_ERROR_KEY: object(),
        ALTERNATIVE_REFACTOR_ERROR_KEY: object(),
    }

    invalidate_stale_state(state, normalise_pasted_source(hotspot_source("changed")))

    assert REFACTOR_KEY not in state
    assert REFACTOR_ERROR_KEY not in state
    assert ALTERNATIVE_REFACTOR_ERROR_KEY not in state

    state = {
        SOURCE_KEY: normalise_pasted_source(source),
        ANALYSIS_KEY: review.original_analysis,
        REVIEW_KEY: review,
        REFACTOR_KEY: valid_refactor(
            source, review, "def focused(value=None):\n    return value\n"
        ),
        REFACTOR_ERROR_KEY: object(),
        ALTERNATIVE_REFACTOR_ERROR_KEY: object(),
    }
    handle_actions(state, source, analyse_clicked=True, review_clicked=False)
    assert REFACTOR_ERROR_KEY not in state
    assert ALTERNATIVE_REFACTOR_ERROR_KEY not in state


def test_non_recommending_review_blocks_refactor():
    source = hotspot_source()
    review = successful_review(source, ReviewOutcome.NO_REFACTOR_NEEDED)
    state = {ANALYSIS_KEY: review.original_analysis, REVIEW_KEY: review}
    calls = []
    message = handle_refactor_action(
        state,
        source,
        refactor_clicked=True,
        optional_instructions="",
        refactorer=lambda *args, **kwargs: calls.append(True),
    )
    assert message == "The AI review did not recommend a targeted refactor."
    assert calls == []


def test_locally_ineligible_review_actions_make_no_model_call():
    calls = []

    def reviewer(*args, **kwargs):
        calls.append(True)

    invalid = "def broken(:\n"
    state = {}
    handle_actions(state, invalid, analyse_clicked=True, review_clicked=False, reviewer=reviewer)
    assert (
        handle_actions(
            state, invalid, analyse_clicked=False, review_clicked=True, reviewer=reviewer
        )
        == "Fix the syntax error before requesting AI review."
    )

    oversized = "#" + ("a" * 100_000) + "\n"
    handle_actions(state, oversized, analyse_clicked=True, review_clicked=False, reviewer=reviewer)
    message = handle_actions(
        state, oversized, analyse_clicked=False, review_clicked=True, reviewer=reviewer
    )
    assert "exceeds the tested AI-review limit" in message
    assert calls == []


def test_summary_and_inventory_preserve_measurements():
    analysis = analyse_script(
        "class Box:\n    def get(self):\n        return 1\n\ndef add(a, b):\n    return a + b\n"
    )
    summary = analysis_summary(analysis, ai_eligible=True)
    assert summary["Functions"] == 1
    assert summary["Methods"] == 1
    assert summary["Classes"] == 1
    assert summary["Analysable units"] == len(analysis.units)
    rows = unit_inventory_rows(analysis)
    assert len(rows) == len(analysis.units)
    assert all(value != "NULL" for row in rows for value in row.values())


def test_source_summary_is_readable_and_technical_metadata_is_collapsed(monkeypatch):
    document = normalise_example_source()
    assert source_summary(document) == (
        f"Built-in example · {len(document.text):,} characters · AI review available"
    )
    recorder = install_recorder(monkeypatch)

    app.render_source_summary(document)

    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    captions = [args[0] for name, args, kwargs in recorder.calls if name == "caption"]
    text_values = [args[0] for name, args, kwargs in recorder.calls if name == "text"]
    assert "**Active source**" in markdown
    assert document.display_name in text_values
    assert source_summary(document) in captions
    assert ("Source technical details", False) in recorder.expanders
    assert not any(
        name == "write" and args and isinstance(args[0], dict)
        for name, args, kwargs in recorder.calls
    )


def test_workflow_indicator_uses_three_approved_stages(monkeypatch):
    document = normalise_example_source()
    state = {}
    assert workflow_statuses(state) == ("Current", "After valid analysis", "After AI review")
    handle_actions(state, document, analyse_clicked=True, review_clicked=False)
    assert workflow_statuses(state) == (
        "Complete",
        "Optional AI review available",
        "After AI review",
    )
    recorder = install_recorder(monkeypatch)

    app.render_workflow(state)

    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    assert "**Workflow progress**" in markdown
    assert {
        "**1 · Analyse**",
        "**2 · Understand**",
        "**3 · Refactor**",
    } <= set(markdown)
    assert any("Complete" in item for item in markdown)
    assert any("Optional AI review available" in item for item in markdown)


def test_refactor_result_classification_and_workflow_statuses_are_explicit():
    source = hotspot_source()
    document = normalise_pasted_source(source)
    review = successful_review(source)
    verified = valid_refactor(source, review, "def focused(value=None):\n    return value\n")
    abstained = RefactorResult(
        review.original_analysis,
        review.evidence,
        review.response,
        None,
        None,
        None,
        None,
        abstained=True,
        decision_reason="No better targeted option was identified.",
    )
    failed = failed_refactor(review)
    base = {
        SOURCE_KEY: document,
        ANALYSIS_KEY: review.original_analysis,
        REVIEW_KEY: review,
    }

    assert classify_refactor_result(None) is RefactorResultState.NO_RESULT
    assert classify_refactor_result(verified) is RefactorResultState.VERIFIED_REFACTOR
    assert classify_refactor_result(abstained) is RefactorResultState.MODEL_ABSTAINED
    assert classify_refactor_result(failed) is RefactorResultState.UNAVAILABLE_OR_INVALID
    assert workflow_statuses({**base, REFACTOR_KEY: verified})[2] == "Verified"
    assert workflow_statuses({**base, REFACTOR_KEY: abstained})[2] == "Available"
    assert workflow_statuses({**base, REFACTOR_ERROR_KEY: failed})[2] == "Available"
    assert workflow_statuses(base)[2] == "Available"


def test_refactor_classifier_requires_complete_verified_comparison_data():
    source = hotspot_source()
    review = successful_review(source)
    incomplete = RefactorResult(
        review.original_analysis,
        review.evidence,
        review.response,
        "def focused(value=None):\n    return value\n",
        CandidateVerification(5000, 43, True, None, None, None, "Static checks only."),
        None,
        None,
    )

    assert incomplete.succeeded
    assert classify_refactor_result(incomplete) is RefactorResultState.UNAVAILABLE_OR_INVALID


class StrictWorkspaceState(dict):
    """Model Streamlit widget ownership separately from permanent navigation state."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.workspace_widget_instantiated = False
        self.source_widget_instantiated = False

    def __setitem__(self, key, value):
        if self.workspace_widget_instantiated and key == app.WORKSPACE_VIEW_WIDGET_KEY:
            raise RuntimeError("workspace selector mutated after widget instantiation")
        if self.source_widget_instantiated and key == SOURCE_MODE_KEY:
            raise RuntimeError("source_input_mode mutated after widget instantiation")
        super().__setitem__(key, value)

    def begin_run(self):
        self.workspace_widget_instantiated = False
        self.source_widget_instantiated = False

    def mark_workspace_widget_instantiated(self):
        self.workspace_widget_instantiated = True

    def select_workspace_in_browser(self, value):
        dict.__setitem__(self, app.WORKSPACE_VIEW_WIDGET_KEY, value)

    def mark_source_widget_instantiated(self):
        self.source_widget_instantiated = True


class RenderingRecorder:
    def __init__(self, widget_state=None):
        self.calls = []
        self.tables = []
        self.expanders = []
        self.containers = []
        self.container_options = []
        self.tab_sets = []
        self.segmented_options = []
        self.segmented_widget_values = []
        self.metric_options = []
        self.code_values = []
        self.button_results = {}
        self.radio_result = None
        self.text_area_result = ""
        self.text_input_result = ""
        self.file_upload_result = None
        self.page_config = None
        self.html_values = []
        self.widget_state = widget_state

    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def columns(self, count, **kwargs):
        column_count = count if isinstance(count, int) else len(count)
        return [self for _ in range(column_count)]

    def metric(self, label, value, **kwargs):
        self.calls.append(("metric", label, value))
        self.metric_options.append((label, value, kwargs))

    def expander(self, label, *, expanded, **kwargs):
        self.expanders.append((label, expanded))
        return self

    def container(self, *, border=False, **kwargs):
        self.containers.append(border)
        self.container_options.append({"border": border, **kwargs})
        return self

    def tabs(self, labels, **kwargs):
        self.tab_sets.append(tuple(labels))
        return [self for _ in labels]

    def segmented_control(self, label, options, **kwargs):
        self.calls.append(("segmented_control", (label, tuple(options)), kwargs))
        self.segmented_options.append(tuple(options))
        if self.widget_state is not None:
            self.segmented_widget_values.append(self.widget_state.get(kwargs.get("key")))
            marker = getattr(self.widget_state, "mark_workspace_widget_instantiated", None)
            if marker is not None:
                marker()
        if self.widget_state is not None:
            return self.widget_state.get(kwargs.get("key"), options[0])
        return options[0]

    def dataframe(self, value, **kwargs):
        self.tables.append((value, kwargs))

    def code(self, value, *, language, height=None, **kwargs):
        self.code_values.append((value, language, height))

    def table(self, value, **kwargs):
        self.tables.append((value, {"table": True, **kwargs}))

    def button(self, label, **kwargs):
        self.calls.append(("button", (label,), kwargs))
        clicked = self.button_results.pop(label, False)
        if clicked and kwargs.get("on_click") is not None:
            kwargs["on_click"](*kwargs.get("args", ()), **kwargs.get("kwargs", {}))
        return clicked

    def empty(self):
        return self

    def spinner(self, *args, **kwargs):
        return self

    def radio(self, *args, **kwargs):
        self.calls.append(("radio", args, kwargs))
        if self.widget_state is not None:
            marker = getattr(self.widget_state, "mark_source_widget_instantiated", None)
            if marker is not None:
                marker()
        if self.radio_result is not None:
            return self.radio_result
        options = args[1]
        index = kwargs.get("index", 0)
        if index is None and self.widget_state is not None:
            return self.widget_state.get(kwargs.get("key"))
        return options[index]

    def text_area(self, *args, **kwargs):
        self.calls.append(("text_area", args, kwargs))
        return self.text_area_result

    def text_input(self, *args, **kwargs):
        self.calls.append(("text_input", args, kwargs))
        return self.text_input_result

    def file_uploader(self, *args, **kwargs):
        self.calls.append(("file_uploader", args, kwargs))
        return self.file_upload_result

    def set_page_config(self, **kwargs):
        self.page_config = kwargs

    def html(self, value, **kwargs):
        self.html_values.append((value, kwargs))

    def __getattr__(self, name):
        return lambda *args, **kwargs: self.calls.append((name, args, kwargs))


def install_recorder(monkeypatch, *, state=None):
    recorder = RenderingRecorder(widget_state=state)
    for name in (
        "columns",
        "metric",
        "expander",
        "container",
        "tabs",
        "segmented_control",
        "dataframe",
        "table",
        "code",
        "button",
        "empty",
        "spinner",
        "radio",
        "text_area",
        "text_input",
        "file_uploader",
        "set_page_config",
        "subheader",
        "caption",
        "divider",
        "error",
        "info",
        "markdown",
        "warning",
        "success",
        "title",
        "text",
        "write",
        "json",
        "html",
    ):
        monkeypatch.setattr(app.st, name, getattr(recorder, name))
    return recorder


def test_main_uses_wide_layout_and_deliberate_landing_without_result_tabs(monkeypatch):
    recorder = install_recorder(monkeypatch)
    monkeypatch.setattr(app.st, "sidebar", recorder)
    monkeypatch.setattr(app.st, "session_state", {})

    app.main()

    assert recorder.page_config == {
        "page_title": "CodeSage",
        "page_icon": "🧭",
        "layout": "wide",
        "initial_sidebar_state": "expanded",
    }
    assert recorder.tab_sets == []
    assert recorder.segmented_options == []
    button_labels = [args[0] for name, args, kwargs in recorder.calls if name == "button"]
    assert button_labels.count("Try the built-in example") == 1
    assert "Analyse code" not in button_labels
    assert "Print-friendly report" not in button_labels
    primary_actions = [
        args[0]
        for name, args, kwargs in recorder.calls
        if name == "button" and kwargs.get("type") == "primary"
    ]
    assert primary_actions == ["Try the built-in example"]
    landing_action = next(
        kwargs
        for name, args, kwargs in recorder.calls
        if name == "button" and args[0] == "Try the built-in example"
    )
    assert "use_container_width" not in landing_action
    headings = [args[0] for name, args, kwargs in recorder.calls if name == "subheader"]
    assert "Your Python maintainability coach" in headings
    assert "How CodeSage helps" in headings
    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    writes = [args[0] for name, args, kwargs in recorder.calls if name == "write" and args]
    captions = [args[0] for name, args, kwargs in recorder.calls if name == "caption"]
    assert (
        "CodeSage finds maintainability hotspots, explains the evidence behind them, and helps "
        "you explore targeted refactoring options."
    ) in writes
    assert "Or choose Paste, Upload or GitHub from the source panel." in captions
    assert any(
        "Static analysis only. CodeSage never executes your code." in item for item in markdown
    )
    assert {"### Find hotspots", "### Understand why", "### Refactor carefully"} <= set(markdown)
    paste_control = next(kwargs for name, args, kwargs in recorder.calls if name == "text_area")
    assert paste_control["height"] == 190
    application = Path("app.py").read_text(encoding="utf-8")
    assert "with st.sidebar:" in application


def test_pasted_code_label_and_placeholder_are_visible_and_specific(monkeypatch):
    recorder = install_recorder(monkeypatch)
    monkeypatch.setattr(app.st, "sidebar", recorder)
    state = StrictWorkspaceState({app.SOURCE_ROUTE_MEMORY_KEY: "Paste code"})
    recorder.radio_result = "Paste code"

    app.render_sidebar(state)

    text_area_call = next(call for call in recorder.calls if call[0] == "text_area")
    label = text_area_call[1][0]
    kwargs = text_area_call[2]
    assert label == "Python source (paste your code here)"
    assert kwargs.get("label_visibility", "visible") == "visible"
    assert kwargs["placeholder"] == "Paste a complete Python script here…"


def test_github_loader_has_scoped_enter_guidance_and_requires_its_button(monkeypatch):
    state = StrictWorkspaceState({app.SOURCE_ROUTE_MEMORY_KEY: "Public GitHub .py URL"})
    recorder = install_recorder(monkeypatch, state=state)
    monkeypatch.setattr(app.st, "sidebar", recorder)
    recorder.radio_result = "Public GitHub .py URL"
    recorder.text_input_result = "https://github.com/example/project/blob/main/remote.py"
    fetches = []
    monkeypatch.setattr(app, "fetch_github_source", lambda url: fetches.append(url))

    assert app.render_sidebar(state) is None

    assert fetches == []
    assert {item.get("key") for item in recorder.container_options} >= {"github_url_loader"}
    captions = [args[0] for name, args, kwargs in recorder.calls if name == "caption"]
    assert "Paste a public GitHub .py URL, then select Load GitHub file." in captions
    application = Path("app.py").read_text(encoding="utf-8")
    assert (
        '.st-key-github_url_loader [data-testid="InputInstructions"] { display: none; }'
        in application
    )
    assert '[data-testid="InputInstructions"] { display: none; }' not in application.replace(
        '.st-key-github_url_loader [data-testid="InputInstructions"] { display: none; }', ""
    )


def test_github_load_button_performs_exactly_one_fetch(monkeypatch):
    source = hotspot_source()
    url = "https://github.com/example/project/blob/main/remote.py"
    document = replace(
        normalise_pasted_source(source),
        origin=SourceOrigin.GITHUB,
        display_name="remote.py",
        external_reference=url,
    )
    state = StrictWorkspaceState({app.SOURCE_ROUTE_MEMORY_KEY: "Public GitHub .py URL"})
    recorder = install_recorder(monkeypatch, state=state)
    monkeypatch.setattr(app.st, "sidebar", recorder)
    recorder.radio_result = "Public GitHub .py URL"
    recorder.text_input_result = url
    recorder.button_results["Load GitHub file"] = True
    fetches = []

    def mocked_fetch(requested_url):
        fetches.append(requested_url)
        return document

    monkeypatch.setattr(app, "fetch_github_source", mocked_fetch)

    assert app.render_sidebar(state) == document
    assert fetches == [url]


def test_main_example_route_survives_reruns_and_analyses_on_first_click(monkeypatch):
    state = StrictWorkspaceState()
    first = install_recorder(monkeypatch, state=state)
    monkeypatch.setattr(app.st, "sidebar", first)
    first.button_results["Try the built-in example"] = True

    assert app.render_sidebar(state) is None
    app.render_landing(state)

    assert state[app.PENDING_SOURCE_MODE_KEY] == EXAMPLE_MODE
    assert state[SOURCE_KEY] == normalise_example_source()
    assert ANALYSIS_KEY not in state

    state.begin_run()
    ready = install_recorder(monkeypatch, state=state)
    monkeypatch.setattr(app.st, "sidebar", ready)
    document = app.render_sidebar(state)
    assert document == normalise_example_source()
    assert state[SOURCE_MODE_KEY] == EXAMPLE_MODE
    assert app.PENDING_SOURCE_MODE_KEY not in state
    ready.button_results["Analyse code"] = True
    app.render_ready_to_analyse(document, state)

    assert state[ANALYSIS_KEY].syntax_valid
    assert state[SOURCE_KEY] == document
    assert state[app.WORKSPACE_VIEW_STATE_KEY] == "Overview"
    assert state[app.SCROLL_TO_TOP_KEY] is True

    state.begin_run()
    results = install_recorder(monkeypatch, state=state)
    app.render_workspace(document, state)
    assert state[app.WORKSPACE_VIEW_STATE_KEY] == "Overview"
    assert state[app.WORKSPACE_VIEW_WIDGET_KEY] == "Overview"
    assert results.segmented_options == [app.WORKSPACE_VIEWS]


def test_deferred_source_route_is_applied_once_before_radio_creation(monkeypatch):
    state = StrictWorkspaceState(
        {
            app.PENDING_SOURCE_MODE_KEY: EXAMPLE_MODE,
            app.SOURCE_ROUTE_MEMORY_KEY: "Paste code",
        }
    )
    recorder = install_recorder(monkeypatch, state=state)
    monkeypatch.setattr(app.st, "sidebar", recorder)

    document = app.render_sidebar(state)

    assert document == normalise_example_source()
    assert state[SOURCE_MODE_KEY] == EXAMPLE_MODE
    assert state[app.SOURCE_ROUTE_MEMORY_KEY] == EXAMPLE_MODE
    assert app.PENDING_SOURCE_MODE_KEY not in state
    radio_call = next(call for call in recorder.calls if call[0] == "radio")
    assert radio_call[2]["label_visibility"] == "collapsed"
    assert any(
        name == "subheader" and args[0] == "Choose your source"
        for name, args, _kwargs in recorder.calls
    )


@pytest.mark.parametrize(
    ("route", "expected_origin", "expected_name"),
    [
        ("Paste code", SourceOrigin.PASTED, "Pasted source"),
        ("Upload .py file", SourceOrigin.UPLOADED, "uploaded.py"),
        ("Public GitHub .py URL", SourceOrigin.GITHUB, "remote.py"),
        (EXAMPLE_MODE, SourceOrigin.EXAMPLE, "CodeSage example.py"),
    ],
)
def test_sidebar_source_routes_retain_exact_document_and_analyse(
    monkeypatch, route, expected_origin, expected_name
):
    source = hotspot_source()
    state = StrictWorkspaceState({app.SOURCE_ROUTE_MEMORY_KEY: route})
    recorder = install_recorder(monkeypatch, state=state)
    monkeypatch.setattr(app.st, "sidebar", recorder)
    recorder.radio_result = route
    if route == "Paste code":
        recorder.text_area_result = source
    elif route == "Upload .py file":

        class Upload:
            name = "uploaded.py"

            @staticmethod
            def getvalue():
                return source.encode("utf-8")

        recorder.file_upload_result = Upload()
    elif route == "Public GitHub .py URL":
        recorder.text_input_result = "https://github.com/example/project/blob/main/remote.py"
        recorder.button_results["Load GitHub file"] = True
        github_document = replace(
            normalise_pasted_source(source),
            origin=SourceOrigin.GITHUB,
            display_name="remote.py",
            external_reference=recorder.text_input_result,
        )
        fetches = []

        def mocked_fetch(url):
            fetches.append(url)
            return github_document

        monkeypatch.setattr(app, "fetch_github_source", mocked_fetch)

    document = app.render_sidebar(state)

    assert document is not None
    assert document.origin is expected_origin
    assert document.display_name == expected_name
    assert state[SOURCE_KEY] == document
    if route != EXAMPLE_MODE:
        assert document.text == source
    app.analyse_for_workspace(state, document)
    assert state[ANALYSIS_KEY].syntax_valid
    assert state[ANALYSIS_KEY].source_digest == document.source_digest
    if route == "Public GitHub .py URL":
        assert fetches == [recorder.text_input_result]


@pytest.mark.parametrize(
    ("origin", "display_name", "external_reference"),
    [
        (SourceOrigin.PASTED, "Pasted source", None),
        (SourceOrigin.UPLOADED, "uploaded.py", None),
        (
            SourceOrigin.GITHUB,
            "remote.py",
            "https://github.com/example/project/blob/main/remote.py",
        ),
        (SourceOrigin.EXAMPLE, "CodeSage example.py", None),
    ],
)
def test_each_source_origin_completes_cached_mock_review_and_refactor_iteration(
    origin, display_name, external_reference
):
    source = hotspot_source()
    document = replace(
        normalise_pasted_source(source),
        origin=origin,
        display_name=display_name,
        external_reference=external_reference,
    )
    state = {}
    review_calls = []
    refactor_calls = []

    def reviewer(current_source, analysis):
        review_calls.append((current_source, analysis.source_digest))
        return successful_review(current_source)

    replacements = iter(
        (
            "def focused(value=None):\n    return value\n",
            "def focused(value=None):\n    return [] if value is None else value\n",
        )
    )

    def refactorer(current_source, analysis, review, **kwargs):
        refactor_calls.append(kwargs["optional_instructions"])
        return valid_refactor(current_source, review, next(replacements))

    handle_actions(
        state,
        document,
        analyse_clicked=True,
        review_clicked=False,
        reviewer=reviewer,
    )
    handle_actions(
        state,
        document,
        analyse_clicked=False,
        review_clicked=True,
        reviewer=reviewer,
    )
    handle_actions(
        state,
        document,
        analyse_clicked=False,
        review_clicked=True,
        reviewer=reviewer,
    )
    handle_refactor_action(
        state,
        document,
        refactor_clicked=True,
        optional_instructions="   ",
        refactorer=refactorer,
    )
    first_refactor = state[REFACTOR_KEY]
    handle_refactor_action(
        state,
        document,
        refactor_clicked=True,
        optional_instructions="  Prefer early returns.  ",
        refactorer=refactorer,
    )

    assert state[SOURCE_KEY] == document
    assert len(review_calls) == 1
    assert refactor_calls == ["", "Prefer early returns."]
    assert state[REFACTOR_KEY] is not first_refactor
    assert state[ANALYSIS_KEY].source_digest == document.source_digest
    assert state[REVIEW_KEY].original_analysis.source_digest == document.source_digest


def test_reference_theme_and_local_font_assets_are_exact():
    config_text = Path(".streamlit/config.toml").read_text(encoding="utf-8")
    config = tomllib.loads(config_text)
    theme = config["theme"]
    assert config["server"]["enableStaticServing"] is True
    assert theme["primaryColor"] == "#cb785c"
    assert theme["backgroundColor"] == "#fdfdf8"
    assert theme["secondaryBackgroundColor"] == "#ecebe3"
    assert theme["textColor"] == "#3d3a2a"
    assert theme["linkColor"] == "#3d3a2a"
    assert theme["borderColor"] == "#d3d2ca"
    assert theme["showWidgetBorder"] is True
    assert theme["baseRadius"] == "0.75rem"
    assert theme["buttonRadius"] == "full"
    assert theme["font"] == "SpaceGrotesk"
    assert theme["headingFontWeights"] == [600, 500, 500, 500, 500, 500]
    assert theme["headingFontSizes"] == ["3rem", "2rem"]
    assert theme["codeFont"] == "SpaceMono"
    assert theme["codeFontSize"] == ".75rem"
    assert theme["codeBackgroundColor"] == "#ecebe4"
    assert theme["showSidebarBorder"] is True
    assert theme["chartCategoricalColors"] == ["#0ea5e9", "#059669", "#fbbf24"]
    assert theme["sidebar"] == {
        "backgroundColor": "#f0f0ec",
        "secondaryBackgroundColor": "#ecebe3",
        "headingFontSizes": ["1.6rem", "1.4rem", "1.2rem"],
        "dataframeHeaderBackgroundColor": "#e4e4e0",
    }
    font_faces = theme["fontFaces"]
    assert font_faces == [
        {
            "family": "SpaceGrotesk",
            "url": "app/static/SpaceGrotesk-VariableFont_wght.ttf",
        },
        {
            "family": "SpaceMono",
            "url": "app/static/SpaceMono-Bold.ttf",
            "style": "normal",
            "weight": 700,
        },
        {
            "family": "SpaceMono",
            "url": "app/static/SpaceMono-BoldItalic.ttf",
            "style": "italic",
            "weight": 700,
        },
        {
            "family": "SpaceMono",
            "url": "app/static/SpaceMono-Italic.ttf",
            "style": "italic",
            "weight": 400,
        },
        {
            "family": "SpaceMono",
            "url": "app/static/SpaceMono-Regular.ttf",
            "style": "normal",
            "weight": 400,
        },
    ]
    assert all(face["url"].startswith("app/static/") for face in font_faces)
    assert "fonts.googleapis.com" not in config_text
    assert "http://" not in config_text and "https://" not in config_text
    for asset in app.REQUIRED_STATIC_ASSETS:
        assert (Path("static") / asset).is_file()
    assert {path.name for path in Path("static").iterdir()} == set(app.REQUIRED_STATIC_ASSETS)
    for font in Path("static").glob("*.ttf"):
        assert font.read_bytes().startswith(b"\x00\x01\x00\x00")
    for licence in Path("static").glob("OFL-*.txt"):
        assert "SIL OPEN FONT LICENSE" in licence.read_text(encoding="utf-8")


def test_results_navigation_is_state_bound_and_does_not_invoke_models(monkeypatch):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    review = successful_review(source)
    refactor = valid_refactor(source, review, "def focused(value=None):\n    return value\n")
    state = {
        SOURCE_KEY: document,
        ANALYSIS_KEY: review.original_analysis,
        REVIEW_KEY: review,
        REFACTOR_KEY: refactor,
        app.WORKSPACE_VIEW_STATE_KEY: "Measurements & evidence",
    }
    identities = {key: id(value) for key, value in state.items()}
    recorder = install_recorder(monkeypatch, state=state)
    monkeypatch.setattr(
        app,
        "handle_actions",
        lambda *args, **kwargs: pytest.fail("navigation must not request an AI review"),
    )
    monkeypatch.setattr(
        app,
        "handle_refactor_action",
        lambda *args, **kwargs: pytest.fail("navigation must not request a refactor"),
    )

    app.render_workspace(document, state)

    assert recorder.segmented_options == [app.WORKSPACE_VIEWS]
    navigation_call = next(call for call in recorder.calls if call[0] == "segmented_control")
    assert navigation_call[1] == ("Results workspace", app.WORKSPACE_VIEWS)
    assert navigation_call[2]["key"] == app.WORKSPACE_VIEW_WIDGET_KEY
    assert navigation_call[2]["width"] == "stretch"
    assert navigation_call[2]["selection_mode"] == "single"
    assert navigation_call[2]["on_change"] is app.store_workspace_widget_selection
    assert recorder.segmented_widget_values == ["Measurements & evidence"]
    assert state[app.WORKSPACE_VIEW_STATE_KEY] == "Measurements & evidence"
    assert state[app.WORKSPACE_VIEW_WIDGET_KEY] == "Measurements & evidence"
    assert {key: id(state[key]) for key in identities} == identities


def test_programmatic_navigation_changes_only_permanent_state_and_scroll():
    state = {
        "analysis": object(),
        "review": object(),
        "refactor": object(),
        app.WORKSPACE_VIEW_WIDGET_KEY: "Overview",
    }
    preserved = dict(state)
    app.navigate_to_workspace(state, "Refactor")
    assert state[app.WORKSPACE_VIEW_STATE_KEY] == "Refactor"
    assert state[app.WORKSPACE_VIEW_WIDGET_KEY] == "Overview"
    assert state[app.SCROLL_TO_TOP_KEY] is True
    assert {key: state[key] for key in preserved} == preserved
    app.navigate_to_workspace(state, "Unknown")
    assert state[app.WORKSPACE_VIEW_STATE_KEY] == "Overview"
    assert state[app.WORKSPACE_VIEW_WIDGET_KEY] == "Overview"


def test_legacy_technical_workspace_alias_is_preserved_and_canonicalised(monkeypatch):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    state = StrictWorkspaceState(
        {
            SOURCE_KEY: document,
            ANALYSIS_KEY: analyse_script(source),
            app.WORKSPACE_VIEW_STATE_KEY: "Technical details",
        }
    )
    recorder = install_recorder(monkeypatch, state=state)

    app.render_workspace(document, state)

    assert state[app.WORKSPACE_VIEW_STATE_KEY] == "Measurements & evidence"
    assert state[app.WORKSPACE_VIEW_WIDGET_KEY] == "Measurements & evidence"
    assert recorder.segmented_options == [app.WORKSPACE_VIEWS]
    assert "Technical details" not in app.WORKSPACE_VIEWS


def test_each_scroll_request_is_consumed_once_and_reexecutes_static_helper(monkeypatch):
    state = {}
    recorder = install_recorder(monkeypatch)

    app.request_scroll_to_top(state)
    assert app.render_requested_scroll(state) is True
    assert app.render_requested_scroll(state) is False
    app.request_scroll_to_top(state)
    assert app.render_requested_scroll(state) is True
    assert app.render_requested_scroll(state) is False

    javascript = [
        (value, options)
        for value, options in recorder.html_values
        if options.get("unsafe_allow_javascript")
    ]
    assert javascript == [
        (app.SCROLL_TO_TOP_SCRIPT_VARIANTS[0], {"unsafe_allow_javascript": True}),
        (app.SCROLL_TO_TOP_SCRIPT_VARIANTS[1], {"unsafe_allow_javascript": True}),
    ]
    assert app.SCROLL_TO_TOP_KEY not in state


def test_widget_callback_stores_visible_selection_and_next_run_synchronises(monkeypatch):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    state = {
        SOURCE_KEY: document,
        ANALYSIS_KEY: analyse_script(source),
        app.WORKSPACE_VIEW_STATE_KEY: "Overview",
    }
    state = StrictWorkspaceState(state)
    recorder = install_recorder(monkeypatch, state=state)
    monkeypatch.setattr(
        app,
        "handle_actions",
        lambda *args, **kwargs: pytest.fail("navigation must not request a review"),
    )

    app.render_workspace(document, state)

    navigation = next(call for call in recorder.calls if call[0] == "segmented_control")
    assert recorder.segmented_widget_values == ["Overview"]
    state.select_workspace_in_browser("AI review")
    callback = navigation[2]["on_change"]
    callback(*navigation[2]["args"])
    assert state[app.WORKSPACE_VIEW_STATE_KEY] == "AI review"
    assert state[app.SCROLL_TO_TOP_KEY] is True
    state.begin_run()
    second_recorder = install_recorder(monkeypatch, state=state)
    app.render_workspace(document, state)
    assert second_recorder.segmented_widget_values == ["AI review"]
    assert state[app.WORKSPACE_VIEW_WIDGET_KEY] == "AI review"


def test_action_renderers_never_assign_the_segmented_widget_key_directly():
    review_source = inspect.getsource(app.render_review_action)
    refactor_source = inspect.getsource(app.render_refactor_action)
    assert "WORKSPACE_VIEW_WIDGET_KEY" not in review_source
    assert "WORKSPACE_VIEW_WIDGET_KEY" not in refactor_source
    assert "navigate_to_workspace" in review_source
    assert "navigate_to_workspace" in refactor_source


def test_first_review_click_through_workspace_uses_one_request_and_deferred_navigation(
    monkeypatch,
):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    state = StrictWorkspaceState(
        {
            SOURCE_KEY: document,
            ANALYSIS_KEY: analyse_script(source),
            app.WORKSPACE_VIEW_STATE_KEY: "Overview",
        }
    )
    recorder = install_recorder(monkeypatch, state=state)
    recorder.button_results["Get AI review"] = True
    calls = []
    reruns = []

    def complete_review(target_state, target_document, **kwargs):
        calls.append((target_document, kwargs))
        target_state[REVIEW_KEY] = successful_review(source)
        target_state.pop(REVIEW_ERROR_KEY, None)
        return None

    monkeypatch.setattr(app, "handle_actions", complete_review)
    monkeypatch.setattr(app.st, "rerun", lambda: reruns.append("rerun"))

    app.render_workspace(document, state)

    assert len(calls) == 1
    assert REVIEW_KEY in state
    assert state[app.WORKSPACE_VIEW_STATE_KEY] == "AI review"
    assert state[app.WORKSPACE_VIEW_WIDGET_KEY] == "Overview"
    assert state[app.SCROLL_TO_TOP_KEY] is True
    assert reruns == ["rerun"]

    state.begin_run()
    second_recorder = install_recorder(monkeypatch, state=state)
    monkeypatch.setattr(
        app,
        "handle_actions",
        lambda *args, **kwargs: pytest.fail("rerendering must not request another review"),
    )
    app.render_workspace(document, state)
    assert state[app.WORKSPACE_VIEW_STATE_KEY] == "AI review"
    assert state[app.WORKSPACE_VIEW_WIDGET_KEY] == "AI review"
    assert second_recorder.segmented_widget_values == ["AI review"]
    assert len(calls) == 1
    assert second_recorder.segmented_options == [app.WORKSPACE_VIEWS]


def test_ai_review_empty_workspace_uses_shared_first_click_action(monkeypatch):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    state = StrictWorkspaceState(
        {
            SOURCE_KEY: document,
            ANALYSIS_KEY: analyse_script(source),
            app.WORKSPACE_VIEW_STATE_KEY: "AI review",
        }
    )
    recorder = install_recorder(monkeypatch, state=state)
    recorder.button_results["Get AI review"] = True
    calls = []

    def complete_review(target_state, target_document, **kwargs):
        calls.append(target_document)
        target_state[REVIEW_KEY] = successful_review(source)
        return None

    monkeypatch.setattr(app, "handle_actions", complete_review)
    monkeypatch.setattr(app.st, "rerun", lambda: None)
    app.render_workspace(document, state)

    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    writes = [args[0] for name, args, kwargs in recorder.calls if name == "write" and args]
    assert "### No AI review yet" in markdown
    assert (
        "AI review is optional. If requested, it will explain prioritised findings using your "
        "code and CodeSage's measured evidence."
    ) in writes
    assert calls == [document]
    assert state[app.WORKSPACE_VIEW_STATE_KEY] == "AI review"
    assert state[app.WORKSPACE_VIEW_WIDGET_KEY] == "AI review"


def test_first_refactor_click_through_workspace_uses_one_request_and_deferred_navigation(
    monkeypatch,
):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    review = successful_review(source)
    state = StrictWorkspaceState(
        {
            SOURCE_KEY: document,
            ANALYSIS_KEY: review.original_analysis,
            REVIEW_KEY: review,
            app.WORKSPACE_VIEW_STATE_KEY: "AI review",
        }
    )
    recorder = install_recorder(monkeypatch, state=state)
    recorder.button_results["Generate suggested refactor"] = True
    calls = []
    reruns = []
    replacement = "def focused(value=None):\n    return value\n"

    def complete_refactor(target_state, target_document, **kwargs):
        calls.append((target_document, kwargs))
        target_state[REFACTOR_KEY] = valid_refactor(source, review, replacement)
        target_state.pop(REFACTOR_ERROR_KEY, None)
        return None

    monkeypatch.setattr(app, "handle_refactor_action", complete_refactor)
    monkeypatch.setattr(app.st, "rerun", lambda: reruns.append("rerun"))
    app.render_workspace(document, state)

    assert len(calls) == 1
    assert state[app.WORKSPACE_VIEW_STATE_KEY] == "Refactor"
    assert state[app.WORKSPACE_VIEW_WIDGET_KEY] == "AI review"
    assert state[app.SCROLL_TO_TOP_KEY] is True
    assert reruns == ["rerun"]

    state.begin_run()
    second_recorder = install_recorder(monkeypatch, state=state)
    monkeypatch.setattr(
        app,
        "handle_refactor_action",
        lambda *args, **kwargs: pytest.fail("rerendering must not request another refactor"),
    )
    app.render_workspace(document, state)
    assert state[app.WORKSPACE_VIEW_STATE_KEY] == "Refactor"
    assert state[app.WORKSPACE_VIEW_WIDGET_KEY] == "Refactor"
    assert second_recorder.segmented_widget_values == ["Refactor"]
    assert len(calls) == 1
    assert second_recorder.segmented_options == [app.WORKSPACE_VIEWS]


def test_refactor_empty_workspace_uses_the_shared_generation_action(monkeypatch):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    review = successful_review(source)
    state = {
        SOURCE_KEY: document,
        ANALYSIS_KEY: review.original_analysis,
        REVIEW_KEY: review,
        app.WORKSPACE_VIEW_STATE_KEY: "Refactor",
    }
    recorder = install_recorder(monkeypatch, state=state)
    app.render_workspace(document, state)

    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    writes = [args[0] for name, args, kwargs in recorder.calls if name == "write" and args]
    buttons = [args[0] for name, args, kwargs in recorder.calls if name == "button"]
    assert "### No suggested refactor yet" in markdown
    assert (
        "Review the findings, then generate a targeted refactor. CodeSage will preserve the "
        "rest of the file unchanged."
    ) in writes
    assert buttons.count("Generate suggested refactor") == 1


def test_first_refactor_click_from_empty_refactor_view_synchronises_visible_selection(
    monkeypatch,
):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    review = successful_review(source)
    state = StrictWorkspaceState(
        {
            SOURCE_KEY: document,
            ANALYSIS_KEY: review.original_analysis,
            REVIEW_KEY: review,
            app.WORKSPACE_VIEW_STATE_KEY: "Refactor",
        }
    )
    recorder = install_recorder(monkeypatch, state=state)
    recorder.button_results["Generate suggested refactor"] = True
    calls = []
    reruns = []

    def complete_refactor(target_state, target_document, **kwargs):
        calls.append((target_document, kwargs))
        target_state[REFACTOR_KEY] = valid_refactor(
            source, review, "def focused(value=None):\n    return value\n"
        )
        return None

    monkeypatch.setattr(app, "handle_refactor_action", complete_refactor)
    monkeypatch.setattr(app.st, "rerun", lambda: reruns.append("rerun"))

    app.render_workspace(document, state)

    assert len(calls) == 1
    assert state[app.WORKSPACE_VIEW_STATE_KEY] == "Refactor"
    assert state[app.WORKSPACE_VIEW_WIDGET_KEY] == "Refactor"
    assert state[app.SCROLL_TO_TOP_KEY] is True
    assert reruns == ["rerun"]


def test_successful_alternative_refactor_keeps_review_and_scrolls_from_top(monkeypatch):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    review = successful_review(source)
    existing = valid_refactor(source, review, "def focused(value=None):\n    return value\n")
    replacement = "def focused(value=None):\n    return [] if value is None else value\n"
    state = StrictWorkspaceState(
        {
            SOURCE_KEY: document,
            ANALYSIS_KEY: review.original_analysis,
            REVIEW_KEY: review,
            REFACTOR_KEY: existing,
            app.WORKSPACE_VIEW_STATE_KEY: "Refactor",
        }
    )
    recorder = install_recorder(monkeypatch, state=state)
    recorder.text_area_result = "Prefer early returns."
    recorder.button_results["Generate a different refactor"] = True
    refactor_calls = []
    reruns = []

    def complete_refactor(target_state, target_document, **kwargs):
        refactor_calls.append(kwargs["optional_instructions"])
        target_state[REFACTOR_KEY] = valid_refactor(source, review, replacement)
        return None

    monkeypatch.setattr(app, "handle_refactor_action", complete_refactor)
    monkeypatch.setattr(
        app,
        "handle_actions",
        lambda *args, **kwargs: pytest.fail("an alternative must not rerun the review"),
    )
    monkeypatch.setattr(app.st, "rerun", lambda: reruns.append("rerun"))

    app.render_workspace(document, state)

    assert refactor_calls == ["Prefer early returns."]
    assert state[REVIEW_KEY] is review
    assert state[REFACTOR_KEY] is not existing
    assert state[app.WORKSPACE_VIEW_STATE_KEY] == "Refactor"
    assert state[app.WORKSPACE_VIEW_WIDGET_KEY] == "Refactor"
    assert state[app.SCROLL_TO_TOP_KEY] is True
    assert reruns == ["rerun"]


@pytest.mark.parametrize(
    "outcome",
    (ReviewOutcome.NO_REFACTOR_NEEDED, ReviewOutcome.INSUFFICIENT_EVIDENCE),
)
def test_non_refactor_review_outcomes_remain_readable_without_generation_action(
    monkeypatch, outcome
):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    review = successful_review(source, outcome)
    state = {
        SOURCE_KEY: document,
        ANALYSIS_KEY: review.original_analysis,
        REVIEW_KEY: review,
        app.WORKSPACE_VIEW_STATE_KEY: "AI review",
    }
    recorder = install_recorder(monkeypatch)

    app.render_workspace(document, state)

    assert any(
        name == "subheader" and args[0] == "AI maintainability review"
        for name, args, _kwargs in recorder.calls
    )
    assert not any(
        name == "button" and args[0] == "Generate suggested refactor"
        for name, args, _kwargs in recorder.calls
    )

    recorder.calls.clear()
    state[app.WORKSPACE_VIEW_STATE_KEY] = "Refactor"
    app.render_workspace(document, state)
    writes = [args[0] for name, args, _kwargs in recorder.calls if name == "write" and args]
    expected = (
        "did not recommend a targeted refactor"
        if outcome is ReviewOutcome.NO_REFACTOR_NEEDED
        else "could not justify a targeted refactor"
    )
    assert any(expected in value for value in writes)
    assert not any(name == "button" for name, _args, _kwargs in recorder.calls)


def test_completed_overview_review_card_navigates_without_a_model_call(monkeypatch):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    review = successful_review(source)
    state = StrictWorkspaceState(
        {
            SOURCE_KEY: document,
            ANALYSIS_KEY: review.original_analysis,
            REVIEW_KEY: review,
            app.WORKSPACE_VIEW_STATE_KEY: "Overview",
        }
    )
    identities = {
        key: id(value) for key, value in state.items() if key != app.WORKSPACE_VIEW_STATE_KEY
    }
    recorder = install_recorder(monkeypatch, state=state)
    recorder.button_results["View AI review"] = True
    monkeypatch.setattr(
        app,
        "handle_actions",
        lambda *args, **kwargs: pytest.fail("navigation must not request a review"),
    )
    monkeypatch.setattr(
        app,
        "handle_refactor_action",
        lambda *args, **kwargs: pytest.fail("navigation must not request a refactor"),
    )
    app.render_workspace(document, state)

    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    writes = [args[0] for name, args, kwargs in recorder.calls if name == "write" and args]
    assert "### AI review ready" in markdown
    assert "CodeSage has completed the evidence-based review." in writes
    assert state[app.WORKSPACE_VIEW_STATE_KEY] == "AI review"
    assert state[app.WORKSPACE_VIEW_WIDGET_KEY] == "Overview"
    assert state[app.SCROLL_TO_TOP_KEY] is True
    assert {key: id(state[key]) for key in identities} == identities


def test_completed_ai_review_shows_refactor_ready_navigation_without_model_call(monkeypatch):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    review = successful_review(source)
    refactor = valid_refactor(source, review, "def focused(value=None):\n    return value\n")
    state = StrictWorkspaceState(
        {
            SOURCE_KEY: document,
            ANALYSIS_KEY: review.original_analysis,
            REVIEW_KEY: review,
            REFACTOR_KEY: refactor,
            app.WORKSPACE_VIEW_STATE_KEY: "AI review",
        }
    )
    identities = {
        key: id(value) for key, value in state.items() if key != app.WORKSPACE_VIEW_STATE_KEY
    }
    recorder = install_recorder(monkeypatch, state=state)
    recorder.button_results["View current verified refactor"] = True
    monkeypatch.setattr(
        app,
        "handle_actions",
        lambda *args, **kwargs: pytest.fail("navigation must not request a review"),
    )
    monkeypatch.setattr(
        app,
        "handle_refactor_action",
        lambda *args, **kwargs: pytest.fail("navigation must not request a refactor"),
    )
    app.render_workspace(document, state)

    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    writes = [args[0] for name, args, kwargs in recorder.calls if name == "write" and args]
    assert "### Suggested refactor ready" in markdown
    assert any(
        value.startswith("CodeSage generated and statically checked a targeted refactor")
        for value in writes
    )
    assert state[app.WORKSPACE_VIEW_STATE_KEY] == "Refactor"
    assert state[app.WORKSPACE_VIEW_WIDGET_KEY] == "AI review"
    assert state[app.SCROLL_TO_TOP_KEY] is True
    assert {key: id(state[key]) for key in identities} == identities


def test_failed_review_stays_on_current_view_and_explicit_retry_is_single_request(monkeypatch):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    analysis = analyse_script(source)
    evidence = build_evidence_package(analysis)
    failure = ReviewResult(
        analysis,
        evidence,
        None,
        "timeout",
        "The AI review request timed out.",
        False,
    )
    state = StrictWorkspaceState(
        {
            SOURCE_KEY: document,
            ANALYSIS_KEY: analysis,
            app.WORKSPACE_VIEW_STATE_KEY: "Overview",
        }
    )
    recorder = install_recorder(monkeypatch, state=state)
    recorder.button_results["Get AI review"] = True
    calls = []

    def fail_review(target_state, *args, **kwargs):
        calls.append("failed")
        target_state[REVIEW_ERROR_KEY] = failure
        return None

    monkeypatch.setattr(app, "handle_actions", fail_review)
    monkeypatch.setattr(app.st, "rerun", lambda: pytest.fail("failure must not rerun"))
    app.render_workspace(document, state)
    assert calls == ["failed"]
    assert app.SCROLL_TO_TOP_KEY not in state
    assert state[app.WORKSPACE_VIEW_STATE_KEY] == "Overview"
    assert state[app.WORKSPACE_VIEW_WIDGET_KEY] == "Overview"
    assert REVIEW_KEY not in state

    state.begin_run()
    retry_recorder = install_recorder(monkeypatch, state=state)
    retry_recorder.button_results["Get AI review"] = True
    reruns = []

    def complete_review(target_state, *args, **kwargs):
        calls.append("succeeded")
        target_state[REVIEW_KEY] = successful_review(source)
        target_state.pop(REVIEW_ERROR_KEY, None)
        return None

    monkeypatch.setattr(app, "handle_actions", complete_review)
    monkeypatch.setattr(app.st, "rerun", lambda: reruns.append("rerun"))
    app.render_workspace(document, state)
    assert calls == ["failed", "succeeded"]
    assert state[app.WORKSPACE_VIEW_STATE_KEY] == "AI review"
    assert state[app.WORKSPACE_VIEW_WIDGET_KEY] == "Overview"
    assert state[app.SCROLL_TO_TOP_KEY] is True
    assert reruns == ["rerun"]


def test_failed_alternative_keeps_verified_refactor_and_does_not_navigate(monkeypatch):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    review = successful_review(source)
    existing = valid_refactor(source, review, "def focused(value=None):\n    return value\n")
    state = StrictWorkspaceState(
        {
            SOURCE_KEY: document,
            ANALYSIS_KEY: review.original_analysis,
            REVIEW_KEY: review,
            REFACTOR_KEY: existing,
            app.WORKSPACE_VIEW_STATE_KEY: "Refactor",
        }
    )
    recorder = install_recorder(monkeypatch, state=state)
    recorder.button_results["Generate a different refactor"] = True
    calls = []

    def fail_alternative(target_state, *args, **kwargs):
        calls.append("failed")
        target_state[REFACTOR_ERROR_KEY] = failed_refactor(review)
        return None

    monkeypatch.setattr(app, "handle_refactor_action", fail_alternative)
    monkeypatch.setattr(app.st, "rerun", lambda: pytest.fail("failure must not rerun"))
    app.render_workspace(document, state)
    assert calls == ["failed"]
    assert state[REFACTOR_KEY] is existing
    assert app.SCROLL_TO_TOP_KEY not in state
    assert state[app.WORKSPACE_VIEW_STATE_KEY] == "Refactor"
    assert state[app.WORKSPACE_VIEW_WIDGET_KEY] == "Refactor"


def test_sidebar_is_a_compact_light_source_panel_without_workflow_actions(monkeypatch):
    state = {}
    recorder = install_recorder(monkeypatch)
    recorder.radio_result = EXAMPLE_MODE
    monkeypatch.setattr(app.st, "sidebar", recorder)

    document = app.render_sidebar(state)

    assert document == normalise_example_source()
    assert state[SOURCE_KEY] == document
    assert any(
        name == "success" and args[0] == "✓ Built-in example loaded"
        for name, args, _kwargs in recorder.calls
    )
    button_labels = [args[0] for name, args, kwargs in recorder.calls if name == "button"]
    assert button_labels == []
    visible_copy = " ".join(str(args[0]) for name, args, kwargs in recorder.calls if args)
    assert "Source panel" not in visible_copy
    assert "Try the built-in example" not in visible_copy
    for excluded in (
        "Print-friendly report",
        "Analyse code",
        "Get AI review",
        "Workflow",
        "future work",
    ):
        assert excluded not in visible_copy

    app.load_example_for_workspace(state)
    loaded_recorder = install_recorder(monkeypatch)
    loaded_recorder.radio_result = EXAMPLE_MODE
    monkeypatch.setattr(app.st, "sidebar", loaded_recorder)
    loaded = app.render_sidebar(state)
    assert loaded == normalise_example_source()
    assert any(
        name == "success" and args[0] == "✓ Built-in example loaded"
        for name, args, kwargs in loaded_recorder.calls
    )


def test_source_loaded_state_uses_full_workspace_and_one_analysis_action(monkeypatch):
    document = normalise_example_source()
    state = {}
    recorder = install_recorder(monkeypatch)
    recorder.button_results["Analyse code"] = True

    app.render_ready_to_analyse(document, state)

    assert recorder.tab_sets == []
    assert recorder.segmented_options == []
    assert recorder.code_values == [(document.text, "python", 360)]
    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    assert "### Source preview" in markdown
    assert "### Ready to analyse" in markdown
    assert any("cyclomatic complexity" in value for value in markdown)
    primary_actions = [
        args[0]
        for name, args, kwargs in recorder.calls
        if name == "button" and kwargs.get("type") == "primary"
    ]
    assert primary_actions == ["Analyse code"]
    assert state[SOURCE_KEY] == document
    assert ANALYSIS_KEY in state


@pytest.mark.parametrize(
    ("with_refactor", "expected_action"),
    [(False, "Generate suggested refactor"), (True, "Generate a different refactor")],
)
def test_reviewed_stages_render_exactly_one_primary_action(
    monkeypatch, with_refactor, expected_action
):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    review = successful_review(source)
    state = {
        SOURCE_KEY: document,
        ANALYSIS_KEY: review.original_analysis,
        REVIEW_KEY: review,
    }
    if with_refactor:
        state[REFACTOR_KEY] = valid_refactor(
            source,
            review,
            "def focused(value=None):\n    return value\n",
        )
    recorder = install_recorder(monkeypatch)

    state[app.WORKSPACE_VIEW_STATE_KEY] = "Refactor" if with_refactor else "AI review"
    app.render_workspace(document, state)

    primary_actions = [
        args[0]
        for name, args, kwargs in recorder.calls
        if name == "button" and kwargs.get("type") == "primary"
    ]
    assert primary_actions == [expected_action]


@pytest.mark.parametrize(
    ("alternative", "heading", "field_label", "button_label"),
    [
        (
            False,
            "### Next step: Generate a suggested refactor",
            "Instructions for this refactor (optional — maximum 500 characters)",
            "Generate suggested refactor",
        ),
        (
            True,
            "### Explore another refactoring option",
            "Instructions for the next refactor (optional — maximum 500 characters)",
            "Generate a different refactor",
        ),
    ],
)
def test_refactor_actions_use_explicit_copy_and_collapsed_technical_disclosure(
    monkeypatch, alternative, heading, field_label, button_label
):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    review = successful_review(source)
    state = {ANALYSIS_KEY: review.original_analysis, REVIEW_KEY: review}
    if alternative:
        state[REFACTOR_KEY] = valid_refactor(
            source, review, "def focused(value=None):\n    return value\n"
        )
    recorder = install_recorder(monkeypatch)

    app.render_refactor_action(document, state, alternative=alternative)

    markdown = [args[0] for name, args, _kwargs in recorder.calls if name == "markdown"]
    assert heading in markdown
    assert ("How CodeSage generates and checks the suggestion", False) in recorder.expanders
    text_area = next(call for call in recorder.calls if call[0] == "text_area")
    assert text_area[1][0] == field_label
    assert text_area[2]["placeholder"].startswith("For example:")
    assert text_area[2]["max_chars"] == 500
    captions = [args[0] for name, args, _kwargs in recorder.calls if name == "caption"]
    assert "0/500 characters" in captions
    buttons = [args[0] for name, args, _kwargs in recorder.calls if name == "button"]
    assert button_label in buttons


def test_completed_state_replaces_hero_with_header_and_segmented_workspace(monkeypatch):
    document = normalise_example_source()
    analysis = analyse_script(document.text)
    state = {SOURCE_KEY: document, ANALYSIS_KEY: analysis}
    recorder = install_recorder(monkeypatch)
    monkeypatch.setattr(app.st, "session_state", state)
    monkeypatch.setattr(app, "render_sidebar", lambda _: document)

    app.main()

    assert recorder.tab_sets == []
    assert recorder.segmented_options == [app.WORKSPACE_VIEWS]
    subheaders = [args[0] for name, args, kwargs in recorder.calls if name == "subheader"]
    assert "Your Python maintainability coach" not in subheaders
    titles = [args[0] for name, args, kwargs in recorder.calls if name == "title"]
    assert "CodeSage" in titles
    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    assert "## CodeSage" not in markdown
    captions = [args[0] for name, args, kwargs in recorder.calls if name == "caption"]
    assert f"{document.display_name} · Built-in example" in captions
    metric_values = {label: value for kind, label, value in recorder.calls if kind == "metric"}
    assert metric_values["Analysis"] == "Complete"
    assert "Hotspots" in metric_values
    assert "Static findings" in metric_values
    assert metric_values["AI review"] == "Optional"
    primary_actions = [
        args[0]
        for name, args, kwargs in recorder.calls
        if name == "button" and kwargs.get("type") == "primary"
    ]
    assert primary_actions == ["Get AI review"]
    navigation_index = next(
        index for index, call in enumerate(recorder.calls) if call[0] == "segmented_control"
    )
    review_action_index = next(
        index
        for index, (name, args, kwargs) in enumerate(recorder.calls)
        if name == "button" and args[0] == "Get AI review"
    )
    assert navigation_index < review_action_index
    secondary_actions = [
        args[0]
        for name, args, kwargs in recorder.calls
        if name == "button" and kwargs.get("type") == "secondary"
    ]
    assert secondary_actions == ["Print-friendly report"]


def test_completed_review_transitions_once_to_the_next_action(monkeypatch):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    analysis = analyse_script(source)
    state = {SOURCE_KEY: document, ANALYSIS_KEY: analysis}
    recorder = install_recorder(monkeypatch)
    recorder.button_results["Get AI review"] = True
    calls = []
    reruns = []

    def complete_review(target_state, target_document, **kwargs):
        calls.append((target_document, kwargs))
        target_state[REVIEW_KEY] = successful_review(source)
        return None

    monkeypatch.setattr(app, "handle_actions", complete_review)
    monkeypatch.setattr(app.st, "rerun", lambda: reruns.append("rerun"))

    app.render_review_action(document, state)

    assert len(calls) == 1
    assert calls[0][1] == {"analyse_clicked": False, "review_clicked": True}
    assert reruns == ["rerun"]
    assert REVIEW_KEY in state
    assert state[app.WORKSPACE_VIEW_STATE_KEY] == "AI review"
    assert state[app.SCROLL_TO_TOP_KEY] is True


def test_print_action_enters_dedicated_mode_before_main_renders(monkeypatch):
    document = normalise_example_source()
    state = {
        SOURCE_MODE_KEY: EXAMPLE_MODE,
        SOURCE_KEY: document,
        ANALYSIS_KEY: analyse_script(document.text),
    }
    recorder = install_recorder(monkeypatch)
    recorder.button_results["Print-friendly report"] = True

    app.render_workspace_header(document, state)

    assert state[app.PRINT_MODE_KEY] is True
    print_call = next(
        (args, kwargs)
        for name, args, kwargs in recorder.calls
        if name == "button" and args[0] == "Print-friendly report"
    )
    assert print_call[1]["on_click"] is app.set_print_mode
    monkeypatch.setattr(app.st, "session_state", state)
    monkeypatch.setattr(
        app,
        "render_sidebar",
        lambda _: pytest.fail("dedicated print mode must bypass the interactive sidebar"),
    )
    recorder.tab_sets.clear()
    recorder.segmented_options.clear()

    app.main()

    assert recorder.tab_sets == []
    assert recorder.segmented_options == []
    assert any(
        name == "title" and args[0] == "CodeSage report" for name, args, kwargs in recorder.calls
    )


def test_sidebar_restores_the_analysed_source_after_print_widget_cleanup(monkeypatch):
    document = normalise_example_source()
    analysis = analyse_script(document.text)
    state = {
        SOURCE_KEY: document,
        ANALYSIS_KEY: analysis,
        app.SOURCE_ROUTE_MEMORY_KEY: EXAMPLE_MODE,
    }
    recorder = install_recorder(monkeypatch)
    monkeypatch.setattr(app.st, "sidebar", recorder)

    restored = app.render_sidebar(state)

    assert restored == document
    assert state[ANALYSIS_KEY] is analysis
    radio_call = next((args, kwargs) for name, args, kwargs in recorder.calls if name == "radio")
    assert radio_call[1]["index"] == 3


def test_workspace_and_print_report_reuse_the_same_stored_results(monkeypatch):
    result = reviewed_issue_refactor(addressed=2)
    document = normalise_pasted_source("def focused(values=[]):\n    return values\n")
    review = ReviewResult(
        result.original_analysis,
        result.evidence,
        result.review,
        None,
        None,
        True,
    )
    state = {
        SOURCE_KEY: document,
        ANALYSIS_KEY: result.original_analysis,
        REVIEW_KEY: review,
        REFACTOR_KEY: result,
    }
    identities = {key: id(value) for key, value in state.items()}
    analysis_snapshot = asdict(result.original_analysis)
    recorder = install_recorder(monkeypatch)

    app.render_workspace(document, state)
    app.render_print_report(
        state,
        timestamp=datetime(2026, 7, 21, 10, 30, tzinfo=timezone.utc),
    )

    assert recorder.tab_sets == []
    assert recorder.segmented_options == [app.WORKSPACE_VIEWS]
    assert {key: id(state[key]) for key in identities} == identities
    assert asdict(result.original_analysis) == analysis_snapshot
    assert state[REVIEW_KEY] is review
    assert state[REFACTOR_KEY] is result
    assert any(
        name == "title" and args[0] == "CodeSage report" for name, args, kwargs in recorder.calls
    )
    assert any(
        name == "caption" and "21 July 2026 at 10:30 UTC" in args[0]
        for name, args, kwargs in recorder.calls
    )


def test_print_mode_toggle_return_action_and_css_contract(monkeypatch):
    state = {}
    app.set_print_mode(state, True)
    assert state == {app.PRINT_MODE_KEY: True}
    recorder = install_recorder(monkeypatch)
    recorder.button_results["Return to app"] = True

    assert app.render_print_report(state) is False
    assert app.PRINT_MODE_KEY not in state
    assert state[app.SCROLL_TO_TOP_KEY] is True
    assert not any(options.get("unsafe_allow_javascript") for _, options in recorder.html_values)
    assert "@media print" in app.APP_STYLES
    for selector in (
        '[data-testid="stSidebar"]',
        '[data-testid="stHeader"]',
        '[data-testid="stToolbar"]',
        '[data-testid="stButton"]',
        '[data-testid="stTabs"]',
        '[data-testid="stTextInput"]',
        '[data-testid="stTextArea"]',
        '[data-testid="stFileUploader"]',
        '[data-testid="stRadio"]',
        ".st-key-landing_workspace",
        ".st-key-ready_workspace",
        ".screen-only",
        ".st-key-print_report",
    ):
        assert selector in app.APP_STYLES
    assert ".st-key-print_report { display: block !important" in app.APP_STYLES
    assert '[data-testid="stSegmentedControl"]' in app.APP_STYLES
    assert ".st-key-workspace_navigation" in app.APP_STYLES
    assert ".severity-high { background: #f9e2d9" in app.APP_STYLES
    assert "break-inside: avoid-page" in app.APP_STYLES
    assert "Print or save as PDF using Ctrl+P on Windows or Command+P on macOS." in str(
        recorder.calls
    )


def test_print_report_is_linear_and_contains_completed_stage_content(monkeypatch):
    result = reviewed_issue_refactor(addressed=2)
    document = normalise_pasted_source("def focused(values=[]):\n    return values\n")
    review_response = result.review.model_copy(
        update={
            "suggested_tests": ["Capture the current result before changing the function."],
            "assumptions_or_limitations": ["Runtime callers were not observed."],
        }
    )
    review = ReviewResult(
        result.original_analysis,
        result.evidence,
        review_response,
        None,
        None,
        True,
    )
    state = {
        SOURCE_KEY: document,
        ANALYSIS_KEY: result.original_analysis,
        REVIEW_KEY: review,
        REFACTOR_KEY: result,
    }
    recorder = install_recorder(monkeypatch)

    assert app.render_print_report(
        state, timestamp=datetime(2026, 7, 21, 10, 30, tzinfo=timezone.utc)
    )

    assert recorder.tab_sets == []
    events = [(name, args[0]) for name, args, kwargs in recorder.calls if args]
    title_index = events.index(("title", "CodeSage report"))
    source_index = events.index(("markdown", "## Source"))
    timestamp_index = next(
        index
        for index, (name, value) in enumerate(events)
        if name == "caption" and str(value).startswith("Report generated")
    )
    summary_index = events.index(("markdown", "## Deterministic summary"))
    assert title_index < source_index < timestamp_index < summary_index
    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    assert markdown.index("## Source") < markdown.index("## Deterministic summary")
    assert "### Find hotspots" not in markdown
    assert "### Understand why" not in markdown
    assert "### Refactor carefully" not in markdown
    subheaders = [args[0] for name, args, kwargs in recorder.calls if name == "subheader"]
    assert "Your Python maintainability coach" not in subheaders
    assert "### Safety checks to run before refactoring" in markdown
    assert "### Re-run your safety checks" in markdown
    assert "**All reviewed static findings addressed**" in markdown
    assert {item.get("key") for item in recorder.container_options} >= {
        "screen_controls",
        "print_report",
        "refactor_metric_group",
    }


@pytest.mark.parametrize("mismatched_component", ["analysis", "review", "refactor"])
def test_print_report_rejects_mixed_source_digests(monkeypatch, mismatched_component):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    review = successful_review(source)
    refactor = valid_refactor(source, review, "def focused(value=None):\n    return value\n")
    other_analysis = analyse_script(hotspot_source("other"))
    state = {
        SOURCE_KEY: document,
        ANALYSIS_KEY: review.original_analysis,
        REVIEW_KEY: review,
        REFACTOR_KEY: refactor,
    }
    if mismatched_component == "analysis":
        state[ANALYSIS_KEY] = other_analysis
    elif mismatched_component == "review":
        state[REVIEW_KEY] = replace(review, original_analysis=other_analysis)
    else:
        state[REFACTOR_KEY] = replace(refactor, original_analysis=other_analysis)
    recorder = install_recorder(monkeypatch)

    app.render_print_report(state, timestamp=datetime(2026, 7, 21, tzinfo=timezone.utc))

    errors = [args[0] for name, args, kwargs in recorder.calls if name == "error"]
    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    assert errors == [
        "The report state is stale. Analyse the current source again before printing."
    ]
    assert "## Source" not in markdown


def test_github_print_report_uses_the_active_sessions_source_identity(monkeypatch):
    source = hotspot_source()
    url = "https://github.com/example/project/blob/main/sessions.py"
    document = replace(
        normalise_pasted_source(source),
        origin=SourceOrigin.GITHUB,
        display_name="sessions.py",
        external_reference=url,
    )
    review = successful_review(source)
    refactor = valid_refactor(source, review, "def focused(value=None):\n    return value\n")
    state = {
        SOURCE_KEY: document,
        ANALYSIS_KEY: review.original_analysis,
        REVIEW_KEY: review,
        REFACTOR_KEY: refactor,
    }
    recorder = install_recorder(monkeypatch)

    app.render_print_report(state, timestamp=datetime(2026, 7, 21, tzinfo=timezone.utc))

    writes = [str(args[0]) for name, args, kwargs in recorder.calls if name == "write" and args]
    assert any(item.startswith("sessions.py · github ·") for item in writes)
    assert not any("CodeSage example.py" in item for item in writes)


def test_only_the_static_local_scroll_javascript_and_no_external_print_component_exists():
    requirements = Path("requirements.txt").read_text(encoding="utf-8").lower()
    application = Path("app.py").read_text(encoding="utf-8").lower()
    for package in ("weasyprint", "reportlab", "fpdf", "pdfkit", "playwright"):
        assert package not in requirements
    assert "components.html" not in application
    assert application.count("unsafe_allow_javascript=true") == 1
    script = app.SCROLL_TO_TOP_SCRIPT.lower()
    assert "scrolltocodesagetop" in script
    assert "codesage-page-top" in script
    for selector in (
        "doc.scrollingelement",
        "doc.documentelement",
        "doc.body",
        '[data-testid="stmain"]',
        '[data-testid="stappviewcontainer"]',
        "section.main",
        "window.scrollto",
    ):
        assert selector in script
    assert "anchor.focus({preventscroll: true})" in script
    assert "[0, 50, 150, 300, 600]" in script
    assert "mutationobserver" in script
    assert "data-codesage-scroll-trigger" in script
    for forbidden in ("http://", "https://", "fetch(", "xmlhttprequest", "websocket", "eval("):
        assert forbidden not in script


def test_appendix_heading_and_every_subsection_are_present(monkeypatch):
    result = reviewed_issue_refactor(addressed=2)
    review = ReviewResult(
        result.original_analysis, result.evidence, result.review, None, None, True
    )
    recorder = install_recorder(monkeypatch)

    app.render_print_measurements_appendix(result.original_analysis, review, result)

    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    assert "## Measurements & evidence appendix" in markdown
    assert any(item.startswith("### All analysed code units (") for item in markdown)
    assert "### Configured hotspot thresholds" in markdown
    assert any(item.startswith("### Analysis warnings (") for item in markdown)
    assert "### Analysis exclusions (0)" in markdown
    assert "### Evidence used by the AI review" in markdown
    assert "### Complete before-and-after measurements" in markdown
    assert "### Structural verification results" in markdown


def test_appendix_retains_every_analysed_unit_row(monkeypatch):
    functions = "\n".join(f"def item_{number}(value):\n    return value\n" for number in range(80))
    analysis = analyse_script(functions)
    inventory = unit_inventory_rows(analysis)
    recorder = install_recorder(monkeypatch)

    app.render_print_measurements_appendix(analysis, None, None)

    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    assert f"### All analysed code units ({len(inventory)})" in markdown
    unit_table_rows = [
        row
        for table, kwargs in recorder.tables
        if kwargs.get("table") is True and table and "Qualified name" in table[0]
        for row in table
    ]
    assert len(unit_table_rows) == len(inventory)
    assert {row["Qualified name"] for row in unit_table_rows} == {
        row["Qualified name"] for row in inventory
    }


def test_appendix_chunks_long_unit_tables_without_losing_rows(monkeypatch):
    functions = "\n".join(f"def item_{number}(value):\n    return value\n" for number in range(90))
    analysis = analyse_script(functions)
    inventory = unit_inventory_rows(analysis)
    recorder = install_recorder(monkeypatch)

    app.render_print_measurements_appendix(analysis, None, None)

    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    part_labels = [item for item in markdown if item.startswith("**Part ")]
    assert len(part_labels) >= 2
    assert part_labels[0] == f"**Part 1 of {len(part_labels)}**"
    unit_tables = [
        table
        for table, kwargs in recorder.tables
        if kwargs.get("table") is True and table and "Qualified name" in table[0]
    ]
    total_rows = sum(len(table) for table in unit_tables)
    assert total_rows == len(inventory)


def test_appendix_includes_every_configured_threshold(monkeypatch):
    analysis = analyse_script("def focused(value):\n    return value\n")
    recorder = install_recorder(monkeypatch)

    app.render_print_measurements_appendix(analysis, None, None)

    threshold_table = next(
        table for table, kwargs in recorder.tables if table and "Threshold" in table[0]
    )
    assert len(threshold_table) == len(THRESHOLDS)


def test_appendix_prints_warnings_and_the_zero_warning_state(monkeypatch):
    with_warning = replace(
        analyse_script("def focused(value):\n    return value\n"),
        analysis_warnings=("Cyclomatic complexity unresolved for focused.",),
    )
    recorder = install_recorder(monkeypatch)
    app.render_print_measurements_appendix(with_warning, None, None)
    writes = [args[0] for name, args, kwargs in recorder.calls if name == "write" and args]
    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    assert "### Analysis warnings (1)" in markdown
    assert "- Cyclomatic complexity unresolved for focused." in writes

    without_warning = analyse_script("def focused(value):\n    return value\n")
    recorder = install_recorder(monkeypatch)
    app.render_print_measurements_appendix(without_warning, None, None)
    writes = [args[0] for name, args, kwargs in recorder.calls if name == "write" and args]
    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    assert "### Analysis warnings (0)" in markdown
    assert "None." in writes


def test_appendix_states_exclusions_explicitly(monkeypatch):
    analysis = analyse_script("def focused(value):\n    return value\n")
    recorder = install_recorder(monkeypatch)

    app.render_print_measurements_appendix(analysis, None, None)

    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    writes = [args[0] for name, args, kwargs in recorder.calls if name == "write" and args]
    assert "### Analysis exclusions (0)" in markdown
    assert "No exclusions apply to this Python script." in writes


def test_appendix_evidence_includes_only_cited_items_and_states_absence(monkeypatch):
    result = reviewed_issue_refactor(addressed=2)
    review = ReviewResult(
        result.original_analysis, result.evidence, result.review, None, None, True
    )
    cited_ids = {
        evidence_id for finding in review.response.findings for evidence_id in finding.evidence_ids
    }
    assert cited_ids < {item.evidence_id for item in review.evidence.items}
    recorder = install_recorder(monkeypatch)

    app.render_print_measurements_appendix(result.original_analysis, review, result)

    evidence_table = next(
        table for table, kwargs in recorder.tables if table and "Evidence ID" in table[0]
    )
    assert {row["Evidence ID"] for row in evidence_table} == cited_ids

    recorder = install_recorder(monkeypatch)
    app.render_print_measurements_appendix(result.original_analysis, None, None)
    writes = [args[0] for name, args, kwargs in recorder.calls if name == "write" and args]
    assert "No AI-review evidence is available because no AI review was requested." in writes


def test_appendix_includes_all_comparison_rows_and_warnings(monkeypatch):
    result = reviewed_issue_refactor(addressed=1)
    comparison = result.verification.comparison
    assert comparison.warnings
    recorder = install_recorder(monkeypatch)

    app.render_print_measurements_appendix(result.original_analysis, None, result)

    directional_tables = [
        table for table, kwargs in recorder.tables if table and table[0].get("Metric") is not None
    ]
    all_directional_rows = [row for table in directional_tables for row in table]
    assert len(all_directional_rows) == len(comparison.directional) + len(comparison.descriptive)
    writes = [args[0] for name, args, kwargs in recorder.calls if name == "write" and args]
    assert all(f"- {warning}" in writes for warning in comparison.warnings)


def test_appendix_states_no_before_after_measurements_when_refactor_absent(monkeypatch):
    analysis = analyse_script("def focused(value):\n    return value\n")
    recorder = install_recorder(monkeypatch)

    app.render_print_measurements_appendix(analysis, None, None)

    writes = [args[0] for name, args, kwargs in recorder.calls if name == "write" and args]
    assert (
        "No before-and-after measurements are available because no verified suggested "
        "refactor is present." in writes
    )
    assert (
        "No structural verification results are available because no verified suggested "
        "refactor is present." in writes
    )


def test_appendix_includes_all_structural_rows_and_correct_totals(monkeypatch):
    result = reviewed_issue_refactor(addressed=2)
    structural = result.verification.comparison.structural
    recorder = install_recorder(monkeypatch)

    app.render_print_measurements_appendix(result.original_analysis, None, result)

    structural_tables = [
        table for table, kwargs in recorder.tables if table and "Category" in table[0]
    ]
    all_rows = [row for table in structural_tables for row in table]
    assert len(all_rows) == len(structural)
    counts = {
        status: sum(item.status.value == status for item in structural)
        for status in ("changed", "unchanged", "added", "removed", "unresolved")
    }
    writes = [args[0] for name, args, kwargs in recorder.calls if name == "write" and args]
    totals_line = next(item for item in writes if item.startswith("Changed:"))
    for status, count in counts.items():
        assert f"{status.title()}: {count}" in totals_line


def test_appendix_never_renders_raw_analysis_json(monkeypatch):
    result = reviewed_issue_refactor(addressed=2)
    review = ReviewResult(
        result.original_analysis, result.evidence, result.review, None, None, True
    )
    recorder = install_recorder(monkeypatch)

    app.render_print_measurements_appendix(result.original_analysis, review, result)

    assert not any(name == "json" for name, args, kwargs in recorder.calls)


def test_small_source_print_report_includes_both_complete_files(monkeypatch):
    result = reviewed_issue_refactor(addressed=2)
    document = normalise_pasted_source("def focused(values=[]):\n    return values\n")
    assert len(document.text) <= PRINT_COMPLETE_SOURCE_CHARACTER_LIMIT
    review = ReviewResult(
        result.original_analysis, result.evidence, result.review, None, None, True
    )
    state = {
        SOURCE_KEY: document,
        ANALYSIS_KEY: result.original_analysis,
        REVIEW_KEY: review,
        REFACTOR_KEY: result,
    }
    recorder = install_recorder(monkeypatch)

    app.render_print_report(state, timestamp=datetime(2026, 7, 21, tzinfo=timezone.utc))

    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    assert "### Compare the complete files" in markdown
    assert "### Complete source files" not in markdown
    code_sources = [
        value for value, language, height in recorder.code_values if language == "python"
    ]
    assert document.text in code_sources
    assert result.suggested_refactor in code_sources


def test_large_source_print_report_omits_complete_files_with_character_count_notice(monkeypatch):
    padding = "#" * (PRINT_COMPLETE_SOURCE_CHARACTER_LIMIT + 500)
    large_text = f"{padding}\ndef focused(values=[]):\n    return values\n"
    document = normalise_pasted_source(large_text)
    assert len(document.text) > PRINT_COMPLETE_SOURCE_CHARACTER_LIMIT
    review = successful_review(large_text)
    result = valid_refactor(
        large_text,
        review,
        f"{padding}\ndef focused(values=None):\n    return [] if values is None else values\n",
    )
    state = {
        SOURCE_KEY: document,
        ANALYSIS_KEY: review.original_analysis,
        REVIEW_KEY: review,
        REFACTOR_KEY: result,
    }
    recorder = install_recorder(monkeypatch)

    app.render_print_report(state, timestamp=datetime(2026, 7, 21, tzinfo=timezone.utc))

    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    assert "### Compare the complete files" not in markdown
    assert "### Complete source files" in markdown
    infos = [args[0] for name, args, kwargs in recorder.calls if name == "info"]
    notice = next(item for item in infos if "omitted from this PDF" in item)
    assert f"{len(document.text):,} characters" in notice
    assert "The complete files remain available in the CodeSage app." in notice
    assert "### Current verified changed hotspot" in markdown
    assert recorder.code_values
    assert any(language == "diff" for _value, language, _height in recorder.code_values)
    code_sources = [
        value for value, language, height in recorder.code_values if language == "python"
    ]
    assert document.text not in code_sources
    assert result.suggested_refactor not in code_sources


def test_summary_first_rendering_is_bounded_complete_and_does_not_mutate(monkeypatch):
    functions = "\n".join(f"def item_{number}(value):\n    return value\n" for number in range(80))
    analysis = analyse_script(functions)
    original = asdict(analysis)
    recorder = install_recorder(monkeypatch)
    app.render_analysis(analysis, ai_eligible=True)
    app.render_analysis_technical(analysis)

    assert asdict(analysis) == original
    assert (f"All analysed code units ({len(analysis.units)})", False) in recorder.expanders
    assert ("Configured hotspot thresholds", False) in recorder.expanders
    assert ("Raw analysis data — advanced", False) in recorder.expanders
    inventory = next(table for table, options in recorder.tables if options.get("height") == 420)
    assert len(inventory) == len(analysis.units)
    assert not any(call[0] == "json" for call in recorder.calls[:-1])


def test_overview_counts_all_findings_but_shows_only_the_priority_hotspot(monkeypatch):
    source = (
        "\n\n".join(f"def issue_{number}(values=[]):\n    return values" for number in range(5))
        + "\n"
    )
    document = normalise_pasted_source(source)
    analysis = analyse_script(source)
    assert len(analysis.hotspots) == 3
    assert analysis_summary(analysis, ai_eligible=True)["Threshold-triggering hotspots"] == 5
    recorder = install_recorder(monkeypatch)

    app.render_overview(document, {ANALYSIS_KEY: analysis})

    metric_values = [(label, value) for kind, label, value in recorder.calls if kind == "metric"]
    assert ("Priority hotspots", 5) in metric_values
    assert metric_values[2] == ("Static findings", 5)
    hotspot_headings = [
        args[0]
        for name, args, kwargs in recorder.calls
        if name == "markdown" and args[0].startswith("#### ")
    ]
    assert len(hotspot_headings) == 1
    assert hotspot_headings[0].startswith("#### 1. issue_0")


def test_syntax_invalid_source_is_not_presented_as_ai_eligible(monkeypatch):
    document = normalise_pasted_source("def broken(\n")
    analysis = analyse_script(document.text)
    assert document.ai_eligible
    assert not analysis.syntax_valid
    recorder = install_recorder(monkeypatch)

    app.render_overview(document, {ANALYSIS_KEY: analysis})

    metrics = {label: value for kind, label, value in recorder.calls if kind == "metric"}
    assert metrics["AI-review status"] == "Unavailable"


def test_small_technical_tables_are_content_sized(monkeypatch):
    source = hotspot_source()
    analysis = analyse_script(source)
    review = successful_review(source)
    refactor = valid_refactor(
        source,
        review,
        "def focused(value=None):\n    return value\n",
    )
    recorder = install_recorder(monkeypatch)

    app.render_analysis_technical(analysis)
    app.render_comparison_technical(refactor)

    assert recorder.tables
    for rows, options in recorder.tables:
        if len(rows) <= 12:
            assert options["height"] == "content"
        else:
            assert options["height"] in {320, 420}


def test_verified_comparison_renders_all_required_expandable_groups(monkeypatch):
    result = reviewed_issue_refactor(addressed=2)
    recorder = install_recorder(monkeypatch)

    app.render_before_after_comparisons(result)

    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    assert "### Full before-and-after comparisons" in markdown
    assert ("Complete directional comparisons", False) in recorder.expanders
    assert ("Complete descriptive comparisons", False) in recorder.expanders
    assert ("Complete structural verification", False) in recorder.expanders
    assert any(
        label.startswith("Complete comparison warnings") for label, _expanded in recorder.expanders
    )


def test_abstention_and_failure_explain_why_no_comparison_exists(monkeypatch):
    source = hotspot_source()
    review = successful_review(source)
    reason = "The measured evidence did not support a better targeted option."

    abstention_recorder = install_recorder(monkeypatch)
    app.render_before_after_comparisons(abstained_refactor(review, reason))
    abstention_markdown = [
        args[0] for name, args, kwargs in abstention_recorder.calls if name == "markdown"
    ]
    abstention_writes = [
        args[0] for name, args, kwargs in abstention_recorder.calls if name == "write" and args
    ]
    abstention_captions = [
        args[0] for name, args, kwargs in abstention_recorder.calls if name == "caption"
    ]
    assert "### No before-and-after comparison" in abstention_markdown
    assert any("no refactored file to compare" in item for item in abstention_writes)
    assert reason in abstention_captions
    assert "### Full before-and-after comparisons" not in abstention_markdown

    failure_recorder = install_recorder(monkeypatch)
    app.render_before_after_comparisons(failed_refactor(review))
    failure_markdown = [
        args[0] for name, args, kwargs in failure_recorder.calls if name == "markdown"
    ]
    failure_writes = [
        args[0] for name, args, kwargs in failure_recorder.calls if name == "write" and args
    ]
    assert "### No verified comparison available" in failure_markdown
    assert any("did not produce code that passed" in item for item in failure_writes)
    assert "### Full before-and-after comparisons" not in failure_markdown


def test_incomplete_success_never_leaves_a_blank_comparison_heading(monkeypatch):
    source = hotspot_source()
    review = successful_review(source)
    result = RefactorResult(
        review.original_analysis,
        review.evidence,
        review.response,
        "def focused(value=None):\n    return value\n",
        CandidateVerification(5000, 43, True, None, None, None, "Static checks only."),
        None,
        None,
    )
    recorder = install_recorder(monkeypatch)

    app.render_before_after_comparisons(result)

    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    assert "### Comparison data unavailable" in markdown
    assert "### Full before-and-after comparisons" not in markdown


def test_warnings_and_exclusions_remain_accessible(monkeypatch):
    analysis = replace(
        analyse_script("def add(a, b):\n    return a + b\n"),
        analysis_warnings=("A measured result could not be resolved.",),
    )
    recorder = install_recorder(monkeypatch)
    app.render_analysis_technical(analysis)
    assert ("Analysis warnings (1)", True) in recorder.expanders
    assert ("Analysis exclusions (0)", False) in recorder.expanders


def test_zero_hotspot_message_is_exact_and_small_file_summary_is_visible(monkeypatch):
    analysis = analyse_script("def add(a, b):\n    return a + b\n")
    recorder = install_recorder(monkeypatch)
    app.render_analysis(analysis, ai_eligible=True)
    info_messages = [args[0] for name, args, kwargs in recorder.calls if name == "info"]
    assert "No threshold-based maintainability hotspots were found." in info_messages
    metric_labels = [label for kind, label, value in recorder.calls if kind == "metric"]
    assert {
        "Syntax",
        "Physical lines",
        "SLOC",
        "Threshold-triggering hotspots",
        "AI review eligible",
    } <= set(metric_labels)


@pytest.mark.parametrize(
    ("score", "rank", "band"),
    [
        (1, "A", "1–5"),
        (5, "A", "1–5"),
        (6, "B", "6–10"),
        (10, "B", "6–10"),
        (11, "C", "11–20"),
        (20, "C", "11–20"),
        (21, "D", "21–30"),
        (30, "D", "21–30"),
        (31, "E", "31–40"),
        (40, "E", "31–40"),
        (41, "F", "41+"),
    ],
)
def test_complexity_rank_explanation_uses_each_radon_boundary(score, rank, band):
    displayed_band, explanation = app.complexity_rank_details(score, rank)
    assert displayed_band == band
    assert f"Complexity {score} is rank {rank}" in explanation
    assert f"{band} band" in explanation
    assert "not an overall code-quality grade" in explanation


def test_hotspot_renders_one_content_sized_complexity_guide(monkeypatch):
    source = (
        "def focused(a, b, c, d):\n"
        "    if a:\n"
        "        if b:\n"
        "            if c:\n"
        "                if d:\n"
        "                    return 1\n"
        "    return 0\n"
    )
    analysis = analyse_script(source)
    recorder = install_recorder(monkeypatch)

    app.render_priority_hotspots(analysis, limit=1)

    assert recorder.expanders.count(("How complexity ranks work", False)) == 1
    rank_table = next(
        rows for rows, options in recorder.tables if options.get("height") == "content"
    )
    assert [row["Rank"] for row in rank_table] == list("ABCDEF")
    metric_values = {label: value for kind, label, value in recorder.calls if kind == "metric"}
    assert "score" in metric_values["Complexity rank"]
    captions = [args[0] for name, args, _kwargs in recorder.calls if name == "caption"]
    assert any("not an overall code-quality grade" in caption for caption in captions)


def test_verified_refactor_renders_only_safe_side_by_side_source(monkeypatch):
    source = hotspot_source()
    review = successful_review(source)
    replacement = "def focused(value=None):\n    return value\n"
    result = valid_refactor(source, review, replacement)
    recorder = install_recorder(monkeypatch)
    app.render_refactor(result, source)
    assert recorder.code_values[0][1:] == ("diff", 320)
    assert recorder.code_values[1:] == [
        (source, "python", 420),
        (replacement, "python", 420),
    ]
    assert ("View before-and-after files side by side", False) in recorder.expanders
    diff_text = recorder.code_values[0][0]
    assert "--- Original code" in diff_text
    assert "+++ Suggested refactor" in diff_text
    assert "def focused(value=[])" in diff_text
    assert "def focused(value=None)" in diff_text
    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    writes = [args[0] for name, args, kwargs in recorder.calls if name == "write" and args]
    assert "### Re-run your safety checks" in markdown
    assert any(
        value.startswith("CodeSage has checked the refactor statically but has not executed it")
        for value in writes
    )
    warning_text = " ".join(
        str(args[0]) for name, args, kwargs in recorder.calls if name == "warning" and args
    )
    assert "behavioural equivalence" in warning_text


def test_refactor_summary_uses_readable_targets_smells_and_structural_metrics(monkeypatch):
    source = hotspot_source()
    review = successful_review(source)
    replacement = "def focused(value=None):\n    return value\n"
    result = valid_refactor(source, review, replacement)
    result = replace(
        result,
        verification=replace(result.verification, target_names=("focused",)),
    )
    recorder = install_recorder(monkeypatch)
    app.render_refactor(result, source)

    writes = [args for name, args, kwargs in recorder.calls if name == "write"]
    assert ("Changed target:", "focused") in writes
    assert ("Correction attempt:", "Not needed") in writes
    metric_labels = [label for kind, label, value in recorder.calls if kind == "metric"]
    assert metric_labels[:3] == ["Nesting depth", "Static findings", "Complexity"]
    assert not any(len(args) == 1 and isinstance(args[0], dict) for args in writes)


@pytest.mark.parametrize(
    ("addressed", "label"),
    [
        (2, "All reviewed static findings addressed"),
        (1, "Some reviewed static findings remain"),
        (0, "Reviewed static findings remain"),
    ],
)
def test_refactor_outcome_classifies_addressed_issue_count(addressed, label):
    result = reviewed_issue_refactor(addressed=addressed)
    comparison_before = result.verification.comparison
    summary = refactor_outcome_summary(result)
    assert summary.label == label
    assert result.verification.comparison is comparison_before


def test_complete_refactor_outcome_is_explicitly_static_and_does_not_overclaim():
    summary = refactor_outcome_summary(reviewed_issue_refactor(addressed=2))
    assert summary.label == "All reviewed static findings addressed"
    assert summary.explanation == (
        "This refactor addresses both static maintainability findings identified for focused."
    )
    combined = f"{summary.label} {summary.explanation}".lower()
    for overclaim in ("runtime defect", "behaviourally equivalent", "correct", "better overall"):
        assert overclaim not in combined


def test_partial_outcome_explains_remaining_threshold_and_complexity_tradeoff():
    summary = refactor_outcome_summary(reviewed_issue_refactor(addressed=1))
    assert summary.label == "Some reviewed static findings remain"
    assert summary.explanation == "This refactor addresses 1 of 2 reviewed static findings."
    assert [issue.label for issue in summary.addressed] == ["Mutable default argument"]
    assert [issue.label for issue in summary.still_present] == ["Deep nesting"]
    assert summary.still_present[0].detail == (
        "Deep nesting remains at 4, which meets CodeSage's configured threshold of 4."
    )
    assert summary.other_measured_changes == (
        "Cyclomatic complexity increased from 6 to 7, but remains below the configured "
        "high-complexity threshold of 11.",
    )


def test_unresolved_or_missing_target_is_never_counted_as_addressed():
    unresolved = reviewed_issue_refactor(addressed=1, unresolved=True)
    summary = refactor_outcome_summary(unresolved)
    assert summary.label == "Unable to compare all reviewed static findings"
    assert summary.unable_to_compare[0].label == "Deep nesting"

    missing_analysis = analyse_script("value = 1\n")
    missing_comparison = compare_scripts(unresolved.original_analysis, missing_analysis)
    verification = replace(
        unresolved.verification,
        analysis=missing_analysis,
        comparison=missing_comparison,
    )
    missing = replace(unresolved, verification=verification)
    missing_summary = refactor_outcome_summary(missing)
    assert missing_summary.label == "Unable to compare all reviewed static findings"
    assert not missing_summary.addressed


def test_partial_resolution_remains_displayable_and_keeps_alternative_action(monkeypatch):
    result = reviewed_issue_refactor(addressed=1)
    monkeypatch.setattr(
        app,
        "handle_refactor_action",
        lambda *args, **kwargs: pytest.fail("rendering must not trigger a model action"),
    )
    recorder = install_recorder(monkeypatch)
    app.render_refactor(result, "def focused(values=[]):\n    return values\n")
    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    assert "### Refactor outcome" in markdown
    assert "**Some reviewed static findings remain**" in markdown
    assert recorder.code_values
    assert recorder.metric_options[:3] == [
        ("Nesting depth", "5 → 4", {"delta": "Improved", "delta_color": "off"}),
        (
            "Static findings",
            "2 → 1",
            {"delta": "Partially addressed", "delta_color": "off"},
        ),
        ("Complexity", "6 → 7", {"delta": "Trade-off", "delta_color": "off"}),
    ]
    state = {REFACTOR_KEY: result}
    assert refactor_action_label(state) == "Generate a different refactor"


def test_large_refactor_code_and_repeated_warnings_are_bounded(monkeypatch):
    source = hotspot_source() + ("# original detail\n" * 500)
    review = successful_review(hotspot_source())
    replacement = "def focused(value=None):\n    return value\n" + ("# retained detail\n" * 500)
    result = valid_refactor(source, review, replacement)
    warnings = tuple(
        f"unit_{number} is absent under the same qualified name; metric comparisons are unresolved."
        for number in range(120)
    )
    comparison = replace(result.verification.comparison, warnings=warnings)
    verification = replace(
        result.verification,
        comparison=comparison,
        target_names=("focused",),
    )
    result = replace(result, verification=verification)
    recorder = install_recorder(monkeypatch)
    app.render_refactor(result, source)
    app.render_comparison_technical(result)

    assert ("View before-and-after files side by side", False) in recorder.expanders
    assert ("Complete comparison warnings (120)", False) in recorder.expanders
    assert recorder.code_values[0][1:] == ("diff", 320)
    assert recorder.code_values[1:] == [
        (source, "python", 420),
        (replacement, "python", 420),
    ]
    warning_calls = [call for call in recorder.calls if call[0] == "warning"]
    assert len(warning_calls) == 2
    warning_table = next(
        table for table, options in recorder.tables if options.get("height") == 320
    )
    assert len(warning_table) == 120


def test_accessible_ui_copy_and_obsolete_quota_copy_absent():
    application = Path("app.py").read_text(encoding="utf-8")
    ui_source = Path("src/codesage/ui.py").read_text(encoding="utf-8")
    visible = application + ui_source
    for expected in (
        "Analyse code",
        "Get AI review",
        "AI maintainability review",
        "Generate suggested refactor",
        "Generate a different refactor",
        "Original code",
        "Suggested refactor",
        "Measurements & evidence",
        "Compare the complete files",
        "View before-and-after files side by side",
        "Optional: get an evidence-based explanation",
    ):
        assert expected in visible
    for obsolete in (
        "Session AI allowance",
        "primary reviews",
        "candidate repairs",
        "candidate regeneration",
        "Complete rewritten file candidate",
        "Candidate verified",
        "Request AI review",
        "Try a different refactor",
        "View complete files",
    ):
        assert obsolete not in visible
    assert "grounded ai" not in visible.lower()


@pytest.mark.parametrize(
    ("outcome", "next_step_heading", "workflow_label"),
    (
        (
            ReviewOutcome.REFACTOR_RECOMMENDED,
            "### Next step: Generate a suggested refactor",
            "Available",
        ),
        (
            ReviewOutcome.NO_REFACTOR_NEEDED,
            "### No refactor recommended",
            "No change recommended",
        ),
        (
            ReviewOutcome.INSUFFICIENT_EVIDENCE,
            "### No refactor offered — insufficient evidence",
            "Insufficient evidence",
        ),
    ),
)
def test_every_successful_review_has_one_explicit_decision_before_coach(
    monkeypatch, outcome, next_step_heading, workflow_label
):
    source, review = choose_priority_item_review(outcome)
    document = normalise_pasted_source(source)
    state = {
        SOURCE_KEY: document,
        ANALYSIS_KEY: review.original_analysis,
        REVIEW_KEY: review,
        app.WORKSPACE_VIEW_STATE_KEY: "AI review",
    }
    recorder = install_recorder(monkeypatch)

    app.render_workspace(document, state)

    markdown = [args[0] for name, args, _kwargs in recorder.calls if name == "markdown" and args]
    assert markdown.count(next_step_heading) == 1
    assert markdown.index(next_step_heading) < markdown.index("### Ask CodeSage about this result")
    assert workflow_statuses(state)[2] == workflow_label
    generation_buttons = [
        args[0]
        for name, args, _kwargs in recorder.calls
        if name == "button" and args and args[0] == "Generate suggested refactor"
    ]
    assert len(generation_buttons) == (1 if outcome is ReviewOutcome.REFACTOR_RECOMMENDED else 0)


def test_high_severity_does_not_override_no_refactor_outcome():
    source, recommended = choose_priority_item_review()
    response = recommended.response.model_copy(
        update={
            "outcome": ReviewOutcome.NO_REFACTOR_NEEDED,
            "summary": "No targeted change is sufficiently useful.",
        }
    )
    review = ReviewResult(
        recommended.original_analysis,
        recommended.evidence,
        response,
        None,
        None,
        True,
    )

    decision = refactor_availability(review)

    assert source
    assert response.findings[0].priority == "high"
    assert decision.status is RefactorAvailabilityStatus.NO_REFACTOR_NEEDED
    assert decision.label == "No change recommended"


def test_choose_priority_item_regression_is_actionable_on_every_surface(monkeypatch):
    source, review = choose_priority_item_review()
    document = normalise_pasted_source(source)
    state = {
        SOURCE_KEY: document,
        ANALYSIS_KEY: review.original_analysis,
        REVIEW_KEY: review,
        app.WORKSPACE_VIEW_STATE_KEY: "Overview",
    }
    decision = refactor_availability(review)
    assert decision.status is RefactorAvailabilityStatus.AVAILABLE
    assert decision.target_names == ("choose_priority_item",)
    assert workflow_statuses(state)[2] == "Available"
    assert "Not offered" not in workflow_statuses(state)

    recorder = install_recorder(monkeypatch)
    app.render_workspace(document, state)
    captions = [args[0] for name, args, _kwargs in recorder.calls if name == "caption" and args]
    assert any(value.startswith("Refactor: Available") for value in captions)

    recorder.calls.clear()
    state[app.WORKSPACE_VIEW_STATE_KEY] = "AI review"
    app.render_workspace(document, state)
    assert any(
        name == "button" and args and args[0] == "Generate suggested refactor"
        for name, args, _kwargs in recorder.calls
    )

    recorder.calls.clear()
    state[app.WORKSPACE_VIEW_STATE_KEY] = "Refactor"
    app.render_workspace(document, state)
    assert any(
        name == "button" and args and args[0] == "Generate suggested refactor"
        for name, args, _kwargs in recorder.calls
    )

    recorder.calls.clear()
    app.render_print_report(state, timestamp=datetime(2026, 7, 21, tzinfo=timezone.utc))
    info_messages = [args[0] for name, args, _kwargs in recorder.calls if name == "info" and args]
    assert "A targeted refactor is available but has not yet been generated." in info_messages


@pytest.mark.parametrize(
    ("outcome", "expected"),
    (
        (
            ReviewOutcome.NO_REFACTOR_NEEDED,
            "The AI review did not recommend a targeted refactor.",
        ),
        (
            ReviewOutcome.INSUFFICIENT_EVIDENCE,
            "The AI review could not justify a targeted refactor from the available static "
            "evidence.",
        ),
    ),
)
def test_print_report_explains_each_non_actionable_review(monkeypatch, outcome, expected):
    source, review = choose_priority_item_review(outcome)
    document = normalise_pasted_source(source)
    state = {
        SOURCE_KEY: document,
        ANALYSIS_KEY: review.original_analysis,
        REVIEW_KEY: review,
    }
    recorder = install_recorder(monkeypatch)

    app.render_print_report(state, timestamp=datetime(2026, 7, 21, tzinfo=timezone.utc))

    info_messages = [args[0] for name, args, _kwargs in recorder.calls if name == "info" and args]
    assert expected in info_messages


def test_unsupported_recommendation_uses_correction_state_everywhere(monkeypatch):
    source, successful = choose_priority_item_review()
    document = normalise_pasted_source(source)
    failed = ReviewResult(
        successful.original_analysis,
        successful.evidence,
        None,
        "unsupported_refactor_recommendation",
        "Safe failure.",
        True,
    )
    state = {
        SOURCE_KEY: document,
        ANALYSIS_KEY: successful.original_analysis,
        REVIEW_ERROR_KEY: failed,
        app.WORKSPACE_VIEW_STATE_KEY: "Refactor",
    }

    assert workflow_statuses(state)[2] == "Review needs correction"
    recorder = install_recorder(monkeypatch)
    app.render_workspace(document, state)
    writes = [args[0] for name, args, _kwargs in recorder.calls if name == "write" and args]
    assert any("grounded target could not be validated" in value for value in writes)
    assert not any(
        name == "button" and args and args[0] == "Generate suggested refactor"
        for name, args, _kwargs in recorder.calls
    )

    recorder.calls.clear()
    app.render_print_report(state, timestamp=datetime(2026, 7, 21, tzinfo=timezone.utc))
    info_messages = [args[0] for name, args, _kwargs in recorder.calls if name == "info" and args]
    assert any("grounded target could not be validated" in value for value in info_messages)


def test_successful_grounding_correction_is_disclosed_once(monkeypatch):
    source = hotspot_source()
    review = replace(
        successful_review(source),
        grounding_correction_status=GroundingCorrectionStatus.SUCCEEDED,
        grounding_correction_attempted=True,
        initial_grounding_failure_code="invalid_evidence_id",
        initial_grounding_failure_detail="E9999",
    )
    recorder = install_recorder(monkeypatch)

    app.render_review(review)

    messages = [args[0] for name, args, _kwargs in recorder.calls if name == "info" and args]
    assert (
        messages.count("CodeSage corrected and revalidated the review's evidence references once.")
        == 1
    )


def test_failed_grounding_correction_shows_only_safe_bounded_details(monkeypatch):
    source = hotspot_source()
    successful = successful_review(source)
    failure = ReviewResult(
        successful.original_analysis,
        successful.evidence,
        None,
        "invalid_evidence_id",
        "PRIVATE-RAW-MODEL-OUTPUT",
        True,
        grounding_correction_status=GroundingCorrectionStatus.FAILED,
        grounding_correction_attempted=True,
        initial_grounding_failure_code="invalid_evidence_id",
        initial_grounding_failure_detail="E9999",
        correction_grounding_failure_code="evidence_source_mismatch",
        initial_response=successful.response,
    )
    recorder = install_recorder(monkeypatch)

    app.render_safe_error_detail(failure)

    rendered = "\n".join(str(args[0]) for _name, args, _kwargs in recorder.calls if args)
    assert "Initial validation failure: invalid_evidence_id" in rendered
    assert "Offending evidence reference: E9999" in rendered
    assert "Correction validation failure: evidence_source_mismatch" in rendered
    assert source not in rendered
    assert "PRIVATE-RAW-MODEL-OUTPUT" not in rendered
    assert "deterministic_evidence_catalogue" not in rendered


def test_failed_grounding_correction_can_be_retried_and_success_clears_error():
    source = hotspot_source()
    document = normalise_pasted_source(source)
    successful = successful_review(source)
    failure = ReviewResult(
        successful.original_analysis,
        successful.evidence,
        None,
        "invalid_evidence_id",
        "Safe failure.",
        True,
        grounding_correction_status=GroundingCorrectionStatus.FAILED,
        grounding_correction_attempted=True,
        initial_grounding_failure_code="invalid_evidence_id",
        initial_grounding_failure_detail="E9999",
        correction_grounding_failure_code="invalid_evidence_id",
        initial_response=successful.response,
    )
    results = iter((failure, successful))
    calls = []

    def reviewer(*_args):
        calls.append(True)
        return next(results)

    state = {SOURCE_KEY: document, ANALYSIS_KEY: successful.original_analysis}
    handle_actions(
        state,
        document,
        analyse_clicked=False,
        review_clicked=True,
        reviewer=reviewer,
    )
    assert REVIEW_KEY not in state
    assert state[REVIEW_ERROR_KEY] is failure

    handle_actions(
        state,
        document,
        analyse_clicked=False,
        review_clicked=True,
        reviewer=reviewer,
    )
    assert state[REVIEW_KEY] is successful
    assert REVIEW_ERROR_KEY not in state
    assert len(calls) == 2


def test_review_disclosure_explains_the_single_reference_correction(monkeypatch):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    state = {ANALYSIS_KEY: analyse_script(source)}
    recorder = install_recorder(monkeypatch)

    app.render_review_action(document, state)

    captions = [args[0] for name, args, _kwargs in recorder.calls if name == "caption" and args]
    assert (
        "CodeSage may make one additional request only when a parsed review's evidence "
        "references fail validation."
    ) in captions


def test_sidebar_and_complete_file_css_are_narrowly_scoped():
    styles = app.APP_STYLES
    assert '[data-testid="stSidebar"] [data-testid="stRadio"] label {' in styles
    assert '[data-testid="stSidebar"] [data-testid="stRadio"] label:focus-within' in styles
    assert '.st-key-complete_file_comparison [data-testid="stExpander"] summary' in styles
    assert '[data-testid="stSidebar"] p' not in styles
    assert '[data-testid="stSidebar"] label {' not in styles


def test_production_ui_freezes_scope_to_complete_python_scripts():
    application = Path("app.py").read_text(encoding="utf-8")
    presentation = Path("src/codesage/ui.py").read_text(encoding="utf-8")
    source_interface = Path("src/codesage/source.py").read_text(encoding="utf-8")
    normal_interface = application + presentation + source_interface

    assert "Try the built-in example" in application
    assert "single-script" in application
    assert "future work" not in application
    assert ".ipynb" not in normal_interface
    assert "Upload one Python file" in application
    assert "Public GitHub .py file URL" in application


def test_review_disclosure_and_heading_are_accessible():
    application = Path("app.py").read_text(encoding="utf-8")
    assert 'st.subheader("AI maintainability review")' in application
    assert "Based on your code and CodeSage's deterministic measurements." in application
    assert "reference the" in application and "relevant code locations" in application
    assert "does not " in application and "rewrite your code." in application


def test_review_is_summary_first_and_separates_educational_content(monkeypatch):
    base = successful_review(hotspot_source())
    response = base.response.model_copy(
        update={"assumptions_or_limitations": ["Runtime callers were not observed."]}
    )
    review = replace(base, response=response)
    recorder = install_recorder(monkeypatch)
    app.render_review(review)

    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    captions = [args[0] for name, args, kwargs in recorder.calls if name == "caption"]
    assert "### Maintainability opportunity identified" in markdown
    assert any("1 hotspot · 1 static finding · focused, lines" in caption for caption in captions)
    assert recorder.containers == [True, True, True]
    assert any("Severity: MEDIUM" in item for item in markdown)
    assert {
        "**Measured evidence**",
        "**Why this matters**",
        "**Recommended change**",
        "**Learning takeaway**",
        "### Safety checks to run before refactoring",
        "1. Run existing tests.",
    } <= set(markdown)
    writes = [args[0] for name, args, kwargs in recorder.calls if name == "write" and args]
    safety_explanation = next(
        value for value in writes if value.startswith("Run these checks on the original code first")
    )
    assert "After generating a refactor, run the same checks again." in safety_explanation
    assert "CodeSage has not created or executed these tests." in safety_explanation
    assert not any("[ ]" in item for item in markdown)
    assert ("What CodeSage cannot determine", False) in recorder.expanders
    assert ("Evidence details", False) in recorder.expanders
    assert ("Assumptions and limitations", False) in recorder.expanders
    evidence_table = next(
        table for table, options in recorder.tables if table and "Evidence IDs" in table[0]
    )
    assert evidence_table[0]["Evidence IDs"].startswith("E")
    assert "@L" in evidence_table[0]["Code location reference"]
    measured_table = next(
        table for table, options in recorder.tables if table and "Measured result" in table[0]
    )
    assert "Evidence IDs" not in measured_table[0]
    small_table_options = [
        options
        for table, options in recorder.tables
        if table and ("Measured result" in table[0] or "Evidence IDs" in table[0])
    ]
    assert all(options["height"] == "content" for options in small_table_options)


def test_readable_outcome_location_and_smell_labels():
    assert readable_outcome("no_refactor_needed") == "No refactor needed"
    assert readable_outcome("insufficient_evidence") == "Insufficient evidence"
    assert readable_source_reference("function:choose_priority_item:12@L12-L22") == (
        "choose_priority_item, lines 12–22"
    )
    assert readable_smell("choose_priority_item:deep_nesting") == "Deep nesting"
    assert readable_smell("choose_priority_item:mutable_default") == ("Mutable default argument")


def test_side_by_side_is_only_rendered_for_verified_refactor(monkeypatch):
    source = hotspot_source()
    review = successful_review(source)
    calls = []
    monkeypatch.setattr(app.st, "subheader", lambda value: calls.append(("heading", value)))
    monkeypatch.setattr(app.st, "caption", lambda value: None)
    monkeypatch.setattr(
        app.st, "columns", lambda count: [pytest.nullcontext(), pytest.nullcontext()]
    )
    app.render_refactor(failed_refactor(review), source)
    assert calls == [("heading", "Suggested refactor")]


def test_model_abstention_is_rendered_with_its_decision_reason(monkeypatch):
    source = hotspot_source()
    review = successful_review(source)
    abstained = RefactorResult(
        review.original_analysis,
        review.evidence,
        review.response,
        None,
        None,
        None,
        None,
        abstained=True,
        decision_reason="The mutable default is the only measured issue and is low risk.",
    )
    recorder = install_recorder(monkeypatch)

    app.render_refactor(abstained, source)

    subheaders = [args[0] for name, args, kwargs in recorder.calls if name == "subheader"]
    writes = [args[0] for name, args, kwargs in recorder.calls if name == "write" and args]
    captions = [args[0] for name, args, kwargs in recorder.calls if name == "caption"]
    infos = [args[0] for name, args, kwargs in recorder.calls if name == "info"]
    assert "Suggested refactor" in subheaders
    assert "No better targeted option identified" in infos
    assert any("did not identify a targeted refactoring option" in item for item in writes)
    assert "The mutable default is the only measured issue and is low risk." in captions


def test_verified_refactor_explicitly_separates_target_body_signature_and_preservation(
    monkeypatch,
):
    source = (
        "def focused(values=[]):\n    return values\n\n"
        "def helper(value):\n    return value\n\n"
        "class Box:\n    def read(self, value):\n        return value\n"
    )
    suggested = source.replace(
        "def focused(values=[]):\n    return values\n",
        "def focused(values=None):\n    return [] if values is None else values\n",
    )
    review = successful_review(source)
    result = valid_refactor(source, review, suggested)
    recorder = install_recorder(monkeypatch)

    app.render_refactor(result, source)

    successes = [args[0] for name, args, kwargs in recorder.calls if name == "success"]
    writes = [args[0] for name, args, kwargs in recorder.calls if name == "write" and args]
    captions = [args[0] for name, args, kwargs in recorder.calls if name == "caption"]
    assert "Code changed: Yes — focused was replaced and verified." in successes
    assert "Target implementation: Changed" in writes
    assert "Target signature: Changed" in writes
    assert any("Changed target: focused (lines 1–2)" in item for item in writes)
    assert any("Unrelated definitions preserved: 3" in item for item in writes)
    assert any("Added definitions: 0" in item for item in writes)
    assert any("Removed definitions: 0" in item for item in writes)
    assert any(
        "Structural preservation: 3 unrelated definitions unchanged" in item for item in captions
    )


def test_abstention_and_failed_result_never_claim_code_changed(monkeypatch):
    source = hotspot_source()
    review = successful_review(source)

    abstention_recorder = install_recorder(monkeypatch)
    app.render_refactor(abstained_refactor(review), source)
    abstention_infos = [
        args[0] for name, args, kwargs in abstention_recorder.calls if name == "info"
    ]
    assert "Code changed: No — the model did not identify a better targeted option." in (
        abstention_infos
    )

    failure_recorder = install_recorder(monkeypatch)
    app.render_refactor(failed_refactor(review), source)
    failure_warnings = [
        args[0] for name, args, kwargs in failure_recorder.calls if name == "warning"
    ]
    assert "Code changed: No verified change was produced." in failure_warnings


def test_unchanged_target_ast_is_not_presented_as_a_verified_refactor(monkeypatch):
    source = hotspot_source()
    review = successful_review(source)
    unchanged = valid_refactor(source, review, source)
    recorder = install_recorder(monkeypatch)

    app.render_refactor(unchanged, source)

    warnings = [args[0] for name, args, kwargs in recorder.calls if name == "warning"]
    successes = [args[0] for name, args, kwargs in recorder.calls if name == "success"]
    assert "Code changed: No verified change was produced." in warnings
    assert not any("Code changed: Yes" in item for item in successes)


def test_target_signature_status_is_independent_of_implementation_change(monkeypatch):
    source = hotspot_source()
    review = successful_review(source)
    body_only_change = valid_refactor(
        source,
        review,
        "def focused(value=[]):\n    return list(value)\n",
    )
    recorder = install_recorder(monkeypatch)

    app.render_refactor(body_only_change, source)

    writes = [args[0] for name, args, kwargs in recorder.calls if name == "write" and args]
    assert "Target implementation: Changed" in writes
    assert "Target signature: Unchanged" in writes


def test_gate_rejected_refactor_shows_no_verified_refactor_was_produced(monkeypatch):
    source = hotspot_source()
    review = successful_review(source)
    state = {
        REFACTOR_ERROR_KEY: RefactorResult(
            review.original_analysis,
            review.evidence,
            review.response,
            None,
            None,
            "refactor_verification_failed",
            "CodeSage could not verify a usable refactor. The AI review is still available.",
            CorrectionStatus.FAILED,
            True,
            True,
            ("complexity_regressed",),
            ("complexity_regressed",),
            gate_explanations=("Cyclomatic complexity increased from 6 to 7.",),
        )
    }
    recorder = install_recorder(monkeypatch)

    app._render_action_errors(state)

    errors = [args[0] for name, args, kwargs in recorder.calls if name == "error"]
    writes = [args[0] for name, args, kwargs in recorder.calls if name == "write" and args]
    assert "No verified refactor was produced." in errors
    assert "No code change is recommended from this request." in writes
    assert "- Cyclomatic complexity increased from 6 to 7." in writes


def _unchanged_notice(writes: list[str]) -> bool:
    return any(
        "current verified refactor shown above remains available and unchanged" in item
        for item in writes
    )


def test_alternative_gate_failure_displays_different_refactor_not_produced(monkeypatch):
    source = hotspot_source()
    review = successful_review(source)
    state = {
        REFACTOR_KEY: valid_refactor(
            source, review, "def focused(value=None):\n    return value\n"
        ),
        ALTERNATIVE_REFACTOR_ERROR_KEY: RefactorResult(
            review.original_analysis,
            review.evidence,
            review.response,
            None,
            None,
            "refactor_verification_failed",
            "CodeSage could not verify a usable refactor. The AI review is still available.",
            CorrectionStatus.FAILED,
            True,
            True,
            ("complexity_regressed",),
            ("complexity_regressed",),
            gate_explanations=("Deep nesting is still present in choose_priority_item.",),
        ),
    }
    recorder = install_recorder(monkeypatch)

    app._render_action_errors(state)

    errors = [args[0] for name, args, kwargs in recorder.calls if name == "error"]
    writes = [args[0] for name, args, kwargs in recorder.calls if name == "write" and args]
    assert "Different refactor not produced" in errors
    assert _unchanged_notice(writes)
    assert "- Deep nesting is still present in choose_priority_item." in writes
    assert "No verified refactor was produced." not in errors
    assert "No code change is recommended from this request." not in writes


def test_alternative_duplicate_failure_displays_dedicated_message(monkeypatch):
    source = hotspot_source()
    review = successful_review(source)
    state = {
        REFACTOR_KEY: valid_refactor(
            source, review, "def focused(value=None):\n    return value\n"
        ),
        ALTERNATIVE_REFACTOR_ERROR_KEY: RefactorResult(
            review.original_analysis,
            review.evidence,
            review.response,
            None,
            None,
            "refactor_verification_failed",
            "CodeSage could not verify a usable refactor. The AI review is still available.",
            CorrectionStatus.FAILED,
            True,
            True,
            ("alternative_not_different",),
            ("alternative_not_different",),
        ),
    }
    recorder = install_recorder(monkeypatch)

    app._render_action_errors(state)

    errors = [args[0] for name, args, kwargs in recorder.calls if name == "error"]
    writes = [args[0] for name, args, kwargs in recorder.calls if name == "write" and args]
    assert "No verified different refactoring option was produced." in errors
    assert _unchanged_notice(writes)
    assert "No code change is recommended from this request." not in writes


def test_alternative_technical_failure_displays_could_not_be_completed(monkeypatch):
    source = hotspot_source()
    review = successful_review(source)
    state = {
        REFACTOR_KEY: valid_refactor(
            source, review, "def focused(value=None):\n    return value\n"
        ),
        ALTERNATIVE_REFACTOR_ERROR_KEY: RefactorResult(
            review.original_analysis,
            review.evidence,
            review.response,
            None,
            None,
            "api_status_error",
            "OpenAI returned HTTP status 503.",
            api_error_detail=ApiErrorDetail(503, "req_xyz"),
        ),
    }
    recorder = install_recorder(monkeypatch)

    app._render_action_errors(state)

    errors = [args[0] for name, args, kwargs in recorder.calls if name == "error"]
    writes = [args[0] for name, args, kwargs in recorder.calls if name == "write" and args]
    assert "Different refactor request could not be completed" in errors
    assert "OpenAI could not complete this request (HTTP 503)." in errors
    assert _unchanged_notice(writes)
    assert ("Technical details", False) in recorder.expanders
    assert "No code change is recommended from this request." not in writes


def test_print_report_excludes_alternative_attempt_errors(monkeypatch):
    result = reviewed_issue_refactor(addressed=2)
    document = normalise_pasted_source("def focused(values=[]):\n    return values\n")
    review = ReviewResult(
        result.original_analysis, result.evidence, result.review, None, None, True
    )
    state = {
        SOURCE_KEY: document,
        ANALYSIS_KEY: result.original_analysis,
        REVIEW_KEY: review,
        REFACTOR_KEY: result,
        ALTERNATIVE_REFACTOR_ERROR_KEY: RefactorResult(
            result.original_analysis,
            result.evidence,
            result.review,
            None,
            None,
            "refactor_verification_failed",
            "CodeSage could not verify a usable refactor. The AI review is still available.",
            CorrectionStatus.FAILED,
            True,
            True,
            ("complexity_regressed",),
            ("complexity_regressed",),
            gate_explanations=("A distinctive private explanation.",),
        ),
    }
    recorder = install_recorder(monkeypatch)

    app.render_print_report(state, timestamp=datetime(2026, 7, 21, tzinfo=timezone.utc))

    errors = [args[0] for name, args, kwargs in recorder.calls if name == "error"]
    writes = [args[0] for name, args, kwargs in recorder.calls if name == "write" and args]
    assert "Different refactor not produced" not in errors
    assert not any("A distinctive private explanation." in item for item in writes)
    assert {"refactor_generation_action", "alternative_refactor_attempt_status"}.isdisjoint(
        {item.get("key") for item in recorder.container_options}
    )


def test_print_css_hides_alternative_generation_controls_and_status():
    assert ".st-key-refactor_generation_action" in app.APP_STYLES
    assert ".st-key-alternative_refactor_attempt_status" in app.APP_STYLES


def test_interactive_workspace_shows_scoped_alternative_failure_in_screen_only_containers(
    monkeypatch,
):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    review = successful_review(source)
    refactor = valid_refactor(source, review, "def focused(value=None):\n    return value\n")
    state = {
        SOURCE_KEY: document,
        ANALYSIS_KEY: review.original_analysis,
        REVIEW_KEY: review,
        REFACTOR_KEY: refactor,
        ALTERNATIVE_REFACTOR_ERROR_KEY: RefactorResult(
            review.original_analysis,
            review.evidence,
            review.response,
            None,
            None,
            "refactor_verification_failed",
            "CodeSage could not verify a usable refactor. The AI review is still available.",
            CorrectionStatus.FAILED,
            True,
            True,
            ("complexity_regressed",),
            ("complexity_regressed",),
            gate_explanations=("Deep nesting remains.",),
        ),
        app.WORKSPACE_VIEW_STATE_KEY: "Refactor",
    }
    recorder = install_recorder(monkeypatch)

    app.render_workspace(document, state)

    errors = [args[0] for name, args, kwargs in recorder.calls if name == "error"]
    assert "Different refactor not produced" in errors
    keys = {item.get("key") for item in recorder.container_options}
    assert {"refactor_generation_action", "alternative_refactor_attempt_status"} <= keys


def test_report_never_shows_both_verified_and_unqualified_no_code_change(monkeypatch):
    result = reviewed_issue_refactor(addressed=2)
    document = normalise_pasted_source("def focused(values=[]):\n    return values\n")
    review = ReviewResult(
        result.original_analysis, result.evidence, result.review, None, None, True
    )
    state = {
        SOURCE_KEY: document,
        ANALYSIS_KEY: result.original_analysis,
        REVIEW_KEY: review,
        REFACTOR_KEY: result,
    }
    recorder = install_recorder(monkeypatch)

    app.render_print_report(state, timestamp=datetime(2026, 7, 21, tzinfo=timezone.utc))

    successes = [args[0] for name, args, kwargs in recorder.calls if name == "success"]
    writes = [args[0] for name, args, kwargs in recorder.calls if name == "write" and args]
    assert "Verified static maintainability improvement" in successes
    assert "No code change is recommended from this request." not in writes
    assert not any("No code change is recommended" in item for item in writes)


def test_all_known_failure_codes_have_accessible_messages():
    assert "refactor_verification_failed" in FAILURE_MESSAGES
    assert "missing_grounding_reference" in FAILURE_MESSAGES
    for code, message in FAILURE_MESSAGES.items():
        assert failure_message(code) == message
        assert message


def test_no_quota_symbols_remain():
    sources = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in ("src/codesage/config.py", "src/codesage/ui.py", "app.py")
    )
    for symbol in (
        "MAX_PRIMARY_REVIEWS_PER_SESSION",
        "MAX_REPAIR_REQUESTS_PER_SESSION",
        "PRIMARY_REVIEW_COUNT_KEY",
        "REPAIR_REQUEST_COUNT_KEY",
    ):
        assert symbol not in sources


def test_production_static_paths_do_not_execute_or_persist_source():
    production = "\n".join(
        Path(path).read_text(encoding="utf-8")
        for path in (
            "app.py",
            "src/codesage/analysis.py",
            "src/codesage/ai.py",
            "src/codesage/ui.py",
        )
    )
    assert "exec(" not in production
    assert "eval(" not in production
    assert "write_text(" not in production
    assert "write_bytes(" not in production


# --- "Ask CodeSage about this result" follow-up chat ---


def coach_reply(content="A concise explanation.", limitations=()):
    return CoachMessage("assistant", content, limitations=tuple(limitations))


def test_ask_codesage_unavailable_before_a_successful_review(monkeypatch):
    source = hotspot_source()
    analysis = analyse_script(source)
    document = normalise_pasted_source(source)
    failed_review = ReviewResult(analysis, None, None, "missing_api_key", "no key")
    state = {ANALYSIS_KEY: analysis, REVIEW_KEY: failed_review}
    recorder = install_recorder(monkeypatch)

    app.render_ask_codesage(document, state)

    assert not any(
        name == "markdown" and args and "Ask CodeSage about this result" in args[0]
        for name, args, kwargs in recorder.calls
    )


def test_ask_codesage_unavailable_with_no_review_at_all(monkeypatch):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    state = {}
    recorder = install_recorder(monkeypatch)

    app.render_ask_codesage(document, state)

    assert recorder.calls == []


def test_ask_codesage_available_after_a_successful_review(monkeypatch):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    review = successful_review(source)
    state = {ANALYSIS_KEY: review.original_analysis, REVIEW_KEY: review}
    recorder = install_recorder(monkeypatch)

    app.render_ask_codesage(document, state)

    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    assert "### Ask CodeSage about this result" in markdown
    captions = [args[0] for name, args, kwargs in recorder.calls if name == "caption"]
    assert any("does not execute the code" in item for item in captions)
    buttons = [args[0] for name, args, kwargs in recorder.calls if name == "button"]
    for starter in coach_starter_questions(refactor_available=False):
        assert starter in buttons
    for refactor_only in (
        "Explain what changed in the refactor.",
        "Why was a different refactor rejected?",
    ):
        assert refactor_only not in buttons


def test_ask_codesage_offers_refactor_specific_starters_when_a_verified_refactor_exists(
    monkeypatch,
):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    review = successful_review(source)
    refactor = valid_refactor(source, review, "def focused(value=None):\n    return value\n")
    state = {
        ANALYSIS_KEY: review.original_analysis,
        REVIEW_KEY: review,
        REFACTOR_KEY: refactor,
    }
    recorder = install_recorder(monkeypatch)

    app.render_ask_codesage(document, state)

    buttons = [args[0] for name, args, kwargs in recorder.calls if name == "button"]
    for starter in coach_starter_questions(refactor_available=True):
        assert starter in buttons


def test_same_conversation_is_shown_beneath_review_and_beneath_refactor(monkeypatch):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    review = successful_review(source)
    refactor = valid_refactor(source, review, "def focused(value=None):\n    return value\n")
    shared_history = (CoachMessage("user", "Why?"), coach_reply("Because of X."))
    state = {
        SOURCE_KEY: document,
        ANALYSIS_KEY: review.original_analysis,
        REVIEW_KEY: review,
        REFACTOR_KEY: refactor,
        COACH_CHAT_KEY: shared_history,
        app.WORKSPACE_VIEW_STATE_KEY: "AI review",
    }
    review_recorder = install_recorder(monkeypatch)
    app.render_workspace(document, state)
    review_writes = [args[0] for name, args, kwargs in review_recorder.calls if name == "markdown"]
    assert any("Because of X." in item for item in review_writes)

    state[app.WORKSPACE_VIEW_STATE_KEY] = "Refactor"
    refactor_recorder = install_recorder(monkeypatch)
    app.render_workspace(document, state)
    refactor_writes = [
        args[0] for name, args, kwargs in refactor_recorder.calls if name == "markdown"
    ]
    assert any("Because of X." in item for item in refactor_writes)
    assert state[COACH_CHAT_KEY] is shared_history


def test_source_change_clears_the_conversation():
    source = hotspot_source()
    review = successful_review(source)
    state = {
        SOURCE_KEY: normalise_pasted_source(source),
        ANALYSIS_KEY: review.original_analysis,
        REVIEW_KEY: review,
        COACH_CHAT_KEY: (coach_reply(),),
        COACH_CHAT_ERROR_KEY: object(),
        COACH_CHAT_CONTEXT_KEY: object(),
    }

    invalidate_stale_state(state, normalise_pasted_source(hotspot_source("changed")))

    assert COACH_CHAT_KEY not in state
    assert COACH_CHAT_ERROR_KEY not in state
    assert COACH_CHAT_CONTEXT_KEY not in state


def test_reanalysis_clears_the_conversation():
    source = hotspot_source()
    review = successful_review(source)
    state = {
        ANALYSIS_KEY: review.original_analysis,
        REVIEW_KEY: review,
        COACH_CHAT_KEY: (coach_reply(),),
        COACH_CHAT_ERROR_KEY: object(),
        COACH_CHAT_CONTEXT_KEY: object(),
    }

    handle_actions(state, source, analyse_clicked=True, review_clicked=False)

    assert COACH_CHAT_KEY not in state
    assert COACH_CHAT_ERROR_KEY not in state
    assert COACH_CHAT_CONTEXT_KEY not in state


def test_successful_alternative_refactor_clears_the_conversation():
    source = hotspot_source()
    review = successful_review(source)
    old = valid_refactor(source, review, "def focused(value=None):\n    return value\n")
    new = valid_refactor(source, review, "def focused(value=None):\n    return list(value or [])\n")
    state = {
        ANALYSIS_KEY: review.original_analysis,
        REVIEW_KEY: review,
        REFACTOR_KEY: old,
        COACH_CHAT_KEY: (coach_reply(),),
        COACH_CHAT_CONTEXT_KEY: object(),
    }

    handle_refactor_action(
        state,
        source,
        refactor_clicked=True,
        optional_instructions="A distinct approach.",
        refactorer=lambda *args, **kwargs: new,
    )

    assert state[REFACTOR_KEY] is new
    assert COACH_CHAT_KEY not in state
    assert COACH_CHAT_CONTEXT_KEY not in state


def test_user_can_explicitly_clear_the_conversation(monkeypatch):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    review = successful_review(source)
    state = {
        ANALYSIS_KEY: review.original_analysis,
        REVIEW_KEY: review,
        COACH_CHAT_KEY: (coach_reply(),),
        COACH_CHAT_CONTEXT_KEY: object(),
    }
    recorder = install_recorder(monkeypatch)
    recorder.button_results["Clear conversation"] = True
    monkeypatch.setattr(app.st, "rerun", lambda: None)

    app.render_ask_codesage(document, state)

    assert COACH_CHAT_KEY not in state
    assert COACH_CHAT_CONTEXT_KEY not in state


def test_clear_coach_chat_only_touches_chat_state():
    state = {
        REVIEW_KEY: object(),
        REFACTOR_KEY: object(),
        COACH_CHAT_KEY: (coach_reply(),),
        COACH_CHAT_ERROR_KEY: object(),
        COACH_CHAT_CONTEXT_KEY: object(),
    }
    clear_coach_chat(state)
    assert COACH_CHAT_KEY not in state
    assert COACH_CHAT_ERROR_KEY not in state
    assert COACH_CHAT_CONTEXT_KEY not in state
    assert REVIEW_KEY in state
    assert REFACTOR_KEY in state


def test_message_character_limit_is_visible_in_the_interface(monkeypatch):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    review = successful_review(source)
    state = {ANALYSIS_KEY: review.original_analysis, REVIEW_KEY: review}
    recorder = install_recorder(monkeypatch)

    app.render_ask_codesage(document, state)

    text_area_call = next(call for call in recorder.calls if call[0] == "text_area")
    assert str(COACH_MESSAGE_CHARACTER_LIMIT) in text_area_call[1][0]
    assert text_area_call[2]["max_chars"] == COACH_MESSAGE_CHARACTER_LIMIT
    captions = [args[0] for name, args, kwargs in recorder.calls if name == "caption"]
    assert f"0/{COACH_MESSAGE_CHARACTER_LIMIT} characters" in captions


def test_send_button_is_not_the_workspace_primary_action(monkeypatch):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    review = successful_review(source)
    state = {ANALYSIS_KEY: review.original_analysis, REVIEW_KEY: review}
    recorder = install_recorder(monkeypatch)

    app.render_ask_codesage(document, state)

    send_call = next(
        call for call in recorder.calls if call[0] == "button" and call[1][0] == "Send"
    )
    assert send_call[2]["type"] != "primary"


def test_only_explicit_submission_creates_an_api_request():
    source = hotspot_source()
    review = successful_review(source)
    state = {ANALYSIS_KEY: review.original_analysis, REVIEW_KEY: review}
    calls = []

    def asker(*args, **kwargs):
        calls.append(True)
        return CoachResult(coach_reply(), None, None, True)

    handle_coach_chat_action(state, source, message="Why?", submit_clicked=False, asker=asker)
    assert calls == []

    handle_coach_chat_action(state, source, message="Why?", submit_clicked=True, asker=asker)
    assert calls == [True]


def test_chat_requires_a_successful_review_before_submitting():
    source = hotspot_source()
    state = {}
    calls = []

    def asker(*args, **kwargs):
        calls.append(True)
        return CoachResult(coach_reply(), None, None, True)

    message = handle_coach_chat_action(
        state, source, message="Why?", submit_clicked=True, asker=asker
    )
    assert calls == []
    assert message == "Get a successful AI review before asking CodeSage about this result."


def test_chat_error_is_displayed_with_the_shared_safe_error_renderer(monkeypatch):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    review = successful_review(source)
    state = {
        ANALYSIS_KEY: review.original_analysis,
        REVIEW_KEY: review,
        COACH_CHAT_ERROR_KEY: CoachResult(
            None,
            "api_status_error",
            "OpenAI returned HTTP status 503.",
            True,
            ApiErrorDetail(503, "req_chat_1"),
        ),
    }
    recorder = install_recorder(monkeypatch)

    app.render_ask_codesage(document, state)

    errors = [args[0] for name, args, kwargs in recorder.calls if name == "error"]
    assert "OpenAI could not complete this request (HTTP 503)." in errors
    assert ("Technical details", False) in recorder.expanders


def test_successful_chat_answer_updates_only_chat_state():
    source = hotspot_source()
    review = successful_review(source)
    state = {ANALYSIS_KEY: review.original_analysis, REVIEW_KEY: review}
    review_identity = id(review)

    def asker(*args, **kwargs):
        return CoachResult(coach_reply("Because of X."), None, None, True)

    handle_coach_chat_action(state, source, message="Why?", submit_clicked=True, asker=asker)

    assert id(state[REVIEW_KEY]) == review_identity
    assert REFACTOR_KEY not in state
    assert len(state[COACH_CHAT_KEY]) == 2
    assert state[COACH_CHAT_KEY][0].role == "user"
    assert state[COACH_CHAT_KEY][1].content == "Because of X."


def test_ask_codesage_is_excluded_from_the_print_report(monkeypatch):
    source = hotspot_source()
    document = normalise_pasted_source(source)
    review = successful_review(source)
    state = {
        SOURCE_KEY: document,
        ANALYSIS_KEY: review.original_analysis,
        REVIEW_KEY: review,
        COACH_CHAT_KEY: (CoachMessage("user", "A private question."), coach_reply()),
    }
    recorder = install_recorder(monkeypatch)

    app.render_print_report(state, timestamp=datetime(2026, 7, 21, tzinfo=timezone.utc))

    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    writes = [args[0] for name, args, kwargs in recorder.calls if name == "write" and args]
    assert not any("Ask CodeSage about this result" in item for item in markdown)
    assert not any("A private question." in str(item) for item in writes + markdown)


def test_print_css_hides_the_ask_codesage_section():
    assert ".st-key-ask_codesage_section" in app.APP_STYLES
