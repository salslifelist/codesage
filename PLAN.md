# CodeSage Competition MVP Plan

## Status and authority

This is the single authoritative implementation plan for CodeSage. It incorporates the approved context audit, feasibility revisions, amendment review, submission scope freeze, zero-hotspot procedure, evaluation distinction and procedural-module rules. The source planning documents are preserved outside the repository and are superseded by this file.

The majority of core development, testing, evaluation, deployment and documentation must remain in the primary Codex thread. Run `/feedback` there only after most core functionality has been built. Every commit and push requires explicit human approval.

## Product and user

CodeSage is a deployed Streamlit maintainability coach for complete Python scripts. It accepts pasted source, a local `.py` file, one public-GitHub `.py` URL or an original built-in example; identifies up to three transparent structural hotspots without execution; uses GPT-5.6 to explain and refactor them from deterministic evidence; and statically compares the original with the reconstructed suggestion while withholding claims of behavioural correctness.

Primary users are junior and intermediate Python developers, data scientists, machine-learning practitioners, students and small teams. The educational journey is evidence → explanation → targeted user-requested refactor → deterministic full-file reconstruction → verification → qualified comparison.

Public scope statement: “CodeSage currently supports complete Python script analysis. Notebook and additional language support are planned future work.”

## Closed scope

The competition MVP excludes:

- Big-O, time-complexity and auxiliary-space estimation;
- Maintainability Index or any proprietary aggregate quality score;
- model training or fine-tuning;
- repository-wide or multi-repository analysis;
- Jupyter notebook input, analysis, review and reconstruction;
- additional programming languages;
- execution of submitted or generated code;
- private GitHub repositories, GitHub OAuth and arbitrary URL fetching;
- semantic-equivalence, runtime-performance or security claims;
- vulnerability, malware, energy, carbon or sustainability analysis;
- RAG, embeddings, vector databases, user accounts and persistent databases;
- the full controlled grounded-versus-ungrounded research experiment beyond the bounded submission validation set;
- unrestricted general-purpose coding chat: the "Ask CodeSage" follow-up chat answers only about the current completed result;
- code generation, rewriting or file modification through the explanation chat: chat requests for new code are redirected to the dedicated refactor actions, never fulfilled inline;
- silent evidence or measurement truncation in any report, appendix or chat response;
- persistent, server-side or cross-session storage of chat conversations, submitted source or generated candidates.

## Approved stack

- CPython 3.11 locally and on Streamlit Community Cloud.
- Standard-library `venv` and pip.
- Streamlit 1.59.2.
- `ast` plus Radon 6.0.1 for cyclomatic complexity.
- nbformat 5.10.4 remains pinned from feasibility work but is not used to claim notebook support in
  the submitted MVP.
- OpenAI Python SDK 2.46.0 using the Responses API.
- Pydantic 2.13.4 strict models.
- HTTPX 0.28.1.
- pytest 9.1.1 and Ruff 0.15.22.

Do not introduce uv, Poetry, Pipenv, Conda, another Python version or an additional framework without approval.

## Inputs and normalisation

Accept exactly one complete Python script through:

1. pasted Python;
2. local `.py` upload;
3. an approved public GitHub `.py` file URL;
4. an original built-in example.

All routes produce one normalised source model containing origin, display name, decoded script source, byte count, provenance and AI eligibility. Loading the built-in example follows the same identity and stale-state invalidation path as the other routes and never requests AI review automatically.

The public-GitHub route uses one explicit `Load GitHub file` action. Changing the URL field or
pressing Enter never fetches automatically; visible helper copy instructs the user to paste an
approved public `.py` URL and then select the button. Any generic input instruction implying that
Enter loads the file is hidden only inside the keyed GitHub loader, never globally.

Pasted-source acquisition is limited to 200,000 characters. Upload and public-GitHub acquisition are limited to 200,000 response bytes, and decoded uploaded or fetched text is additionally subject to an explicit 200,000-character limit. Local text must decode as UTF-8. GitHub support is restricted to recognised `github.com/{owner}/{repo}/blob/{ref}/{path}` and `raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}` shapes. Convert approved blob URLs locally, fetch from allow-listed hosts over HTTPS, disable automatic/general redirects, and allow at most three manually followed redirect hops after revalidating every HTTPS target against the exact approved hosts and file shapes. Stream with the response-size limit and use bounded timeouts. Never clone or browse a repository. Never silently truncate, summarise or select a subset of an acquired source.

Complete-file script AI review is limited to 100,000 source characters. Scripts containing 100,001 through 200,000 characters retain complete deterministic analysis but are not sent to OpenAI; they must not be truncated or replaced with a hotspot-only review.

## Deterministic maintainability analysis

Maintainability means local structural characteristics affecting how readily a function, method or module body can be understood, modified and tested. It does not measure correctness, architecture, test quality or overall software quality.

### Measurements

