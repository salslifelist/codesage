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
