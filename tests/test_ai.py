from __future__ import annotations

import json
import logging
from types import SimpleNamespace

import httpx
import openai
import pytest
from pydantic import ValidationError

from codesage.ai import (
    MAX_OPTIONAL_INSTRUCTIONS,
    ApiErrorDetail,
    CorrectionStatus,
    Finding,
    FindingReferenceCorrection,
    GroundingCorrectionStatus,
    RefactorDecisionOutcome,
    RefactorAvailabilityStatus,
    ReviewMode,
    ReviewGroundingCorrectionResponse,
    ReviewOutcome,
    ReviewResponse,
    ScriptRefactorResponse,
    ScriptReviewResponse,
    TechnicalCorrectionResponse,
    _verify_candidate,
    _validate_response,
    create_openai_client,
    generate_script_refactor,
    normalise_script_response,
    refactor_availability,
    review_allows_refactor,
    review_script,
)
from codesage.analysis import analyse_script
from codesage.config import REFACTOR_INSTRUCTION_CHARACTER_LIMIT
from codesage.evidence import build_evidence_package
from codesage.models import UnitKind
from codesage.source import normalise_example_source


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
        outcome=RefactorDecisionOutcome.SUGGESTED_REFACTOR,
        target_source_reference=target_reference(analysis),
        replacement_source=replacement,
        decision_reason="This approach should improve the reviewed issue.",
    )


def abstained_response(analysis, reason="No clearly better targeted replacement was found."):
    return ScriptRefactorResponse(
        outcome=RefactorDecisionOutcome.NO_BETTER_REFACTOR,
        target_source_reference=target_reference(analysis),
        decision_reason=reason,
    )


def correction_response(analysis, replacement):
    return TechnicalCorrectionResponse(
        target_source_reference=target_reference(analysis),
        replacement_source=replacement,
    )


def grounding_correction(analysis, *, finding_index=0):
    finding = supported_finding(analysis)
    return ReviewGroundingCorrectionResponse(
        corrections=[
            FindingReferenceCorrection(
                finding_index=finding_index,
                source_reference=finding.source_reference,
                evidence_ids=finding.evidence_ids,
            )
        ]
    )


def test_grounding_correction_schema_is_reference_only_and_rejects_duplicate_indexes():
    analysis = analyse_script(source_with_hotspot())
    correction = grounding_correction(analysis).corrections[0]
    assert set(FindingReferenceCorrection.model_fields) == {
        "finding_index",
        "source_reference",
        "evidence_ids",
    }
    assert set(ReviewGroundingCorrectionResponse.model_fields) == {"corrections"}
    with pytest.raises(ValidationError):
        ReviewGroundingCorrectionResponse(corrections=[correction, correction])


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
    client = FakeClient(
        api_result(response),
        api_result(ReviewGroundingCorrectionResponse(corrections=[])),
    )
    result = review_script(source, analysis, client=client)
    assert result.error_code == "zero_hotspot_mode_violation"
    assert not review_allows_refactor(result)
    assert len(client.responses.calls) == 1


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
    result = review_script(
        source,
        analysis,
        client=FakeClient(
            api_result(response),
            api_result(ReviewGroundingCorrectionResponse(corrections=[])),
        ),
    )
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
        result = review_script(
            source,
            analysis,
            client=FakeClient(
                api_result(parsed),
                api_result(ReviewGroundingCorrectionResponse(corrections=[])),
            ),
        )
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
    result = review_script(
        source,
        analysis,
        client=FakeClient(
            api_result(parsed),
            api_result(ReviewGroundingCorrectionResponse(corrections=[])),
        ),
    )
    assert result.error_code == "missing_grounding_reference"
    assert result.original_analysis is analysis


def _review_with_reference_change(analysis, **changes):
    finding = supported_finding(analysis).model_copy(update=changes)
    return ScriptReviewResponse(
        outcome=ReviewOutcome.REFACTOR_RECOMMENDED,
        summary="Original summary bytes.",
        findings=[finding],
        suggested_tests=["Run the original checks."],
        assumptions_or_limitations=["Static evidence only."],
    )


