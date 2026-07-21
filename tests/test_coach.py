"""Tests for the bounded, evidence-grounded "Ask CodeSage" follow-up chat."""

from __future__ import annotations

import json
from types import SimpleNamespace

import httpx
import openai
import pytest
from pydantic import ValidationError

from codesage.ai import (
    ApiErrorDetail,
    CoachMessage,
    CoachResponse,
    Finding,
    ReviewOutcome,
    ReviewResult,
    ScriptRefactorResponse,
    ScriptReviewResponse,
    RefactorDecisionOutcome,
    ask_coach,
    generate_script_refactor,
    review_script,
)
from codesage.analysis import analyse_script
from codesage.config import COACH_CHAT_HISTORY_MESSAGES, COACH_MESSAGE_CHARACTER_LIMIT
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
    )


def completed_review(source: str) -> ReviewResult:
    analysis = analyse_script(source)
    client = FakeClient(api_result(script_response(analysis)))
    return review_script(source, analysis, client=client)


def coach_answer(
    answer="A concise explanation.",
    evidence_ids=None,
    source_references=None,
    limitations=None,
):
    return CoachResponse(
        answer=answer,
        evidence_ids=evidence_ids or [],
        source_references=source_references or [],
        limitations=limitations or [],
    )


def test_chat_requires_a_successful_review():
    source = source_with_hotspot()
    analysis = analyse_script(source)
    failed_review = ReviewResult(analysis, None, None, "missing_api_key", "no key")
    with pytest.raises(ValueError, match="successful AI review"):
        ask_coach(source, analysis, failed_review, None, (), "Why does this matter?")


def test_stale_source_is_rejected_before_any_request():
    source = source_with_hotspot()
    review = completed_review(source)
    stale_analysis = analyse_script("def other():\n    return 1\n")
    client = FakeClient()
    result = ask_coach(source, stale_analysis, review, None, (), "Why?", client=client)
    assert result.error_code == "coach_source_mismatch"
    assert client.responses.calls == []


def test_empty_question_is_rejected_before_any_request():
    source = source_with_hotspot()
    analysis = analyse_script(source)
    review = completed_review(source)
    client = FakeClient()
    result = ask_coach(source, analysis, review, None, (), "   ", client=client)
    assert result.error_code == "empty_message"
    assert client.responses.calls == []


def test_overlong_question_is_rejected_before_any_request():
    source = source_with_hotspot()
    analysis = analyse_script(source)
    review = completed_review(source)
    client = FakeClient()
    overlong = "x" * (COACH_MESSAGE_CHARACTER_LIMIT + 1)
    result = ask_coach(source, analysis, review, None, (), overlong, client=client)
    assert result.error_code == "message_too_long"
    assert client.responses.calls == []


def test_successful_answer_is_returned_and_uses_bounded_reasonable_request():
    source = source_with_hotspot()
    analysis = analyse_script(source)
    review = completed_review(source)
    cited_id = review.evidence.items[
        next(
            index
            for index, item in enumerate(review.evidence.items)
            if item.fact == "smell.mutable_default"
        )
    ].evidence_id
    target_reference = review.response.findings[0].source_reference
    client = FakeClient(
        api_result(coach_answer(evidence_ids=[cited_id], source_references=[target_reference]))
    )

    result = ask_coach(source, analysis, review, None, (), "Why does this matter?", client=client)

    assert result.succeeded
    assert result.message is not None
    assert result.message.role == "assistant"
    assert result.message.evidence_ids == (cited_id,)
    request = client.responses.calls[0]
    assert request["text_format"] is CoachResponse
    assert request["store"] is False
    assert request["reasoning"] == {"effort": "low"}
    assert "tools" not in request


def test_only_review_cited_evidence_is_sent_not_the_whole_package():
    source = source_with_hotspot()
    analysis = analyse_script(source)
    review = completed_review(source)
    evidence = review.evidence
    cited_ids = {
        evidence_id for finding in review.response.findings for evidence_id in finding.evidence_ids
    }
    assert cited_ids < {item.evidence_id for item in evidence.items}
    client = FakeClient(api_result(coach_answer()))

    ask_coach(source, analysis, review, None, (), "Why?", client=client)

    payload = json.loads(client.responses.calls[0]["input"][0]["content"])
    payload_ids = {item["evidence_id"] for item in payload["cited_deterministic_evidence"]}
    assert payload_ids == cited_ids
    assert len(payload["cited_deterministic_evidence"]) < len(evidence.items)


