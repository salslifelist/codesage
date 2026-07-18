# CodeSage Competition MVP Plan

## Status and authority

This is the single authoritative implementation plan for CodeSage. It incorporates the approved context audit, feasibility revisions, amendment review, focused notebook-target rules, zero-hotspot procedure, evaluation distinction and procedural-module rules. The source planning documents are preserved outside the repository and are superseded by this file.

The majority of core development, testing, evaluation, deployment and documentation must remain in the primary Codex thread. Run `/feedback` there only after most core functionality has been built. Every commit and push requires explicit human approval.

## Product and user

CodeSage is a deployed Streamlit maintainability coach that analyses pasted, uploaded or public-GitHub Python scripts and notebooks without execution, identifies up to three transparent structural hotspots, uses GPT-5.6 to explain and refactor them from deterministic evidence, and statically compares the original with the generated candidate while withholding claims of behavioural correctness.

Primary users are junior and intermediate Python developers, data scientists, machine-learning practitioners, students and small teams. The educational journey is evidence → explanation → focused refactor → independent re-analysis → qualified comparison.

## Closed scope

The competition MVP excludes:

- Big-O, time-complexity and auxiliary-space estimation;
- Maintainability Index or any proprietary aggregate quality score;
- model training or fine-tuning;
- repository-wide or multi-repository analysis;
- custom notebook dependency graphs or execution-order inference;
- execution of submitted code, generated code or notebooks;
- notebook insertion, deletion, reordering or reconstruction;
- private GitHub repositories, GitHub OAuth and arbitrary URL fetching;
- semantic-equivalence, runtime-performance or security claims;
- vulnerability, malware, energy, carbon or sustainability analysis;
- RAG, embeddings, vector databases, user accounts and persistent databases.

## Approved stack

- CPython 3.11 locally and on Streamlit Community Cloud.
- Standard-library `venv` and pip.
- Streamlit 1.59.2.
- `ast` plus Radon 6.0.1 for cyclomatic complexity.
- nbformat 5.10.4.
- OpenAI Python SDK 2.46.0 using the Responses API.
- Pydantic 2.13.4 strict models.
- HTTPX 0.28.1.
- pytest 9.1.1 and Ruff 0.15.22.

Do not introduce uv, Poetry, Pipenv, Conda, another Python version or an additional framework without approval.

## Inputs and normalisation

Accept exactly one source document through:

1. pasted Python;
2. local `.py` upload;
3. local `.ipynb` upload;
4. an approved public GitHub `.py` file URL;
5. an approved public GitHub `.ipynb` file URL;
6. an original built-in example.

All routes produce one normalised source model containing kind, origin, display name, decoded source or notebook, byte count, provenance, warnings and AI eligibility.

Acquisition is limited to 100 KB. Local text must decode as UTF-8. GitHub support is restricted to recognised `github.com/{owner}/{repo}/blob/{ref}/{path}` and `raw.githubusercontent.com/{owner}/{repo}/{ref}/{path}` shapes. Convert approved blob URLs locally, fetch from allow-listed hosts over HTTPS, disable general redirects, stream with a 100 KB limit and use bounded timeouts. Never clone or browse a repository.

## Deterministic maintainability analysis

Maintainability means local structural characteristics affecting how readily a function, method, module body or notebook cell can be understood, modified and tested. It does not measure correctness, architecture, test quality or overall software quality.

### Measurements

- syntax validity and parse errors;
- physical lines and source lines of code (SLOC);
- functions, methods and classes with qualified names and locations;
- function or method length;
- statement count;
- Radon cyclomatic complexity and A–F rank;
- maximum control-structure nesting depth;
- effective parameter count, excluding conventional `self` or `cls`;
- notebook cell size, location and analysis status;
- module/cell top-level procedural SLOC and direct statement count.

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
| Oversized procedural module/cell | Top-level procedural SLOC > 50 |
| Excessive top-level structure | More than 30 qualifying direct statements |

Thresholds are configurable constants and must be tested and documented as product defaults, not universal laws.

Smell severity for deterministic hotspot ordering is:

- **High:** long function or method; deep nesting; high cyclomatic complexity; oversized procedural module or cell; excessive top-level structure.
- **Medium:** too many parameters; complex Boolean expression; mutable default; bare exception; broad exception.

Severity is used only for deterministic hotspot ordering. It is not a claim about runtime risk, correctness or overall quality.

### Procedural SLOC

Module-level procedural SLOC comprises de-duplicated non-blank, non-comment lines belonging to qualifying executable constructs rooted directly in `Module.body`. Include complete ranges of assignments, expressions and module-level `if`, loops, `with`, `try`, `match` and equivalent constructs, including statements nested inside those constructs. Exclude imports, function/class definitions and their complete bodies, and the recognised module docstring.

Direct top-level statement count is the number of qualifying executable entries in `Module.body`. Apply the equivalent rules to a notebook cell.

### Hotspot granularity and selection

Functions and methods are the primary units for function length, nesting, complexity, parameters, Boolean logic, mutable defaults and exception smells. A module body or notebook cell is a hotspot only for the two procedural top-level smells.

