"""Pure session-state and presentation helpers for the script interface."""

from __future__ import annotations

from collections.abc import Callable, MutableMapping
from dataclasses import dataclass
from enum import StrEnum
import re
from typing import Any

from codesage.ai import (
    CoachMessage,
    CoachResult,
    RefactorResult,
    RefactorAvailabilityStatus,
    ReviewResult,
    ask_coach,
    generate_script_refactor,
    refactor_availability,
    review_script,
)
from codesage.analysis import analyse_script
from codesage.config import PASTED_SOURCE_CHARACTER_LIMIT, SCRIPT_AI_REVIEW_CHARACTER_LIMIT
from codesage.models import AnalysisResult, AnalysedUnit, UnitKind
from codesage.source import (
    SourceDocument,
    SourceOrigin,
    normalise_example_source,
    normalise_pasted_source,
)
from codesage.thresholds import (
    COMPLEX_BOOLEAN_LEAVES,
    DEEP_NESTING_DEPTH,
    EXCESSIVE_TOP_LEVEL_STATEMENTS,
    HIGH_COMPLEXITY,
    LONG_FUNCTION_SLOC,
    OVERSIZED_PROCEDURAL_SLOC,
    TOO_MANY_PARAMETERS,
)

SOURCE_CHARACTER_LIMIT = PASTED_SOURCE_CHARACTER_LIMIT
ANALYSIS_KEY = "script_analysis"
REVIEW_KEY = "script_review"
REVIEW_ERROR_KEY = "script_review_error"
REFACTOR_KEY = "script_refactor"
REFACTOR_REQUEST_KEY = "script_refactor_request_identity"
REFACTOR_ERROR_KEY = "script_refactor_error"
ALTERNATIVE_REFACTOR_ERROR_KEY = "script_alternative_refactor_error"
REFACTOR_INSTRUCTIONS_KEY = "script_refactor_instructions"
SOURCE_KEY = "active_source_document"
SOURCE_MODE_KEY = "source_input_mode"
EXAMPLE_MODE = "Built-in example"

COACH_CHAT_KEY = "codesage_coach_chat"
COACH_CHAT_ERROR_KEY = "codesage_coach_chat_error"
COACH_CHAT_CONTEXT_KEY = "codesage_coach_chat_context_identity"

ReviewFunction = Callable[..., ReviewResult]
RefactorFunction = Callable[..., RefactorResult]
CoachFunction = Callable[..., CoachResult]
NOT_APPLICABLE = "—"


class RefactorResultState(StrEnum):
    """User-relevant state of the stored refactor result."""

    VERIFIED_REFACTOR = "verified_refactor"
    MODEL_ABSTAINED = "model_abstained"
    UNAVAILABLE_OR_INVALID = "unavailable_or_invalid"
    NO_RESULT = "no_result"


def classify_refactor_result(value: object | None) -> RefactorResultState:
    """Classify a stored value without treating mere key presence as verified code."""
    if value is None:
        return RefactorResultState.NO_RESULT
    if not isinstance(value, RefactorResult):
        return RefactorResultState.UNAVAILABLE_OR_INVALID
    if value.abstained:
        return RefactorResultState.MODEL_ABSTAINED
    verification = value.verification
    if (
        value.succeeded
        and value.suggested_refactor is not None
        and verification is not None
        and verification.analysis is not None
        and verification.comparison is not None
        and verification.syntax_valid
    ):
        return RefactorResultState.VERIFIED_REFACTOR
    return RefactorResultState.UNAVAILABLE_OR_INVALID


def _document(source: SourceDocument | str) -> SourceDocument:
    return source if isinstance(source, SourceDocument) else normalise_pasted_source(source)


def _clear_source_results(state: MutableMapping[str, Any]) -> None:
    for key in (
        SOURCE_KEY,
        ANALYSIS_KEY,
        REVIEW_KEY,
        REVIEW_ERROR_KEY,
        REFACTOR_KEY,
        REFACTOR_REQUEST_KEY,
        REFACTOR_ERROR_KEY,
        ALTERNATIVE_REFACTOR_ERROR_KEY,
        REFACTOR_INSTRUCTIONS_KEY,
        COACH_CHAT_KEY,
        COACH_CHAT_ERROR_KEY,
        COACH_CHAT_CONTEXT_KEY,
    ):
        state.pop(key, None)


