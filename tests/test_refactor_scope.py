from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from codesage.ai import (
    CorrectionStatus,
    Finding,
    ReviewOutcome,
    ReviewResponse,
    ReviewResult,
    ScriptRefactorResponse,
    TechnicalCorrectionResponse,
    _verify_candidate,
    generate_script_refactor,
)
from codesage.analysis import analyse_script
from codesage.evidence import build_evidence_package


ORIGINAL = """import os

def choose_priority_item(values=[]):
    for value in values:
        if value:
            return value
    return None

def untouched(value):
    return value + 1

class Service:
    def method(self, value):
        return value

class Other:
    label = "other"
"""


class FakeResponses:
    def __init__(self, *values):
        self.values = list(values)
        self.calls = []

    def parse(self, **kwargs):
        self.calls.append(kwargs)
        return self.values.pop(0)


class FakeClient:
    def __init__(self, *values):
        self.responses = FakeResponses(*values)


def api_result(parsed):
    return SimpleNamespace(output_parsed=parsed, status="completed", output=())


def review_result(*, mutable_default: bool = True) -> ReviewResult:
    analysis = analyse_script(ORIGINAL)
    evidence = build_evidence_package(analysis)
    target_reference = next(
        item.source_reference
        for item in evidence.items
        if "function:choose_priority_item:" in item.source_reference
    )
    evidence_id = next(
        item.evidence_id
        for item in evidence.items
        if item.source_reference == target_reference
        and item.fact == ("smell.mutable_default" if mutable_default else "unit.nesting_depth")
    )
    finding = Finding(
        title="Focused target",
        category="maintainability",
        priority="medium",
        source_reference=target_reference,
        evidence_ids=[evidence_id],
        explanation="The measured result supports a focused change.",
        recommendation="Change only choose_priority_item.",
        learning_takeaway="Keep changes local to the reviewed definition.",
        uncertainty="Runtime behaviour was not observed.",
    )
    response = ReviewResponse(
        outcome=ReviewOutcome.REFACTOR_RECOMMENDED,
        summary="Review the selected target.",
        findings=[finding],
    )
    return ReviewResult(analysis, evidence, response, None, None, True)


def verify(candidate: str, *, mutable_default: bool = True):
    review = review_result(mutable_default=mutable_default)
    return _verify_candidate(
        ORIGINAL,
        candidate,
        review.original_analysis,
        review.response,
        review.evidence,
    )


VALID_BODY_CHANGE = ORIGINAL.replace(
    "    for value in values:\n        if value:\n            return value\n",
    "    for value in values:\n        if value is not None:\n            return value\n",
)
VALID_REPLACEMENT = """def choose_priority_item(values=[]):
    for value in values:
        if value is not None:
            return value
    return None
"""


def test_focused_target_body_change_preserves_unrelated_static_structure():
    result = verify(VALID_BODY_CHANGE)
    assert not isinstance(result, tuple)
    assert result.syntax_valid
    assert result.target_names == ("choose_priority_item",)
    assert result.comparison is not None
    assert "behavioural equivalence" in result.non_equivalence_notice


def test_supported_mutable_default_change_is_allowed_and_reported():
    candidate = VALID_BODY_CHANGE.replace("values=[]", "values=None").replace(
        "    for value in values:\n",
        "    values = [] if values is None else values\n    for value in values:\n",
    )
    result = verify(candidate)
    assert not isinstance(result, tuple)
    signature = next(
        item
        for item in result.comparison.structural
        if item.category == "signature" and item.name == "choose_priority_item"
    )
    assert signature.status.value == "changed"
    assert "choose_priority_item:mutable_default" in result.comparison.smells_removed


def test_target_default_change_without_supporting_evidence_is_rejected():
    candidate = VALID_BODY_CHANGE.replace("values=[]", "values=None")
    result = verify(candidate, mutable_default=False)
    assert result[0] == "unrelated_signature_changed"


@pytest.mark.parametrize(
    ("candidate", "code"),
    [
        (
            ORIGINAL.replace("def untouched(value):\n    return value + 1\n\n", ""),
            "unrelated_symbol_removed",
        ),
        (
            ORIGINAL.replace("    def method(self, value):\n        return value\n", "    pass\n"),
            "unrelated_symbol_removed",
        ),
        (ORIGINAL.replace('class Other:\n    label = "other"\n', ""), "unrelated_symbol_removed"),
        (
            ORIGINAL.replace("def untouched(value):", "def untouched(value, extra=None):"),
            "unrelated_signature_changed",
        ),
        (ORIGINAL.replace("return value + 1", "return value + 2"), "unrelated_definition_changed"),
        (ORIGINAL.replace("import os\n", ""), "required_import_removed"),
    ],
)
def test_unrelated_definition_and_import_changes_are_rejected(candidate, code):
    assert verify(candidate)[0] == code