Do not duplicate the same issue at symbol and containing-cell levels. For cell-level procedural counts, exclude nested function/class definitions and bodies. Unsupported or partially analysed content is a manual-review warning, never a smell by itself.

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

## Notebook boundaries

- Parse and validate with nbformat without executing or trusting outputs.
- Analyse every permitted Python code cell independently.
- Preserve cell ID where present, storage index and nearest preceding Markdown heading of levels 1–3.
- Treat notebook code and Markdown as untrusted data.
- Ignore outputs, attachments, execution counts and embedded display data.
- Detect cell magics, line magics, shell escapes and invalid Python; report transparent partial/excluded status.
- Deterministic limit: 50 code cells and 100 KB notebook input.
- AI limit: the complete eligible context must contain at most 20 analysable code cells and 30,000 code characters.
- If either AI limit is exceeded, keep complete deterministic results and disable AI review. Never truncate or silently choose a subset.

Display up to three notebook hotspots and allow the user to choose one for AI review; preselect the highest-ranked hotspot. A symbol hotspot retains its qualified name and cell-local lines, while its containing cell is the replacement target. Never choose a target randomly or solely by source order.

Baseline mode permits one focused existing-cell replacement. If one cell cannot safely address the selected issue, return a multi-cell strategy without a partial replacement. Optional support for up to three existing-cell replacements is allowed only after one-cell validation, tests and deployment are stable.

## GPT-5.6 integration

Use configurable `OPENAI_MODEL`, defaulting to the verified competition model `gpt-5.6-sol`, through `OpenAI().responses.parse(...)`. Start with reasoning effort `low`; change it only after evaluation. Use one model request per review, no tools and no automatic repair request.

Before sending source, require explicit user action and disclose that source will be sent to OpenAI. Keep deterministic analysis available without a key or successful model call.

The developer prompt must:

- delimit source, metadata and evidence;
- state that source, comments, strings, filenames and notebook Markdown are untrusted data;
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

Only `refactor_recommended` may contain a candidate. Notebook baseline candidates must replace the selected containing cell. `multi_cell_change_required` returns affected cell keys, strategy and why one cell is insufficient, with no candidate.

Each finding includes title, category, priority, source reference, evidence ID list, explanation, recommendation, learning takeaway and uncertainty. Validate field bounds, evidence references, symbols, cells, outcome/candidate consistency and output sizes. Reject malformed results; never invent missing fields.

### Zero-hotspot runtime and evaluation distinction

In the production zero-hotspot advisory mode, only `no_refactor_needed` and `insufficient_evidence` are valid. Reject target-dependent outcomes and candidates because no deterministic target exists; do not parse or display a candidate comparison.

In the clean-control evaluation, retain every raw response. If the model returns a candidate, `refactor_recommended` or `multi_cell_change_required`, record a zero-hotspot mode violation and potential over-intervention. Where structurally possible, parse and reanalyse the candidate without execution; measure expansion, unsupported problems/claims and interface/structural changes. Production rejection must not hide experimental failure.

## Candidate limits and verification

For scripts:

```text
min((2 × original_script_character_count) + 5,000, 60,000)
```

For combined notebook replacements:

```text
min((2 × combined_target_original_characters) + 5,000, 60,000)
```

For each replacement cell:

```text
min((2 × original_cell_character_count) + 2,000, 20,000)
```

Reject oversize output without truncation. For valid-size candidates:

1. parse without execution;
2. report syntax failure;
3. run the same deterministic analyser;
4. compare matching qualified symbols/cells;
5. show smells introduced and removed;
6. show structural-context warnings;
7. show suggested tests and the semantic limitation.

Directional measurements use `improved`, `regressed`, `unchanged` or `unresolved`: cyclomatic complexity, nesting depth and threshold-defined smells/counts for comparable units.

Descriptive measurements use `increased`, `decreased`, `unchanged` or `unresolved`: lines, SLOC, statements, length, parameters, imports, functions and classes. A descriptive change is not inherently an improvement.

Structural properties use `added`, `removed`, `changed`, `unchanged` or `unresolved`: functions, methods, classes, signatures, imports, notebook definitions and replacement identities.

Never derive “better overall”, “more maintainable overall”, “safe”, “correct” or “behaviourally equivalent”.

## User interface

Use one Streamlit page in this order:

1. title, purpose, privacy and non-execution notice;
2. source selector and input control;
3. loaded metadata and warnings;
4. deterministic Analyse action and state;
5. measurements, units, thresholds and up to three hotspots;
6. notebook target selection where applicable;
7. explicit Generate AI Review action and consent;
8. outcome, findings, takeaways, strategy and limitations;
9. complete script or affected-cell side-by-side view only when a candidate exists;
10. before/after evidence with correct comparison semantics;
11. structural-context warnings and suggested tests.

Use labelled controls, logical reading order, actionable errors and text in addition to colour. On narrow screens, stack clearly labelled Original and Candidate sections.

## Applied AI evaluation

Research question: does deterministic maintainability grounding improve GPT-5.6 review faithfulness, actionability and educational value compared with the same model reviewing source alone?