@pytest.mark.parametrize(
    ("change_kind", "expected_code"),
    (
        ("unknown_id", "invalid_evidence_id"),
        ("unknown_source", "invalid_source_reference"),
        ("mismatch", "evidence_source_mismatch"),
        ("duplicate", "duplicate_evidence_id"),
        ("missing", "missing_grounding_reference"),
    ),
)
def test_each_eligible_grounding_failure_uses_exactly_one_correction(change_kind, expected_code):
    source = source_with_hotspot()
    analysis = analyse_script(source)
    valid = supported_finding(analysis)
    package = build_evidence_package(analysis)
    changes = {}
    if change_kind == "unknown_id":
        changes = {"evidence_ids": ["E9999"]}
    elif change_kind == "unknown_source":
        changes = {"source_reference": "function:missing:1@L1-L1"}
    elif change_kind == "mismatch":
        other = next(
            item for item in package.items if item.source_reference != valid.source_reference
        )
        changes = {"evidence_ids": [other.evidence_id]}
    elif change_kind == "duplicate":
        changes = {"evidence_ids": [valid.evidence_ids[0], valid.evidence_ids[0]]}
    else:
        changes = {"source_reference": "", "evidence_ids": []}
    parsed = _review_with_reference_change(analysis, **changes)
    client = FakeClient(api_result(parsed), api_result(grounding_correction(analysis)))

    result = review_script(source, analysis, client=client)

    assert result.succeeded
    assert len(client.responses.calls) == 2
    assert result.grounding_correction_attempted
    assert result.grounding_correction_status is GroundingCorrectionStatus.SUCCEEDED
    assert result.initial_grounding_failure_code == expected_code
    assert result.correction_grounding_failure_code is None
    assert result.initial_response is not None
    assert result.response.findings[0].source_reference == valid.source_reference
    assert result.response.findings[0].evidence_ids == valid.evidence_ids


def test_valid_review_uses_no_grounding_correction_request():
    source = source_with_hotspot()
    analysis = analyse_script(source)
    client = FakeClient(api_result(script_response(analysis)))

    result = review_script(source, analysis, client=client)

    assert result.succeeded
    assert len(client.responses.calls) == 1
    assert not result.grounding_correction_attempted
    assert result.grounding_correction_status is GroundingCorrectionStatus.NOT_NEEDED


def test_grounding_correction_preserves_all_review_prose_and_changes_only_references():
    source = source_with_hotspot()
    analysis = analyse_script(source)
    parsed = _review_with_reference_change(analysis, evidence_ids=["E9999"])
    client = FakeClient(api_result(parsed), api_result(grounding_correction(analysis)))

    result = review_script(source, analysis, client=client)

    original = result.initial_response.model_dump(mode="json")
    corrected = result.response.model_dump(mode="json")
    for payload in (original, corrected):
        for finding in payload["findings"]:
            finding.pop("source_reference")
            finding.pop("evidence_ids")
    assert json.dumps(original, ensure_ascii=False, separators=(",", ":")) == json.dumps(
        corrected, ensure_ascii=False, separators=(",", ":")
    )
    correction_request = client.responses.calls[1]
    assert correction_request["text_format"] is ReviewGroundingCorrectionResponse
    envelope = json.loads(correction_request["input"][0]["content"])
    assert set(envelope) == {
        "validation_failure_code",
        "safe_offending_reference_or_id",
        "original_parsed_review",
        "deterministic_evidence_catalogue",
    }
    assert source not in correction_request["input"][0]["content"]


@pytest.mark.parametrize("invalid_kind", ("unknown_id", "unknown_source"))
def test_invalid_grounding_correction_is_rejected_without_a_third_request(invalid_kind):
    source = source_with_hotspot()
    analysis = analyse_script(source)
    parsed = _review_with_reference_change(analysis, evidence_ids=["E9999"])
    valid = grounding_correction(analysis).corrections[0]
    invalid = valid.model_copy(
        update=(
            {"evidence_ids": ["E8888"]}
            if invalid_kind == "unknown_id"
            else {"source_reference": "function:unknown:1@L1-L1"}
        )
    )
    correction = ReviewGroundingCorrectionResponse(corrections=[invalid])
    client = FakeClient(api_result(parsed), api_result(correction))

    result = review_script(source, analysis, client=client)

    assert not result.succeeded
    assert len(client.responses.calls) == 2
    assert result.grounding_correction_status is GroundingCorrectionStatus.FAILED
    assert result.correction_grounding_failure_code == (
        "invalid_evidence_id" if invalid_kind == "unknown_id" else "invalid_source_reference"
    )


