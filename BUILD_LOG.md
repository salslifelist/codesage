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

## 2026-07-21 — Workflow reliability, navigation clarity and explanatory UX

### Implemented changes

- Updated `app.py` and `src/codesage/ui.py` so the landing-page built-in example uses deferred
  source-route selection before the sidebar radio is instantiated, retains the canonical active
  source and invalidates results belonging to another source. Deferred workspace navigation remains
  widget-safe.
- Added one static, local, one-use scroll-to-top helper for successful source, analysis, workspace,
  review, refactor and return-from-print transitions. The helper contains no user-controlled data or
  network operation and is not rendered in print output.
- Made the four sidebar routes more prominent with a scoped `Choose your source` treatment; clarified
  that AI review is optional; explained Radon complexity bands without presenting them as an overall
  grade; renamed the technical workspace to `Measurements & evidence` with a legacy session alias;
  and clarified complete-file and first/alternative-refactor actions.
- Normalised surrounding whitespace in optional refactor instructions for cache identity while
  leaving source, deterministic analysis and AI-review state unchanged.
- Narrowly updated `PLAN.md`; added regression coverage in `tests/test_ui.py`. No deterministic
  analysis, AI schema or prompt, evidence validation, reconstruction, comparison, source limit or
  print-report data logic changed.

### Automated verification

- `246 passed` in the complete pytest suite.
- Ruff check passed; Ruff format check passed for all 19 Python files; `pip check` reported no broken
  requirements; `git diff --check` passed.
- Streamlit AppTest completed Landing → Try the built-in example → Ready to analyse → Analyse code →
  Results on first clicks with no exception, preserving the Built-in example route and producing
  deterministic results without an AI request.
- Strict multi-run tests exercised the built-in example from the landing page and sidebar, pasted
  Python, an in-memory uploaded `.py` and a mocked public-GitHub `.py` response. Mocked review and
  first/alternative-refactor paths covered each source origin, cached review reuse, no instructions,
  whitespace-only instructions and explicit alternative instructions. Existing suite coverage also
  retained supported review outcomes, controlled failures and retries, technical correction bounds,
  failed-alternative preservation and non-equivalence/interface warnings.

### Manual browser verification

- Actual browser viewport scrolling, 1366×768 sidebar fit, keyboard focus and the complete manual
  journey matrix were not confirmed in this milestone run. Streamlit restart was attempted, but the
  existing listener processes could not be stopped under the available execution identity; no claim
  of visual or scroll acceptance is recorded.

### Unchanged boundaries

- CodeSage remains a Python-script-only, static, non-executing tool. All OpenAI and HTTP boundaries
  were mocked; no live OpenAI or HTTP request occurred. The protected checkpoint tag was not changed.

### Incomplete checks

- Product-owner browser acceptance is still required for actual one-time viewport movement, sidebar
  density at the target resolution, all end-to-end visible outcomes and print preview. Nothing was
  staged, committed or pushed.

## 2026-07-21 — Browser-verified workspace navigation and scroll correction

### Implemented changes

- Separated canonical workspace state (`workspace_view`) from the segmented-control widget state
  (`_workspace_view_selector`). Each workspace render now canonicalises and copies application state
  into the widget before creation; its callback copies a user selection back into application state.
- Removed pending workspace navigation. Successful review and refactor actions and navigation-only
  controls now update only canonical state, request one scroll and rerun once where an action has
  completed. They never mutate the instantiated widget key.
- Expanded the static local scroll helper to reset the page anchor, browser document, Streamlit main
  area, app-view container, legacy main section and browser window. Two fixed local trigger variants
  ensure that repeated same-workspace results, including alternative refactors, execute the one-use
  scroll without including user data or making a network request.
- Added stricter state and rendering tests for permanent/widget synchronisation, first-click review
  and refactor transitions, navigation-only controls, alternative refactors, failed actions and
  one-use browser-scroll triggering. No deterministic analysis, AI schema or prompt, validation,
  reconstruction, caching, comparison or print-report behaviour changed.

