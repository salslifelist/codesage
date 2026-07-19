from __future__ import annotations

import socket
from pathlib import Path
from types import SimpleNamespace

import pytest

from codesage.ai import (
    ReviewOutcome,
    ReviewResponse,
    ReviewResult,
    ScriptReviewResponse,
    review_script,
)
from codesage.analysis import NO_HOTSPOTS, analyse_script
from codesage.source import (
    AI_REVIEW_CHARACTER_LIMIT,
    SOURCE_INGESTION_LIMIT,
    SourceDocument,
    SourceIngestionError,
    SourceOrigin,
    normalise_pasted_source,
)
from codesage.ui import (
    ANALYSIS_KEY,
    FAILURE_MESSAGES,
    REVIEW_KEY,
    failure_message,
    handle_actions,
    metric_rows,
    structural_rows,
)


def successful_review(source):
    analysis = analyse_script(source)
    response = ReviewResponse(
        outcome=ReviewOutcome.NO_REFACTOR_NEEDED,
        summary="Mocked successful review.",
        findings=[],
    )
    return ReviewResult(analysis, None, response, None, None, None)


def test_no_review_before_explicit_action_and_reruns_do_not_repeat():
    source = "def focused(value=[]):\n    return value\n"
    state = {}
    calls = []

    def reviewer(current_source, analysis):
        calls.append((current_source, analysis.source_digest))
        return successful_review(current_source)

    handle_actions(state, source, analyse_clicked=True, review_clicked=False, reviewer=reviewer)
    handle_actions(state, source, analyse_clicked=False, review_clicked=False, reviewer=reviewer)
    assert calls == []

    handle_actions(state, source, analyse_clicked=False, review_clicked=True, reviewer=reviewer)
    handle_actions(state, source, analyse_clicked=False, review_clicked=False, reviewer=reviewer)
    handle_actions(state, source, analyse_clicked=False, review_clicked=True, reviewer=reviewer)

    assert len(calls) == 1
    assert REVIEW_KEY in state


def test_source_change_clears_stale_analysis_and_review():
    original = "def original(value=[]):\n    return value\n"
    changed = "def changed(value=[]):\n    return value\n"
    state = {}
    handle_actions(state, original, analyse_clicked=True, review_clicked=False)
    state[REVIEW_KEY] = successful_review(original)

    handle_actions(state, changed, analyse_clicked=False, review_clicked=False)

    assert ANALYSIS_KEY not in state
    assert REVIEW_KEY not in state


def test_review_requires_current_valid_analysis():
    calls = []

    def reviewer(source, analysis):
        calls.append(source)

    state = {}

    message = handle_actions(
        state,
        "def valid():\n    return 1\n",
        analyse_clicked=False,
        review_clicked=True,
        reviewer=reviewer,
    )
    assert message == "Analyse the current script before requesting AI review."

    invalid = "def broken(:\n"
    handle_actions(state, invalid, analyse_clicked=True, review_clicked=False, reviewer=reviewer)
    message = handle_actions(
        state, invalid, analyse_clicked=False, review_clicked=True, reviewer=reviewer
    )
    assert message == "Fix the syntax error before requesting AI review."
    assert calls == []


def test_source_limit_is_exact_and_never_truncates():
    accepted = "#" * SOURCE_INGESTION_LIMIT
    state = {}
    assert handle_actions(state, accepted, analyse_clicked=True, review_clicked=False) is None
    assert state[ANALYSIS_KEY].source_digest == analyse_script(accepted).source_digest

    rejected = accepted + "x"
    with pytest.raises(SourceIngestionError) as caught:
        handle_actions(state, rejected, analyse_clicked=True, review_clicked=False)
    assert caught.value.code == "source_too_large"


def test_file_above_ai_limit_is_analysed_but_never_truncated_or_reviewed():
    source = "#" * (AI_REVIEW_CHARACTER_LIMIT + 1)
    state = {}
    calls = []

    handle_actions(state, source, analyse_clicked=True, review_clicked=False)
    message = handle_actions(
        state,
        source,
        analyse_clicked=False,
        review_clicked=True,
        reviewer=lambda current, analysis: calls.append(current),
    )

    assert state[ANALYSIS_KEY].physical_lines == 1
    assert message.startswith("Complete-file AI review is limited")
    assert calls == []


def test_identical_text_from_a_different_origin_invalidates_state():
    text = "def shared(value=[]):\n    return value\n"
    pasted = normalise_pasted_source(text)
    uploaded = SourceDocument.create(text, "shared.py", SourceOrigin.UPLOADED)
    state = {}
    handle_actions(state, pasted, analyse_clicked=True, review_clicked=False)
    state[REVIEW_KEY] = successful_review(text)

    handle_actions(state, uploaded, analyse_clicked=False, review_clicked=False)

    assert ANALYSIS_KEY not in state
    assert REVIEW_KEY not in state


def test_zero_hotspot_and_hotspot_ordering_are_preserved():
    clean = analyse_script("def clean(value):\n    return value\n")
    assert clean.outcome == NO_HOTSPOTS
    assert clean.hotspots == ()

    source = (
        "def medium(value=[]):\n    return value\n\n"
        "def high(values):\n"
        "    if values:\n"
        "        for value in values:\n"
        "            while value:\n"
        "                if value:\n"
        "                    return value\n"
    )
    assert [item.qualified_name for item in analyse_script(source).hotspots] == ["high", "medium"]


def test_candidate_comparison_view_rows_are_complete():
    original = analyse_script("def focused(value=[]):\n    return value\n")
    candidate = analyse_script("def focused(value=None):\n    return value\n")
    from codesage.comparison import compare_scripts

    comparison = compare_scripts(original, candidate)
    directional = metric_rows(comparison.directional)
    structural = structural_rows(comparison.structural)

    assert any(row["Metric"] == "smell.mutable_default" for row in directional)
    assert any(row["Category"] == "function" and row["Name"] == "focused" for row in structural)
    assert comparison.smells_removed == ("focused:mutable_default",)


