from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import httpx
import openai
import pytest
from pydantic import ValidationError

from codesage.ai import (
    CorrectionStatus,
    Finding,
    ReviewMode,
    ReviewOutcome,
    ReviewResponse,
    ScriptRefactorResponse,
    ScriptReviewResponse,
    TechnicalCorrectionResponse,
    _verify_candidate,
    _validate_response,
    generate_script_refactor,
    normalise_script_response,
    review_allows_refactor,
    review_script,
)
from codesage.analysis import analyse_script
from codesage.evidence import build_evidence_package


class FakeResponses:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        result = self.results.pop(0)
        if isinstance(result, Exception):
            raise result
        return result


class FakeClient:
    def __init__(self, *results):
        self.responses = FakeResponses(*results)


def api_result(parsed=None, *, status="completed", output=()):
    return SimpleNamespace(output_parsed=parsed, status=status, output=output)


def source_with_hotspot() -> str:
    return "def focused(value=[]):\n    return value\n"


def supported_finding(analysis):
    package = build_evidence_package(analysis)
    item = next(
        (item for item in package.items if item.fact == "smell.mutable_default"),
        package.items[0],
    )
    return Finding(
        title="Mutable default",
        category="maintainability",
        priority="medium",
        source_reference=item.source_reference,
        evidence_ids=[item.evidence_id],
        explanation="The measured result identifies a mutable default.",
        recommendation="Use None and initialise a new list inside the function.",
        learning_takeaway="Defaults are created when a function is defined.",
        uncertainty="Static analysis does not observe runtime use.",
    )


def script_response(analysis, outcome=ReviewOutcome.REFACTOR_RECOMMENDED):
    findings = (
        [supported_finding(analysis)] if outcome is ReviewOutcome.REFACTOR_RECOMMENDED else []
    )
    return ScriptReviewResponse(
        outcome=outcome,
        summary="Evidence-based review summary.",
        findings=findings,
        suggested_tests=["Run existing tests."],
        assumptions_or_limitations=["Runtime behaviour was not observed."],
    )


def completed_review(source: str, client: FakeClient | None = None):
    analysis = analyse_script(source)
    client = client or FakeClient(api_result(script_response(analysis)))
    return analysis, client, review_script(source, analysis, client=client)


def target_reference(analysis):
    target = analysis.hotspots[0]
    return f"{target.key}@L{target.line}-L{target.end_line}"


def refactor_response(analysis, replacement):
    return ScriptRefactorResponse(
        target_source_reference=target_reference(analysis),
        replacement_source=replacement,
    )


def correction_response(analysis, replacement):
    return TechnicalCorrectionResponse(
        target_source_reference=target_reference(analysis),
        replacement_source=replacement,
    )


def test_review_is_one_explanation_only_request():
    source = source_with_hotspot()
    analysis, client, result = completed_review(source)

    assert result.succeeded
    assert len(client.responses.calls) == 1
    request = client.responses.calls[0]
    assert request["text_format"] is ScriptReviewResponse
    assert "tools" not in request
    assert request["reasoning"] == {"effort": "low"}
    assert request["store"] is False
    assert result.response is not None
    assert result.response.candidate is None
    assert "suggested_refactor" not in ScriptReviewResponse.model_fields
    envelope = json.loads(request["input"][0]["content"])
    assert envelope["untrusted_source"] == source


def test_script_review_schema_rejects_rewritten_source_and_notebook_outcome():
    assert "candidate" not in ScriptReviewResponse.model_fields
    assert "strategy" not in ScriptReviewResponse.model_fields
    assert "affected_cell_keys" not in ScriptReviewResponse.model_fields
    with pytest.raises(ValidationError):
        ScriptReviewResponse(
            outcome=ReviewOutcome.MULTI_CELL_CHANGE_REQUIRED,
            summary="Not valid for scripts.",
            findings=[],
        )