### Automated verification

- `247 passed` in the complete pytest suite.
- Ruff check passed; Ruff format check passed for all 19 Python files; `pip check` reported no broken
  requirements; `git diff --check` passed.
- All OpenAI and GitHub boundaries remained mocked or unused; no live model or GitHub request was
  made.

### Browser verification

- Exercised a clean local Chrome tab at 1366×768 against the mocked Streamlit acceptance server on
  `127.0.0.1:8502`. Deterministic analysis used production code; the AI-review and refactor boundaries
  were local mocks with visible call counters.
- One Overview review action made exactly one mocked review call, selected AI review and moved the
  actual Streamlit main scroller from 864 pixels to 0. One refactor action made exactly one mocked
  refactor call, selected Refactor and moved the scroller from 1,565 pixels to 0.
- View AI review and View suggested refactor selected their destinations and returned the scroller to
  0 without changing the model-call counters. Manual selection of all four workspace segments also
  returned the Streamlit main scroller to 0.
- Alternative refactors with no instructions and with explicit instructions each made one new mocked
  refactor call, did not rerun the review, retained Refactor as the visible selection and returned the
  scroller to 0. The complete acceptance journey ended with one review call and three explicit
  refactor calls.

### Repository state

- The correction remains uncommitted and unstaged. No commit or push occurred, and the protected
  checkpoint tag was not changed.

## 2026-07-21 — Refactor-quality milestone: deterministic maintainability gate

### Implemented changes

- Strengthened refactor eligibility: a `refactor_recommended` review may enable generation only
  when at least one finding for the selected target cites an actual `smell.<code>` evidence item.
  General measurements without a threshold-triggering smell no longer enable generation. The
  derived smell codes are supplied to the refactor request as explicit static maintainability
  goals, and the target is still always the one selected by deterministic hotspot ordering.
- Extended `ScriptRefactorResponse` so the refactor model may return `suggested_refactor` (a
  replacement plus `decision_reason`) or `no_better_refactor` (no replacement, a required
  `decision_reason`, no correction attempt, no candidate reconstructed or displayed).
- Added `MaintainabilityImprovementDecision` in `comparison.py`: a deterministic, non-scoring
  accept/reject object (`accepted`, `failure_codes`, `improvements`, `regressions`,
  `explanation`) computed from the existing static comparison and the review's grounded smell
  citations for the approved target(s). It requires every reviewed smell resolved, at least one
  measured improvement, and no regression in complexity, nesting, parameter count, smell severity
  counts or newly introduced smells.
- Wired the gate into `generate_script_refactor` after the existing focused structural checks: a
  gate rejection now feeds the exact failure codes and measured before/after explanation into the
  same one-bounded-correction pipeline already used for structural/reconstruction failures
  (extended, not duplicated); a rejected correction withholds both candidates.
- Replaced overconfident review/refactor wording: review outcome `refactor_recommended` now reads
  "Maintainability opportunity identified"; a verified candidate reads "Verified static
  maintainability improvement"; model abstention reads "No better targeted option identified" with
  the model's `decision_reason`; a withheld candidate reads "No verified improvement found" with
  concrete deterministic reasons (for example, "Cyclomatic complexity increased from 6 to 7.").
  Existing before/after measurements, complete files, non-equivalence and interface warnings and
  safety checks are unchanged.
- Replaced the seven-line toy built-in example with an original ~86-line delivery-dispatch
  script (module docstring, one `Order` dataclass, seven functions, clean constants and type
  hints). It analyses to exactly one priority hotspot (`choose_next_delivery`: nesting depth 4,
  complexity 5, no mutable default) with every other definition free of smells, and is verified
  refactorable by guard clauses to nesting depth 2 with complexity unchanged and no new smell.
- Applied the deferred pasted-code copy correction: the Paste-code control now reads "Python
  source (paste your code here)" with placeholder "Paste a complete Python script here…"; no
  other source-route labels changed.
