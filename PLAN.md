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
- the full controlled grounded-versus-ungrounded research experiment beyond the bounded submission validation set.

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

Each explicit refactor-generation request may make at most one automatic technical-correction request, and only when a successfully parsed targeted replacement is malformed, names the wrong target, contains invalid syntax or unsupported content, or cannot be inserted safely. The correction remains bound to the same target, requests only a replacement region and never requests the complete file. Correction never recurses or changes the validated review. A user may explicitly request a different targeted refactor, with optional instructions, without rerunning that review.

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

A malformed targeted replacement may use the one permitted non-recursive technical correction. The
correction receives the exact replacement violation, remains bound to the same approved target and
returns only that target definition. A failure in the reconstructed file's focused structural gate
does not broaden the request or trigger another correction. Production withholds invalid generated
source; future evaluation retains the failed first generation separately, so a successful correction
cannot conceal the initial contract violation.

Directional measurements use `improved`, `regressed`, `unchanged` or `unresolved`: cyclomatic complexity, nesting depth and threshold-defined smells/counts for comparable units.

Descriptive measurements use `increased`, `decreased`, `unchanged` or `unresolved`: lines, SLOC, statements, length, parameters, imports, functions and classes. A descriptive change is not inherently an improvement.

Structural properties use `added`, `removed`, `changed`, `unchanged` or `unresolved`: functions, methods, classes, signatures, imports and replacement identities.

Never derive “better overall”, “more maintainable overall”, “safe”, “correct” or “behaviourally equivalent”.

Large verified comparisons use summary-first progressive disclosure: target metrics and structural
counts remain prominent, while complete source, metric tables, structural changes and aggregated
warning inventories remain available in collapsed, bounded-height controls.

## User interface

CodeSage has two presentation modes over the same source-bound deterministic analysis, AI review,
verified suggested refactor and comparison state. Changing presentation mode must not rerun analysis,
make an OpenAI request or duplicate business logic.

Interactive app mode is a wide Streamlit workspace with a compact, light source sidebar. The sidebar
contains CodeSage identity, the four script source routes, the selected route's basic control and an
active-source status where applicable; workflow explanations, future-work copy, primary workflow
actions and print controls stay out of the sidebar.

The interactive workspace has three deliberate states. With no source loaded, show a balanced,
screen-only CodeSage introduction, one Load built-in example action, guidance to the other sidebar
routes, a three-step explanation and three compact value cards; do not show result tabs or invented
results. With a source loaded but not analysed, retain compact product identity and show the active
source, a bounded preview, what CodeSage will measure and one prominent Analyse code action. After
analysis, remove the landing treatment, show a compact source and result-status header, then expose
the four bounded result tabs: Overview, AI review, Suggested refactor and Technical details.

At each stage, one primary workflow action is shown in the main workspace: Load built-in example,
Analyse code, Get AI review, Generate suggested refactor or Try a different refactor as applicable.
The Overview is summary-first; AI findings use distinct cards; a verified refactor leads with compact
target measurements and a bounded unified diff; complete files and detailed inventories, evidence,
comparisons, warnings and raw technical data remain available through collapsed or bounded-height
controls. Print-friendly report is a secondary post-analysis action.

Model-suggested checks are presented as a numbered, non-interactive “Safety checks to run before
refactoring” section. They are recommendations for the user to run against the original code and then
rerun against a verified suggested refactor. CodeSage does not create or execute those tests.

Print-friendly report mode renders a single-column linear report from the same completed state, with
no interactive workspace tabs and no additional analysis or model request. It includes the available
source, deterministic summary, priority hotspot and findings, AI review, safety checks, verified
refactor outcome, target measurements, interface and trade-off warnings, assumptions and limitations.
The interactive landing hero and value cards are excluded from the report.
Browser Print or Save as PDF is the supported output route; print styling hides Streamlit chrome,
interactive controls and screen-only notices without a PDF library, external JavaScript or a
third-party print component.

Use labelled controls, logical reading order, actionable errors and text in addition to colour. Small
tables are content-sized; large inventories, comparisons, warning lists and code views are bounded
and scrollable. The sidebar, tabs, metric cards and finding cards must remain usable at standard
laptop width and in a narrower browser window.

## Submission validation and future applied-AI evaluation

Submission validation demonstrates the four script source routes, deterministic thresholds, explicit
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

Cover all four script routes and limits; URL allow-listing, conversion, redirects, timeouts and HTML; all measurements, smells and thresholds; procedural SLOC range de-duplication; hotspot granularity, ordering and zero-hotspot results; strict production AI schemas and outcomes; replacement and reconstructed-file size formulas; comparison semantics; structural warnings; deterministic fallback; built-in-example invalidation; bounded rendering; and static-only claims.

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

- All four Python-script source routes pass their acceptance checks.
- The deterministic analyser reports the approved measurements and smells without execution.
- Procedural script hotspots, symbol granularity, de-duplication and zero-hotspot outcomes are tested.
- At most three transparent hotspots are shown.
- A user can load the built-in example, analyse it deterministically and choose whether to request AI review.
- `refactor_recommended` enables a separate explicit targeted script replacement, reconstructed into
  a complete suggested script locally.
- AI review remains useful without generating source; abstention and no-refactor outcomes do not enable refactor generation.
- Candidate size, syntax, re-analysis and comparison rules pass.
- Complete Original code and Suggested refactor views appear only for statically verified refactors
  and remain available through bounded progressive disclosure in interactive mode.
- Oversized accepted scripts retain deterministic results and disable AI without truncation.
- AI failures preserve deterministic results.
- Bounded submission validation is recorded without implying completion of a controlled research experiment.
- Automated tests, Ruff, dependency checks and manual acceptance pass.
- Deployment works from a clean browser with secrets and cost controls.
- README, licence, installation, supported platforms, evaluation, privacy and limitations are complete.
- Public video is under three minutes and matches the tagged deployment.
- Devpost fields, repository access and competition evidence are verified.
- `/feedback` is run in the primary thread only after most core functionality is built.

## Repository and approval workflow

Use one authoritative README, this plan, a concise `AGENTS.md`, `BUILD_LOG.md`, evaluation documentation and a submission checklist. Avoid duplicate specifications.

Before each milestone, state objective, likely files, acceptance criteria, risks and cut line. After work, run relevant checks, show the diff, report verified/unverified behaviour and suggest a conventional commit. Wait for explicit approval before every commit, push, repository-visibility change, remote creation, deployment or `/feedback` run.