def test_shared_review_schema_retains_future_notebook_fields():
    response = ReviewResponse(
        outcome=ReviewOutcome.MULTI_CELL_CHANGE_REQUIRED,
        summary="A future notebook response.",
        findings=[],
        strategy="Update two existing cells.",
        affected_cell_keys=["cell-1", "cell-2"],
    )
    assert response.strategy is not None
    assert response.affected_cell_keys == ["cell-1", "cell-2"]


def test_normalised_review_contains_no_rewritten_source():
    analysis = analyse_script(source_with_hotspot())
    normalised = normalise_script_response(script_response(analysis))
    assert normalised.candidate is None
    assert normalised.strategy is None
    assert normalised.affected_cell_keys == []


@pytest.mark.parametrize(
    ("outcome", "expected"),
    [
        (ReviewOutcome.REFACTOR_RECOMMENDED, True),
        (ReviewOutcome.NO_REFACTOR_NEEDED, False),
        (ReviewOutcome.INSUFFICIENT_EVIDENCE, False),
    ],
)
def test_only_supported_refactor_recommendation_enables_generation(outcome, expected):
    source = source_with_hotspot()
    analysis = analyse_script(source)
    client = FakeClient(api_result(script_response(analysis, outcome)))
    review = review_script(source, analysis, client=client)
    assert review_allows_refactor(review) is expected


def test_zero_hotspot_mode_never_enables_refactor():
    source = "def add(left, right):\n    return left + right\n"
    analysis = analyse_script(source)
    response = ScriptReviewResponse(
        outcome=ReviewOutcome.REFACTOR_RECOMMENDED,
        summary="Unsupported recommendation.",
        findings=[],
    )
    result = review_script(source, analysis, client=FakeClient(api_result(response)))
    assert result.error_code == "zero_hotspot_mode_violation"
    assert not review_allows_refactor(result)


def test_script_mode_rejects_notebook_fields_but_shared_mode_does_not():
    source = source_with_hotspot()
    analysis = analyse_script(source)
    evidence = build_evidence_package(analysis)
    response = ReviewResponse(
        outcome=ReviewOutcome.MULTI_CELL_CHANGE_REQUIRED,
        summary="Future notebook plan.",
        findings=[],
        strategy="Change two cells.",
        affected_cell_keys=["one", "two"],
    )
    assert (
        _validate_response(response, analysis, evidence, mode=ReviewMode.SCRIPT)[0]
        == "mode_violation"
    )
    assert _validate_response(response, analysis, evidence, mode=ReviewMode.SHARED) is None


def test_evidence_validation_remains_strict():
    source = source_with_hotspot()
    analysis = analyse_script(source)
    response = script_response(analysis)
    response.findings[0].evidence_ids = ["unknown-evidence"]
    result = review_script(source, analysis, client=FakeClient(api_result(response)))
    assert result.error_code == "invalid_evidence_id"
    assert result.original_analysis == analysis


def test_source_digest_mismatch_and_invalid_syntax_stop_before_client_use():
    source = source_with_hotspot()
    client = FakeClient(api_result(script_response(analyse_script(source))))
    mismatch = review_script(
        source,
        analyse_script("def other(value=[]):\n    return value\n"),
        client=client,
    )
    invalid_source = "def broken(:\n"
    invalid = review_script(invalid_source, analyse_script(invalid_source), client=client)
    assert mismatch.error_code == "source_analysis_mismatch"
    assert invalid.error_code == "source_syntax_error"
    assert client.responses.calls == []


def test_cross_location_and_duplicate_evidence_references_are_rejected():
    source = "def first(value=[]):\n    return value\n\ndef second(value={}):\n    return value\n"
    analysis = analyse_script(source)
    package = build_evidence_package(analysis)
    first, second = (
        package.items[0],
        next(
            item
            for item in package.items
            if item.source_reference != package.items[0].source_reference
        ),
    )
    base = supported_finding(analysis)
    cross_location = base.model_copy(
        update={"source_reference": first.source_reference, "evidence_ids": [second.evidence_id]}
    )
    duplicate = base.model_copy(update={"evidence_ids": [base.evidence_ids[0]] * 2})
    for finding, code in (
        (cross_location, "evidence_source_mismatch"),
        (duplicate, "duplicate_evidence_id"),
    ):
        parsed = ScriptReviewResponse(
            outcome=ReviewOutcome.REFACTOR_RECOMMENDED,
            summary="Invalid references.",
            findings=[finding],
        )
        result = review_script(source, analysis, client=FakeClient(api_result(parsed)))
        assert result.error_code == code


