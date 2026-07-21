from __future__ import annotations

import json
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from codesage.ai import (
    CorrectionStatus,
    Finding,
    RefactorDecisionOutcome,
    ReviewOutcome,
    ReviewResponse,
    ReviewResult,
    ScriptRefactorResponse,
    TechnicalCorrectionResponse,
    generate_script_refactor,
)
from codesage.analysis import analyse_script
from codesage.evidence import build_evidence_package


class FakeResponses:
    def __init__(self, *results):
        self.results = list(results)
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self.results.pop(0)


class FakeClient:
    def __init__(self, *results):
        self.responses = FakeResponses(*results)


def api_result(parsed):
    return SimpleNamespace(output_parsed=parsed, status="completed", output=())


def review_for(source: str, target_name: str) -> ReviewResult:
    analysis = analyse_script(source)
    evidence = build_evidence_package(analysis)
    reference = next(
        item.source_reference
        for item in evidence.items
        if item.fact == "smell.mutable_default" and target_name in item.source_reference
    )
    evidence_id = next(
        item.evidence_id
        for item in evidence.items
        if item.source_reference == reference and item.fact == "smell.mutable_default"
    )
    finding = Finding(
        title="Mutable default",
        category="maintainability",
        priority="medium",
        source_reference=reference,
        evidence_ids=[evidence_id],
        explanation="The measured default is shared.",
        recommendation="Use None and initialise locally.",
        learning_takeaway="Mutable defaults retain state between calls.",
        uncertainty="Runtime callers were not observed.",
    )
    response = ReviewResponse(
        outcome=ReviewOutcome.REFACTOR_RECOMMENDED,
        summary="Make one focused change.",
        findings=[finding],
    )
    return ReviewResult(analysis, evidence, response, None, None, True)


def target_reference(review: ReviewResult) -> str:
    return review.response.findings[0].source_reference


def response(review: ReviewResult, replacement: str, *, reference: str | None = None):
    return ScriptRefactorResponse(
        outcome=RefactorDecisionOutcome.SUGGESTED_REFACTOR,
        target_source_reference=reference or target_reference(review),
        replacement_source=replacement,
        decision_reason="This approach should improve the reviewed issue.",
    )


def abstained(review: ReviewResult, reason: str = "No clearly better targeted option was found."):
    return ScriptRefactorResponse(
        outcome=RefactorDecisionOutcome.NO_BETTER_REFACTOR,
        target_source_reference=target_reference(review),
        decision_reason=reason,
    )


def correction(review: ReviewResult, replacement: str, *, reference: str | None = None):
    return TechnicalCorrectionResponse(
        target_source_reference=reference or target_reference(review),
        replacement_source=replacement,
    )


def test_schema_requires_target_reference_and_replacement_only():
    assert set(ScriptRefactorResponse.model_fields) == {
        "outcome",
        "target_source_reference",
        "replacement_source",
        "decision_reason",
    }
    with pytest.raises(ValidationError):
        ScriptRefactorResponse.model_validate(
            {
                "outcome": "suggested_refactor",
                "target_source_reference": "function:focused:1@L1-L2",
                "suggested_refactor": "x",
                "decision_reason": "A reason.",
            }
        )


def test_suggested_refactor_requires_replacement_and_abstention_forbids_it():
    with pytest.raises(ValidationError):
        ScriptRefactorResponse(
            outcome=RefactorDecisionOutcome.SUGGESTED_REFACTOR,
            target_source_reference="function:focused:1@L1-L2",
            decision_reason="Missing replacement.",
        )
    with pytest.raises(ValidationError):
        ScriptRefactorResponse(
            outcome=RefactorDecisionOutcome.NO_BETTER_REFACTOR,
            target_source_reference="function:focused:1@L1-L2",
            replacement_source="def focused():\n    return None\n",
            decision_reason="Should not include a replacement.",
        )


