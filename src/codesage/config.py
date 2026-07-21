"""Canonical bounded product configuration for the CodeSage script MVP."""

from __future__ import annotations

import hmac
import os
from collections.abc import Mapping
from dataclasses import dataclass


AI_ENABLED_VALUES = frozenset({"1", "true", "yes", "on"})


@dataclass(frozen=True)
class AIAccessConfiguration:
    """Non-secret availability facts for hosted AI features."""

    enabled: bool
    access_code_configured: bool
    api_key_configured: bool
    model: str | None

    @property
    def available(self) -> bool:
        """Return whether a browser session may attempt to unlock AI features."""
        return self.enabled and self.access_code_configured and self.api_key_configured


def read_ai_access_configuration(
    environ: Mapping[str, str] | None = None,
) -> AIAccessConfiguration:
    """Read hosted-AI availability without retaining either configured secret."""
    values = os.environ if environ is None else environ
    enabled = values.get("AI_ENABLED", "").strip().lower() in AI_ENABLED_VALUES
    access_code = values.get("JUDGE_ACCESS_CODE", "")
    api_key = values.get("OPENAI_API_KEY", "")
    model = values.get("OPENAI_MODEL", "").strip() or None
    return AIAccessConfiguration(
        enabled=enabled,
        access_code_configured=bool(access_code.strip()),
        api_key_configured=bool(api_key.strip()),
        model=model,
    )


def verify_judge_access_code(
    submitted_code: str,
    environ: Mapping[str, str] | None = None,
) -> bool:
    """Compare a submitted code in constant time when hosted AI is configured."""
    values = os.environ if environ is None else environ
    configuration = read_ai_access_configuration(values)
    expected_code = values.get("JUDGE_ACCESS_CODE", "")
    if not configuration.available or not submitted_code:
        return False
    return hmac.compare_digest(submitted_code, expected_code)


PASTED_SOURCE_CHARACTER_LIMIT = 200_000
SOURCE_RESPONSE_BYTE_LIMIT = 200_000
DECODED_SOURCE_CHARACTER_LIMIT = 200_000
SCRIPT_AI_REVIEW_CHARACTER_LIMIT = 100_000
SCRIPT_CANDIDATE_ABSOLUTE_LIMIT = 160_000

GITHUB_REQUEST_TIMEOUT_SECONDS = 10.0
MAX_VALIDATED_GITHUB_REDIRECTS = 3

REFACTOR_INSTRUCTION_CHARACTER_LIMIT = 500

# "Ask CodeSage about this result" follow-up chat. Explanation-only: bounded input,
# bounded conversation history sent to the model and a modest output budget, since
# answers are short explanations, not generated code or complete-file reviews.
COACH_MESSAGE_CHARACTER_LIMIT = 1_000
COACH_CHAT_HISTORY_MESSAGES = 6
COACH_MAX_OUTPUT_TOKENS = 2_000

# Print reports omit duplicated complete-file source listings above this size to
# keep the generated PDF a reasonable length; measurements and evidence are never
# shortened because of source size.
PRINT_COMPLETE_SOURCE_CHARACTER_LIMIT = 12_000

# Complete-file reviews may contain up to 100,000 input characters and a large
# structured candidate. These remain finite safeguards, not service guarantees.
OPENAI_REQUEST_TIMEOUT_SECONDS = 120.0
OPENAI_MAX_OUTPUT_TOKENS = 64_000

# Reserved for the future notebook milestone; keeping them here prevents the
# approved limits from drifting while notebook support remains out of scope.
NOTEBOOK_DETERMINISTIC_CODE_CELL_LIMIT = 50
NOTEBOOK_AI_ANALYSABLE_CELL_LIMIT = 20
NOTEBOOK_AI_CODE_CHARACTER_LIMIT = 30_000