def test_missing_evidence_reference_is_rejected_in_production():
    source = source_with_hotspot()
    analysis = analyse_script(source)
    finding = supported_finding(analysis).model_copy(
        update={"source_reference": "", "evidence_ids": []}
    )
    parsed = ScriptReviewResponse(
        outcome=ReviewOutcome.REFACTOR_RECOMMENDED,
        summary="Unsupported finding.",
        findings=[finding],
    )
    result = review_script(source, analysis, client=FakeClient(api_result(parsed)))
    assert result.error_code == "missing_grounding_reference"
    assert result.original_analysis is analysis


def test_refactor_is_separate_and_receives_only_target_context():
    source = source_with_hotspot()
    analysis, review_client, review = completed_review(source)
    generated = (
        "def focused(value=None):\n    if value is None:\n        value = []\n    return value\n"
    )
    refactor_client = FakeClient(api_result(refactor_response(analysis, generated)))

    result = generate_script_refactor(
        source,
        analysis,
        review,
        optional_instructions="Keep the public signature stable where practical.",
        client=refactor_client,
    )

    assert len(review_client.responses.calls) == 1
    assert len(refactor_client.responses.calls) == 1
    assert result.succeeded
    assert result.suggested_refactor == generated
    request = refactor_client.responses.calls[0]
    assert request["text_format"] is ScriptRefactorResponse
    payload = json.loads(request["input"][0]["content"])
    assert payload["untrusted_target_source"] == source
    assert "untrusted_source" not in payload
    assert payload["approved_target"]["qualified_name"] == "focused"
    assert (
        payload["untrusted_optional_instructions"]
        == "Keep the public signature stable where practical."
    )
    assert payload["deterministic_evidence"] == json.loads(json.dumps(review.evidence.as_dict()))
    assert payload["validated_ai_review"]["summary"] == review.response.summary


@pytest.mark.parametrize(
    "invalid",
    ["function:focused:1@L1-L2", "```python\ndef focused():\n    pass\n```", "def broken(:\n"],
)
def test_invalid_generation_gets_at_most_one_correction(invalid):
    source = source_with_hotspot()
    analysis, _, review = completed_review(source)
    client = FakeClient(
        api_result(refactor_response(analysis, invalid)),
        api_result(correction_response(analysis, "def still_broken(:\n")),
    )
    result = generate_script_refactor(source, analysis, review, client=client)
    assert not result.succeeded
    assert result.error_code == "refactor_verification_failed"
    assert result.correction_status is CorrectionStatus.FAILED
    assert result.correction_attempted
    assert result.review == review.response
    assert len(client.responses.calls) == 2
    assert client.responses.calls[1]["text_format"] is TechnicalCorrectionResponse


def test_successful_one_time_correction_is_verified():
    source = source_with_hotspot()
    analysis, _, review = completed_review(source)
    corrected = (
        "def focused(value=None):\n    if value is None:\n        value = []\n    return value\n"
    )
    progress = []
    client = FakeClient(
        api_result(refactor_response(analysis, "not Python prose")),
        api_result(correction_response(analysis, corrected)),
    )
    result = generate_script_refactor(
        source,
        analysis,
        review,
        client=client,
        on_correction_start=lambda code: progress.append("started"),
    )
    assert result.succeeded
    assert result.suggested_refactor == corrected
    assert result.correction_status is CorrectionStatus.SUCCEEDED
    assert progress == ["started"]
    assert len(client.responses.calls) == 2