- Updated `PLAN.md`'s GPT-5.6-integration and candidate-verification sections to state the code-
  aware recommendation/generation decision, model abstention, deterministic veto authority, and
  that an absent accepted candidate does not prove no refactor exists.

### Automated verification

- `273 passed` in the complete pytest suite (up from 250 before this milestone), including a new
  focused `tests/test_maintainability_gate.py` (16 tests covering each required acceptance and
  rejection path directly against the gate) and new/updated tests in `test_ai.py` (eligibility,
  static goals, abstention, gate-triggered correction, correction-also-fails withholding),
  `test_ui.py` (abstention and withheld-candidate rendering, pasted-code label/placeholder) and
  `test_source.py` (built-in-example realism and guard-clause refactorability).
- Ruff check passed; Ruff format check passed for all 20 Python files; `pip check` reported no
  broken requirements; `git diff --check` reported no whitespace errors.
- Ran one scripted, fully mocked built-in-example journey (no live OpenAI request): load example
  -> analyse (hotspot `choose_next_delivery`, complexity 5, nesting 4) -> mocked review reads
  "Maintainability opportunity identified" -> mocked guard-clause refactor -> gate accepts
  (nesting 4 to 2, complexity unchanged at 5, deep-nesting smell resolved) -> every character
  outside the target preserved exactly -> success path renders "Verified static maintainability
  improvement". The same script also confirmed a deliberately complexity-regressing candidate is
  withheld after one failed correction attempt, and that model abstention returns the supplied
  `decision_reason` with no correction attempted.
- All OpenAI interactions remained mocked in both the automated suite and the scripted journey; no
  live OpenAI or GitHub request was made.

### Not completed in this timebox

- No live-model acceptance run (real `gpt-5.6-sol` calls) was performed; only mocked boundaries
  were exercised, per instruction.
- Manual browser verification of the updated copy and the new built-in example's on-screen
  rendering was not performed in this pass; only the Streamlit-recorder-based automated tests
  exercised the rendering code paths.
- No README, video or submission work was started.

### Repository state

- Nothing is staged. No commit or push occurred, and no deployment was started.

## 2026-07-21 — GitHub guidance, refactor-state clarity and comparison completeness

### Implemented changes

- Kept `Load GitHub file` as the sole GitHub acquisition action. The keyed
  `github_url_loader` now displays explicit button guidance and applies a scoped rule that hides
  Streamlit's `InputInstructions` only inside that loader; changing the field or pressing Enter does
  not fetch.
- Added one refactor-result classifier with four states: verified refactor, model abstention,
  unavailable/invalid and no result. Workflow status now distinguishes `Verified`, `No change
  proposed`, `Attempt failed`, `Available`, `Not offered` and `After AI review`; key presence alone
  never means code changed.
- Added a deterministic target-AST change check to refactor verification. An unchanged approved
  target is a typed `target_implementation_unchanged` failure. Verified presentation now separates
  target implementation and signature status, gives the original target line range, reports key
  before/after measurements and states unrelated-preservation, added, removed and unresolved
  definition counts without calling them a broad changed-structure count.
- Measurements & evidence now renders complete directional, descriptive and structural-verification
  groups only for a verified comparison. Model abstention, failed generation and unexpectedly
  incomplete comparison state each render a specific bordered explanation; no empty full-comparison
  heading is emitted.
- Print reports now validate the active document digest against deterministic analysis and every
  present review/refactor original-analysis digest before printing any source or result content. A
  mismatch displays the stale-report instruction instead of mixing sources.
- Updated `PLAN.md` narrowly. No source validation, host restriction, byte/character limit, timeout,
  AI schema/prompt, reconstruction, caching, print data or non-execution rule was weakened.

### Verification

- `366 passed` in the complete pytest suite. New coverage verifies explicit GitHub-button loading,
  scoped input-instruction CSS, every refactor result/workflow state, comparison absence messages,
  target AST and signature separation, preservation counts, unchanged-target rejection and
  source-bound print identity including `sessions.py`.