- syntax validity and parse errors;
- physical lines and source lines of code (SLOC);
- functions, methods and classes with qualified names and locations;
- function or method length;
- statement count;
- Radon cyclomatic complexity and A–F rank;
- maximum control-structure nesting depth;
- effective parameter count, excluding conventional `self` or `cls`;
- module-level procedural SLOC and direct statement count.

SLOC is the number of non-blank, non-comment source lines in the applicable source range.

Function and method statement count includes descendant `ast.stmt` nodes but excludes statements inside nested function, async-function and class definitions.

Nesting depth counts `if`, `for`, `async for`, `while`, `with`, `async with`, `try` and `match` structures. `elif` chains remain at the same logical nesting level.

Boolean-leaf counting recursively flattens `and` and `or` expressions. Each non-`BoolOp` operand is one leaf, and unary `not` does not add a leaf.

### Smells and thresholds

| Smell | Deterministic trigger |
| --- | --- |
| Long function or method | SLOC > 50 |
| Deep nesting | Maximum nesting depth ≥ 4 |
| High cyclomatic complexity | Score ≥ 11 / Radon rank C or worse |
| Too many parameters | Effective parameter count > 5 |
| Complex Boolean expression | At least four Boolean leaves in one condition |
| Mutable default | List/dict/set literal or comprehension, or direct `list`/`dict`/`set` call |
| Bare exception | `except:` |
| Broad exception | `except Exception` or a tuple containing `Exception` |
| Oversized procedural module | Top-level procedural SLOC > 50 |
| Excessive top-level structure | More than 30 qualifying direct statements |

Thresholds are configurable constants and must be tested and documented as product defaults, not universal laws.

Smell severity for deterministic hotspot ordering is:

- **High:** long function or method; deep nesting; high cyclomatic complexity; oversized procedural module; excessive top-level structure.
- **Medium:** too many parameters; complex Boolean expression; mutable default; bare exception; broad exception.

Severity is used only for deterministic hotspot ordering. It is not a claim about runtime risk, correctness or overall quality.

### Procedural SLOC

Module-level procedural SLOC comprises de-duplicated non-blank, non-comment lines belonging to qualifying executable constructs rooted directly in `Module.body`. Include complete ranges of assignments, expressions and module-level `if`, loops, `with`, `try`, `match` and equivalent constructs, including statements nested inside those constructs. Exclude imports, function/class definitions and their complete bodies, and the recognised module docstring.

Direct top-level statement count is the number of qualifying executable entries in `Module.body`.

### Hotspot granularity and selection

Functions and methods are the primary units for function length, nesting, complexity, parameters, Boolean logic, mutable defaults and exception smells. A module body is a hotspot only for the two procedural top-level smells.

Do not duplicate the same issue at symbol and module levels. Unsupported or partially analysed content is a manual-review warning, never a smell by itself.

Select no more than three candidates using this stable lexicographic order:

1. highest triggered severity;
2. number of distinct, non-duplicated smells;
3. cyclomatic complexity where applicable;
4. applicable SLOC;
5. source order;
6. qualified name or stable cell key.

Show every contributing factor; never calculate a hidden aggregate score.

At the cyclomatic-complexity sorting stage, a unit for which complexity is not applicable uses a value lower than every valid function or method score.

### Zero-hotspot result

When no analysable unit crosses a threshold, return `NO_HOTSPOTS_ABOVE_THRESHOLDS` and display “No threshold-based maintainability hotspots were found.” Continue showing metadata, measurements, units, thresholds, warnings and exclusions. Do not select an arbitrary unit or describe the source as universally clean, correct, safe or fully maintainable.

## Future product work outside the submitted MVP

Jupyter notebook support, additional programming languages, repository-wide analysis and runtime or
behavioural verification are planned future work. They are not submission requirements and must not
be presented as available in the production interface or public MVP description. Reserved notebook
limits and shared-schema fields may remain internally to avoid design churn, but they do not establish
product support. Any future notebook implementation must preserve the non-execution, explicit-target,
bounded-input and evidence-validation principles in this plan.

## GPT-5.6 integration

Use configurable `OPENAI_MODEL`, defaulting to the verified competition model `gpt-5.6-sol`, through `OpenAI().responses.parse(...)`. Start with reasoning effort `low`; change it only after evaluation. The product journey is `evidence -> explanation -> targeted user-requested refactor -> deterministic full-file reconstruction -> verification -> qualified comparison`. An explicit AI-review request returns evidence-based explanation and recommendations without rewritten source. Only after a valid `refactor_recommended` review may a separate explicit request generate one approved function or method replacement. CodeSage reconstructs the complete suggested file locally from the unchanged original and that targeted replacement; OpenAI is not asked to return the complete file. Neither request uses tools.