def test_calculated_and_absolute_refactor_limits_are_enforced_before_parsing(monkeypatch):
    source = source_with_hotspot()
    analysis = analyse_script(source)
    calculated_limit = (2 * len(source)) + 5_000
    oversized = "#" * (calculated_limit + 1)
    assert _verify_candidate(source, oversized, analysis)[0] == "candidate_too_large"
    large_source = "#" * 80_000 + "\n" + source
    large_analysis = analyse_script(large_source)
    assert _verify_candidate(large_source, "#" * 160_001, large_analysis)[0] == (
        "candidate_too_large"
    )
    monkeypatch.setattr(
        __import__("codesage.ai", fromlist=["ast"]).ast,
        "parse",
        lambda value: pytest.fail("oversized generated source must not be parsed"),
    )
    assert _verify_candidate(source, oversized, analysis)[0] == "candidate_too_large"


def test_calculated_size_failure_is_eligible_for_one_correction():
    source = source_with_hotspot()
    analysis, _, review = completed_review(source)
    oversized = "#" * ((2 * len(source)) + 5_001)
    corrected = "def focused(value=None):\n    return value\n"
    client = FakeClient(
        api_result(refactor_response(analysis, oversized)),
        api_result(correction_response(analysis, corrected)),
    )
    result = generate_script_refactor(source, analysis, review, client=client)
    assert result.succeeded
    assert result.correction_status is CorrectionStatus.SUCCEEDED
    assert len(client.responses.calls) == 2


@pytest.mark.parametrize("status", ["incomplete", "failed", "cancelled", "in_progress"])
def test_refactor_terminal_failure_does_not_trigger_correction(status):
    source = source_with_hotspot()
    analysis, _, review = completed_review(source)
    client = FakeClient(api_result(status=status))
    result = generate_script_refactor(source, analysis, review, client=client)
    assert not result.correction_attempted
    assert len(client.responses.calls) == 1


def test_valid_refactor_is_reanalysed_and_compared_without_equivalence_claim(monkeypatch):
    source = source_with_hotspot()
    analysis, _, review = completed_review(source)
    generated = "def focused(value=None):\n    return value\n"
    import codesage.ai as ai_module

    real_analyse = ai_module.analyse_script
    seen = []

    def spy(value):
        seen.append(value)
        return real_analyse(value)

    monkeypatch.setattr(ai_module, "analyse_script", spy)
    result = generate_script_refactor(
        source,
        analysis,
        review,
        client=FakeClient(api_result(refactor_response(analysis, generated))),
    )
    assert result.succeeded
    assert seen == [generated]
    comparison = result.verification.comparison
    assert comparison.directional
    assert comparison.descriptive
    assert comparison.structural is not None
    assert comparison.smells_removed == ("focused:mutable_default",)
    assert "does not establish behavioural equivalence" in (
        result.verification.non_equivalence_notice
    )


def test_separate_refactor_operations_each_have_their_own_single_correction():
    source = source_with_hotspot()
    analysis, _, review = completed_review(source)
    corrected = "def focused(value=None):\n    return value\n"

    for instructions in ("First approach", "Second approach"):
        client = FakeClient(
            api_result(refactor_response(analysis, "def broken(:\n")),
            api_result(correction_response(analysis, corrected)),
        )
        result = generate_script_refactor(
            source,
            analysis,
            review,
            optional_instructions=instructions,
            client=client,
        )
        assert result.succeeded
        assert result.correction_status is CorrectionStatus.SUCCEEDED
        assert result.correction_attempted
        assert len(client.responses.calls) == 2


def test_review_failure_does_not_trigger_refactor_request():
    source = source_with_hotspot()
    analysis = analyse_script(source)
    result = review_script(source, analysis, client=FakeClient(api_result(None, status="failed")))
    assert not result.succeeded
    assert result.error_code == "response_failed"


@pytest.mark.parametrize(
    ("status", "code"),
    [
        ("incomplete", "incomplete"),
        ("failed", "response_failed"),
        ("cancelled", "response_cancelled"),
        ("queued", "response_not_terminal"),
        ("in_progress", "response_not_terminal"),
        ("unknown", "invalid_response_status"),
    ],
)
def test_non_completed_review_statuses_are_typed(status, code):
    source = source_with_hotspot()
    analysis = analyse_script(source)
    result = review_script(source, analysis, client=FakeClient(api_result(status=status)))
    assert result.error_code == code
    assert result.original_analysis is analysis