- Ruff check passed; Ruff format check passed for all 21 Python files; `pip check` reported no broken
  requirements; `git diff --check` passed.
- A localhost Chrome acceptance run at 1366×768 used production Streamlit presentation with mocked
  GitHub, review and refactor boundaries. Enter changed the URL without fetching; the explicit load
  button made one mocked fetch. The verified result showed the target implementation and signature
  change, Measurements & evidence exposed all three comparison groups, and the report identified
  `sessions.py · github` without built-in-example or stale-state content. Final mocked counts were
  one fetch, one review and one refactor.
- No live GitHub or OpenAI request occurred. Nothing was staged, committed, pushed or deployed.

## 2026-07-21 — Manual testing: alternative-refactor and print-report issues

Manual testing of the deployed maintainability-gate milestone surfaced several issues, recorded
here factually before any correction:

- The optional-refactor instructions field enforced a 500-character maximum without making that
  limit sufficiently visible in the interface.
- A shorter instruction pasted successfully, confirming that the earlier apparent paste failure
  was caused by the length cap rather than a defect in the paste path itself.
- The alternative-refactor request then returned a generic OpenAI error, while the interface
  concealed the available HTTP status detail that would have explained it.
- The alternative-refactor flow did not include the existing verified refactor in the next model
  request, so the model could not reliably know what approach to avoid repeating.
- The requested private-helper test conflicted with the one-definition targeted-replacement
  contract and was corrected.
- A successful current refactor and a failed alternative attempt were displayed together using
  wording ("No verified improvement found" / "No code change is recommended") that read as
  contradictory, since both messages appeared without identifying that they belonged to different
  requests.
- The printed report omitted the full Measurements & evidence workspace.
- Large reports were dominated by duplicated complete-source listings (the original and suggested
  files each printed in full).
- Manual review identified a valuable missing feature: a bounded, evidence-grounded follow-up
  explanation surface ("Ask CodeSage") for questions about the completed result.

Manual-test artefacts referenced: "PDF Report - 50K example - 21.07.pdf" and "PDF Report - GitHub
example with optional improvements - 21.07.pdf" (retained outside the repository; not embedded
here).

## 2026-07-21 — Alternative-refactor truthfulness, safe API errors, print appendix and bounded follow-up chat

### Implemented changes

In response to the manual-testing findings above:

- Moved the optional-refactor instruction limit into `codesage/config.py` as
  `REFACTOR_INSTRUCTION_CHARACTER_LIMIT` (500); `ai.py` and `app.py` both use the same constant.
  The field label now states the limit explicitly and a live "current/500 characters" counter is
  shown below it.
- `openai.APIStatusError` handling now captures a new `ApiErrorDetail(status_code, request_id)` on
  `ReviewResult`/`RefactorResult`. The interface shows "OpenAI could not complete this request
  (HTTP {status})." with the request ID, when present, inside a collapsed "Technical details"
  control. The raw response body is never displayed or logged; all other typed failures keep
  their existing fixed messages.
- `create_openai_client` now configures `max_retries=1`, documented as a transport-level retry
  distinct from CodeSage's own one bounded technical-correction attempt.
- "Generate a different refactor" now passes the existing verified refactor into
  `generate_script_refactor` as `previous_suggestion`. `ai.py` extracts only the approved target's
  definition from that previous complete-file suggestion via AST slicing
  (`_extract_target_definition_source`) and sends it as `untrusted_previous_replacement_source`;
  the complete previous file is never resent. The refactor and correction prompts require a
  meaningfully different coding approach.
- Added an AST-fingerprint comparison between the newly generated targeted replacement and the
  previous replacement. An identical replacement is rejected as `alternative_not_different`, is
  eligible for the existing single technical-correction attempt, and a still-identical correction
  withholds both candidates ("No verified different refactoring option was produced."). No
  existing maintainability, syntax, scope or preservation gate was weakened.