def clear_coach_chat(state: MutableMapping[str, Any]) -> None:
    """Explicitly clear the current Ask CodeSage conversation only."""
    state.pop(COACH_CHAT_KEY, None)
    state.pop(COACH_CHAT_ERROR_KEY, None)
    state.pop(COACH_CHAT_CONTEXT_KEY, None)


def invalidate_stale_state(
    state: MutableMapping[str, Any], source: SourceDocument | str | None
) -> None:
    """Remove results that do not belong to the current complete source identity."""
    if source is None:
        _clear_source_results(state)
        return
    document = _document(source)
    stored_document = state.get(SOURCE_KEY)
    if stored_document is not None and stored_document.identity != document.identity:
        _clear_source_results(state)
        return
    analysis = state.get(ANALYSIS_KEY)
    if analysis is not None and analysis.source_digest != document.source_digest:
        _clear_source_results(state)
        return
    review = state.get(REVIEW_KEY)
    if review is not None and review.original_analysis.source_digest != document.source_digest:
        _clear_source_results(state)
        return
    refactor = state.get(REFACTOR_KEY)
    if (
        isinstance(refactor, RefactorResult)
        and refactor.original_analysis.source_digest != document.source_digest
    ):
        _clear_source_results(state)


def load_example(state: MutableMapping[str, Any]) -> SourceDocument:
    """Select the canonical example and invalidate results belonging to another source."""
    document = normalise_example_source()
    invalidate_stale_state(state, document)
    state[SOURCE_KEY] = document
    return document


def source_summary(document: SourceDocument) -> str:
    """Return concise source metadata for the normal reading flow."""
    origin = {
        SourceOrigin.PASTED: "Pasted source",
        SourceOrigin.UPLOADED: "Uploaded file",
        SourceOrigin.GITHUB: "Public GitHub file",
        SourceOrigin.EXAMPLE: "Built-in example",
    }[document.origin]
    eligibility = "AI review available" if document.ai_eligible else "Deterministic analysis only"
    return f"{origin} · {len(document.text):,} characters · {eligibility}"


def workflow_statuses(state: MutableMapping[str, Any]) -> tuple[str, str, str]:
    """Describe the three non-interactive product stages from existing state only."""
    analysis = state.get(ANALYSIS_KEY)
    document = state.get(SOURCE_KEY)
    analysis_complete = analysis is not None
    review = state.get(REVIEW_KEY)
    review_complete = isinstance(review, ReviewResult) and review.succeeded
    stored_refactor = state.get(REFACTOR_KEY)
    decision = refactor_availability(
        review if review is not None else state.get(REVIEW_ERROR_KEY),
        stored_refactor if isinstance(stored_refactor, RefactorResult) else None,
    )
    review_available = bool(
        analysis is not None
        and analysis.syntax_valid
        and isinstance(document, SourceDocument)
        and document.ai_eligible
    )
    return (
        "Complete" if analysis_complete else "Current",
        (
            "Complete"
            if review_complete
            else "Optional AI review available"
            if review_available
            else "After valid analysis"
            if analysis is None
            else "Unavailable for this source"
        ),
        decision.label,
    )


def handle_actions(
    state: MutableMapping[str, Any],
    source: SourceDocument | str,
    *,
    analyse_clicked: bool,
    review_clicked: bool,
    reviewer: ReviewFunction = review_script,
) -> str | None:
    """Apply explicit UI actions without executing or persisting submitted source."""
    document = _document(source)
    invalidate_stale_state(state, document)

    if analyse_clicked:
        analysis = analyse_script(document.text)
        state[SOURCE_KEY] = document
        state[ANALYSIS_KEY] = analysis
        state.pop(REVIEW_KEY, None)
        state.pop(REVIEW_ERROR_KEY, None)
        state.pop(REFACTOR_KEY, None)
        state.pop(REFACTOR_REQUEST_KEY, None)
        state.pop(REFACTOR_ERROR_KEY, None)
        state.pop(ALTERNATIVE_REFACTOR_ERROR_KEY, None)
        clear_coach_chat(state)

    if review_clicked:
        analysis = state.get(ANALYSIS_KEY)
        if analysis is None:
            return "Analyse the current script before requesting AI review."
        if not analysis.syntax_valid:
            return "Fix the syntax error before requesting AI review."
        if len(document.text) > SCRIPT_AI_REVIEW_CHARACTER_LIMIT:
            return (
                "The complete file exceeds the tested AI-review limit of "
                f"{SCRIPT_AI_REVIEW_CHARACTER_LIMIT:,} characters. Complete deterministic "
                "analysis remains available; no source is truncated or partially reviewed."
            )
        if REVIEW_KEY not in state:
            result = reviewer(document.text, analysis)
            if result.succeeded:
                state[REVIEW_KEY] = result
                state.pop(REVIEW_ERROR_KEY, None)
            else:
                state[REVIEW_ERROR_KEY] = result
    return None


