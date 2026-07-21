from __future__ import annotations

from pathlib import Path
from dataclasses import asdict, replace
from datetime import datetime, timezone

import pytest

import app
from codesage.ai import (
    CandidateVerification,
    CorrectionStatus,
    Finding,
    RefactorResult,
    ReviewOutcome,
    ReviewResponse,
    ReviewResult,
)
from codesage.analysis import analyse_script
from codesage.comparison import compare_scripts
from codesage.evidence import build_evidence_package
from codesage.models import Severity, Smell
from codesage.source import normalise_example_source, normalise_pasted_source
from codesage.ui import (
    ANALYSIS_KEY,
    EXAMPLE_MODE,
    FAILURE_MESSAGES,
    REFACTOR_ERROR_KEY,
    REFACTOR_KEY,
    REVIEW_KEY,
    SOURCE_MODE_KEY,
    SOURCE_KEY,
    analysis_summary,
    failure_message,
    handle_actions,
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


def hotspot_source(name="focused"):
    return f"def {name}(value=[]):\n    return value\n"


def successful_review(source, outcome=ReviewOutcome.REFACTOR_RECOMMENDED):
    analysis = analyse_script(source)
    evidence = build_evidence_package(analysis)
    item = evidence.items[0]
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
    assert state[SOURCE_MODE_KEY] == EXAMPLE_MODE
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
    assert state[ANALYSIS_KEY].hotspots[0].qualified_name == "choose_priority_item"
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
    assert state[REFACTOR_ERROR_KEY].error_code == "refactor_verification_failed"


class ActionSlot:
    def __init__(self):
        self.buttons = []
        self.empty_calls = 0

    def button(self, label, **kwargs):
        self.buttons.append((label, kwargs))
        return False

    def empty(self):
        self.empty_calls += 1


def test_verified_refactor_immediately_replaces_initial_action_without_another_call():
    source = hotspot_source()
    review = successful_review(source)
    state = {ANALYSIS_KEY: review.original_analysis, REVIEW_KEY: review}
    calls = []
    initial_label = refactor_action_label(state)
    assert initial_label == "Generate suggested refactor"

    def refactorer(*args, **kwargs):
        calls.append("refactor")
        return valid_refactor(source, review, "def focused(value=None):\n    return value\n")

    handle_refactor_action(
        state,
        source,
        refactor_clicked=True,
        optional_instructions="Keep the change small.",
        refactorer=refactorer,
    )
    slot = ActionSlot()
    app.refresh_refactor_action(slot, state, initial_label)

    assert calls == ["refactor"]
    assert slot.empty_calls == 1
    assert slot.buttons == [
        (
            "Try a different refactor",
            {"type": "primary", "key": "try_different_refactor"},
        )
    ]
    assert state[REVIEW_KEY] is review


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
    assert message == "This AI review does not recommend a supported refactor."
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
    assert workflow_statuses(state) == ("Complete", "Available", "After AI review")
    recorder = install_recorder(monkeypatch)

    app.render_workflow(state)

    captions = [args[0] for name, args, kwargs in recorder.calls if name == "caption"]
    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    assert "1 Analyse code  →  2 AI review  →  3 Suggested refactor" in captions
    assert {
        "**1 · Analyse code**",
        "**2 · AI review**",
        "**3 · Suggested refactor**",
    } <= set(markdown)


def test_workflow_placeholder_refreshes_from_updated_state_without_another_action(monkeypatch):
    document = normalise_example_source()
    state = {}
    recorder = install_recorder(monkeypatch)

    class WorkflowSlot:
        def __init__(self):
            self.empty_calls = 0

        def empty(self):
            self.empty_calls += 1

        def container(self):
            return recorder

    slot = WorkflowSlot()
    handle_actions(state, document, analyse_clicked=True, review_clicked=False)
    app.refresh_workflow(slot, state)

    captions = [args[0] for name, args, kwargs in recorder.calls if name == "caption"]
    assert slot.empty_calls == 1
    assert "Complete" in captions
    assert "Available" in captions


class RenderingRecorder:
    def __init__(self):
        self.calls = []
        self.tables = []
        self.expanders = []
        self.containers = []
        self.container_options = []
        self.tab_sets = []
        self.metric_options = []
        self.code_values = []
        self.button_results = {}
        self.radio_result = None
        self.text_area_result = ""
        self.text_input_result = ""
        self.page_config = None
        self.html_values = []

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
        if self.radio_result is not None:
            return self.radio_result
        options = args[1]
        return options[kwargs.get("index", 0)]

    def text_area(self, *args, **kwargs):
        self.calls.append(("text_area", args, kwargs))
        return self.text_area_result

    def text_input(self, *args, **kwargs):
        self.calls.append(("text_input", args, kwargs))
        return self.text_input_result

    def file_uploader(self, *args, **kwargs):
        self.calls.append(("file_uploader", args, kwargs))
        return None

    def set_page_config(self, **kwargs):
        self.page_config = kwargs

    def html(self, value, **kwargs):
        self.html_values.append((value, kwargs))

    def __getattr__(self, name):
        return lambda *args, **kwargs: self.calls.append((name, args, kwargs))


def install_recorder(monkeypatch):
    recorder = RenderingRecorder()
    for name in (
        "columns",
        "metric",
        "expander",
        "container",
        "tabs",
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
    button_labels = [args[0] for name, args, kwargs in recorder.calls if name == "button"]
    assert button_labels.count("Load built-in example") == 1
    assert "Analyse code" not in button_labels
    assert "Print-friendly report" not in button_labels
    primary_actions = [
        args[0]
        for name, args, kwargs in recorder.calls
        if name == "button" and kwargs.get("type") == "primary"
    ]
    assert primary_actions == ["Load built-in example"]
    headings = [args[0] for name, args, kwargs in recorder.calls if name == "subheader"]
    assert "Your Python maintainability coach" in headings
    assert "How CodeSage helps" in headings
    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    assert "**Static analysis only. CodeSage never executes your code.**" in markdown
    assert {"### Find hotspots", "### Understand why", "### Refactor carefully"} <= set(markdown)
    paste_control = next(kwargs for name, args, kwargs in recorder.calls if name == "text_area")
    assert paste_control["height"] == 190
    application = Path("app.py").read_text(encoding="utf-8")
    assert "with st.sidebar:" in application


def test_sidebar_is_a_compact_light_source_panel_without_workflow_actions(monkeypatch):
    state = {}
    recorder = install_recorder(monkeypatch)
    recorder.radio_result = EXAMPLE_MODE
    monkeypatch.setattr(app.st, "sidebar", recorder)

    document = app.render_sidebar(state)

    assert document == normalise_example_source()
    button_labels = [args[0] for name, args, kwargs in recorder.calls if name == "button"]
    assert button_labels == []
    visible_copy = " ".join(str(args[0]) for name, args, kwargs in recorder.calls if args)
    assert "Source panel" in visible_copy
    assert "Active source" in visible_copy
    assert document.display_name in visible_copy
    for excluded in (
        "Print-friendly report",
        "Analyse code",
        "Get AI review",
        "Workflow",
        "future work",
    ):
        assert excluded not in visible_copy
    assert "background: #f8fafc" in app.APP_STYLES


def test_source_loaded_state_uses_full_workspace_and_one_analysis_action(monkeypatch):
    document = normalise_example_source()
    state = {}
    recorder = install_recorder(monkeypatch)
    recorder.button_results["Analyse code"] = True

    app.render_ready_to_analyse(document, state)

    assert recorder.tab_sets == []
    assert recorder.code_values == [(document.text, "python", 360)]
    markdown = [args[0] for name, args, kwargs in recorder.calls if name == "markdown"]
    assert "### Active source" in markdown
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
    [(False, "Generate suggested refactor"), (True, "Try a different refactor")],
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

    app.render_stage_action(document, state)

    primary_actions = [
        args[0]
        for name, args, kwargs in recorder.calls
        if name == "button" and kwargs.get("type") == "primary"
    ]
    assert primary_actions == [expected_action]


def test_completed_state_replaces_hero_with_header_actions_and_tabs(monkeypatch):
    document = normalise_example_source()
    analysis = analyse_script(document.text)
    state = {SOURCE_KEY: document, ANALYSIS_KEY: analysis}
    recorder = install_recorder(monkeypatch)
    monkeypatch.setattr(app.st, "session_state", state)
    monkeypatch.setattr(app, "render_sidebar", lambda _: document)

    app.main()

    assert recorder.tab_sets == [
        ("Overview", "AI review", "Suggested refactor", "Technical details")
    ]
    subheaders = [args[0] for name, args, kwargs in recorder.calls if name == "subheader"]
    assert "Your Python maintainability coach" not in subheaders
    captions = [args[0] for name, args, kwargs in recorder.calls if name == "caption"]
    assert f"Active source: {document.display_name}" in captions
    metric_values = {label: value for kind, label, value in recorder.calls if kind == "metric"}
    assert metric_values["Analysis"] == "Complete"
    assert "Hotspots" in metric_values
    assert "Static findings" in metric_values
    assert metric_values["AI review"] == "Available"
    primary_actions = [
        args[0]
        for name, args, kwargs in recorder.calls
        if name == "button" and kwargs.get("type") == "primary"
    ]
    assert primary_actions == ["Get AI review"]
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

    app.render_stage_action(document, state)

    assert len(calls) == 1
    assert calls[0][1] == {"analyse_clicked": False, "review_clicked": True}
    assert reruns == ["rerun"]
    assert REVIEW_KEY in state


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

    app.main()

    assert recorder.tab_sets == []
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

    assert recorder.tab_sets == [
        ("Overview", "AI review", "Suggested refactor", "Technical details")
    ]
    assert {key: id(value) for key, value in state.items()} == identities
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
    assert "background: #f8fafc" in app.APP_STYLES
    assert '[data-testid="stSidebar"] label { color: #172033; }' in app.APP_STYLES
    assert "background: #172033" not in app.APP_STYLES
    assert ".severity-high { background: #ffedd5" in app.APP_STYLES
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


def test_no_pdf_library_javascript_or_external_print_component_was_added():
    requirements = Path("requirements.txt").read_text(encoding="utf-8").lower()
    application = Path("app.py").read_text(encoding="utf-8").lower()
    for package in ("weasyprint", "reportlab", "fpdf", "pdfkit", "playwright"):
        assert package not in requirements
    assert "unsafe_allow_javascript=true" not in application
    assert "components.html" not in application


def test_summary_first_rendering_is_bounded_complete_and_does_not_mutate(monkeypatch):
    functions = "\n".join(f"def item_{number}(value):\n    return value\n" for number in range(80))
    analysis = analyse_script(functions)
    original = asdict(analysis)
    recorder = install_recorder(monkeypatch)
    app.render_analysis(analysis, ai_eligible=True)
    app.render_analysis_technical(analysis)

    assert asdict(analysis) == original
    assert (f"Analysable units ({len(analysis.units)})", False) in recorder.expanders
    assert ("Configured thresholds", False) in recorder.expanders
    assert ("Technical details", False) in recorder.expanders
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
    assert ("Hotspots", 5) in metric_values
    assert metric_values[3] == ("Static findings", 5)
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
    assert metrics["AI eligibility"] == "Unavailable"


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


def test_warnings_and_exclusions_remain_accessible(monkeypatch):
    analysis = replace(
        analyse_script("def add(a, b):\n    return a + b\n"),
        analysis_warnings=("A measured result could not be resolved.",),
    )
    recorder = install_recorder(monkeypatch)
    app.render_analysis_technical(analysis)
    assert ("Warnings (1)", True) in recorder.expanders
    assert ("Exclusions (0)", False) in recorder.expanders


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
    assert ("View complete files", False) in recorder.expanders
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
    assert refactor_action_label(state) == "Try a different refactor"


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

    assert ("View complete files", False) in recorder.expanders
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
        "Try a different refactor",
        "Optional instructions",
        "Original code",
        "Suggested refactor",
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
    ):
        assert obsolete not in visible
    assert "grounded" not in visible.lower()


def test_production_ui_freezes_scope_to_complete_python_scripts():
    application = Path("app.py").read_text(encoding="utf-8")
    presentation = Path("src/codesage/ui.py").read_text(encoding="utf-8")
    source_interface = Path("src/codesage/source.py").read_text(encoding="utf-8")
    normal_interface = application + presentation + source_interface

    assert "Load built-in example" in application
    assert "complete Python script" in application
    assert "future work" not in application
    assert ".ipynb" not in normal_interface
    assert "Upload one Python file" in application
    assert "Public GitHub .py file URL" in application


def test_review_disclosure_and_heading_are_accessible():
    application = Path("app.py").read_text(encoding="utf-8")
    assert 'st.subheader("AI maintainability review")' in application
    assert "Based on your code and CodeSage's deterministic measurements." in application
    assert "reference the relevant code" in application
    assert "does not rewrite your code" in application


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
    assert "### Refactor recommended" in markdown
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
    assert calls == []


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