- Introduced `ALTERNATIVE_REFACTOR_ERROR_KEY` in `ui.py`, separate from `REFACTOR_ERROR_KEY`.
  `handle_refactor_action` now routes a failed alternative request to the new key without touching
  the existing verified `REFACTOR_KEY`, and defines explicit clearing rules for both error keys
  across initial requests, alternative requests, successful requests and source/review staleness.
  `app.py` renders the two failure states with distinct wording: a first-refactor failure reads
  "No verified refactor was produced." / "No code change is recommended from this request."; an
  alternative failure reads "Different refactor not produced" (maintainability gate), "No verified
  different refactoring option was produced." (AST-equivalent rejection) or "Different refactor
  request could not be completed" (API/technical error) — always stating that the current verified
  refactor remains available and unchanged, and never showing the unqualified "No code change is
  recommended" sentence while a verified refactor exists. The verified-refactor heading now reads
  "Current verified refactor" / "Current verified changed hotspot". The alternative-generation form
  and its attempt status are each wrapped in a keyed screen-only container
  (`refactor_generation_action`, `alternative_refactor_attempt_status`) and hidden under
  `@media print`.
- Added a dedicated, print-only Measurements & evidence appendix (`render_print_measurements_appendix`)
  using only static headings, text and `st.table`, never expanders or interactive dataframes. It
  includes every analysed unit (chunked into labelled "Part N of M" tables when large), every
  configured threshold, every warning or an explicit "None.", the exclusions statement, every
  evidence item cited by the AI review (never uncited evidence, or an explicit absence statement),
  every directional/descriptive/structural comparison row with status totals, or explicit absence
  statements when no verified refactor exists. Raw analysis JSON remains onscreen-only.
- Added `PRINT_COMPLETE_SOURCE_CHARACTER_LIMIT` (12,000 characters) in `config.py`. At or below the
  threshold both complete files print in full; above it, both are replaced with an explicit notice
  stating the exact character count, while the changed-hotspot diff and the appendix remain
  included. A section is never labelled "Compare the complete files" when the files were omitted.
  The print report order is now: source; summary; hotspot; review; refactor and diff; complete
  files (when within the limit); appendix, last.
- Added the bounded, evidence-based "Ask CodeSage about this result" follow-up chat: a new
  `CoachResponse` structured-output schema (`answer`, `evidence_ids`, `source_references`,
  `limitations`, `suggested_follow_up`) with no field capable of carrying replacement source; a new
  `ask_coach` request function in `ai.py`, separate from review and refactor generation; and
  `CoachMessage`/`CoachResult` value objects. The request sends only the review's cited evidence,
  the approved target source (never the complete file), the current verified target replacement
  when one exists, target-scoped before/after measurements and warnings, suggested safety checks
  and a bounded recent history; every returned evidence ID and source reference is validated
  against that exact supplied context before display. The chat is rendered beneath the completed AI
  review and beneath the current verified refactor from one shared `COACH_CHAT_KEY` session-state
  history, becomes available only after a successful review, offers state-appropriate starter
  questions that submit through the same mechanism, and shows a live message counter against the
  new `COACH_MESSAGE_CHARACTER_LIMIT` (1,000 characters). The conversation clears on source change,
  reanalysis, a new review, source-digest mismatch, a successful refactor replacement or an
  explicit "Clear conversation". The chat is wrapped in a keyed screen-only container
  (`ask_codesage_section`), excluded from the print report and never persisted beyond the session.
- Updated `PLAN.md` with new/updated sections covering alternative refactoring, the refactor state
  model, optional-instruction limits, API error and retry policy, the print-report specification,
  the Ask CodeSage follow-up chat, new Definition of Done acceptance criteria and new closed-scope
  exclusions.

### Configuration constants introduced or changed