def handle_refactor_action(
    state: MutableMapping[str, Any],
    source: SourceDocument | str,
    *,
    refactor_clicked: bool,
    optional_instructions: str,
    refactorer: RefactorFunction = generate_script_refactor,
    on_correction_start: Callable[[str], None] | None = None,
) -> str | None:
    """Generate the current refactor, or replace it with a distinct alternative.

    A request is treated as an alternative exactly when a verified refactor is already
    stored in REFACTOR_KEY. An alternative's failure never disturbs that existing verified
    refactor: it is recorded separately under ALTERNATIVE_REFACTOR_ERROR_KEY.
    """
    document = _document(source)
    invalidate_stale_state(state, document)
    if not refactor_clicked:
        return None
    analysis = state.get(ANALYSIS_KEY)
    review = state.get(REVIEW_KEY)
    if analysis is None or review is None:
        return "Get an AI review for the current source before generating a refactor."
    decision = refactor_availability(review)
    if decision.status is not RefactorAvailabilityStatus.AVAILABLE:
        return decision.explanation
    normalised_instructions = optional_instructions.strip()
    request_identity = (
        document.identity,
        review.response.model_dump_json() if review.response is not None else "",
        normalised_instructions,
    )
    cached_state = classify_refactor_result(state.get(REFACTOR_KEY))
    if state.get(REFACTOR_REQUEST_KEY) == request_identity and cached_state in {
        RefactorResultState.VERIFIED_REFACTOR,
        RefactorResultState.MODEL_ABSTAINED,
    }:
        return None
    existing_refactor = state.get(REFACTOR_KEY)
    is_alternative = (
        classify_refactor_result(existing_refactor) is RefactorResultState.VERIFIED_REFACTOR
    )
    if is_alternative:
        state.pop(ALTERNATIVE_REFACTOR_ERROR_KEY, None)
    else:
        state.pop(REFACTOR_KEY, None)
        state.pop(REFACTOR_ERROR_KEY, None)
        state.pop(ALTERNATIVE_REFACTOR_ERROR_KEY, None)
    call_kwargs: dict[str, Any] = {
        "optional_instructions": normalised_instructions,
        "on_correction_start": on_correction_start,
    }
    if (
        is_alternative
        and isinstance(existing_refactor, RefactorResult)
        and existing_refactor.suggested_refactor is not None
    ):
        call_kwargs["previous_suggestion"] = existing_refactor.suggested_refactor
    result = refactorer(document.text, analysis, review, **call_kwargs)
    if result.error_code is None:
        state[REFACTOR_KEY] = result
        state[REFACTOR_REQUEST_KEY] = request_identity
        state.pop(REFACTOR_ERROR_KEY, None)
        state.pop(ALTERNATIVE_REFACTOR_ERROR_KEY, None)
        clear_coach_chat(state)
    elif is_alternative:
        state[ALTERNATIVE_REFACTOR_ERROR_KEY] = result
    else:
        state[REFACTOR_ERROR_KEY] = result
    return None


def _coach_context_identity(
    state: MutableMapping[str, Any], document: SourceDocument
) -> tuple[Any, ...]:
    """Identify the exact source, review and refactor a chat answer depends on."""
    review = state.get(REVIEW_KEY)
    refactor = state.get(REFACTOR_KEY)
    return (
        document.identity,
        review.response.model_dump_json()
        if review is not None and review.response is not None
        else None,
        refactor.suggested_refactor
        if classify_refactor_result(refactor) is RefactorResultState.VERIFIED_REFACTOR
        else None,
    )