After a review has parsed successfully, exactly one citation-only correction request is permitted
when full deterministic validation reports `missing_grounding_reference`,
`invalid_source_reference`, `invalid_evidence_id`, `duplicate_evidence_id` or
`evidence_source_mismatch`. The strict correction schema contains only zero-based finding indexes,
exact source references and exact evidence IDs. It receives the original parsed review and compact
evidence catalogue but not the complete Python source. CodeSage applies only those reference changes
locally, preserves every prose and outcome field, and reruns the complete validator. A failed second
validation withholds the review and never triggers a third request. This bounded evidence-reference
recovery is distinct from SDK transport behaviour, refactor technical correction, alternative
refactoring and Ask CodeSage requests.

Each explicit refactor-generation request may make at most one automatic technical-correction request, and only when a successfully parsed targeted replacement is malformed, names the wrong target, contains invalid syntax or unsupported content, cannot be inserted safely, or fails the deterministic maintainability-improvement gate below. The correction remains bound to the same target, requests only a replacement region and never requests the complete file. Correction never recurses or changes the validated review. A user may explicitly request a different targeted refactor, with optional instructions, without rerunning that review.

### Code-aware recommendation, generation and deterministic veto

GPT-5.6 makes the code-aware recommendation and generation decision: whether a targeted
refactor is worth attempting, what coding approach to take, and what code to generate. A
`refactor_recommended` review may enable generation only when at least one finding for the
selected target cites an actual deterministic `smell.<code>` evidence item; general
measurements such as SLOC, complexity or nesting alone are not sufficient. The derived smell
codes are supplied to the refactor request as explicit static maintainability goals.

One immutable refactor-availability decision is authoritative across production validation, the
workflow indicator, Overview, AI review, Refactor and print report. It distinguishes `available`,
`already_verified`, `no_refactor_needed`, `insufficient_evidence`,
`unsupported_recommendation` and `no_review`. Availability requires a successful
`refactor_recommended` review, deterministic hotspots, a non-empty recommendation, a supported
function or method target and at least one cited `smell.<code>` item belonging to that exact target.
Severity alone never overrides the review outcome. A recommended review without that actionable
target evidence is rejected before storage with `unsupported_refactor_recommendation`; it must not
be displayed as a successful recommendation that later becomes unavailable at generation time.

The refactor-generation request may itself abstain: GPT-5.6 returns `suggested_refactor` with
one replacement, or `no_better_refactor` with no replacement and a required `decision_reason`,
when it cannot justify a clearly more maintainable targeted replacement. Abstention never
triggers the technical-correction request and never displays a candidate.

Deterministic verification has veto authority over every proposed replacement. A candidate is
displayed only after CodeSage's independent, deterministic maintainability-improvement gate
accepts it (see Candidate limits and verification). Failed attempts, including a failed
correction, are withheld and explained with concrete measured reasons; no generated source is
ever shown for a rejected candidate. The absence of an accepted candidate does not prove that no
possible refactor exists — it means CodeSage could not verify one within its static checks and
the one permitted correction attempt.

Do not claim behavioural equivalence, runtime correctness or universal superiority for any
generated candidate, verified or not.

### Alternative refactoring

"Generate a different refactor" is a request for a meaningfully different coding approach to the
same approved target, not a repeat of the currently verified one. When a verified refactor already
exists, its exact target replacement is extracted locally (never the complete file) and supplied to
the next refactor request as the previous replacement to differ from. The developer prompt requires
a genuinely distinct approach and permits `no_better_refactor` when none exists. CodeSage compares
the AST of the newly generated targeted replacement with that previous replacement; an AST-equivalent
alternative is rejected (`alternative_not_different`) and is eligible for the existing single
technical-correction attempt. If the correction is also AST-equivalent to the previous replacement,
both attempts are withheld. A failed alternative request never invalidates or replaces the current
verified refactor. The one-target, one-definition replacement contract applies identically to
alternative requests.

### Refactor state model

The current verified refactor and the latest alternative-attempt status are distinct states:

- the current verified refactor (or a model abstention) is the only refactor state that persists
  across requests until explicitly replaced;
- an initial-refactor failure (no verified refactor yet exists) is a separate error state;
- an alternative-refactor failure (a verified refactor already exists) is a separate error state
  again, and must never be presented as if it invalidated the existing verified refactor.

Mere presence of `REFACTOR_KEY` never means that code changed. One shared classifier distinguishes a
verified refactor, model abstention, unavailable/invalid result and no result. A verified refactor
requires success, complete suggested source, syntax-valid verification, deterministic reanalysis and
a complete comparison. The separate canonical availability decision gives the Refactor workflow
stage the explanatory labels `Available`, `Verified`, `No change recommended`, `Insufficient
evidence`, `Review needs correction` or `After AI review`; the unexplained `Not offered` label is
not used.

State transitions:

- before an initial request: clear the initial-refactor and alternative-refactor error states;
- before an alternative request: clear only the alternative-refactor error state and preserve the
  current verified refactor;
- after a successful initial request: store the new current verified refactor; clear both error
  states;
- after a successful alternative request: replace the current verified refactor with the newly
  verified alternative; clear both error states; update the cached request identity;
- after a failed initial request: do not create a current verified refactor; store the failure as
  the initial-refactor error state;