- `REFACTOR_INSTRUCTION_CHARACTER_LIMIT = 500` (moved from an `ai.py`-local constant).
- `PRINT_COMPLETE_SOURCE_CHARACTER_LIMIT = 12_000`.
- `COACH_MESSAGE_CHARACTER_LIMIT = 1_000`.
- `COACH_CHAT_HISTORY_MESSAGES = 6` (maximum recent turns sent to the model).
- `COACH_MAX_OUTPUT_TOKENS = 2_000`.

### State keys introduced or changed

- `ALTERNATIVE_REFACTOR_ERROR_KEY = "script_alternative_refactor_error"`.
- `COACH_CHAT_KEY = "codesage_coach_chat"`.
- `COACH_CHAT_ERROR_KEY = "codesage_coach_chat_error"`.
- `COACH_CHAT_CONTEXT_KEY = "codesage_coach_chat_context_identity"`.

### Files changed

`src/codesage/config.py`, `src/codesage/ai.py`, `src/codesage/ui.py`, `app.py`, `PLAN.md`,
`BUILD_LOG.md`; tests in `tests/test_ai.py`, `tests/test_ui.py`, `tests/test_reconstruction.py`,
`tests/test_refactor_scope.py`, `tests/test_source.py`, and two new files
`tests/test_coach.py` and `tests/test_maintainability_gate.py` (the latter carried over from the
prior milestone).

### Automated verification