def coach_starter_questions(*, refactor_available: bool) -> tuple[str, ...]:
    """Return the optional starter questions appropriate to the current result state."""
    base = (
        "Explain the highest-priority finding more simply.",
        "Why does this issue matter?",
        "What should I test before changing the code?",
        "Explain the before-and-after measurements.",
        "What could CodeSage not verify?",
    )
    if not refactor_available:
        return base
    return base + (
        "Explain what changed in the refactor.",
        "Why did this measurement remain unchanged?",
        "Could this interface change affect callers?",
        "Why was a different refactor rejected?",
    )


def handle_coach_chat_action(
    state: MutableMapping[str, Any],
    source: SourceDocument | str,
    *,
    message: str,
    submit_clicked: bool,
    asker: CoachFunction = ask_coach,
) -> str | None:
    """Answer one explicit "Ask CodeSage" question. Makes an API request only on submission."""
    document = _document(source)
    if not submit_clicked:
        return None
    analysis = state.get(ANALYSIS_KEY)
    review = state.get(REVIEW_KEY)
    if analysis is None or review is None or not review.succeeded:
        return "Get a successful AI review before asking CodeSage about this result."
    identity = _coach_context_identity(state, document)
    if state.get(COACH_CHAT_CONTEXT_KEY) not in (None, identity):
        clear_coach_chat(state)
    state[COACH_CHAT_CONTEXT_KEY] = identity
    history: tuple[CoachMessage, ...] = tuple(state.get(COACH_CHAT_KEY, ()))
    refactor = state.get(REFACTOR_KEY)
    result = asker(document.text, analysis, review, refactor, history, message)
    if result.succeeded:
        assert result.message is not None
        user_message = CoachMessage("user", message.strip())
        state[COACH_CHAT_KEY] = (*history, user_message, result.message)
        state.pop(COACH_CHAT_ERROR_KEY, None)
    else:
        state[COACH_CHAT_ERROR_KEY] = result
    return None


def _display_value(value: int | str | None) -> int | str:
    return NOT_APPLICABLE if value is None else value


def analysis_summary(analysis: AnalysisResult, *, ai_eligible: bool | None) -> dict[str, int | str]:
    """Return compact file-level and inventory counts without altering analysis."""
    function_count = sum(unit.kind is UnitKind.FUNCTION for unit in analysis.units)
    method_count = sum(unit.kind is UnitKind.METHOD for unit in analysis.units)
    procedural_count = sum(unit.kind is UnitKind.MODULE for unit in analysis.units)
    hotspot_count = sum(bool(unit.smells) for unit in analysis.units)
    return {
        "Syntax": "Valid" if analysis.syntax_valid else "Invalid",
        "Physical lines": analysis.physical_lines,
        "SLOC": analysis.sloc,
        "Functions": function_count,
        "Methods": method_count,
        "Classes": len(analysis.classes),
        "Procedural units": procedural_count,
        "Analysable units": len(analysis.units),
        "Threshold-triggering hotspots": hotspot_count,
        "Warnings": len(analysis.analysis_warnings),
        "Exclusions": 0,
        "AI review eligible": (
            "Yes" if ai_eligible is True else "No" if ai_eligible is False else NOT_APPLICABLE
        ),
    }


def unit_inventory_rows(analysis: AnalysisResult) -> list[dict[str, int | str]]:
    """Return one bounded-table row per analysable unit."""
    return [
        {
            "Qualified name": unit.qualified_name,
            "Unit type": unit.kind.value,
            "Line range": f"{unit.line}–{unit.end_line}",
            "SLOC": unit.sloc,
            "Statements": unit.statement_count,
            "Complexity": str(_display_value(unit.complexity)),
            "Complexity rank": str(_display_value(unit.complexity_rank)),
            "Nesting depth": str(_display_value(unit.nesting_depth)),
            "Effective parameters": str(_display_value(unit.parameter_count)),
            "Smell count": len(unit.smells),
        }
        for unit in analysis.units
    ]


def unit_measurements(unit: AnalysedUnit) -> dict[str, int | str]:
    return {
        "SLOC": unit.sloc,
        "Statements": unit.statement_count,
        "Complexity": _display_value(unit.complexity),
        "Complexity rank": _display_value(unit.complexity_rank),
        "Nesting depth": _display_value(unit.nesting_depth),
        "Parameters": _display_value(unit.parameter_count),
    }