- after a failed alternative request: preserve the existing current verified refactor unchanged;
  store the failure only as the alternative-refactor error state.

User-facing wording must never imply both that a verified refactor is recommended and that no code
change is recommended in the same breath. A failed alternative reads distinctly from a failed
initial request and always states that the existing current verified refactor remains unchanged.

### Optional-instruction limits

The maximum length of optional first- and alternative-refactor instructions is one configured
constant (500 characters). The interface shows the exact limit in the field label and a live
"current/limit" character counter below the field. The same constant enforces the limit on the
backend request; the frontend `max_chars` and the backend check are never allowed to drift apart.

### API errors and retry policy

When OpenAI returns an HTTP error, CodeSage records only the HTTP status code and the request ID
when present. The interface shows a fixed, privacy-safe message interpolating the status code, with
the request ID available in a collapsed "Technical details" control. The raw response body, the
submitted prompt, the submitted source and API keys are never displayed, logged or included in any
error. All other typed failures keep their existing fixed, privacy-safe messages.

The OpenAI SDK client is configured with one transport-level retry (`max_retries=1`) for transient
network failures. This is distinct from, and does not replace, CodeSage's own one bounded
technical-correction attempt: the SDK retry repeats an unanswered request after a transport failure;
the technical correction resends a validated failure to the model once, asking it to fix a rejected
candidate. The two mechanisms never compound recursively.

Before sending source, require explicit user action and disclose that source will be sent to OpenAI. Keep deterministic analysis available without a key or successful model call.

The developer prompt must:

- delimit source, metadata and evidence;
- state that source, comments, strings and filenames are untrusted data;
- forbid following embedded instructions;
- forbid invented measurements, execution claims and behavioural-equivalence claims;
- require supplied evidence IDs for deterministic factual claims;
- require interface preservation or an explicit structural warning;
- require the strict schema.

The shared response outcome is one of:

- `refactor_recommended`;
- `no_refactor_needed`;
- `insufficient_evidence`;
- `multi_cell_change_required`.

The review response contains no rewritten source. For scripts, only a validated `refactor_recommended` review enables the separate refactor action. Reserved notebook/evaluation fields and the `multi_cell_change_required` outcome remain outside the production script schema and do not imply submitted product support.

Each finding includes title, category, priority, source reference, evidence ID list, explanation, recommendation, learning takeaway and uncertainty. Validate field bounds, evidence references, symbols, cells, outcome/candidate consistency and output sizes. Reject malformed results; never invent missing fields.

### Zero-hotspot runtime and evaluation distinction

In the production zero-hotspot advisory mode, only `no_refactor_needed` and `insufficient_evidence` are valid. Reject target-dependent outcomes and candidates because no deterministic target exists; do not parse or display a candidate comparison.

In the clean-control evaluation, retain every raw response. If the model returns a candidate, `refactor_recommended` or `multi_cell_change_required`, record a zero-hotspot mode violation and potential over-intervention. Where structurally possible, parse and reanalyse the candidate without execution; measure expansion, unsupported problems/claims and interface/structural changes. Production rejection must not hide experimental failure.

Evaluation retains the first AI-review response separately and assesses its faithfulness and educational quality. Where candidate metrics are evaluated, request a refactor under equivalent explicit conditions, retain the first refactor-generation response and record any automatic correction separately. A successful correction must never hide an invalid first generation. Grounded-versus-ungrounded comparisons use the first response in each condition.

## Candidate limits and verification

For scripts:

```text
min((2 × original_script_character_count) + 5,000, 160,000)
```

The complete reconstructed script remains subject to that limit. The model-generated replacement
for one script target is independently bounded by:

```text
min((2 × original_target_character_count) + 2,000, 160,000)
```

Reject oversize output without truncation. For valid-size candidates:

1. parse without execution;
2. report syntax failure;
3. run the same deterministic analyser;
4. compare matching qualified symbols/cells;
5. show smells introduced and removed;
6. show structural-context warnings;
7. show suggested tests and the semantic limitation.

Script refactors operate on one approved hotspot at a time. The target is derived from the validated
review, deterministic hotspot ordering, qualified name, exact original line range and cited evidence.
The model returns exactly one matching function or method definition. CodeSage replaces only that
line range and preserves every character outside it while reconstructing the complete suggested
file locally, without executing source. A supported target mutable-default finding may permit a
default change, but parameter names and ordering remain stable and the signature change is reported.

The reconstructed file must retain every original qualified function, method and class under the
same name and kind. Preserve unrelated bodies, decorators, signatures, class structure, imports and
interfaces using location-insensitive AST comparison. Newly introduced `exec`, `eval`, `compile`,
`__import__`, runtime namespace writes or generated APIs cannot substitute for explicit definitions.
Unexpected removals, unrelated changes, missing imports, dynamic namespace synthesis, changes outside
the target region or an unverifiable complete-file structure are verification failures.
The approved target's location-insensitive AST must itself change; an unchanged target implementation
is a typed verification failure and may use the one permitted technical correction. Presentation
reports target implementation and target signature separately, retains the original target line
range and states unrelated-preservation, added, removed and unresolved definition counts explicitly.