def test_candidate_and_comparison_render_with_safe_streamlit_primitives(monkeypatch):
    import app

    source = "def focused(value=[]):\n    return value\n"
    candidate = "def focused(value=None):\n    return value\n"
    parsed = ScriptReviewResponse(
        outcome=ReviewOutcome.REFACTOR_RECOMMENDED,
        summary="A focused candidate is available.",
        findings=[],
        candidate_source=candidate,
        suggested_tests=["Run unit tests."],
    )
    api_response = SimpleNamespace(
        output_parsed=parsed, status="completed", output=(), incomplete_details=None
    )
    client = SimpleNamespace(responses=SimpleNamespace(parse=lambda **kwargs: api_response))
    review = review_script(source, analyse_script(source), client=client)

    class Recorder:
        def __init__(self):
            self.code_calls = []
            self.tables = []

        def code(self, value, *, language):
            self.code_calls.append((value, language))

        def dataframe(self, value, **kwargs):
            self.tables.append(value)

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    recorder = Recorder()
    monkeypatch.setattr(app, "st", recorder)

    app.render_review(review)

    assert recorder.code_calls == [(candidate, "python")]
    assert len(recorder.tables) == 3
    assert all(recorder.tables)


def test_failed_candidate_repair_keeps_review_and_never_renders_candidate(monkeypatch):
    import app

    source = "def focused(value=[]):\n    return value\n"
    analysis = analyse_script(source)
    response = ReviewResponse(
        outcome=ReviewOutcome.REFACTOR_RECOMMENDED,
        summary="The grounded review remains available.",
        findings=[],
        candidate=None,
    )
    review = ReviewResult(
        analysis,
        None,
        response,
        None,
        None,
        None,
        "candidate_syntax_invalid",
    )

    class Recorder:
        def __init__(self):
            self.code_calls = []
            self.warnings = []

        def code(self, value, **kwargs):
            self.code_calls.append(value)

        def warning(self, value):
            self.warnings.append(value)

        def __getattr__(self, name):
            return lambda *args, **kwargs: None

    recorder = Recorder()
    monkeypatch.setattr(app, "st", recorder)

    app.render_review(review)

    assert recorder.code_calls == []
    assert recorder.warnings == [failure_message("candidate_syntax_invalid")]


@pytest.mark.parametrize(
    ("code", "expected"),
    [
        ("missing_api_key", "OpenAI API access is not configured."),
        ("timeout", "The AI review timed out. Try again later."),
        ("invalid_evidence_id", "The model response cited invalid deterministic evidence."),
        ("candidate_too_large", "The proposed candidate exceeded the permitted size."),
    ],
)
def test_typed_failure_messages_are_fixed(code, expected):
    assert failure_message(code) == expected


def test_every_known_ai_error_code_has_a_user_facing_message():
    known_codes = {
        "api_status_error",
        "candidate_invariant",
        "candidate_syntax_invalid",
        "candidate_too_large",
        "connection_error",
        "duplicate_evidence_id",
        "evidence_source_mismatch",
        "incomplete",
        "invalid_evidence_id",
        "invalid_response_status",
        "invalid_source_reference",
        "invalid_structured_output",
        "missing_api_key",
        "missing_grounding_reference",
        "missing_parsed_output",
        "mode_violation",
        "rate_limit",
        "refusal",
        "response_cancelled",
        "response_failed",
        "response_not_terminal",
        "script_field_violation",
        "source_analysis_mismatch",
        "source_syntax_error",
        "timeout",
        "zero_hotspot_mode_violation",
    }

    assert known_codes <= FAILURE_MESSAGES.keys()
    assert all(failure_message(code) != failure_message("unknown") for code in known_codes)


def test_syntax_error_without_location_omits_none_values(monkeypatch):
    import app

    analysis = analyse_script("\x00")
    errors = []
    recorder = SimpleNamespace(
        subheader=lambda *args, **kwargs: None,
        write=lambda *args, **kwargs: None,
        error=lambda message: errors.append(message),
    )
    monkeypatch.setattr(app, "st", recorder)

    app.render_analysis(analysis)

    assert errors
    assert "None" not in errors[0]


def test_no_source_candidate_logging_or_network_access(monkeypatch, caplog):
    monkeypatch.setattr(
        socket,
        "create_connection",
        lambda *args, **kwargs: pytest.fail("network access is forbidden"),
    )
    source = "PRIVATE-SOURCE = True\ndef focused(value=[]):\n    return value\n"
    candidate = "PRIVATE-CANDIDATE = True\n"
    state = {}

    def reviewer(current_source, analysis):
        assert current_source == source
        return successful_review(current_source)

    handle_actions(state, source, analyse_clicked=True, review_clicked=False, reviewer=reviewer)
    handle_actions(state, source, analyse_clicked=False, review_clicked=True, reviewer=reviewer)

    assert source not in caplog.text
    assert candidate not in caplog.text


def test_deployment_requirements_install_the_src_layout_project():
    requirements = Path("requirements.txt").read_text(encoding="utf-8").splitlines()
    pyproject = Path("pyproject.toml").read_text(encoding="utf-8")

    assert "." in requirements
    assert 'where = ["src"]' in pyproject


def test_temporary_diagnostic_caption_is_absent():
    application = Path("app.py").read_text(encoding="utf-8")

    assert "Diagnostic code:" not in application
    assert "Diagnostic detail:" not in application
    assert 'st.spinner("Requesting grounded AI review…")' in application