- `350 passed` in the complete pytest suite (up from 273 at the start of this entry's work),
  including 23 new tests in `tests/test_coach.py` covering chat availability preconditions, source
  mismatch, empty/overlong messages, cited-evidence-only context, target-only source (never the
  complete file), verified-replacement inclusion, evidence/source-reference citation validation,
  bounded history, and safe handling of timeout/rate-limit/connection/API-status/refusal/invalid-
  structured-output failures; and new/updated tests in `tests/test_ui.py` covering the alternative-
  refactor state separation and wording, the print appendix subsections and chunking, the print-size
  threshold's omission notice, and the "Ask CodeSage" section's availability, placement, starter
  questions, character limit, explicit-submission-only requests, state-clearing rules and print
  exclusion.
- Ruff check passed; Ruff format check passed for all Python files; `pip check` reported no broken
  requirements; `git diff --check` reported no whitespace errors.
- All OpenAI interactions remained mocked; no live OpenAI or GitHub request was made.

### Chat status

Implemented and tested (previously planned only). The chat is explanation-only: its response schema
has no code-bearing field, so a request for new or different code can only be redirected to the
dedicated refactor actions in prose.

### Not completed in this timebox

- No live-model acceptance run (real `gpt-5.6-sol` calls) was performed for the alternative-refactor
  fix or the chat feature; only mocked boundaries were exercised.
- Manual browser verification of the new wording, the print appendix's rendered PDF output and the
  "Ask CodeSage" chat's on-screen behaviour was not performed in this pass; only the
  Streamlit-recorder-based automated tests exercised these rendering paths.
- The chat's conversation history is bounded only for what is sent to the model
  (`COACH_CHAT_HISTORY_MESSAGES`); the displayed, in-session transcript itself is not separately
  capped and could grow long within a single session.
- No README, video or submission work was started.

### Repository state

- Nothing is staged. No commit or push occurred, and no deployment was started.

## 2026-07-21 — Canonical post-review refactor decision

- Recorded the manual-testing contradiction in which one review could be presented as both
  recommending a refactor and having the Refactor stage marked `Not offered`.
- Added immutable `RefactorAvailabilityDecision` and `RefactorAvailabilityStatus` values. One
  evidence-derived helper now supplies the availability state, label, explanation and approved
  target names used by review validation, workflow status, Overview, AI review, Refactor and the
  print report.
- Availability now requires a successful `refactor_recommended` review, at least one deterministic
  hotspot, a non-empty recommendation, a supported function or method target and a cited
  `smell.<code>` evidence item belonging to that target. High or medium severity does not override
  `no_refactor_needed` or `insufficient_evidence`.
- Production review validation now rejects a recommended review without an actionable target or
  cited target smell as `unsupported_refactor_recommendation`, before it can be stored and displayed
  as a successful review. The user-facing error remains fixed and contains no source or raw model
  content.
- Every successful AI-review page now shows exactly one explicit Next step or no-refactor conclusion
  after findings, safety checks and limitations and before Ask CodeSage. The Refactor workspace and
  print report use the same state-specific decision instead of the generic `Not offered` wording.
- Added a `choose_priority_item` regression fixture with 10 SLOC, nesting depth 5, complexity 6/rank
  B, deep-nesting and mutable-default evidence and targeted recommendations. Its canonical decision
  is `available` across Overview, AI review, workflow, Refactor and print.
- The complete automated suite passed with 376 tests. Ruff check and format check, `pip check` and
  `git diff --check` passed after the final implementation.
- Real local browser acceptance at 1366 × 768 used the actual Streamlit application with a temporary
  mocked review boundary. `refactor_recommended` showed the generation action; `no_refactor_needed`
  showed `No refactor recommended`; `insufficient_evidence` showed its explicit evidence result. In
  all three journeys the decision appeared before Ask CodeSage, the AI-review heading was present,
  and `Not offered` was absent. No external HTTP, GitHub or OpenAI request occurred.
- Nothing was staged, committed or pushed.

## 2026-07-21 — Manual testing discovery: invalid built-in review evidence reference

- The built-in example completed deterministic analysis successfully during manual testing.
- The live AI-review response parsed into the production structured schema but contained an
  evidence ID absent from the deterministic evidence package. Existing deterministic validation
  correctly returned `invalid_evidence_id` and withheld the complete review.
- At the time of that discovery, the 350-test suite used mocked OpenAI responses. No prior
  live-model acceptance journey had exercised a parsed review containing an unknown evidence ID.

## 2026-07-21 — Bounded evidence-reference recovery

- Added strict `FindingReferenceCorrection` and `ReviewGroundingCorrectionResponse` schemas. They
  can carry only original finding indexes, exact source references and exact evidence IDs; duplicate
  indexes, unknown catalogue values and out-of-range positions are rejected.
- Added one citation-only correction request for the five approved grounding failures. It receives
  the safe validation failure, immutable original parsed review and compact evidence catalogue, but
  never the complete source. API, refusal, incomplete, structured-output, mode, zero-hotspot and
  recommendation failures cannot enter this path.
- Reference changes are applied locally to the original review. Outcome, summary, finding order and
  count, all finding prose, suggested tests and assumptions/limitations remain unchanged before the
  complete production validator runs again. A second failure withholds the review and cannot recurse.
- `ReviewResult` now records correction status, whether it was attempted, initial and corrected
  failure codes, a bounded safe offending reference and the initial parsed response for in-session
  evaluation. This state is separate from refactor correction and Ask CodeSage.
- The interface discloses the possible extra citation-validation request, notes a successful
  correction once, and exposes only bounded validation codes and the safe offending identifier in
  collapsed failure details. Failed correction does not create `REVIEW_KEY`; an explicit retry
  remains possible, and success clears `REVIEW_ERROR_KEY`.
- Files changed for this bounded correction: `src/codesage/ai.py`, `app.py`, `tests/test_ai.py`,
  `tests/test_ui.py`, `PLAN.md` and `BUILD_LOG.md`.
- The complete automated suite passed with 393 tests. Ruff check and format check passed, `pip check`
  reported no broken requirements and `git diff --check` passed.
- The mandatory live built-in journey was not run in this execution because `OPENAI_API_KEY` was not
  available to the Codex process. No live OpenAI, GitHub or other external request occurred.
- Nothing was staged, committed or pushed.

## 2026-07-21 — Final competition-build submission checkpoint

### Scope frozen

- All supplied implementation prompts, including bounded evidence-reference recovery and
  revalidation, are complete in this checkpoint. No new feature, redesign, dependency change,
  deployment, release, tag or history rewrite was added for the checkpoint.
- Principal included behaviour: deterministic Python-script analysis and prioritised hotspots;
  evidence-based AI review; one bounded citation-only correction; explicit refactor-availability
  states; targeted replacement generation and deterministic full-file reconstruction; static
  maintainability and structure gates; one bounded refactor correction; genuine alternative
  handling with separate current/attempt state; privacy-safe API errors; optional instructions;
  Ask CodeSage; bounded Measurements & evidence views; the complete print appendix and large-source
  print policy; source-bound print validation; explicit GitHub loading; and verified target-body
  change reporting.

### Files included

- Configuration and governance: `.streamlit/config.toml`, `AGENTS.md`, `PLAN.md`, `BUILD_LOG.md`.
- Application: `app.py`, `src/codesage/ai.py`, `src/codesage/comparison.py`,
  `src/codesage/config.py`, `src/codesage/source.py`, `src/codesage/ui.py`.
- Tests: `tests/test_ai.py`, `tests/test_coach.py`, `tests/test_maintainability_gate.py`,
  `tests/test_reconstruction.py`, `tests/test_refactor_scope.py`, `tests/test_source.py`,
  `tests/test_ui.py`.
- Local static assets: Space Grotesk and Space Mono font files plus both SIL OFL licence files under
  `static/`.

### Configuration and state

- The checkpoint's bounded configuration includes 200,000-character acquisition, 200,000-byte
  fetched/uploaded response and 200,000-character decoded-source limits; a 100,000-character AI
  review limit; 160,000-character absolute reconstructed-source limit; 10-second GitHub timeout and
  three validated redirects; 500-character refactor instructions; 1,000-character coach messages;
  six coach-history messages; 2,000 coach output tokens; 12,000-character complete-source print
  threshold; and the 120-second/64,000-token OpenAI request bounds. Python 3.11 remains required.
- Durable session-state keys cover source and source route; analysis; review and review failure;
  current refactor, request identity, initial/alternative failures and instructions; coach history,
  error and context identity; print mode; canonical/widget workspace navigation; and one-use scroll
  state. Source changes and reanalysis invalidate dependent state.

### Tests and verification

- Tests added or updated cover acquisition and limits, analysis, evidence, comparison,
  maintainability vetoes, reconstruction, focused scope, AI review/refactor/correction boundaries,
  bounded evidence-reference recovery, Ask CodeSage, session caching/navigation, progressive UI and
  print-report behaviour. All OpenAI and ordinary HTTP boundaries are mocked in automated tests.
- Final automated result: `393 passed in 3.65s` on CPython 3.11.9.
- Ruff check: `All checks passed!`.
- Ruff format check: `21 files already formatted`.
- Pip check: `No broken requirements found.`.
- `git diff --check` passed with no whitespace errors; Git emitted only informational LF-to-CRLF
  working-copy warnings.
- A redacted scan of all intended text content found no likely real credentials. Ignored local
  environments, caches and build output were excluded. No secrets, screenshots, generated PDFs,
  manual source fixtures, browser output or uploaded conversation artefacts are included.

### Verification boundaries and remaining submission work

- Live OpenAI testing occurred during earlier manual discoveries, including the parsed unknown-ID
  response recorded above. No live OpenAI request was made for this checkpoint, and the final
  post-recovery built-in journey was not performed because the key was unavailable to Codex.
- Earlier local browser checks are recorded in their original entries. A complete final manual
  browser regression of this exact checkpoint was not performed and is not claimed.
- Remaining known limitations: Python scripts only; static analysis never executes code and cannot
  establish behavioural equivalence, runtime correctness or security; full controlled evaluation is
  future work; the exact checkpoint is not yet deployment-verified.
- The polished submission README and demo script/video remain intentionally pending as the next
  submission tasks. Deployment, public submission evidence and Devpost completion remain separate.
- This checkpoint is committed and pushed only after the automated verification, documentation
  reconciliation, file audit and secret scan above pass.