A malformed targeted replacement may use the one permitted non-recursive technical correction. The
correction receives the exact replacement violation, remains bound to the same approved target and
returns only that target definition. A failure in the reconstructed file's focused structural gate
does not broaden the request or trigger another correction. Production withholds invalid generated
source; future evaluation retains the failed first generation separately, so a successful correction
cannot conceal the initial contract violation.

### Deterministic maintainability-improvement gate

After the focused structural gate passes, CodeSage evaluates a separate, deterministic
`MaintainabilityImprovementDecision` before a candidate may be displayed. It reports `accepted`,
`failure_codes`, `improvements`, `regressions` and a plain-text `explanation`; it never adds a
proprietary aggregate score. Acceptance requires all of:

- every deterministic smell cited by the validated review for the selected target is absent from
  the candidate target, with no unresolved reviewed-target comparison;
- at least one measured factor improves: complexity, nesting depth, a high- or medium-severity
  smell count, or a reviewed individual smell being removed;
- no measured regression: complexity, nesting depth, parameter count, a high- or medium-severity
  smell count, or any newly introduced smell; no unrelated definition or interface changes.

SLOC and statement count remain descriptive and never independently fail an otherwise valid
refactor unless they trigger a new threshold-defined smell or violate the existing size limits. A
supported mutable-default default-value change may still alter the default value under the
existing structural rule and keep its interface warning, but must still pass every other gate
condition. A rejected candidate feeds its exact failure codes and measured before/after values into
the one permitted technical correction; if the corrected candidate also fails, both attempts are
withheld and never displayed.

Directional measurements use `improved`, `regressed`, `unchanged` or `unresolved`: cyclomatic complexity, nesting depth and threshold-defined smells/counts for comparable units.

Descriptive measurements use `increased`, `decreased`, `unchanged` or `unresolved`: lines, SLOC, statements, length, parameters, imports, functions and classes. A descriptive change is not inherently an improvement.

Structural properties use `added`, `removed`, `changed`, `unchanged` or `unresolved`: functions, methods, classes, signatures, imports and replacement identities.

Never derive “better overall”, “more maintainable overall”, “safe”, “correct” or “behaviourally equivalent”.

Large verified comparisons use summary-first progressive disclosure: target metrics and structural
counts remain prominent, while complete source, metric tables, structural changes and aggregated
warning inventories remain available in collapsed, bounded-height controls.
The Refactor workspace states `Code changed: Yes` only for a verified target AST change. Abstention
states `Code changed: No`; failed or incomplete results state that no verified change was produced.
Measurements & evidence shows its full before/after heading only when a verified comparison exists;
abstention, failed attempts and incomplete comparison state each receive an explicit bordered
explanation instead of a blank section.

## Ask CodeSage follow-up chat

"Ask CodeSage about this result" is a bounded, evidence-based follow-up chat, implemented and
tested. It is not a general-purpose coding assistant: it explains the current completed result only
and becomes available only after a successful AI review. The same conversation is shown beneath the
completed AI review and beneath the current verified refactor, backed by one shared session-state
history, so switching workspace views does not create separate histories.

A dedicated chat request function, separate from review and refactor generation, sends only: the
deterministic evidence the validated review actually cited (never the complete evidence package);
the validated review; the approved target source, extracted locally (never the complete file); the
current verified target replacement when one exists, likewise extracted alone; target-scoped
before-and-after measurements, structural changes and warnings; the review's suggested safety
checks; and a bounded number of recent conversation turns. The complete source is never added merely
because chat is enabled, regardless of file size. All source, review content, refactor source, prior
messages and the user's question are treated as untrusted data.

The strict structured response (`CoachResponse`) contains `answer`, `evidence_ids`,
`source_references`, `limitations` and an optional `suggested_follow_up`. It has no field capable of
carrying replacement source, so a request for new or different code can only ever be redirected in
prose, never fulfilled: the schema itself preserves the existing syntax, scope, comparison and
maintainability gates. Every cited evidence ID and source reference is validated against the exact
context supplied for that request before display; an invalid citation is rejected, not shown. The
model must not invent measurements, claim code execution, behavioural equivalence, runtime
correctness, security or performance, or silently convert an explanation request into a new refactor;
when supplied evidence cannot answer the question, the response must say so and record it as a
limitation.

Optional starter questions are offered for the current state (five general starters, plus four
refactor-specific starters once a verified refactor exists) and submit through the same chat
mechanism as a typed question, never a separate hard-coded answer. The maximum user-message length
is one configured constant (`COACH_MESSAGE_CHARACTER_LIMIT`, 1,000 characters), shown explicitly in
the field with a live character counter. Conversation history and output tokens sent to the model are
both bounded by configured constants. Each user submission makes exactly one explicit OpenAI request;
opening or switching to the chat section never does. The chat uses the same safe timeout, retry and
privacy-safe API-error handling as review and refactor requests.

