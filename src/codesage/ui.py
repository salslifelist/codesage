"""Pure session-state and presentation helpers for the script interface."""

from __future__ import annotations

from collections.abc import Callable, MutableMapping
from typing import Any

from codesage.ai import ReviewResult, review_script
from codesage.analysis import analyse_script
from codesage.models import AnalysisResult, AnalysedUnit
from codesage.source import (
    AI_REVIEW_CHARACTER_LIMIT,
    SOURCE_INGESTION_LIMIT,
    SourceDocument,
    normalise_pasted_source,
)

SOURCE_CHARACTER_LIMIT = SOURCE_INGESTION_LIMIT
ANALYSIS_KEY = "script_analysis"
REVIEW_KEY = "script_review"
SOURCE_KEY = "active_source_document"

ReviewFunction = Callable[[str, AnalysisResult], ReviewResult]


def _document(source: SourceDocument | str) -> SourceDocument:
    return source if isinstance(source, SourceDocument) else normalise_pasted_source(source)


def invalidate_stale_state(
    state: MutableMapping[str, Any], source: SourceDocument | str | None
) -> None:
    """Remove results that do not belong to the current complete source identity."""
    if source is None:
        state.pop(SOURCE_KEY, None)
        state.pop(ANALYSIS_KEY, None)
        state.pop(REVIEW_KEY, None)
        return
    document = _document(source)
    stored_document = state.get(SOURCE_KEY)
    if stored_document is not None and stored_document.identity != document.identity:
        state.pop(SOURCE_KEY, None)
        state.pop(ANALYSIS_KEY, None)
        state.pop(REVIEW_KEY, None)
        return
    analysis = state.get(ANALYSIS_KEY)
    if analysis is not None and analysis.source_digest != document.source_digest:
        state.pop(SOURCE_KEY, None)
        state.pop(ANALYSIS_KEY, None)
        state.pop(REVIEW_KEY, None)
        return
    review = state.get(REVIEW_KEY)
    if review is not None and review.original_analysis.source_digest != document.source_digest:
        state.pop(REVIEW_KEY, None)


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

    if review_clicked:
        analysis = state.get(ANALYSIS_KEY)
        if analysis is None:
            return "Analyse the current script before requesting AI review."
        if not analysis.syntax_valid:
            return "Fix the syntax error before requesting AI review."
        if len(document.text) > AI_REVIEW_CHARACTER_LIMIT:
            return (
                f"Complete-file AI review is limited to {AI_REVIEW_CHARACTER_LIMIT:,} "
                "characters; deterministic analysis remains available."
            )
        if REVIEW_KEY not in state:
            state[REVIEW_KEY] = reviewer(document.text, analysis)
    return None


def unit_measurements(unit: AnalysedUnit) -> dict[str, int | str | None]:
    return {
        "SLOC": unit.sloc,
        "Statements": unit.statement_count,
        "Complexity": unit.complexity,
        "Complexity rank": unit.complexity_rank,
        "Nesting depth": unit.nesting_depth,
        "Parameters": unit.parameter_count,
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


FAILURE_MESSAGES = {
    "missing_api_key": "OpenAI API access is not configured.",
    "timeout": "The AI review timed out. Try again later.",
    "rate_limit": "The AI review rate limit was reached. Try again later.",
    "connection_error": "The AI review service could not be reached.",
    "api_status_error": "The AI review service returned an error.",
    "refusal": "The model declined to provide this review.",
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
    "candidate_invariant": "The model response did not contain a valid candidate for its outcome.",
    "candidate_syntax_invalid": (
        "The proposed candidate was not valid Python and could not be repaired safely. "
        "The grounded review is still available."
    ),
    "zero_hotspot_mode_violation": "The model recommended an unsupported zero-hotspot change.",
    "missing_grounding_reference": "The model response omitted required grounding references.",
    "invalid_source_reference": "The model response cited an invalid source reference.",
    "invalid_evidence_id": "The model response cited invalid deterministic evidence.",
    "duplicate_evidence_id": "The model response repeated a deterministic evidence reference.",
    "evidence_source_mismatch": "The model response linked evidence to the wrong source.",
    "candidate_too_large": "The proposed candidate exceeded the permitted size.",
}


def failure_message(error_code: str | None) -> str:
    """Map internal typed failures to fixed, privacy-safe interface text."""
    if error_code in FAILURE_MESSAGES:
        return FAILURE_MESSAGES[error_code]
    return "The AI review could not be completed safely."