def metric_rows(items: tuple[Any, ...]) -> list[dict[str, Any]]:
    return [
        {
            "Unit": item.qualified_name,
            "Metric": item.metric,
            "Before": item.before,
            "After": item.after,
            "Status": item.status.value,
        }
        for item in items
    ]


def structural_rows(items: tuple[Any, ...]) -> list[dict[str, str]]:
    return [
        {"Category": item.category, "Name": item.name, "Status": item.status.value}
        for item in items
    ]


def refactor_action_label(state: MutableMapping[str, Any]) -> str:
    """Return the accessible action for the current verified-refactor state."""
    return (
        "Generate a different refactor"
        if classify_refactor_result(state.get(REFACTOR_KEY))
        is RefactorResultState.VERIFIED_REFACTOR
        else "Generate suggested refactor"
    )


_OUTCOME_LABELS = {
    "refactor_recommended": "Maintainability opportunity identified",
}


def readable_outcome(value: str) -> str:
    if value in _OUTCOME_LABELS:
        return _OUTCOME_LABELS[value]
    return value.replace("_", " ").capitalize()


def readable_smell(value: str) -> str:
    code = value.rsplit(":", 1)[-1]
    labels = {
        "deep_nesting": "Deep nesting",
        "mutable_default": "Mutable default argument",
        "long_function": "Long function or method",
        "high_cyclomatic_complexity": "High cyclomatic complexity",
        "oversized_procedural_module": "Oversized procedural module",
        "excessive_top_level_structure": "Excessive top-level structure",
        "too_many_parameters": "Too many parameters",
        "complex_boolean_expression": "Complex Boolean expression",
        "bare_exception": "Bare exception",
        "broad_exception": "Broad exception",
    }
    return labels.get(code, code.replace("_", " ").capitalize())


def readable_source_reference(value: str) -> str:
    match = re.match(r"(?:function|method|class|module):(.+):\d+@L(\d+)-L(\d+)$", value)
    if not match:
        return "Referenced code location"
    name, start, end = match.groups()
    return f"{name}, lines {start}–{end}"


@dataclass(frozen=True, slots=True)
class ReviewedIssueResult:
    code: str
    label: str
    status: str
    detail: str


@dataclass(frozen=True, slots=True)
class RefactorOutcomeSummary:
    label: str
    explanation: str
    addressed: tuple[ReviewedIssueResult, ...]
    still_present: tuple[ReviewedIssueResult, ...]
    unable_to_compare: tuple[ReviewedIssueResult, ...]
    other_measured_changes: tuple[str, ...]


_ISSUE_MEASUREMENTS = {
    "deep_nesting": ("nesting_depth", DEEP_NESTING_DEPTH),
    "high_cyclomatic_complexity": ("complexity", HIGH_COMPLEXITY),
    "long_function": ("sloc", LONG_FUNCTION_SLOC),
    "too_many_parameters": ("parameter_count", TOO_MANY_PARAMETERS),
    "oversized_procedural_module": ("sloc", OVERSIZED_PROCEDURAL_SLOC),
    "excessive_top_level_structure": (
        "statement_count",
        EXCESSIVE_TOP_LEVEL_STATEMENTS,
    ),
    "complex_boolean_expression": (None, COMPLEX_BOOLEAN_LEAVES),
}


def _reference_target(value: str) -> str | None:
    match = re.match(r"(?:function|method|class|module):(.+):\d+@L\d+-L\d+$", value)
    return match.group(1) if match else None


def _reviewed_smells(refactor: RefactorResult) -> tuple[tuple[str, str], ...]:
    cited_ids = {
        evidence_id for finding in refactor.review.findings for evidence_id in finding.evidence_ids
    }
    cited_facts = {
        (item.source_reference, item.fact.removeprefix("smell."))
        for item in refactor.evidence.items
        if item.evidence_id in cited_ids and item.fact.startswith("smell.")
    }
    targets = {
        target
        for finding in refactor.review.findings
        if (target := _reference_target(finding.source_reference)) is not None
    }
    if refactor.verification is not None and refactor.verification.target_names:
        targets &= set(refactor.verification.target_names)
    original_units = {unit.qualified_name: unit for unit in refactor.original_analysis.units}
    references_by_target = {
        target: {
            item.source_reference
            for item in refactor.evidence.items
            if _reference_target(item.source_reference) == target
        }
        for target in targets
    }
    reviewed: list[tuple[str, str]] = []
    for target in sorted(targets):
        unit = original_units.get(target)
        if unit is None:
            continue
        for smell in unit.smells:
            if any(
                (reference, smell.code) in cited_facts for reference in references_by_target[target]
            ):
                reviewed.append((target, smell.code))
    if reviewed:
        return tuple(dict.fromkeys(reviewed))
    return tuple(
        (target, smell.code)
        for target in sorted(targets)
        if target in original_units
        for smell in original_units[target].smells
    )