@pytest.mark.parametrize("invalid_kind", ("duplicate_index", "out_of_range"))
def test_duplicate_and_out_of_range_correction_indexes_are_rejected(invalid_kind):
    source = source_with_hotspot()
    analysis = analyse_script(source)
    parsed = _review_with_reference_change(analysis, evidence_ids=["E9999"])
    valid = grounding_correction(analysis).corrections[0]
    correction = (
        ReviewGroundingCorrectionResponse.model_construct(corrections=[valid, valid])
        if invalid_kind == "duplicate_index"
        else ReviewGroundingCorrectionResponse(
            corrections=[valid.model_copy(update={"finding_index": 1})]
        )
    )
    client = FakeClient(api_result(parsed), api_result(correction))

    result = review_script(source, analysis, client=client)

    assert not result.succeeded
    assert len(client.responses.calls) == 2
    assert result.correction_grounding_failure_code == (
        "grounding_correction_duplicate_finding_index"
        if invalid_kind == "duplicate_index"
        else "grounding_correction_finding_index_out_of_range"
    )


def test_real_built_in_evidence_catalogue_recovers_mocked_unknown_id():
    document = normalise_example_source()
    analysis = analyse_script(document.text)
    target = next(
        unit
        for unit in analysis.hotspots
        if unit.kind in {UnitKind.FUNCTION, UnitKind.METHOD} and unit.smells
    )
    package = build_evidence_package(analysis)
    reference = f"{target.key}@L{target.line}-L{target.end_line}"
    item = next(
        item
        for item in package.items
        if item.source_reference == reference and item.fact.startswith("smell.")
    )
    finding = Finding(
        title="Built-in hotspot",
        category="maintainability",
        priority="high",
        source_reference=reference,
        evidence_ids=["E9999"],
        explanation="The measured issue affects readability.",
        recommendation="Make one focused change.",
        learning_takeaway="Use the supplied evidence catalogue.",
        uncertainty="Runtime behaviour was not observed.",
    )
    parsed = ScriptReviewResponse(
        outcome=ReviewOutcome.REFACTOR_RECOMMENDED,
        summary="Built-in example review.",
        findings=[finding],
    )
    correction = ReviewGroundingCorrectionResponse(
        corrections=[
            FindingReferenceCorrection(
                finding_index=0,
                source_reference=reference,
                evidence_ids=[item.evidence_id],
            )
        ]
    )
    client = FakeClient(api_result(parsed), api_result(correction))

    result = review_script(document.text, analysis, client=client)

    assert result.succeeded
    assert result.response.findings[0].evidence_ids == [item.evidence_id]
    assert result.grounding_correction_status is GroundingCorrectionStatus.SUCCEEDED
    assert len(client.responses.calls) == 2


def test_refactor_is_separate_and_receives_only_target_context():
    source = source_with_hotspot()
    analysis, review_client, review = completed_review(source)
    generated = "def focused(value=None):\n    return value\n"
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
    corrected = "def focused(value=None):\n    return value\n"
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
    refusal_client = FakeClient(api_result(output=refusal))
    missing_client = FakeClient(api_result())
    wrong_type_client = FakeClient(api_result(object()))
    refused = review_script(source, analysis, client=refusal_client)
    missing = review_script(source, analysis, client=missing_client)
    wrong_type = review_script(source, analysis, client=wrong_type_client)
    assert refused.error_code == "refusal"
    assert missing.error_code == "missing_parsed_output"
    assert wrong_type.error_code == "invalid_structured_output"
    assert len(refusal_client.responses.calls) == 1
    assert len(missing_client.responses.calls) == 1
    assert len(wrong_type_client.responses.calls) == 1


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


