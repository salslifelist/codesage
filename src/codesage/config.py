"""Canonical bounded product configuration for the CodeSage script MVP."""

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