def refactor_outcome_summary(refactor: RefactorResult) -> RefactorOutcomeSummary:
    """Classify reviewed deterministic smells without changing verification or comparison."""
    verification = refactor.verification
    if verification is None or verification.analysis is None or verification.comparison is None:
        return RefactorOutcomeSummary(
            "Unable to compare all reviewed static findings",
            "CodeSage could not determine whether every reviewed static finding was addressed.",
            (),
            (),
            (),
            (),
        )
    after_units = {unit.qualified_name: unit for unit in verification.analysis.units}
    addressed: list[ReviewedIssueResult] = []
    still_present: list[ReviewedIssueResult] = []
    unresolved: list[ReviewedIssueResult] = []
    reviewed = _reviewed_smells(refactor)
    for target, code in reviewed:
        label = readable_smell(code)
        after = after_units.get(target)
        measurement_name, threshold = _ISSUE_MEASUREMENTS.get(code, (None, None))
        current_value = getattr(after, measurement_name) if after and measurement_name else None
        if after is None or (measurement_name is not None and current_value is None):
            unresolved.append(
                ReviewedIssueResult(
                    code, label, "unable_to_compare", f"{label} could not be compared."
                )
            )
        elif code in {smell.code for smell in after.smells}:
            detail = f"{label} is still present."
            if current_value is not None and threshold is not None:
                detail = (
                    f"{label} remains at {current_value}, which meets CodeSage's configured "
                    f"threshold of {threshold}."
                )
            still_present.append(ReviewedIssueResult(code, label, "still_present", detail))
        else:
            addressed.append(ReviewedIssueResult(code, label, "addressed", label))

    total = len(reviewed)
    if unresolved:
        outcome_label = "Unable to compare all reviewed static findings"
        explanation = (
            "CodeSage could not determine whether every reviewed static finding was addressed."
        )
    elif total and len(addressed) == total:
        outcome_label = "All reviewed static findings addressed"
        targets = ", ".join(verification.target_names)
        if total == 1:
            explanation = (
                "This refactor addresses the reviewed static maintainability finding identified "
                f"for {targets}."
            )
        elif total == 2:
            explanation = (
                "This refactor addresses both static maintainability findings identified for "
                f"{targets}."
            )
        else:
            explanation = (
                f"This refactor addresses all {total} static maintainability findings identified "
                f"for {targets}."
            )
    elif addressed:
        outcome_label = "Some reviewed static findings remain"
        explanation = (
            f"This refactor addresses {len(addressed)} of {total} reviewed static findings."
        )
    else:
        outcome_label = "Reviewed static findings remain"
        explanation = (
            "This refactor passed static verification, but the reviewed static maintainability "
            "findings remain."
        )

    other_changes: list[str] = []
    for item in verification.comparison.directional:
        if item.qualified_name not in verification.target_names or item.status.value != "regressed":
            continue
        if item.metric == "complexity" and item.before is not None and item.after is not None:
            suffix = (
                f", but remains below the configured high-complexity threshold of {HIGH_COMPLEXITY}"
                if item.after < HIGH_COMPLEXITY
                else f", meeting the configured high-complexity threshold of {HIGH_COMPLEXITY}"
            )
            other_changes.append(
                f"Cyclomatic complexity increased from {item.before} to {item.after}{suffix}."
            )
    for smell in verification.comparison.smells_introduced:
        if smell.rsplit(":", 1)[0] in verification.target_names:
            other_changes.append(f"New measured issue: {readable_smell(smell)}.")
    return RefactorOutcomeSummary(
        outcome_label,
        explanation,
        tuple(addressed),
        tuple(still_present),
        tuple(unresolved),
        tuple(dict.fromkeys(other_changes)),
    )