def unsupported_finding(analysis):
    package = build_evidence_package(analysis)
    item = next(item for item in package.items if item.fact == "unit.complexity")
    return Finding(
        title="Complexity measurement",
        category="maintainability",
        priority="medium",
        source_reference=item.source_reference,
        evidence_ids=[item.evidence_id],
        explanation="The measured complexity is noted.",
        recommendation="Consider simplifying this function.",
        learning_takeaway="Complexity measures independent paths.",
        uncertainty="Static analysis does not observe runtime use.",
    )


def test_recommended_review_without_smell_evidence_is_rejected_before_generation():
    source = source_with_hotspot()
    analysis = analyse_script(source)
    response = ScriptReviewResponse(
        outcome=ReviewOutcome.REFACTOR_RECOMMENDED,
        summary="General measurement only, no smell cited.",
        findings=[unsupported_finding(analysis)],
    )
    review = review_script(source, analysis, client=FakeClient(api_result(response)))
    assert not review.succeeded
    assert review.error_code == "unsupported_refactor_recommendation"
    assert not review_allows_refactor(review)

    assert review.response is None


def test_recommended_review_without_supported_function_or_method_target_is_rejected():
    source = "\n".join(f"value_{index} = {index}" for index in range(31)) + "\n"
    analysis = analyse_script(source)
    package = build_evidence_package(analysis)
    item = next(item for item in package.items if item.fact.startswith("smell."))
    response = ScriptReviewResponse(
        outcome=ReviewOutcome.REFACTOR_RECOMMENDED,
        summary="Refactoring is recommended.",
        findings=[
            Finding(
                title="Top-level structure",
                category="maintainability",
                priority="high",
                source_reference=item.source_reference,
                evidence_ids=[item.evidence_id],
                explanation="The module has many top-level statements.",
                recommendation="Reorganise the module.",
                learning_takeaway="Keep module structure deliberate.",
                uncertainty="Runtime behaviour was not observed.",
            )
        ],
    )

    review = review_script(source, analysis, client=FakeClient(api_result(response)))

    assert not review.succeeded
    assert review.error_code == "unsupported_refactor_recommendation"
    decision = refactor_availability(review)
    assert decision.status is RefactorAvailabilityStatus.UNSUPPORTED_RECOMMENDATION
    assert decision.failure_code == "unsupported_refactor_recommendation"


def test_supported_recommended_review_has_one_canonical_available_target():
    source = source_with_hotspot()
    analysis, _, review = completed_review(source)

    decision = refactor_availability(review)

    assert decision.status is RefactorAvailabilityStatus.AVAILABLE
    assert decision.label == "Available"
    assert decision.target_names == ("focused",)


def test_refactor_request_includes_derived_static_maintainability_goals():
    source = source_with_hotspot()
    analysis, _, review = completed_review(source)
    generated = "def focused(value=None):\n    return value\n"
    client = FakeClient(api_result(refactor_response(analysis, generated)))

    generate_script_refactor(source, analysis, review, client=client)

    payload = json.loads(client.responses.calls[0]["input"][0]["content"])
    assert payload["static_maintainability_goals"] == ["mutable_default"]


def test_model_abstention_returns_no_candidate_and_skips_correction():
    source = source_with_hotspot()
    analysis, _, review = completed_review(source)
    client = FakeClient(
        api_result(abstained_response(analysis, "No clearly better option was justified."))
    )

    result = generate_script_refactor(source, analysis, review, client=client)

    assert not result.succeeded
    assert result.abstained
    assert result.decision_reason == "No clearly better option was justified."
    assert result.suggested_refactor is None
    assert result.correction_status is CorrectionStatus.NOT_NEEDED
    assert not result.correction_attempted
    assert len(client.responses.calls) == 1


def test_gate_rejection_triggers_the_one_correction_attempt_and_can_still_succeed():
    source = source_with_hotspot()
    analysis, _, review = completed_review(source)
    regressing = "def focused(value=None):\n    value = value or []\n    return value\n"
    fixed = "def focused(value=None):\n    return value\n"
    client = FakeClient(
        api_result(refactor_response(analysis, regressing)),
        api_result(correction_response(analysis, fixed)),
    )

    result = generate_script_refactor(source, analysis, review, client=client)

    assert result.succeeded
    assert result.correction_status is CorrectionStatus.SUCCEEDED
    assert result.initial_failure_codes == ("complexity_regressed",)
    assert len(client.responses.calls) == 2