def test_approved_target_source_is_sent_but_not_the_complete_source():
    source = (
        "SECRET_UNRELATED = 42\n\n"
        "def focused(value=[]):\n    return value\n\n"
        "def unrelated():\n    return SECRET_UNRELATED\n"
    )
    analysis = analyse_script(source)
    review = completed_review(source)
    client = FakeClient(api_result(coach_answer()))

    ask_coach(source, analysis, review, None, (), "Why?", client=client)

    payload = json.loads(client.responses.calls[0]["input"][0]["content"])
    assert (
        payload["untrusted_approved_target_source"] == "def focused(value=[]):\n    return value\n"
    )
    assert "untrusted_source" not in payload
    assert "SECRET_UNRELATED" not in json.dumps(payload)


def test_large_source_is_never_resent_merely_because_chat_is_enabled():
    padding = "\n".join(
        f"def unrelated_{index}(value):\n    return value\n" for index in range(400)
    )
    source = f"{padding}\ndef focused(value=[]):\n    return value\n"
    analysis = analyse_script(source)
    review = completed_review(source)
    client = FakeClient(api_result(coach_answer()))

    ask_coach(source, analysis, review, None, (), "Why?", client=client)

    payload_text = client.responses.calls[0]["input"][0]["content"]
    assert len(payload_text) < len(source)
    assert "unrelated_0" not in payload_text


def test_verified_target_replacement_is_included_when_present():
    source = source_with_hotspot()
    analysis = analyse_script(source)
    review = completed_review(source)
    replacement = "def focused(value=None):\n    return value\n"
    refactor_client = FakeClient(
        api_result(
            ScriptRefactorResponse(
                outcome=RefactorDecisionOutcome.SUGGESTED_REFACTOR,
                target_source_reference=review.response.findings[0].source_reference,
                replacement_source=replacement,
                decision_reason="Removes the mutable default.",
            )
        )
    )
    refactor = generate_script_refactor(source, analysis, review, client=refactor_client)
    assert refactor.succeeded
    coach_client = FakeClient(api_result(coach_answer()))

    ask_coach(source, analysis, review, refactor, (), "What changed?", client=coach_client)

    payload = json.loads(coach_client.responses.calls[0]["input"][0]["content"])
    assert payload["untrusted_verified_target_replacement"] == replacement
    assert payload["target_comparison"] is not None
    assert payload["target_comparison"]["structural"] or payload["target_comparison"]["directional"]


def test_no_replacement_or_comparison_is_sent_without_a_verified_refactor():
    source = source_with_hotspot()
    analysis = analyse_script(source)
    review = completed_review(source)
    client = FakeClient(api_result(coach_answer()))

    ask_coach(source, analysis, review, None, (), "What changed?", client=client)

    payload = json.loads(client.responses.calls[0]["input"][0]["content"])
    assert payload["untrusted_verified_target_replacement"] is None
    assert payload["target_comparison"] is None


def test_invalid_evidence_id_citation_is_rejected():
    source = source_with_hotspot()
    analysis = analyse_script(source)
    review = completed_review(source)
    client = FakeClient(api_result(coach_answer(evidence_ids=["E9999"])))

    result = ask_coach(source, analysis, review, None, (), "Why?", client=client)

    assert result.error_code == "invalid_evidence_id"
    assert not result.succeeded


def test_invalid_source_reference_citation_is_rejected():
    source = source_with_hotspot()
    analysis = analyse_script(source)
    review = completed_review(source)
    client = FakeClient(api_result(coach_answer(source_references=["function:unknown:1@L1-L2"])))

    result = ask_coach(source, analysis, review, None, (), "Why?", client=client)

    assert result.error_code == "invalid_source_reference"


def test_limitations_and_follow_up_round_trip_into_the_message():
    source = source_with_hotspot()
    analysis = analyse_script(source)
    review = completed_review(source)
    parsed = CoachResponse(
        answer="Static analysis cannot confirm runtime behaviour here.",
        evidence_ids=[],
        source_references=[],
        limitations=["Static analysis does not observe runtime use."],
        suggested_follow_up="Would you like the before-and-after measurements?",
    )
    client = FakeClient(api_result(parsed))

    result = ask_coach(source, analysis, review, None, (), "Why?", client=client)

    assert result.succeeded
    assert result.message.limitations == ("Static analysis does not observe runtime use.",)