FAILURE_MESSAGES = {
    "missing_api_key": "OpenAI API access is not configured.",
    "timeout": "The OpenAI request timed out. Try again later.",
    "rate_limit": "The OpenAI rate limit was reached. Try again later.",
    "connection_error": "OpenAI could not be reached.",
    "api_status_error": "OpenAI returned an error.",
    "refusal": "The model declined the request.",
    "incomplete": "The model response was incomplete.",
    "response_failed": "The model could not complete the review.",
    "response_cancelled": "The AI review was cancelled.",
    "response_not_terminal": "The AI review did not reach a completed state.",
    "invalid_response_status": "The AI review returned an unknown response state.",
    "missing_parsed_output": "The model did not return a structured review.",
    "invalid_structured_output": "The model returned an invalid structured response.",
    "source_analysis_mismatch": "The source changed. Analyse it again before review.",
    "source_syntax_error": "Fix the syntax error before requesting AI review.",
    "source_too_large_for_ai": (
        "This file is too large for complete-file AI review; deterministic analysis is available."
    ),
    "mode_violation": "The model returned an outcome that is invalid for script review.",
    "script_field_violation": "The model returned fields that are invalid for script review.",
    "zero_hotspot_mode_violation": "The model recommended an unsupported zero-hotspot change.",
    "missing_grounding_reference": "The AI finding was not supported by CodeSage's evidence.",
    "invalid_source_reference": "The AI response referenced an unknown code location.",
    "invalid_evidence_id": "The AI response referenced an unknown piece of evidence.",
    "duplicate_evidence_id": "The model response repeated a deterministic evidence reference.",
    "evidence_source_mismatch": "The AI response linked a finding to the wrong code location.",
    "missing_recommendation": "The AI response did not provide a supported recommendation.",
    "unsupported_refactor_recommendation": (
        "The AI review recommended a refactor but did not provide the grounded target evidence "
        "required to offer one."
    ),
    "refactor_not_available": "This review does not recommend a supported refactor.",
    "refactor_missing_smell_evidence": (
        "The reviewed finding for this hotspot did not cite a measured maintainability smell."
    ),
    "instructions_too_long": "Optional instructions are too long.",
    "candidate_too_large": "The generated refactor exceeded the permitted size.",
    "candidate_syntax_invalid": "The generated refactor was not valid Python.",
    "candidate_format_invalid": "The generated refactor was not complete Python source.",
    "candidate_incomplete": "The generated refactor was not a complete-file replacement.",
    "refactor_verification_failed": (
        "CodeSage could not verify that the generated refactor stayed within the recommended "
        "scope. The AI review is still available."
    ),
    "unrelated_symbol_removed": "The generated refactor removed an unrelated definition.",
    "unrelated_signature_changed": "The generated refactor changed an unrelated interface.",
    "unrelated_definition_changed": "The generated refactor changed unrelated code.",
    "required_import_removed": "The generated refactor removed a required import.",
    "dynamic_code_generation_introduced": (
        "The generated refactor introduced unsupported runtime code generation."
    ),
    "target_scope_violation": "The generated refactor exceeded the recommended change scope.",
    "target_implementation_unchanged": (
        "The generated version did not change the reviewed target implementation."
    ),
    "complete_file_structure_unverified": (
        "CodeSage could not verify the complete static file structure."
    ),
    "target_reference_mismatch": "The generated replacement referenced the wrong code location.",
    "replacement_too_large": "The generated replacement exceeded its permitted size.",
    "replacement_format_invalid": "The generated replacement was not one Python definition.",
    "replacement_syntax_invalid": "The generated replacement was not valid Python.",
    "replacement_definition_count_invalid": (
        "The generated replacement contained more than the selected hotspot."
    ),
    "replacement_target_mismatch": "The generated replacement named a different target.",
    "reconstruction_failed": "CodeSage could not insert the generated replacement reliably.",
    "alternative_not_different": (
        "The generated replacement was identical to the current verified refactor."
    ),
    "coach_source_mismatch": "The source changed. Analyse it again before asking a question.",
    "empty_message": "Enter a question before sending.",
    "message_too_long": "Questions are too long.",
}


def failure_message(error_code: str | None) -> str:
    """Map internal typed failures to fixed, privacy-safe interface text."""
    if error_code in FAILURE_MESSAGES:
        return FAILURE_MESSAGES[error_code]
    return "The AI review could not be completed safely."