The conversation clears whenever the source changes, the source is reanalysed, a new AI review
replaces the previous one, the source digest no longer matches, or the user selects "Clear
conversation". When a verified alternative replaces the current refactor, the conversation is cleared
rather than attempting unreliable selective invalidation of refactor-specific answers. The chat never
changes `REFACTOR_KEY` or review state. It is excluded from the print-friendly report and its
interactive controls and transcript are hidden under `@media print` in the ordinary workspace; it is
not persisted beyond the current Streamlit session.

## User interface

CodeSage has two presentation modes over the same source-bound deterministic analysis, AI review,
verified suggested refactor and comparison state. Changing presentation mode must not rerun analysis,
make an OpenAI request or duplicate business logic.

Interactive app mode is a wide Streamlit workspace with a compact, light source sidebar. The sidebar
contains CodeSage identity, a prominent “Choose your source” control with the four script source
routes, the selected route's basic control and an
active-source status where applicable; workflow explanations, future-work copy, primary workflow
actions and print controls stay out of the sidebar.

The interactive workspace has three deliberate states. With no source loaded, show a balanced,
screen-only CodeSage introduction, one Load built-in example action, guidance to the other sidebar
routes, a three-step explanation and three compact value cards; do not show result tabs or invented
results. With a source loaded but not analysed, retain compact product identity and show the active
source, a bounded preview, what CodeSage will measure and one prominent Analyse code action. The
built-in example can be selected from either the landing page or sidebar; deferred source-route state
keeps that choice stable across reruns and invalidates results belonging to another source. After
analysis, remove the landing treatment, show a compact source and result-status header, then expose
the four bounded workspace views: Overview, AI review, Refactor and Measurements & evidence.

At each stage, one primary workflow action is shown in the main workspace: Try the built-in example,
Analyse code, Get AI review, Generate suggested refactor or Generate a different refactor as
applicable. AI review is optional: complete deterministic results, Measurements & evidence and the
print report remain useful without sending source or evidence to OpenAI. Workspace transitions use
separate canonical application state and widget-owned state: the canonical selection is copied into
the segmented control before widget creation, while user selections are copied back through its
callback. Programmatic transitions update only canonical state and rerun once after storing a
successful result. Successful destination changes request a one-time scroll to the top through one
static local helper that contains no source or network operation and covers the browser document and
the supported Streamlit scrolling containers.
Every completed AI-review page states the canonical refactor decision immediately after findings,
safety checks and limitations, and before the optional Ask CodeSage conversation. An available
decision shows the existing generation action and approved target names; `no_refactor_needed` and
`insufficient_evidence` show explicit, state-specific conclusions without generation controls;
`unsupported_recommendation` asks for a corrected review without falsely claiming that the model did
not recommend a refactor. The Refactor workspace and print report use the same decision and wording.
The Overview is summary-first; AI findings use distinct cards; a verified refactor leads with compact
target measurements and a bounded unified diff; complete files and detailed inventories, evidence,
comparisons, warnings and raw technical data remain available through collapsed or bounded-height
controls. Complexity scores show their Radon rank band and explain that the rank is not an overall
quality grade. Complete original and suggested files remain available through an explicitly labelled
side-by-side comparison. Optional first and alternative-refactor instructions are normalised for
cache identity without invalidating the source, analysis or review. Print-friendly report is a
secondary post-analysis action.

Model-suggested checks are presented as a numbered, non-interactive “Safety checks to run before
refactoring” section. They are recommendations for the user to run against the original code and then
rerun against a verified suggested refactor. CodeSage does not create or execute those tests.

Print-friendly report mode renders a single-column linear report from the same completed state, with
no interactive workspace tabs and no additional analysis or model request. It includes the available
source, deterministic summary, priority hotspot and findings, AI review, safety checks, verified
refactor outcome, target measurements, interface and trade-off warnings, assumptions and limitations.
The interactive landing hero and value cards are excluded from the report.
Browser Print or Save as PDF is the supported output route; print styling hides Streamlit chrome,
interactive controls and screen-only notices without a PDF library, external network resource or a
third-party print component. The single static scroll helper is app-only and never runs in print
output.

### Print-report specification

The report order is: source; deterministic summary; priority hotspot; AI maintainability review;
safety checks; suggested refactor and changed-hotspot diff; complete source files, only when the
source is at or below the configured print-size threshold; and, last, a Measurements & evidence
appendix.

