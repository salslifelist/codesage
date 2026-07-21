# CodeSage build log

This log records material decisions, verified bootstrap events and milestone outcomes. It does not duplicate the product specification in `PLAN.md`.

## 18 July 2026 — Context and scope

- Established this Codex conversation as the primary OpenAI Build Week development thread.
- Audited the original proposal and reduced the competition MVP to maintainability analysis, evidence-grounded GPT-5.6 guidance and deterministic candidate re-analysis.
- Excluded Big-O, Maintainability Index, training, repository-wide analysis, notebook execution/reconstruction, dependency graphs and unsupported correctness/security/sustainability claims.
- Approved focused notebook target selection, zero-hotspot behaviour, clean-control over-intervention evaluation and procedural module/cell hotspot rules.
- Approved the final implementation plan with a five-hour contingency and protected submission reserve.

## 18 July 2026 — Workspace and GitHub bootstrap

- Archived the five superseded planning/context source files intact to a sibling local directory outside the repository before Git initialisation.
- Downloaded GitHub CLI 2.96.0 from the official immutable GitHub release.
- Verified its SHA-256 against the official checksum and verified the valid GitHub, Inc. Authenticode signature.
- Installed GitHub CLI 2.96.0 and authenticated the intended GitHub account using HTTPS Git protocol.
- Created the protective `.gitignore` before secrets or environments.
- Initialised an empty local Git repository on branch `main`.
- Verified that no Git remote exists and no commit has been created.

## 18 July 2026 — Python and dependency bootstrap

- Selected the existing CPython 3.11.9 installation for local development and Python 3.11 for deployment.
- Created `.venv` with the standard-library `venv` module and pip 24.0.
- Installed Radon 6.0.1 for the approved compatibility spike.
- Verified programmatic cyclomatic-complexity analysis using a synthetic function: complexity `2`, rank `A`.
- Confirmed `pip check` reported no broken Radon requirements.
- Pinned the approved runtime and development dependencies in `requirements.txt` and `requirements-dev.txt`.
- Installed the resolved dependency set into `.venv`.
- Verified exact direct-package versions, nbformat validation, OpenAI SDK `responses.parse`, a bounded HTTPX mock client, pytest 9.1.1, Ruff 0.15.22 and `pip check`.
- No OpenAI API call was made.

## Current state

- The private GitHub repository exists, and local `main` tracks `origin/main` at the
  verified bootstrap commit.
- The deterministic script-analysis milestone is implemented as uncommitted changes.
- No files are staged.
- No deployment or live-model evaluation has begun.
- `/feedback` has not been run.

## 19 July 2026 — Deterministic script-analysis vertical slice

- Added a genuine `src/codesage` package with setuptools package discovery and an
  editable installation in the approved Python 3.11 environment.
- Implemented non-executing AST analysis for syntax status, SLOC, qualified functions
  and methods, statement counts, effective parameters, nesting, Boolean leaves,
  mutable defaults, exception handling and Radon cyclomatic complexity.
- Implemented procedural module SLOC and direct-statement measurement with imports,
  the recognised docstring and complete nested definitions excluded.
- Implemented the approved smell thresholds, explicit severities, deterministic
  hotspot ordering, three-hotspot limit and zero-hotspot outcome.
- Verified 29 focused tests, Ruff checks and formatting, dependency consistency and
  package import resolution from `src/codesage`.

## 19 July 2026 — Script AI review and candidate verification

- Added a stable deterministic evidence package with versioned prompts, unique evidence
  IDs, source references, thresholds, measurements, smells and hotspot-selection facts.
- Added a strict, injectable Responses API boundary with bounded output and timeout,
  disabled retries, no tools, no storage and mocked automated tests only.
- Added script outcome, evidence-reference and zero-hotspot validation, preserving the
  original deterministic analysis for every handled AI failure.
- Bound reviews to the exact SHA-256 source digest, rejected syntax-invalid originals
  before client creation and used a deterministic collision-safe JSON data envelope.