def test_request_contains_only_approved_target_source_not_complete_file():
    source = (
        "SECRET_UNRELATED = 42\n\n"
        "def focused(values=[]):\n    return values\n\n"
        "def unrelated():\n    return SECRET_UNRELATED\n"
    )
    review = review_for(source, "focused")
    replacement = "def focused(values=None):\n    return values\n"
    client = FakeClient(api_result(response(review, replacement)))
    result = generate_script_refactor(source, review.original_analysis, review, client=client)

    assert result.succeeded
    payload = json.loads(client.responses.calls[0]["input"][0]["content"])
    assert payload["untrusted_target_source"] == "def focused(values=[]):\n    return values\n"
    assert "SECRET_UNRELATED" not in json.dumps(payload)
    assert "untrusted_source" not in payload
    assert (
        "you are not being asked to return it" in client.responses.calls[0]["instructions"].lower()
    )


def test_multiple_review_findings_still_select_one_deterministic_hotspot():
    source = (
        "def first(values=[]):\n    return values\n\ndef second(values=[]):\n    return values\n"
    )
    analysis = analyse_script(source)
    evidence = build_evidence_package(analysis)
    findings = []
    for name in ("first", "second"):
        item = next(
            item
            for item in evidence.items
            if item.fact == "smell.mutable_default" and name in item.source_reference
        )
        findings.append(
            Finding(
                title=f"Mutable default in {name}",
                category="maintainability",
                priority="medium",
                source_reference=item.source_reference,
                evidence_ids=[item.evidence_id],
                explanation="The measured default is shared.",
                recommendation="Use None and initialise locally.",
                learning_takeaway="Mutable defaults retain state between calls.",
                uncertainty="Runtime callers were not observed.",
            )
        )
    response_value = ReviewResponse(
        outcome=ReviewOutcome.REFACTOR_RECOMMENDED,
        summary="Address the measured defaults.",
        findings=findings,
    )
    review = ReviewResult(analysis, evidence, response_value, None, None, True)
    replacement = "def first(values=None):\n    return values\n"
    client = FakeClient(api_result(response(review, replacement)))

    result = generate_script_refactor(source, analysis, review, client=client)

    assert result.succeeded
    payload = json.loads(client.responses.calls[0]["input"][0]["content"])
    assert payload["approved_target"]["qualified_name"] == "first"
    assert payload["untrusted_target_source"] == "def first(values=[]):\n    return values\n"
    assert result.verification.target_names == ("first",)
    assert "def second(values=[]):\n    return values\n" in result.suggested_refactor


def test_reconstruction_preserves_every_character_outside_target_and_line_endings():
    source = (
        "import os\r\n# preserved header\r\n\r\n"
        "def focused(values=[]):\r\n    return values\r\n\r\n"
        "# preserved suffix\r\ndef unrelated():\r\n    return os.name\r\n"
    )
    review = review_for(source, "focused")
    replacement = "def focused(values=None):\n    return values\n"
    result = generate_script_refactor(
        source,
        review.original_analysis,
        review,
        client=FakeClient(api_result(response(review, replacement))),
    )
    assert result.succeeded
    original_lines = source.splitlines(keepends=True)
    target = review.original_analysis.hotspots[0]
    prefix = "".join(original_lines[: target.line - 1])
    suffix = "".join(original_lines[target.end_line :])
    assert result.suggested_refactor.startswith(prefix)
    assert result.suggested_refactor.endswith(suffix)
    inserted = result.suggested_refactor[len(prefix) : -len(suffix)]
    assert "\r\n" in inserted
    assert "\n" not in inserted.replace("\r\n", "")


def test_method_replacement_is_reindented_inside_its_original_class():
    source = (
        "class Service:\n"
        "    def focused(self, values=[]):\n"
        "        return values\n\n"
        "def unrelated():\n"
        "    return 1\n"
    )
    review = review_for(source, "Service.focused")
    replacement = "def focused(self, values=None):\n    return values\n"
    result = generate_script_refactor(
        source,
        review.original_analysis,
        review,
        client=FakeClient(api_result(response(review, replacement))),
    )
    assert result.succeeded
    assert "    def focused(self, values=None):" in result.suggested_refactor
    assert "def unrelated():\n    return 1\n" in result.suggested_refactor