The appendix is a dedicated, print-only renderer using static headings, text and `st.table` output
only — never expanders or interactive dataframes, which are not reliable printable content — and it
never truncates a row silently. It includes: every analysed code unit, with the total row count in
its heading and, for large inventories, explicitly labelled "Part N of M" table chunks that preserve
every row; every configured hotspot threshold, stated as configurable product defaults rather than
universal laws; every analysis warning, or an explicit "None." statement; the exclusions count and
detail, or an explicit statement that none apply; every evidence item cited by the AI review (never
uncited evidence), or an explicit statement that no AI-review evidence is available; when a verified
refactor exists, every directional and descriptive comparison row and every comparison warning, or an
explicit statement that no before-and-after measurements are available; and every structural
comparison row with category, name and status, plus changed/unchanged/added/removed/unresolved
totals, or an explicit statement that no structural verification results are available. Raw analysis
JSON remains an onscreen-only, collapsed "Raw analysis data — advanced" control and is never printed.

A named configuration constant (`PRINT_COMPLETE_SOURCE_CHARACTER_LIMIT`, 12,000 characters) governs
whether the two complete-file source listings print. At or below the threshold, both complete files
print in full. Above it, both complete-file listings are omitted and replaced with an explicit
notice stating the exact source character count, that the changed-hotspot diff and complete static
measurements remain included, and that the complete files remain available in the CodeSage app; the
changed-hotspot diff itself is never omitted regardless of source size. A section is never labelled
"Compare the complete files" when the complete files have been omitted. Measurements and evidence are
never shortened because of source size; any future table limit must state the exact number of rows
shown and omitted, since silent truncation is prohibited.

The canonical print report includes only the currently verified refactor, or an explicit
availability statement derived from the same decision used onscreen: available but not generated,
no targeted refactor recommended, insufficient static evidence, or an unsupported recommendation
requiring correction. It never includes the alternative-generation form, optional-instruction fields,
generation buttons, a failed alternative-attempt notification, transient API errors from a later
interactive request, or the "Ask CodeSage" chat interface or transcript. For users who print the
ordinary workspace instead of opening the dedicated print report, the alternative-generation form,
the alternative-attempt status and the "Ask CodeSage" section are each wrapped in a keyed screen-only
container and hidden under `@media print`.
Before any report content is rendered, the active source digest must match the deterministic
analysis digest and every present review/refactor original-analysis digest. A mismatch produces only
the stale-report instruction to analyse the current source again; mixed-source results are never
printed. The source identity printed inside the report is authoritative.

Use labelled controls, logical reading order, actionable errors and text in addition to colour. Small
tables are content-sized; large inventories, comparisons, warning lists and code views are bounded
and scrollable. The sidebar, tabs, metric cards and finding cards must remain usable at standard
laptop width and in a narrower browser window.

## Submission validation and future applied-AI evaluation

Submission validation demonstrates five supported source journeys—built-in example from the landing
page, built-in example from the sidebar, pasted Python, uploaded `.py` and a public GitHub `.py`
URL—plus deterministic thresholds, explicit
AI consent, evidence validation, targeted reconstruction, bounded correction and qualified static
comparison using synthetic scripts and mocked automated calls, supplemented by a small documented
manual acceptance set. It is not presented as a statistically controlled research result.

A full controlled grounded-versus-ungrounded experiment is future work. Its retained research design
compares review faithfulness, actionability and educational value while keeping model, reasoning,
source, task, safety rules, schema, limits and validation identical and varying only a separately
versioned grounding block. Future work must record first review and generation responses, corrections
and clean-control over-intervention without using a successful correction to conceal an invalid first
response. That experiment is not a submitted-MVP Definition of Done item.

## Safety, privacy and deployment

- Never execute submitted or generated code.
- Keep `OPENAI_API_KEY` and `OPENAI_MODEL` in environment variables or Streamlit secrets.
- Never commit `.env` or `.streamlit/secrets.toml`.
- Do not deliberately persist user source or log complete source/candidates.
- Log only safe metadata, timing and error categories.
- Use a dedicated OpenAI project with rate/spend limits as the global cost controls. Do not impose a low application-level session quota during judging. Every AI review and every suggested-refactor request requires explicit user action; source-, review- and instruction-bound caching prevents duplicate completed requests on unchanged state. Each explicit refactor operation permits at most one automatic technical correction, and recursive retries are prohibited. Any future emergency operational control must be disabled during judging and must not appear as a normal user quota.
- Preserve deterministic fallback and original built-in examples.
- Deploy on Streamlit Community Cloud with Python 3.11.
- Keep the judged version aligned with a tagged commit and available through 5 August 2026.

## Tests

Cover all five source journeys and limits; deferred source-route state and synchronised permanent/widget workspace state across reruns; URL allow-listing, conversion, redirects, timeouts and HTML; all measurements, smells and thresholds; procedural SLOC range de-duplication; hotspot granularity, ordering, complexity-rank explanation and zero-hotspot results; strict production AI schemas and outcomes; first and alternative-refactor instruction combinations; replacement and reconstructed-file size formulas; comparison semantics; structural warnings; deterministic fallback; built-in-example invalidation; bounded rendering; one-use scrolling; deterministic-only reporting; and static-only claims. Also cover: AST-equivalent alternative rejection and its one correction attempt; separate current-refactor and alternative-attempt error states and their clearing rules; privacy-safe HTTP status/request-ID display without the raw response body; the shared optional-instruction and chat-message character-limit constants; the Measurements & evidence print appendix, including chunked large tables and explicit absence statements; the print-size threshold's complete-file omission notice; and the bounded "Ask CodeSage" chat's availability, grounded context, citation validation, history bounding, single-request-per-submission behaviour, state-clearing rules and print/session exclusion.