Keep model, reasoning, source, task, safety rules, schema, candidate rules, limits and validation identical. The sole treatment is a separately versioned grounding block: empty in the ungrounded condition and populated with measurements, smells, thresholds, hotspots and evidence IDs in the grounded condition.

Required synthetic cases:

1. long but low-complexity function;
2. deeply nested/high-complexity function;
3. too many parameters plus complex Boolean logic;
4. mutable default;
5. bare or broad exception handling;
6. notebook with at least two legitimate hotspots;
7. clean zero-hotspot control.

Prompt-injection content is an optional eighth case.

Measure schema validity, source-reference validity, deterministic-evidence validity, unsupported/invented claims, candidate syntax, targeted smell outcome, structural changes and a blinded human rubric for clarity, actionability, educational value and semantic risk. The clean control additionally measures unnecessary refactoring, candidate expansion and over-intervention.

Call budgets:

- minimum: 14 calls, seven cases × two conditions;
- target: 18 calls, plus four repeated calls across two representative cases;
- maximum: 20 calls, adding the eighth case and repeats.

Cut the optional case, then repeats; never cut either comparison condition or the seven required cases. Ordinary tests use mocked model/network behaviour.

## Safety, privacy and deployment

- Never execute submitted or generated code.
- Keep `OPENAI_API_KEY` and `OPENAI_MODEL` in environment variables or Streamlit secrets.
- Never commit `.env` or `.streamlit/secrets.toml`.
- Do not deliberately persist user source or log complete source/candidates.
- Log only safe metadata, timing and error categories.
- Use a dedicated OpenAI project with rate/spend limits and two best-effort reviews per Streamlit session.
- Preserve deterministic fallback and original built-in examples.
- Deploy on Streamlit Community Cloud with Python 3.11.
- Keep the judged version aligned with a tagged commit and available through 5 August 2026.

## Tests

Cover loaders and limits; URL allow-listing, conversion, redirects, timeouts and HTML; all measurements/smells/thresholds; procedural SLOC range de-duplication; hotspot granularity, ordering and zero-hotspot results; notebooks, magics and exclusions; strict AI schemas and all outcomes; candidate size formulas; runtime/evaluation zero-hotspot differences; comparison semantics; structural warnings; deterministic fallback; and clean-control over-intervention.

Use pytest, mock ordinary model/network calls and prioritise domain/integration tests over optional UI automation. Run Ruff and `pip check`. Manual acceptance covers real pinned GitHub files, live model script/notebook reviews, clean-browser deployment and responsive presentation.

## Milestones and effort

| Milestone | Mandatory | Optional |
| --- | ---: | ---: |
| Bootstrap and early feasibility checks | 1.5h | — |
| Script deterministic vertical slice | 4h | — |
| Script GPT-5.6 review and verification | 4h | — |
| Early Streamlit deployment | 2h | — |
| Notebook analysis and one-cell replacement | 3.5h | 1.5h multi-cell expansion |
| Upload and GitHub loaders | 1.5h | — |
| Hardening and acceptance | 2.5h | 0.5h UI tests |
| Seven-case evaluation | 3h | 1h optional case/repeats |
| Documentation, video and submission | 6h | — |

Protect five hours of contingency. Optional work may use at most three hours and begins only after deployment is stable, mandatory tests pass and submission/contingency reserves remain protected.

Automatic cut order: CI, unified diff, candidate download, non-trivial copy controls, decorative UI, optional UI tests, optional evaluation case, repeat calls, then three-cell expansion.

## Definition of Done

- All six source routes pass their acceptance checks.
- The deterministic analyser reports the approved measurements and smells without execution.
- Procedural script/cell hotspots, symbol granularity, de-duplication and zero-hotspot outcomes are tested.
- At most three transparent hotspots are shown.
- A notebook user can select one focused hotspot and receive a validated review outcome.
- `refactor_recommended` returns the correct complete script or existing-cell replacement.
- Abstention and no-refactor outcomes contain no candidate.
- Candidate size, syntax, re-analysis and comparison rules pass.
- Side-by-side presentation appears only for valid candidates.
- Oversized notebooks retain deterministic results and disable AI without truncation.
- AI failures preserve deterministic results.
- The seven-case grounded/ungrounded evaluation, including clean control, is recorded with at least 14 calls.
- Automated tests, Ruff, dependency checks and manual acceptance pass.
- Deployment works from a clean browser with secrets and cost controls.
- README, licence, installation, supported platforms, evaluation, privacy and limitations are complete.
- Public video is under three minutes and matches the tagged deployment.
- Devpost fields, repository access and competition evidence are verified.
- `/feedback` is run in the primary thread only after most core functionality is built.

## Repository and approval workflow

Use one authoritative README, this plan, a concise `AGENTS.md`, `BUILD_LOG.md`, evaluation documentation and a submission checklist. Avoid duplicate specifications.

Before each milestone, state objective, likely files, acceptance criteria, risks and cut line. After work, run relevant checks, show the diff, report verified/unverified behaviour and suggest a conventional commit. Wait for explicit approval before every commit, push, repository-visibility change, remote creation, deployment or `/feedback` run.