@pytest.mark.parametrize(
    ("invalid", "code"),
    [
        (
            "import os\ndef focused(values=None):\n    return values\n",
            "replacement_definition_count_invalid",
        ),
        ("def other(values=None):\n    return values\n", "replacement_target_mismatch"),
        (
            "def focused(values=None):\n    return values\n\ndef other():\n    return 1\n",
            "replacement_definition_count_invalid",
        ),
        (
            "```python\ndef focused(values=None):\n    return values\n```",
            "replacement_format_invalid",
        ),
        ("Here is the replacement for focused.", "replacement_syntax_invalid"),
        ("def focused(values=None):\n    ...\n", "replacement_format_invalid"),
    ],
)
def test_invalid_targeted_responses_stop_after_one_correction(invalid, code):
    source = "def focused(values=[]):\n    return values\n"
    review = review_for(source, "focused")
    client = FakeClient(
        api_result(response(review, invalid)),
        api_result(correction(review, invalid)),
    )
    result = generate_script_refactor(source, review.original_analysis, review, client=client)
    assert not result.succeeded
    assert result.initial_failure_codes == (code,)
    assert result.correction_failure_codes == (code,)
    assert len(client.responses.calls) == 2


def test_wrong_reference_correction_remains_bound_to_original_target():
    source = "def focused(values=[]):\n    return values\n"
    review = review_for(source, "focused")
    client = FakeClient(
        api_result(response(review, "def broken(:\n")),
        api_result(
            correction(
                review,
                "def focused(values=None):\n    return values\n",
                reference="function:other:1@L1-L2",
            )
        ),
    )
    result = generate_script_refactor(source, review.original_analysis, review, client=client)
    assert not result.succeeded
    assert result.correction_failure_codes == ("target_reference_mismatch",)
    assert len(client.responses.calls) == 2


def test_invalid_syntax_gets_one_valid_targeted_correction_and_full_reanalysis():
    source = "def focused(values=[]):\n    return values\n\nvalue = 1\n"
    review = review_for(source, "focused")
    replacement = "def focused(values=None):\n    return values\n"
    client = FakeClient(
        api_result(response(review, "def focused(:\n")),
        api_result(correction(review, replacement)),
    )
    result = generate_script_refactor(source, review.original_analysis, review, client=client)
    assert result.succeeded
    assert result.correction_status is CorrectionStatus.SUCCEEDED
    assert result.verification.analysis.source_digest != review.original_analysis.source_digest
    assert result.verification.comparison is not None
    assert len(client.responses.calls) == 2


def test_large_reconstruction_preserves_more_than_two_hundred_unrelated_units():
    unrelated = "\n".join(
        f"def unrelated_{index}(value):\n    return value + {index}\n" for index in range(205)
    )
    source = (
        "HEADER = 'preserve exactly'\n\n"
        "def focused(values=[]):\n    return values\n\n"
        f"{unrelated}\n"
    )
    review = review_for(source, "focused")
    replacement = "def focused(values=None):\n    return values\n"
    result = generate_script_refactor(
        source,
        review.original_analysis,
        review,
        client=FakeClient(api_result(response(review, replacement))),
    )
    assert result.succeeded
    before_names = {
        unit.qualified_name
        for unit in review.original_analysis.units
        if unit.qualified_name.startswith("unrelated_")
    }
    after_names = {
        unit.qualified_name
        for unit in result.verification.analysis.units
        if unit.qualified_name.startswith("unrelated_")
    }
    assert len(before_names) == 205
    assert after_names == before_names
    assert result.suggested_refactor.endswith(unrelated + "\n")