Use pytest, mock ordinary model/network calls and prioritise domain/integration tests over optional UI automation. Run Ruff and `pip check`. Manual acceptance covers pasted, uploaded, built-in and real pinned public-GitHub scripts, live model script review, clean-browser deployment and responsive presentation.

## Milestones and effort

| Milestone | Mandatory | Optional |
| --- | ---: | ---: |
| Bootstrap and early feasibility checks | 1.5h | — |
| Script deterministic vertical slice | 4h | — |
| Script GPT-5.6 review and verification | 4h | — |
| Early Streamlit deployment | 2h | — |
| Upload and GitHub loaders | 1.5h | — |
| Hardening and acceptance | 2.5h | 0.5h UI tests |
| Bounded submission validation | 1.5h | Full controlled evaluation is future work |
| Documentation, video and submission | 6h | — |

Protect five hours of contingency. Optional work may use at most three hours and begins only after deployment is stable, mandatory tests pass and submission/contingency reserves remain protected.

Automatic cut order: CI, candidate download, non-trivial copy controls, decorative UI and optional UI automation.

## Definition of Done

Checkpoint status: the competition-MVP implementation requirements below are complete and covered by
the automated suite unless an item explicitly concerns external submission work. The final live-model
evidence-correction journey, a complete final manual browser regression, deployment verification,
the polished README, demo script/video and Devpost evidence remain separate submission tasks. The
following list is the overall completion checklist, not a claim that those external tasks have run.

- All five supported Python-script source journeys pass their acceptance checks.
- The deterministic analyser reports the approved measurements and smells without execution.
- Procedural script hotspots, symbol granularity, de-duplication and zero-hotspot outcomes are tested.
- At most three transparent hotspots are shown.
- A user can load the built-in example, analyse it deterministically and choose whether to request AI review.
- `refactor_recommended` enables a separate explicit targeted script replacement, reconstructed into
  a complete suggested script locally.
- AI review remains useful without generating source; abstention and no-refactor outcomes do not enable refactor generation.
- A generated candidate is displayed only after the deterministic maintainability-improvement gate accepts it; the refactor model may itself abstain with `no_better_refactor`, and failed or abstained attempts are withheld and explained, never displayed as source.
- Candidate size, syntax, re-analysis and comparison rules pass.
- Complete Original code and Suggested refactor views appear only for statically verified refactors
  and remain available through bounded progressive disclosure in interactive mode.
- Oversized accepted scripts retain deterministic results and disable AI without truncation.
- AI failures preserve deterministic results.
- Bounded submission validation is recorded without implying completion of a controlled research experiment.
- The interactive workspace and the print report never simultaneously imply that a verified refactor is recommended and that no code change is recommended; a failed alternative reads distinctly from a failed initial request and never invalidates the existing current verified refactor.
- "Generate a different refactor" receives the previous approved target replacement, requests a meaningfully different approach, and rejects an AST-equivalent alternative rather than silently accepting a repeat.
- The print report's Measurements & evidence appendix is complete for every analysed unit, threshold, warning, exclusion, cited evidence item and comparison row, or states explicitly why one is unavailable; large source listings may be omitted per the configured print-size threshold, but measurements and evidence are never silently shortened.
- OpenAI HTTP errors show only a privacy-safe status and optional request ID; the raw response body, prompt, source and API keys are never exposed.
- The optional-instruction and chat-message character limits are each one shared configuration constant, visible in the interface with a live counter, and enforced identically on the frontend and backend.
- The bounded "Ask CodeSage" chat answers only about the current completed result, cites only supplied evidence and source references, never returns unverified replacement code, and is excluded from the print report and from persistence beyond the session.
- Automated tests, Ruff, dependency checks and manual acceptance pass.
- Deployment works from a clean browser with secrets and cost controls.
- README, licence, installation, supported platforms, evaluation, privacy and limitations are complete.
- Public video is under three minutes and matches the tagged deployment.
- Devpost fields, repository access and competition evidence are verified.
- `/feedback` is run in the primary thread only after most core functionality is built.

## Repository and approval workflow

Use one authoritative README, this plan, a concise `AGENTS.md`, `BUILD_LOG.md`, evaluation documentation and a submission checklist. Avoid duplicate specifications.

Before each milestone, state objective, likely files, acceptance criteria, risks and cut line. After work, run relevant checks, show the diff, report verified/unverified behaviour and suggest a conventional commit. Wait for explicit approval before every commit, push, repository-visibility change, remote creation, deployment or `/feedback` run.