def test_conversation_history_sent_to_the_model_is_bounded():
    source = source_with_hotspot()
    analysis = analyse_script(source)
    review = completed_review(source)
    history = tuple(
        CoachMessage("user" if index % 2 == 0 else "assistant", f"turn {index}")
        for index in range(COACH_CHAT_HISTORY_MESSAGES + 4)
    )
    client = FakeClient(api_result(coach_answer()))

    ask_coach(source, analysis, review, None, history, "Why?", client=client)

    payload = json.loads(client.responses.calls[0]["input"][0]["content"])
    assert len(payload["untrusted_conversation_history"]) == COACH_CHAT_HISTORY_MESSAGES
    assert payload["untrusted_conversation_history"][-1]["content"] == "turn " + str(
        COACH_CHAT_HISTORY_MESSAGES + 3
    )


def test_no_live_openai_call_without_a_configured_api_key(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    source = source_with_hotspot()
    analysis = analyse_script(source)
    review = completed_review(source)
    result = ask_coach(source, analysis, review, None, (), "Why?")
    assert result.error_code == "missing_api_key"
    assert not result.request_attempted


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
    ]


@pytest.mark.parametrize(("error", "code"), openai_errors())
def test_transport_failures_are_typed_and_safe(error, code):
    source = source_with_hotspot()
    analysis = analyse_script(source)
    review = completed_review(source)
    client = FakeClient(error)

    result = ask_coach(source, analysis, review, None, (), "Why?", client=client)

    assert result.error_code == code
    assert result.request_attempted


def test_api_status_error_is_captured_safely_without_the_raw_body():
    source = source_with_hotspot()
    analysis = analyse_script(source)
    review = completed_review(source)
    request = httpx.Request("POST", "https://api.openai.com/v1/responses")
    sentinel = "PRIVATE-BODY-SENTINEL"
    response = httpx.Response(
        500, request=request, headers={"x-request-id": "req_coach_1"}, json={"error": sentinel}
    )
    error = openai.APIStatusError("failed", response=response, body={"error": sentinel})
    client = FakeClient(error)

    result = ask_coach(source, analysis, review, None, (), "Why?", client=client)

    assert result.error_code == "api_status_error"
    assert result.api_error_detail == ApiErrorDetail(500, "req_coach_1")
    assert sentinel not in result.error_message


def test_refusal_and_invalid_structured_output_are_typed():
    source = source_with_hotspot()
    analysis = analyse_script(source)
    review = completed_review(source)
    refusal_output = [SimpleNamespace(content=[SimpleNamespace(type="refusal")])]
    refused = ask_coach(
        source,
        analysis,
        review,
        None,
        (),
        "Why?",
        client=FakeClient(api_result(output=refusal_output)),
    )
    missing = ask_coach(source, analysis, review, None, (), "Why?", client=FakeClient(api_result()))
    wrong_type = ask_coach(
        source, analysis, review, None, (), "Why?", client=FakeClient(api_result(object()))
    )
    assert refused.error_code == "refusal"
    assert missing.error_code == "invalid_structured_output"
    assert wrong_type.error_code == "invalid_structured_output"


def test_validation_error_from_the_sdk_is_typed_and_safe():
    source = source_with_hotspot()
    analysis = analyse_script(source)
    review = completed_review(source)
    with pytest.raises(ValidationError) as caught:
        CoachResponse.model_validate({"answer": ""})
    client = FakeClient(caught.value)

    result = ask_coach(source, analysis, review, None, (), "Why?", client=client)

    assert result.error_code == "invalid_structured_output"


def test_schema_has_no_field_capable_of_carrying_replacement_code():
    forbidden_fields = {"replacement_source", "candidate", "code", "target_source_reference"}
    assert forbidden_fields.isdisjoint(CoachResponse.model_fields)


def test_developer_instructions_prohibit_execution_equivalence_and_code_generation():
    from codesage.ai import COACH_DEVELOPER_INSTRUCTIONS

    lowered = COACH_DEVELOPER_INSTRUCTIONS.lower()
    assert "execution" in lowered
    assert "behavioural equivalence" in lowered
    assert "runtime correctness" in lowered
    assert "generate suggested refactor" in lowered
    assert "generate a different refactor" in lowered
    assert "not a general-purpose coding assistant" in lowered