def test_gate_rejection_withholds_both_candidates_when_correction_also_regresses():
    source = source_with_hotspot()
    analysis, _, review = completed_review(source)
    regressing = "def focused(value=None):\n    value = value or []\n    return value\n"
    client = FakeClient(
        api_result(refactor_response(analysis, regressing)),
        api_result(correction_response(analysis, regressing)),
    )

    result = generate_script_refactor(source, analysis, review, client=client)

    assert not result.succeeded
    assert result.suggested_refactor is None
    assert result.correction_status is CorrectionStatus.FAILED
    assert result.error_code == "refactor_verification_failed"
    assert result.initial_failure_codes == ("complexity_regressed",)
    assert result.correction_failure_codes == ("complexity_regressed",)
    assert result.gate_explanations
    assert any("complexity" in item.lower() for item in result.gate_explanations)


def test_shared_instruction_character_limit_constant_is_used():
    assert REFACTOR_INSTRUCTION_CHARACTER_LIMIT == 500
    assert MAX_OPTIONAL_INSTRUCTIONS == REFACTOR_INSTRUCTION_CHARACTER_LIMIT


def test_one_retry_is_configured_on_the_openai_client(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test")
    client = create_openai_client()
    assert client.max_retries == 1


def test_api_status_error_captures_safe_status_and_request_id_not_body():
    source = source_with_hotspot()
    analysis = analyse_script(source)
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    sentinel = "PRIVATE-BODY-SENTINEL"
    response = httpx.Response(
        502,
        request=request,
        headers={"x-request-id": "req_abc123"},
        json={"error": {"message": sentinel}},
    )
    error = openai.APIStatusError(
        "failed", response=response, body={"error": {"message": sentinel}}
    )
    result = review_script(source, analysis, client=FakeClient(error))
    assert result.error_code == "api_status_error"
    assert result.api_error_detail == ApiErrorDetail(502, "req_abc123")
    assert sentinel not in result.error_message
    assert sentinel not in str(result.api_error_detail)


def test_api_status_error_without_request_id_header_is_still_safe():
    source = source_with_hotspot()
    analysis, _, review = completed_review(source)
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    response = httpx.Response(503, request=request)
    error = openai.APIStatusError("failed", response=response, body=None)
    result = generate_script_refactor(source, analysis, review, client=FakeClient(error))
    assert result.error_code == "api_status_error"
    assert result.api_error_detail is not None
    assert result.api_error_detail.status_code == 503
    assert result.api_error_detail.request_id is None


def test_first_refactor_request_has_no_previous_replacement_in_payload():
    source = source_with_hotspot()
    analysis, _, review = completed_review(source)
    generated = "def focused(value=None):\n    return value\n"
    client = FakeClient(api_result(refactor_response(analysis, generated)))

    generate_script_refactor(source, analysis, review, client=client)

    payload = json.loads(client.responses.calls[0]["input"][0]["content"])
    assert payload["untrusted_previous_replacement_source"] is None


def test_alternative_request_sends_only_the_previous_target_not_the_complete_file():
    source = source_with_hotspot()
    analysis, _, review = completed_review(source)
    unrelated_padding = "\n".join(
        f"def unrelated_{index}(value):\n    return value + {index}\n" for index in range(50)
    )
    previous_target_only = "def focused(value=None):\n    return value\n"
    previous_suggestion = f"{previous_target_only}\n\n{unrelated_padding}"
    generated = "def focused(value=None):\n    result = value\n    return result\n"
    client = FakeClient(api_result(refactor_response(analysis, generated)))

    generate_script_refactor(
        source, analysis, review, previous_suggestion=previous_suggestion, client=client
    )

    payload = json.loads(client.responses.calls[0]["input"][0]["content"])
    assert payload["untrusted_previous_replacement_source"] == previous_target_only
    assert "unrelated_0" not in json.dumps(payload)
    assert len(payload["untrusted_previous_replacement_source"]) < len(previous_suggestion)


def test_identical_alternative_replacement_is_rejected_and_correction_is_tried():
    source = source_with_hotspot()
    analysis, _, review = completed_review(source)
    previous_suggestion = "def focused(value=None):\n    return value\n"
    identical_generated = "def focused(value=None):\n    return value\n"
    client = FakeClient(
        api_result(refactor_response(analysis, identical_generated)),
        api_result(correction_response(analysis, identical_generated)),
    )

    result = generate_script_refactor(
        source, analysis, review, previous_suggestion=previous_suggestion, client=client
    )

    assert not result.succeeded
    assert result.initial_failure_codes == ("alternative_not_different",)
    assert result.correction_failure_codes == ("alternative_not_different",)
    assert len(client.responses.calls) == 2


def test_correction_that_reproduces_the_previous_replacement_is_also_rejected():
    """The duplicate check applies to the correction attempt too, not only the first try."""
    source = source_with_hotspot()
    analysis, _, review = completed_review(source)
    previous_suggestion = "def focused(value=None):\n    return value\n"
    client = FakeClient(
        api_result(refactor_response(analysis, "def broken(:\n")),
        api_result(correction_response(analysis, previous_suggestion)),
    )

    result = generate_script_refactor(
        source, analysis, review, previous_suggestion=previous_suggestion, client=client
    )

    assert not result.succeeded
    assert result.error_code == "refactor_verification_failed"
    assert result.correction_status is CorrectionStatus.FAILED
    assert result.initial_failure_codes == ("replacement_syntax_invalid",)
    assert result.correction_failure_codes == ("alternative_not_different",)


def test_genuinely_different_alternative_replacement_is_accepted():
    source = source_with_hotspot()
    analysis, _, review = completed_review(source)
    previous_suggestion = "def focused(value=None):\n    return value\n"
    different_generated = "def focused(value=None):\n    result = value\n    return result\n"
    client = FakeClient(api_result(refactor_response(analysis, different_generated)))

    result = generate_script_refactor(
        source, analysis, review, previous_suggestion=previous_suggestion, client=client
    )

    assert result.succeeded
    assert result.suggested_refactor == different_generated


def test_abstention_remains_supported_when_a_previous_suggestion_exists():
    source = source_with_hotspot()
    analysis, _, review = completed_review(source)
    previous_suggestion = "def focused(value=None):\n    return value\n"
    client = FakeClient(
        api_result(abstained_response(analysis, "No distinct better option exists."))
    )

    result = generate_script_refactor(
        source, analysis, review, previous_suggestion=previous_suggestion, client=client
    )

    assert result.abstained
    assert result.decision_reason == "No distinct better option exists."
    assert not result.correction_attempted
    assert len(client.responses.calls) == 1


def test_correction_payload_also_carries_the_previous_replacement():
    source = source_with_hotspot()
    analysis, _, review = completed_review(source)
    previous_suggestion = "def focused(value=None):\n    return value\n"
    regressing = "def focused(value=None):\n    value = value or []\n    return value\n"
    corrected = "def focused(value=None):\n    result = value\n    return result\n"
    client = FakeClient(
        api_result(refactor_response(analysis, regressing)),
        api_result(correction_response(analysis, corrected)),
    )

    result = generate_script_refactor(
        source, analysis, review, previous_suggestion=previous_suggestion, client=client
    )

    assert result.succeeded
    correction_payload = json.loads(client.responses.calls[1]["input"][0]["content"])
    assert correction_payload["untrusted_previous_replacement_source"] == previous_suggestion


def test_one_target_contract_still_rejects_multiple_definitions_for_an_alternative():
    source = source_with_hotspot()
    analysis, _, review = completed_review(source)
    previous_suggestion = "def focused(value=None):\n    return value\n"
    two_definitions = (
        "def focused(value=None):\n    return value\n\ndef helper(value):\n    return value\n"
    )
    client = FakeClient(
        api_result(refactor_response(analysis, two_definitions)),
        api_result(correction_response(analysis, two_definitions)),
    )

    result = generate_script_refactor(
        source, analysis, review, previous_suggestion=previous_suggestion, client=client
    )

    assert not result.succeeded
    assert result.initial_failure_codes == ("replacement_definition_count_invalid",)
    assert result.correction_failure_codes == ("replacement_definition_count_invalid",)