- Bound each cited evidence ID to its source reference and completed terminal-status,
  script-field and privacy-safe failure validation without exposing raw API or structured-output
  exception details.
- Kept one response schema reusable for grounded and ungrounded evaluation while requiring
  complete deterministic grounding references in production review.
- Added exact candidate-size enforcement, syntax checking, same-pipeline reanalysis and
  separate directional, descriptive and structural comparisons without execution or an
  overall verdict.
- Extended deterministic inventory with signatures and imports for exact function,
  method, class, signature and import change reporting, including structural
  fingerprints, canonical individual import bindings and severity-specific smell comparisons.
- Verified 83 tests, Ruff checks and formatting, dependency consistency and package
  import resolution. No live OpenAI API call was made.

## 19 July 2026 — Script Streamlit interface and mocked integration

- Added a root Streamlit entry point for bounded single-script deterministic analysis and a
  separately triggered grounded AI review using the existing review boundary.
- Enforced SHA-256-bound session state, stale-result invalidation and at-most-once review behavior
  for each analysed source in a session.
- Added one canonical source-document model for pasted source, UTF-8 Python uploads and bounded
  public GitHub file URLs, with origin-aware stale-state invalidation and no source persistence.
- Separated the 200,000-character/byte acquisition limits from the complete-file AI-review limit
  so larger accepted files retain deterministic analysis without truncation.
- Added safe rendering for deterministic hotspots, grounded findings, candidates, static
  verification, comparisons, warnings and typed privacy-safe failures without source execution.
- Added a lean script-only production structured-output schema and normalised successful parses
  into the shared notebook/evaluation-compatible response model before downstream validation.
- Clarified the candidate-source contract, added local syntax validation and bounded invalid
  candidates to one schema-constrained repair attempt with safe partial-review fallback.
- Made ordinary AI review and candidate comparison explicitly complete-file scoped and extended
  deterministic evidence with referenceable class inventory.
- Added the local project requirement to the runtime requirements and verified a clean Python
  3.11 installation imported CodeSage from isolated `site-packages` with consistent dependencies.
- Verified 133 tests, Ruff checks and formatting, dependency consistency, package import
  resolution, secret-file ignores and removal of temporary verification artefacts.
- No additional live OpenAI API request occurred during the schema correction, and no deployment
  occurred.

## 19 July 2026 — Specification alignment and script-contract hardening

- Centralised script acquisition, decoded-content, AI-review, candidate, request and session limits.
- Verified 200,000-character pasted acquisition, 200,000-byte upload/GitHub acquisition and an
  independent decoded-content guard without truncation.
- Raised complete-file script AI eligibility to 100,000 characters and retained deterministic-only
  behaviour above that limit through the acquisition ceiling.
- Applied the 160,000-character absolute script-candidate ceiling, retained one bounded
  candidate-only repair and preserved the primary grounded response separately from any repaired
  candidate.
- Added session-wide limits of two primary reviews and one repair request, exact zero-hotspot copy,
  deterministic detail, OpenAI disclosure and verified-only Original/Candidate presentation.
- Verified 153 tests, Ruff checks and formatting, dependency consistency and whitespace checks.
  All OpenAI and HTTP interactions remained mocked; no live OpenAI or external HTTP request was
  made and no deployment occurred.

## 20 July 2026 — Bounded deterministic-results presentation

- Replaced sequential per-unit rendering with a summary-first view, concise priority hotspots and
  one collapsed, bounded-height analysable-unit inventory.
- Kept thresholds, warnings, exclusions and technical data accessible in proportionate collapsed
  sections without changing deterministic analysis or hotspot selection.
- Verified 159 tests, Ruff checks and formatting, dependency consistency and whitespace checks.
  No live OpenAI or external HTTP request was made.

## 20 July 2026 — Separate AI review and suggested-refactor workflow