def test_refusal_and_missing_structured_output_are_typed():
    source = source_with_hotspot()
    analysis = analyse_script(source)
    refusal = [SimpleNamespace(content=[SimpleNamespace(type="refusal")])]
    refused = review_script(source, analysis, client=FakeClient(api_result(output=refusal)))
    missing = review_script(source, analysis, client=FakeClient(api_result()))
    wrong_type = review_script(source, analysis, client=FakeClient(api_result(object())))
    assert refused.error_code == "refusal"
    assert missing.error_code == "missing_parsed_output"
    assert wrong_type.error_code == "invalid_structured_output"


def openai_errors():
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    return [
        (openai.APITimeoutError(request=request), "timeout"),
        (openai.APIConnectionError(request=request), "connection_error"),
        (
            openai.RateLimitError(
                "rate limited", response=httpx.Response(429, request=request), body=None
            ),
            "rate_limit",
        ),
        (
            openai.APIStatusError(
                "failed", response=httpx.Response(500, request=request), body=None
            ),
            "api_status_error",
        ),
    ]


@pytest.mark.parametrize(("error", "code"), openai_errors())
def test_openai_review_failures_are_typed_and_do_not_trigger_correction(error, code):
    source = source_with_hotspot()
    analysis = analyse_script(source)
    client = FakeClient(error)
    result = review_script(source, analysis, client=client)
    assert result.error_code == code
    assert result.original_analysis is analysis
    assert len(client.responses.calls) == 1


def test_api_error_body_and_validation_input_are_not_exposed():
    source = source_with_hotspot()
    analysis = analyse_script(source)
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    sentinel = "PRIVATE-API-BODY-SENTINEL"
    api_error = openai.APIStatusError(
        "unsafe exception text",
        response=httpx.Response(500, request=request, json={"detail": sentinel}),
        body={"detail": sentinel},
    )
    api_result_value = review_script(source, analysis, client=FakeClient(api_error))
    assert sentinel not in api_result_value.error_message

    with pytest.raises(ValidationError) as caught:
        ScriptReviewResponse.model_validate(
            {"outcome": "no_refactor_needed", "summary": sentinel, "findings": "invalid"}
        )
    validation_result = review_script(source, analysis, client=FakeClient(caught.value))
    assert validation_result.error_code == "invalid_structured_output"
    assert sentinel not in validation_result.error_message


def test_refactor_transport_failures_do_not_trigger_technical_correction():
    source = source_with_hotspot()
    analysis, _, review = completed_review(source)
    for error, code in openai_errors():
        client = FakeClient(error)
        result = generate_script_refactor(source, analysis, review, client=client)
        assert result.error_code == code
        assert not result.correction_attempted
        assert len(client.responses.calls) == 1


def test_submitted_and_generated_source_are_not_logged(caplog):
    source = "# PRIVATE-SOURCE-SENTINEL\n" + source_with_hotspot()
    analysis = analyse_script(source)
    review_client = FakeClient(api_result(script_response(analysis)))
    with caplog.at_level(logging.DEBUG):
        review = review_script(source, analysis, client=review_client)
        generated = "# PRIVATE-GENERATED-SENTINEL\ndef focused(value=None):\n    return value\n"
        generate_script_refactor(
            source,
            analysis,
            review,
            client=FakeClient(api_result(refactor_response(analysis, generated))),
        )
    assert "PRIVATE-SOURCE-SENTINEL" not in caplog.text
    assert "PRIVATE-GENERATED-SENTINEL" not in caplog.text


def test_review_result_success_invariant_is_enforced():
    from codesage.ai import ReviewResult

    analysis = analyse_script(source_with_hotspot())
    with pytest.raises(ValueError, match="requires a response"):
        ReviewResult(analysis, None, None, None, None)


def test_no_live_openai_calls(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    source = source_with_hotspot()
    result = review_script(source, analyse_script(source))
    assert result.error_code == "missing_api_key"
    assert not result.request_attempted
