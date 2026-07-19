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
- Separated the 200,000-character/byte ingestion limit from the 20,000-character complete-file AI
  review limit so larger accepted files retain deterministic analysis without truncation.
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