- Separated the evidence-based AI explanation schema and request from explicit complete-file
  refactor generation, while retaining strict evidence and source-digest validation.
- Added source-, review- and instruction-bound caching, explicit alternative-refactor requests and
  at most one non-recursive technical correction for an unverifiable generated file.
- Removed low application-level session quotas and replaced technical candidate terminology in the
  normal interface with accessible review and suggested-refactor language.
- Superseded the session limits recorded in the 19 July historical milestone; production no longer
  blocks reviews, refactors or corrections based on session-wide call counts.
- Preserved a valid review and any previously verified refactor when a later generation fails.
- Verified 100 tests, Ruff checks and formatting, dependency consistency and whitespace checks.
  All OpenAI and HTTP interactions remained mocked; no live OpenAI or external HTTP request was
  made.

## 20 July 2026 — Test-coverage regression audit

- Accounted for obsolete bundled-review and quota tests and restored meaningful coverage for
  acquisition failures, AI boundary failures, refactor limits, correction bounds, privacy and
  bounded interface rendering without changing production behaviour.
- Verified 134 tests, Ruff checks and formatting, dependency consistency and whitespace checks.
  All OpenAI and HTTP interactions remained mocked; no live OpenAI or external HTTP request was
  made.

## 20 July 2026 — Focused-refactor verification and bounded results

- Added validated-target derivation and location-insensitive AST preservation checks for original
  definitions, unrelated bodies and signatures, imports and target parameter shape.
- Rejected newly introduced runtime code generation and namespace synthesis, and made focused-scope
  failures eligible for the existing single non-recursive technical correction.
- Prevented missing units from being reported as smell removals and replaced unbounded refactor
  output with target-first summaries, collapsed code and bounded comparison and warning tables.
- Verified 156 tests, Ruff checks and formatting, dependency consistency and whitespace checks.
  All OpenAI and HTTP interactions remained mocked; no live OpenAI or external HTTP request was
  made.

### Live 49,800-character focused-refactor acceptance

- Manually accepted `codesage_50k_hotspot.py`: 1,395 physical lines, 1,008 SLOC, 63 functions,
  184 methods, 62 classes and 248 analysable units. The reviewed `choose_priority_item` target had
  nesting depth 5, complexity 6, and mutable-default and deep-nesting smells.
- The first generated refactor passed focused verification without correction. It preserved every
  unrelated explicit definition and introduced no dynamic generation or namespace synthesis;
  structural counts were 0 added, 0 removed, 2 changed, 557 unchanged and 0 unresolved.
- Target nesting improved from 5 to 3 and both detected smells were removed. Complexity increased
  from 6 to 7, SLOC from 11 to 12 and statements from 10 to 11; parameter count remained 2. The
  evidence-supported mutable list default changed to `None`.
- Static verification did not establish behavioural equivalence. With all code and comparison
  sections expanded, the bounded result occupied eight pages rather than the previous 55-page flow.

### Post-acceptance result-state and labels

- Replaced the completed generation action in place with `Try a different refactor` after verified
  state changes, without a rerun or additional model request.
- Added readable outcome, target, smell, correction and structural labels and moved canonical
  evidence references into collapsed evidence details.
- Verified 162 tests, Ruff checks and formatting, dependency consistency and whitespace checks.
  All OpenAI and HTTP interactions remained mocked; no live OpenAI or external HTTP request was
  made.

### Optional-instructions partial-resolution acceptance

- Reused the unchanged AI review in the same session and followed the requested no-`continue`,
  no-helper preference without rerunning the review.
- The verified alternative resolved the mutable-default issue but left deep nesting at 4, exactly
  the configured deep-nesting threshold, exposing the need for a prominent partial-resolution
  summary distinct from technical verification.
- Added deterministic reviewed-issue outcome classification and prominent measured trade-offs;
  verified 168 tests, Ruff checks and formatting, dependency consistency and whitespace checks.
  All OpenAI and HTTP interactions remained mocked; no live OpenAI or external HTTP request was
  made.