def test_runtime_factory_cannot_replace_explicit_definitions():
    candidate = """import os
def choose_priority_item(values=[]):
    return next(iter(values), None)

def install(name):
    globals()[name] = lambda value: value

for name in ("untouched", "Service", "Other"):
    install(name)
"""
    result = verify(candidate)
    assert result[0] in {"unrelated_symbol_removed", "dynamic_code_generation_introduced"}


@pytest.mark.parametrize(
    "addition",
    [
        '\nexec("def generated():\\n    return 1")\n',
        '\nsource = "def generated():\\n    return 1"\nexec(source)\n',
        '\nglobals()["generated"] = lambda: 1\n',
        '\neval("1 + 1")\n',
        '\ncompile("value = 1", "<generated>", "exec")\n',
        '\n__import__("math")\n',
    ],
)
def test_new_dynamic_generation_and_namespace_synthesis_are_rejected(addition):
    assert verify(VALID_BODY_CHANGE + addition)[0] == "dynamic_code_generation_introduced"


def test_unchanged_preexisting_dynamic_construct_is_not_a_false_positive():
    original = ORIGINAL + '\nexec("value = 1")\n'
    analysis = analyse_script(original)
    base_review = review_result()
    review = ReviewResult(
        analysis, build_evidence_package(analysis), base_review.response, None, None, True
    )
    candidate = original.replace("if value:\n", "if value is not None:\n")
    result = _verify_candidate(original, candidate, analysis, review.response, review.evidence)
    assert not isinstance(result, tuple)


def test_scale_collapse_of_explicit_units_cannot_pass():
    definitions = "\n".join(
        f"def explicit_{index}(value):\n    return value\n" for index in range(244)
    )
    original = ORIGINAL + "\n" + definitions
    base = review_result()
    analysis = analyse_script(original)
    evidence = build_evidence_package(analysis)
    review = ReviewResult(analysis, evidence, base.response, None, None, True)
    collapsed = VALID_BODY_CHANGE + '\nexec("# generated APIs")\n'
    result = _verify_candidate(original, collapsed, analysis, review.response, evidence)
    assert isinstance(result, tuple)
    assert result[0] == "unrelated_symbol_removed"


def test_full_module_response_gets_one_target_only_correction_and_records_both_outcomes():
    review = review_result()
    invalid = ORIGINAL.replace("def untouched(value):\n    return value + 1\n\n", "")
    reference = review.response.findings[0].source_reference
    client = FakeClient(
        api_result(
            ScriptRefactorResponse(
                target_source_reference=reference,
                replacement_source=invalid,
            )
        ),
        api_result(
            TechnicalCorrectionResponse(
                target_source_reference=reference,
                replacement_source=VALID_REPLACEMENT,
            )
        ),
    )
    seen = []
    attempts = []
    result = generate_script_refactor(
        ORIGINAL,
        review.original_analysis,
        review,
        client=client,
        on_correction_start=seen.append,
        on_generation_attempt=lambda stage, source, codes: attempts.append((stage, source, codes)),
    )
    assert result.succeeded
    assert result.correction_status is CorrectionStatus.SUCCEEDED
    assert result.initial_failure_codes == ("replacement_definition_count_invalid",)
    assert result.correction_failure_codes == ()
    assert seen == ["replacement_definition_count_invalid"]
    assert attempts == [
        ("initial", invalid, ("replacement_definition_count_invalid",)),
        ("correction", VALID_REPLACEMENT, ()),
    ]
    assert len(client.responses.calls) == 2
    correction_payload = json.loads(client.responses.calls[1]["input"][0]["content"])
    assert correction_payload["verification_violation_codes"] == [
        "replacement_definition_count_invalid"
    ]
    assert correction_payload["focused_refactor_requirements"] == {
        "complete_file_return_prohibited": True,
        "dynamic_code_generation_prohibited": True,
        "targeted_replacement_only": True,
    }
    assert correction_payload["untrusted_target_source"].startswith("def choose_priority_item")
    assert "untrusted_source" not in correction_payload


def test_second_invalid_targeted_replacement_stops_without_a_third_request():
    review = review_result()
    invalid = ORIGINAL.replace("def untouched(value):\n    return value + 1\n\n", "")
    reference = review.response.findings[0].source_reference
    client = FakeClient(
        api_result(
            ScriptRefactorResponse(
                target_source_reference=reference,
                replacement_source=invalid,
            )
        ),
        api_result(
            TechnicalCorrectionResponse(
                target_source_reference=reference,
                replacement_source=invalid,
            )
        ),
    )
    result = generate_script_refactor(ORIGINAL, review.original_analysis, review, client=client)
    assert not result.succeeded
    assert result.review is review.response
    assert result.initial_failure_codes == ("replacement_definition_count_invalid",)
    assert result.correction_failure_codes == ("replacement_definition_count_invalid",)
    assert len(client.responses.calls) == 2