### Targeted script-refactor reconstruction

- Replaced complete-file model generation with a strict target-reference and single-definition
  response for one deterministically approved function or method hotspot.
- Reconstructed the complete suggested script locally by preserving the exact original prefix and
  suffix around the approved line range, then applied the existing syntax, deterministic analysis,
  focused-structure and comparison gates to the reconstructed file.
- Kept the single non-recursive technical correction bound to the same target and limited it to
  malformed targeted replacements; a model-produced full module, wrong definition, multiple
  definitions, Markdown, prose, ellipses or invalid syntax is not accepted as a refactor.
- Verified preservation with a synthetic script containing 205 unrelated functions and verified
  182 tests, Ruff checks and formatting, dependency consistency and whitespace checks. All OpenAI
  and HTTP interactions remained mocked; no live OpenAI or external HTTP request was made.

### Submission scope freeze and focused interface

- Froze the submitted product scope to complete Python scripts supplied by paste, local `.py`
  upload, one public-GitHub `.py` URL or the original built-in example; notebook, additional-language,
  repository-wide, runtime-verification and full controlled-evaluation work is explicitly future.
- Added a canonical, no-setup example route with the same source identity and stale-result
  invalidation behaviour as other scripts, without automatic AI review.
- Replaced normal-flow source JSON with a concise summary, added a three-stage workflow indicator,
  and reorganised AI review output into a scan-first outcome, bordered finding sections, visible
  measured evidence and recommendations, a suggested-test checklist and collapsed limitations.
- Clarified refactor outcomes as reviewed static findings and retained the visible complexity and
  non-equivalence qualifications.
- Applied a restrained native Streamlit light theme without custom CSS or additional dependencies.
- Verified 189 tests, Ruff checks and formatting, dependency consistency, Streamlit theme loading
  and whitespace checks. All OpenAI and HTTP interactions remained mocked; no live OpenAI or
  external HTTP request was made.

### Screen-first and print-friendly interface

- Added a wide, sidebar-led interactive workspace with Overview, AI review, Suggested refactor and
  Technical details tabs, all using the existing source-bound state without changing production
  analysis or AI behaviour.
- Added a same-state linear print-friendly report with screen-only print/return controls and local
  print CSS that hides app chrome and controls, without a PDF library, external JavaScript, an
  external print component or a network dependency.
- Reframed model-suggested checks as a numbered, non-interactive `Safety checks to run before
  refactoring` section, explained that CodeSage neither creates nor executes those tests, and added
  the equivalent post-refactor reminder.
- Replaced long default result flows with compact measurements and finding cards, a bounded unified
  hotspot diff, collapsed complete-file views and size-aware technical tables while retaining the
  full verified result data.
- Verified 198 tests, Ruff checks and formatting, dependency consistency, Streamlit theme loading,
  a no-exception local app/print/return runtime smoke and whitespace checks. All OpenAI and HTTP
  interactions remained mocked; no live OpenAI or external HTTP request was made.

### Landing-page and state-transition clarification

- Added distinct no-source, ready-to-analyse and completed-analysis screens. Result tabs are absent
  until deterministic analysis completes; the landing screen contains one built-in-example action,
  a two-column product introduction and three static value cards without invented result data.
- Moved all workflow and print actions out of the sidebar. The light source panel now contains only
  source selection, its basic acquisition control and compact active-source status; each workflow
  stage presents one primary action in the main workspace.
- Added a bounded source preview and Ready to analyse card, a compact post-analysis status header and
  durable source-route restoration so entering and leaving print mode preserves completed state.
- Verified 205 tests, Ruff checks and formatting, dependency consistency, a no-exception local
  landing/example/analysis/print/return Streamlit state-transition smoke and whitespace checks. All
  OpenAI and HTTP interactions remained mocked; no live OpenAI or external HTTP request was made.
