"""CodeSage Streamlit entry point for bounded single-script review."""

from __future__ import annotations

import ast
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime
from difflib import unified_diff

import streamlit as st

from codesage.ai import (
    CorrectionStatus,
    GroundingCorrectionStatus,
    RefactorAvailabilityStatus,
    ReviewOutcome,
    refactor_availability,
)
from codesage.config import (
    AIAccessConfiguration,
    COACH_MESSAGE_CHARACTER_LIMIT,
    PRINT_COMPLETE_SOURCE_CHARACTER_LIMIT,
    REFACTOR_INSTRUCTION_CHARACTER_LIMIT,
    read_ai_access_configuration,
    verify_judge_access_code,
)
from codesage.evidence import THRESHOLDS
from codesage.models import AnalysisResult
from codesage.source import (
    SourceDocument,
    SourceIngestionError,
    fetch_github_source,
    normalise_example_source,
    normalise_pasted_source,
    normalise_uploaded_file,
)
from codesage.ui import (
    ALTERNATIVE_REFACTOR_ERROR_KEY,
    ANALYSIS_KEY,
    COACH_CHAT_ERROR_KEY,
    COACH_CHAT_KEY,
    EXAMPLE_MODE,
    REFACTOR_ERROR_KEY,
    REFACTOR_INSTRUCTIONS_KEY,
    REFACTOR_KEY,
    RefactorResultState,
    REVIEW_ERROR_KEY,
    REVIEW_KEY,
    SOURCE_KEY,
    SOURCE_MODE_KEY,
    SOURCE_CHARACTER_LIMIT,
    analysis_summary,
    clear_coach_chat,
    classify_refactor_result,
    coach_starter_questions,
    failure_message,
    handle_actions,
    handle_coach_chat_action,
    handle_refactor_action,
    invalidate_stale_state,
    load_example,
    metric_rows,
    readable_outcome,
    readable_smell,
    readable_source_reference,
    refactor_outcome_summary,
    source_summary,
    structural_rows,
    unit_inventory_rows,
    unit_measurements,
    workflow_statuses,
)

PRINT_MODE_KEY = "print_friendly_report"
SOURCE_ROUTE_MEMORY_KEY = "source_route_memory"
PENDING_SOURCE_MODE_KEY = "pending_source_input_mode"
EXAMPLE_LOADED_KEY = "built_in_example_loaded"
WORKSPACE_VIEW_STATE_KEY = "workspace_view"
WORKSPACE_VIEW_WIDGET_KEY = "_workspace_view_selector"
SCROLL_TO_TOP_KEY = "scroll_to_codesage_top"
SCROLL_SCRIPT_VARIANT_KEY = "_scroll_to_codesage_top_variant"
JUDGE_AI_ACCESS_GRANTED_KEY = "judge_ai_access_granted"
JUDGE_ACCESS_CODE_WIDGET_KEY = "_judge_access_code_input"
SOURCE_ROUTES = ("Paste code", "Upload .py file", "Public GitHub .py URL", EXAMPLE_MODE)
WORKSPACE_VIEWS = ("Overview", "AI review", "Refactor", "Measurements & evidence")
WORKSPACE_VIEW_ALIASES = {"Technical details": "Measurements & evidence"}
REQUIRED_STATIC_ASSETS = (
    "SpaceGrotesk-VariableFont_wght.ttf",
    "SpaceMono-Regular.ttf",
    "SpaceMono-Italic.ttf",
    "SpaceMono-Bold.ttf",
    "SpaceMono-BoldItalic.ttf",
    "OFL-SpaceGrotesk.txt",
    "OFL-SpaceMono.txt",
)
APP_STYLES = """
<style>
  .hero-safety { color: #625e4d; font-weight: 600; margin-top: 0.8rem; }
  .value-card-label { color: #8f4f3b; font-size: 0.78rem; font-weight: 700; }
  .workflow-status { color: #625e4d; font-size: 0.84rem; }
  .severity-badge {
    display: inline-block;
    border-radius: 999px;
    font-size: 0.76rem;
    font-weight: 700;
    letter-spacing: 0.025em;
    padding: 0.2rem 0.55rem;
    margin-bottom: 0.35rem;
  }
  .severity-high { background: #f9e2d9; color: #8a3d2d; border: 1px solid #dda28e; }
  .severity-medium { background: #f7ebc8; color: #755b16; border: 1px solid #dfca82; }
  .severity-low { background: #eee9f7; color: #554375; border: 1px solid #cfc1e4; }
  .status-label { font-size: 0.78rem; font-weight: 700; }
  .status-improved, .status-addressed { color: #24724b; }
  .status-trade-off, .status-partially-addressed { color: #806216; }
  .status-not-comparable, .status-unchanged { color: #625e4d; }
  .st-key-workspace_navigation { margin-top: 0.25rem; margin-bottom: 0.8rem; }
  [data-testid="stSidebar"] [data-testid="stRadio"] label {
    font-size: 1.02rem;
    font-weight: 600;
    line-height: 1.35;
    min-height: 2.35rem;
    padding-block: 0.25rem;
  }
  [data-testid="stSidebar"] [data-testid="stRadio"] label:focus-within {
    outline: 2px solid #cb785c;
    outline-offset: 2px;
    border-radius: 0.45rem;
  }
  .st-key-github_url_loader [data-testid="InputInstructions"] { display: none; }
  .st-key-complete_file_comparison [data-testid="stExpander"] summary {
    font-size: 1rem;
    font-weight: 600;
  }
  .st-key-print_report { max-width: 920px; margin: 0 auto; }
  @media (max-width: 1000px) {
    .st-key-landing_workspace [data-testid="stHorizontalBlock"],
    .st-key-ready_workspace [data-testid="stHorizontalBlock"] { flex-wrap: wrap; }
    .st-key-landing_workspace [data-testid="column"],
    .st-key-ready_workspace [data-testid="column"] {
      flex: 1 1 100% !important;
      min-width: 100% !important;
    }
  }
  @media print {
    [data-testid="stSidebar"],
    [data-testid="stHeader"],
    [data-testid="stToolbar"],
    [data-testid="stMainMenu"],
    [data-testid="stButton"],
    [data-testid="stTabs"],
    [data-testid="stSegmentedControl"],
    [data-testid="stTextInput"],
    [data-testid="stTextArea"],
    [data-testid="stFileUploader"],
    [data-testid="stRadio"],
    .st-key-landing_workspace,
    .st-key-ready_workspace,
    .st-key-workflow_progress,
    .st-key-workspace_navigation,
    .st-key-screen_controls,
    .st-key-refactor_generation_action,
    .st-key-alternative_refactor_attempt_status,
    .st-key-ask_codesage_section,
    .screen-only { display: none !important; }
    [data-testid="stAppViewContainer"],
    [data-testid="stMain"],
    .stApp { background: #ffffff !important; }
    .st-key-print_report { display: block !important; max-width: none; color: #111827; }
    [data-testid="stVerticalBlockBorderWrapper"],
    .st-key-refactor_metric_group,
    [class*="st-key-finding_"] { break-inside: avoid-page; page-break-inside: avoid; }
    pre, table { break-inside: auto; page-break-inside: auto; }
  }
</style>
"""
PAGE_TOP_ANCHOR = '<div id="codesage-page-top"></div>'
SCROLL_TO_TOP_SCRIPT = """
<script>
(() => {
  const doc = window.document;
  const triggerSelector = "[data-codesage-scroll-trigger]";

  const scrollToCodeSageTop = () => {
    const anchor = doc.getElementById("codesage-page-top");

    if (anchor) {
      anchor.setAttribute("tabindex", "-1");
      anchor.scrollIntoView({
        behavior: "auto",
        block: "start",
        inline: "nearest"
      });
      try {
        anchor.focus({preventScroll: true});
      } catch (_) {}
    }

    const possibleScrollers = [
      doc.scrollingElement,
      doc.documentElement,
      doc.body,
      doc.querySelector('[data-testid="stMain"]'),
      doc.querySelector('[data-testid="stAppViewContainer"]'),
      doc.querySelector('section.main')
    ].filter(Boolean);

    for (const element of possibleScrollers) {
      try {
        element.scrollTop = 0;
        if (typeof element.scrollTo === "function") {
          element.scrollTo({top: 0, left: 0, behavior: "auto"});
        }
      } catch (_) {}
    }

    try {
      window.scrollTo({top: 0, left: 0, behavior: "auto"});
    } catch (_) {}
  };

  const scheduleScroll = () => {
    [0, 50, 150, 300, 600].forEach((delay) => {
      window.setTimeout(scrollToCodeSageTop, delay);
    });
  };

  if (!window.__codesageScrollObserver) {
    window.__codesageScrollObserver = new MutationObserver((records) => {
      const triggerAdded = records.some((record) =>
        [...record.addedNodes].some((node) =>
          node.nodeType === 1 &&
          (node.matches?.(triggerSelector) || node.querySelector?.(triggerSelector))
        )
      );
      if (triggerAdded) scheduleScroll();
    });
    window.__codesageScrollObserver.observe(doc.documentElement, {
      childList: true,
      subtree: true
    });
  }

  scheduleScroll();
})();
</script>
"""
SCROLL_TO_TOP_SCRIPT_VARIANTS = (
    '<div data-codesage-scroll-trigger="a" hidden></div>' + SCROLL_TO_TOP_SCRIPT,
    '<div data-codesage-scroll-trigger="b" hidden></div>' + SCROLL_TO_TOP_SCRIPT,
)

COMPLEXITY_RANKS = (
    ("A", 1, 5, "Low complexity"),
    ("B", 6, 10, "Low complexity"),
    ("C", 11, 20, "Moderate complexity"),
    ("D", 21, 30, "Higher complexity"),
    ("E", 31, 40, "High complexity"),
    ("F", 41, None, "Very high complexity"),
)


def complexity_rank_details(score: int, rank: str) -> tuple[str, str]:
    """Explain a measured Radon score without treating its rank as an overall grade."""
    for expected_rank, lower, upper, _meaning in COMPLEXITY_RANKS:
        if expected_rank == rank:
            band = f"{lower}+" if upper is None else f"{lower}–{upper}"
            return (
                band,
                f"Complexity {score} is rank {rank} because it falls in the {band} band. "
                "Complexity measures branching and independent decision paths; the rank is "
                "not an overall code-quality grade.",
            )
    return (
        "Not available",
        f"Complexity {score} has no recognised display band. The rank is not an overall "
        "code-quality grade.",
    )


def render_complexity_rank_guide() -> None:
    rows = [
        {
            "Rank": rank,
            "Score range": f"{lower}+" if upper is None else f"{lower}–{upper}",
            "Meaning": meaning,
        }
        for rank, lower, upper, meaning in COMPLEXITY_RANKS
    ]
    with st.expander("How complexity ranks work", expanded=False):
        st.dataframe(rows, hide_index=True, width="stretch", height="content")
        st.caption(
            "Complexity is one structural measurement. Deep nesting, mutable defaults and "
            "other maintainability findings are measured separately."
        )


def render_priority_hotspots(
    analysis: AnalysisResult,
    *,
    limit: int | None = None,
    print_mode: bool = False,
) -> None:
    if not analysis.hotspots:
        st.info("No threshold-based maintainability hotspots were found.")
        return
    hotspots = analysis.hotspots if limit is None else analysis.hotspots[:limit]
    heading = "Priority hotspot" if len(hotspots) == 1 else "Priority hotspots"
    st.markdown(f"### {heading}")
    for position, hotspot in enumerate(hotspots, start=1):
        with st.container(border=True):
            st.markdown(
                f"#### {position}. {hotspot.qualified_name} · lines "
                f"{hotspot.line}–{hotspot.end_line}"
            )
            measurements = unit_measurements(hotspot)
            complexity = measurements["Complexity"]
            complexity_rank = measurements["Complexity rank"]
            rank_display = complexity_rank
            rank_explanation = None
            if isinstance(complexity, int) and isinstance(complexity_rank, str):
                band, rank_explanation = complexity_rank_details(complexity, complexity_rank)
                rank_display = f"{complexity_rank} (score {band})"
            metric_values = (
                ("Nesting depth", measurements["Nesting depth"]),
                ("Complexity", complexity),
                ("Complexity rank", rank_display),
                ("Static findings", len(hotspot.smells)),
            )
            for column, (label, value) in zip(st.columns(4), metric_values, strict=True):
                column.metric(label, value)
            st.markdown(
                "  \n".join(
                    f"- **{smell.severity.value.upper()} · {readable_smell(smell.code)}:** "
                    f"{smell.message}"
                    for smell in hotspot.smells
                )
            )
            if rank_explanation is not None:
                st.caption(rank_explanation)
    if not print_mode:
        render_complexity_rank_guide()


def render_analysis(
    analysis: AnalysisResult,
    *,
    heading: str = "Deterministic analysis",
    ai_eligible: bool | None = None,
) -> None:
    st.subheader(heading)
    summary = analysis_summary(analysis, ai_eligible=ai_eligible)
    for column, label in zip(
        st.columns(5),
        ("Syntax", "Physical lines", "SLOC", "Threshold-triggering hotspots", "AI review eligible"),
        strict=True,
    ):
        column.metric(label, summary[label])

    if not analysis.syntax_valid:
        failure = analysis.syntax_failure
        if failure is None:
            st.error("The script contains invalid syntax.")
        else:
            location = []
            if failure.line is not None:
                location.append(f"line {failure.line}")
            if failure.offset is not None:
                location.append(f"column {failure.offset}")
            suffix = f" at {', '.join(location)}" if location else ""
            st.error(f"{failure.message}{suffix}.")
        return

    render_priority_hotspots(analysis)


def render_analysis_technical(analysis: AnalysisResult) -> None:
    inventory = unit_inventory_rows(analysis)
    with st.expander(f"All analysed code units ({len(inventory)})", expanded=False):
        st.dataframe(
            inventory,
            hide_index=True,
            width="stretch",
            height=_table_height(inventory, bounded_height=420),
        )

    thresholds = [
        {"Threshold": name.replace("_", " ").title(), "Default": value}
        for name, value in THRESHOLDS.items()
    ]
    with st.expander("Configured hotspot thresholds", expanded=False):
        st.caption("These are configurable product defaults, not universal laws.")
        st.dataframe(
            thresholds,
            hide_index=True,
            width="stretch",
            height=_table_height(thresholds, bounded_height=320),
        )

    with st.expander(
        f"Analysis warnings ({len(analysis.analysis_warnings)})",
        expanded=bool(analysis.analysis_warnings),
    ):
        if not analysis.analysis_warnings:
            st.write("None.")
        for warning in analysis.analysis_warnings:
            st.warning(warning)

    with st.expander("Analysis exclusions (0)", expanded=False):
        st.write("No exclusions apply to this Python script.")

    with st.expander("Raw analysis data — advanced", expanded=False):
        st.caption("Raw deterministic data for debugging and audit use.")
        st.json(asdict(analysis), expanded=False)


def _evidence_rows(review, finding) -> list[dict[str, str]]:
    if review.evidence is None:
        return []
    evidence_by_id = {item.evidence_id: item for item in review.evidence.items}
    rows = []
    for evidence_id in finding.evidence_ids:
        item = evidence_by_id.get(evidence_id)
        if item is None:
            continue
        label = item.fact.removeprefix("unit.").removeprefix("smell.")
        label = label.replace("_", " ").replace(".", " ").title()
        value = item.value
        if isinstance(value, dict):
            value = value.get("message") or ", ".join(
                f"{key.replace('_', ' ')}: {detail}" for key, detail in value.items()
            )
        rows.append({"Measured result": label, "Value": str(value)})
    return rows


def render_workflow(state, *, compact: bool = False) -> None:
    st.markdown("**Workflow progress**")
    labels = ("1 · Analyse", "2 · Understand", "3 · Refactor")
    statuses = workflow_statuses(state)
    if compact:
        for label, status in zip(labels, statuses, strict=True):
            st.markdown(f"**{label}:** {status}")
        return
    with st.container(key="workflow_progress"):
        for column, label, status in zip(
            st.columns(3),
            labels,
            statuses,
            strict=True,
        ):
            with column:
                st.markdown(f"**{label}**")
                st.markdown(
                    f'<span class="workflow-status">{status}</span>',
                    unsafe_allow_html=True,
                )


def render_source_summary(document: SourceDocument) -> None:
    st.markdown("**Active source**")
    st.text(document.display_name)
    st.caption(source_summary(document))
    with st.expander("Source technical details", expanded=False):
        st.json(
            {
                "Display name": document.display_name,
                "Origin": document.origin.value,
                "Characters": len(document.text),
                "Acquired bytes": document.byte_count,
                "AI review eligible": document.ai_eligible,
                "External reference": document.external_reference,
            },
            expanded=False,
        )


def render_review(review, *, print_mode: bool = False) -> None:
    st.subheader("AI maintainability review")
    st.caption("Based on your code and CodeSage's deterministic measurements.")
    if not review.succeeded:
        st.error(failure_message(review.error_code))
        return
    response = review.response
    if response is None:
        st.error("The AI review returned no response.")
        return
    if review.grounding_correction_status is GroundingCorrectionStatus.SUCCEEDED:
        st.info("CodeSage corrected and revalidated the review's evidence references once.")

    locations = tuple(
        dict.fromkeys(
            readable_source_reference(item.source_reference) for item in response.findings
        )
    )
    hotspot_count = len(locations)
    finding_count = len(response.findings)
    hotspot_label = "hotspot" if hotspot_count == 1 else "hotspots"
    finding_label = "static finding" if finding_count == 1 else "static findings"
    overview_parts = [
        f"{hotspot_count} {hotspot_label}",
        f"{finding_count} {finding_label}",
    ]
    if locations:
        overview_parts.append("; ".join(locations))
    with st.container(border=True):
        st.markdown(f"### {readable_outcome(response.outcome.value)}")
        if response.outcome is ReviewOutcome.REFACTOR_RECOMMENDED:
            st.caption(
                "The measured evidence supports trying a targeted refactoring option. Any "
                "generated option must still pass CodeSage's independent maintainability checks."
            )
        st.caption(" · ".join(overview_parts))
        st.write(response.summary)

    evidence_rows = []
    for finding_index, finding in enumerate(response.findings, start=1):
        with st.container(border=True, key=f"finding_{finding_index}"):
            st.markdown(f"#### {finding.title}")
            severity_class = f"severity-{finding.priority.lower()}"
            st.markdown(
                f'<span class="severity-badge {severity_class}">Severity: '
                f"{finding.priority.upper()}</span>",
                unsafe_allow_html=True,
            )
            st.caption(
                f"Category: {finding.category} · "
                f"Code location: {readable_source_reference(finding.source_reference)}"
            )
            st.markdown("**Measured evidence**")
            measured_rows = _evidence_rows(review, finding)
            if measured_rows:
                if print_mode:
                    st.table(measured_rows, width="stretch")
                else:
                    st.dataframe(
                        measured_rows,
                        hide_index=True,
                        width="stretch",
                        height="content",
                    )
            st.markdown("**Why this matters**")
            st.write(finding.explanation)
            st.markdown("**Recommended change**")
            st.write(finding.recommendation)
            st.markdown("**Learning takeaway**")
            st.write(finding.learning_takeaway)
            if print_mode:
                st.markdown("**What CodeSage cannot determine**")
                st.write(finding.uncertainty)
            else:
                with st.expander("What CodeSage cannot determine", expanded=False):
                    st.write(finding.uncertainty)
        evidence_rows.append(
            {
                "Finding": finding.title,
                "Code location reference": finding.source_reference,
                "Evidence IDs": ", ".join(finding.evidence_ids),
            }
        )
    if evidence_rows:
        if print_mode:
            st.markdown("### Evidence references")
            st.table(evidence_rows, width="stretch")
        else:
            with st.expander("Evidence details", expanded=False):
                st.dataframe(
                    evidence_rows,
                    hide_index=True,
                    width="stretch",
                    height="content",
                )
    if response.suggested_tests:
        with st.container(border=True):
            st.markdown("### Safety checks to run before refactoring")
            st.write(
                "Run these checks on the original code first to capture its current behaviour. "
                "After generating a refactor, run the same checks again. CodeSage has not created "
                "or executed these tests."
            )
            st.markdown(
                "\n".join(
                    f"{position}. {check}"
                    for position, check in enumerate(response.suggested_tests, start=1)
                )
            )
    if response.assumptions_or_limitations:
        if print_mode:
            st.markdown("### Assumptions and limitations")
            for limitation in response.assumptions_or_limitations:
                st.write(f"- {limitation}")
        else:
            with st.expander("Assumptions and limitations", expanded=False):
                for limitation in response.assumptions_or_limitations:
                    st.write(f"- {limitation}")


def _change_status(before: int | None, after: int | None, *, lower_is_better: bool) -> str:
    if before is None or after is None:
        return "Not comparable"
    if before == after:
        return "Unchanged"
    improved = after < before if lower_is_better else after > before
    return "Improved" if improved else "Trade-off"


def _unified_target_diff(original_source: str, suggested_source: str) -> str:
    return "\n".join(
        unified_diff(
            original_source.splitlines(),
            suggested_source.splitlines(),
            fromfile="Original code",
            tofile="Suggested refactor",
            lineterm="",
            n=3,
        )
    )


@dataclass(frozen=True, slots=True)
class TargetChangeSummary:
    """Deterministic presentation facts for one verified refactor target."""

    target_name: str
    original_line: int | None
    original_end_line: int | None
    implementation_changed: bool | None
    signature_changed: bool | None
    unrelated_preserved: int
    added_definitions: int
    removed_definitions: int
    unresolved_definitions: int


def _definition_index(source: str) -> dict[str, ast.AST]:
    tree = ast.parse(source)
    definitions: dict[str, ast.AST] = {}

    def visit(body: list[ast.stmt], scope: tuple[str, ...]) -> None:
        for statement in body:
            if isinstance(statement, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
                qualified_name = ".".join((*scope, statement.name))
                definitions[qualified_name] = statement
                visit(statement.body, (*scope, statement.name))
            else:
                for child in ast.iter_child_nodes(statement):
                    child_body = getattr(child, "body", None)
                    if isinstance(child_body, list):
                        visit(child_body, scope)

    visit(tree.body, ())
    return definitions


def _refactor_target_names(refactor) -> tuple[str, ...]:
    verification = getattr(refactor, "verification", None)
    if verification is not None and verification.target_names:
        return verification.target_names
    names: list[str] = []
    for finding in getattr(refactor, "review", ()).findings:
        reference = finding.source_reference
        if ":" not in reference or "@L" not in reference:
            continue
        name = reference.split(":", 1)[1].rsplit(":", 1)[0]
        names.append(name)
    return tuple(dict.fromkeys(names))


def target_change_summary(refactor, original_source: str) -> TargetChangeSummary | None:
    """Derive target-body, signature and preservation facts without executing source."""
    if classify_refactor_result(refactor) is not RefactorResultState.VERIFIED_REFACTOR:
        return None
    verification = refactor.verification
    assert verification is not None
    assert verification.analysis is not None
    assert verification.comparison is not None
    assert refactor.suggested_refactor is not None
    targets = _refactor_target_names(refactor)
    if not targets:
        return None
    target = targets[0]
    try:
        original_definition = _definition_index(original_source).get(target)
        suggested_definition = _definition_index(refactor.suggested_refactor).get(target)
    except SyntaxError:
        return None
    implementation_changed = (
        None
        if original_definition is None or suggested_definition is None
        else ast.dump(original_definition, annotate_fields=True, include_attributes=False)
        != ast.dump(suggested_definition, annotate_fields=True, include_attributes=False)
    )
    original_units = {unit.qualified_name: unit for unit in refactor.original_analysis.units}
    suggested_units = {unit.qualified_name: unit for unit in verification.analysis.units}
    before_unit = original_units.get(target)
    after_unit = suggested_units.get(target)
    signature_changed = (
        None
        if before_unit is None or after_unit is None
        else before_unit.signature != after_unit.signature
    )
    definition_categories = {"function", "method", "class"}
    definition_items = [
        item
        for item in verification.comparison.structural
        if item.category in definition_categories
    ]
    unrelated_preserved = sum(
        item.name not in targets and item.status.value == "unchanged" for item in definition_items
    )
    return TargetChangeSummary(
        target,
        before_unit.line if before_unit is not None else None,
        before_unit.end_line if before_unit is not None else None,
        implementation_changed,
        signature_changed,
        unrelated_preserved,
        sum(item.status.value == "added" for item in definition_items),
        sum(item.status.value == "removed" for item in definition_items),
        sum(item.status.value == "unresolved" for item in definition_items),
    )


def render_refactor(
    refactor,
    original_source: str,
    *,
    print_mode: bool = False,
    include_complete_files: bool = True,
) -> None:
    refactor_state = classify_refactor_result(refactor)
    if refactor_state is RefactorResultState.MODEL_ABSTAINED:
        st.subheader("Suggested refactor")
        st.info("Code changed: No — the model did not identify a better targeted option.")
        st.info("No better targeted option identified")
        st.write(
            "The AI did not identify a targeted refactoring option it could justify from the "
            "supplied code and measured evidence."
        )
        if refactor.decision_reason:
            st.caption(refactor.decision_reason)
        return
    if refactor_state is not RefactorResultState.VERIFIED_REFACTOR:
        st.subheader("Suggested refactor")
        st.warning("Code changed: No verified change was produced.")
        return
    verification = refactor.verification
    change_summary = target_change_summary(refactor, original_source)
    if change_summary is None or change_summary.implementation_changed is not True:
        st.subheader("Suggested refactor")
        st.warning("Code changed: No verified change was produced.")
        return
    assert verification is not None
    assert verification.analysis is not None
    assert verification.comparison is not None
    st.subheader("Current verified refactor")
    st.success("Verified static maintainability improvement")
    st.caption(
        "The suggested refactor addresses all reviewed static findings for the selected target, "
        "improves at least one measured maintainability factor and introduces no measured "
        "maintainability regression."
    )
    if refactor.correction_status is CorrectionStatus.SUCCEEDED:
        st.info("CodeSage needed one extra attempt to produce verifiable Python.")
    st.caption(
        "CodeSage verified that this is valid Python and that the required static definitions "
        "were preserved. Static checks do not prove runtime behaviour or equivalence."
    )
    outcome_summary = refactor_outcome_summary(refactor)
    comparison = verification.comparison
    targets = _refactor_target_names(refactor)
    original_units = {unit.qualified_name: unit for unit in refactor.original_analysis.units}
    suggested_units = {unit.qualified_name: unit for unit in verification.analysis.units}
    target = targets[0] if targets else None
    before_unit = original_units.get(target) if target else None
    after_unit = suggested_units.get(target) if target else None
    before_findings = len(
        outcome_summary.addressed
        + outcome_summary.still_present
        + outcome_summary.unable_to_compare
    )
    after_findings = (
        None if outcome_summary.unable_to_compare else len(outcome_summary.still_present)
    )
    finding_status = (
        "Not comparable"
        if after_findings is None
        else "Addressed"
        if after_findings == 0
        else "Partially addressed"
    )

    metric_cards = (
        (
            "Nesting depth",
            getattr(before_unit, "nesting_depth", None),
            getattr(after_unit, "nesting_depth", None),
            None,
        ),
        ("Static findings", before_findings, after_findings, finding_status),
        (
            "Complexity",
            getattr(before_unit, "complexity", None),
            getattr(after_unit, "complexity", None),
            None,
        ),
    )
    with st.container(key="refactor_metric_group"):
        for column, (label, before, after, fixed_status) in zip(
            st.columns(3), metric_cards, strict=True
        ):
            status = fixed_status or _change_status(before, after, lower_is_better=True)
            value = (
                f"{before if before is not None else '—'} → {after if after is not None else '—'}"
            )
            column.metric(label, value, delta=status, delta_color="off")
            status_class = status.lower().replace(" ", "-")
            column.markdown(
                f'<span class="status-label status-{status_class}">{status}</span>',
                unsafe_allow_html=True,
            )

    st.markdown("### Refactor outcome")
    st.markdown(f"**{outcome_summary.label}**")
    st.write(outcome_summary.explanation)
    if outcome_summary.addressed:
        st.markdown("**Addressed:**")
        for issue in outcome_summary.addressed:
            st.write(f"- {issue.detail}")
    if outcome_summary.still_present:
        st.markdown("**Still present:**")
        for issue in outcome_summary.still_present:
            st.write(f"- {issue.detail}")
    if outcome_summary.unable_to_compare:
        st.markdown("**Unable to compare:**")
        for issue in outcome_summary.unable_to_compare:
            st.write(f"- {issue.detail}")
    if outcome_summary.other_measured_changes:
        st.warning(" ".join(outcome_summary.other_measured_changes))
    st.write("Changed target:", ", ".join(targets))
    st.success("Required unrelated static definitions were preserved.")
    st.write(
        "Correction attempt:",
        "Used once" if refactor.correction_status is CorrectionStatus.SUCCEEDED else "Not needed",
    )
    st.caption(
        f"Structural preservation: {change_summary.unrelated_preserved} unrelated definitions "
        f"unchanged · {change_summary.added_definitions} added · "
        f"{change_summary.removed_definitions} removed · "
        f"{change_summary.unresolved_definitions} unresolved"
    )

    interface_changes = [
        item
        for item in comparison.structural
        if item.category == "signature" and item.status.value == "changed"
    ]
    if interface_changes:
        st.warning(
            "Static interface change: "
            + ", ".join(item.name for item in interface_changes)
            + ". Review callers before adopting this refactor."
        )
    st.warning(verification.non_equivalence_notice)

    line_range = (
        f"lines {change_summary.original_line}–{change_summary.original_end_line}"
        if change_summary.original_line is not None and change_summary.original_end_line is not None
        else "original line range unavailable"
    )
    signature_status = (
        "Changed"
        if change_summary.signature_changed is True
        else "Unchanged"
        if change_summary.signature_changed is False
        else "Unavailable"
    )
    before_nesting = getattr(before_unit, "nesting_depth", None)
    after_nesting = getattr(after_unit, "nesting_depth", None)
    before_complexity = getattr(before_unit, "complexity", None)
    after_complexity = getattr(after_unit, "complexity", None)
    with st.container(border=True):
        st.markdown("### Change summary")
        st.success(f"Code changed: Yes — {change_summary.target_name} was replaced and verified.")
        st.write(f"Changed target: {change_summary.target_name} ({line_range})")
        st.write("Target implementation: Changed")
        st.write(f"Target signature: {signature_status}")
        st.write(
            f"Unrelated definitions preserved: {change_summary.unrelated_preserved} · "
            f"Added definitions: {change_summary.added_definitions} · "
            f"Removed definitions: {change_summary.removed_definitions} · "
            f"Unresolved definitions: {change_summary.unresolved_definitions}"
        )
        st.write(
            "Key measurements: "
            f"nesting {before_nesting if before_nesting is not None else '—'} → "
            f"{after_nesting if after_nesting is not None else '—'} · "
            f"complexity {before_complexity if before_complexity is not None else '—'} → "
            f"{after_complexity if after_complexity is not None else '—'} · "
            f"static findings {before_findings} → "
            f"{after_findings if after_findings is not None else '—'}"
        )

    st.markdown("### Current verified changed hotspot")
    target_diff = (
        _unified_target_diff(original_source, refactor.suggested_refactor)
        or "No textual change was detected."
    )
    if print_mode:
        st.code(target_diff, language="diff")
    else:
        st.code(target_diff, language="diff", height=320)

    def code_comparison() -> None:
        original_column, refactor_column = st.columns(2)
        with original_column:
            st.markdown("**Original code**")
            st.code(original_source, language="python", height=420)
        with refactor_column:
            st.markdown("**Suggested refactor**")
            st.code(refactor.suggested_refactor, language="python", height=420)

    if print_mode:
        if include_complete_files:
            st.markdown("### Compare the complete files")
            st.write("View the original file and the full suggested version side by side.")
            st.markdown("**Before refactoring — original file**")
            st.code(original_source, language="python")
            st.markdown("**After refactoring — suggested file**")
            st.code(refactor.suggested_refactor, language="python")
        else:
            st.markdown("### Complete source files")
            st.info(
                "Complete source listings were omitted from this PDF because the source "
                f"contains {len(original_source):,} characters. The changed-hotspot diff and "
                "complete static measurements remain included. The complete files remain "
                "available in the CodeSage app."
            )
        st.markdown("### Re-run your safety checks")
        st.write(
            "CodeSage has checked the refactor statically but has not executed it. Run the same "
            "checks against the refactored code and compare the results."
        )
    else:
        st.markdown("### Compare the complete files")
        st.write("View the original file and the full suggested version side by side.")
        with st.container(key="complete_file_comparison"):
            with st.expander("View before-and-after files side by side", expanded=False):
                original_column, refactor_column = st.columns(2)
                with original_column:
                    st.markdown("**Before refactoring — original file**")
                    st.code(original_source, language="python", height=420)
                with refactor_column:
                    st.markdown("**After refactoring — suggested file**")
                    st.code(refactor.suggested_refactor, language="python", height=420)
        st.markdown("### Re-run your safety checks")
        st.write(
            "CodeSage has checked the refactor statically but has not executed it. Run the same "
            "checks against the refactored code and compare the results."
        )


def render_comparison_technical(refactor) -> None:
    if not refactor.succeeded or refactor.verification is None:
        return
    comparison = refactor.verification.comparison
    if comparison is None:
        return
    directional = metric_rows(comparison.directional)
    descriptive = metric_rows(comparison.descriptive)
    structural = structural_rows(comparison.structural)
    with st.expander("Complete directional comparisons", expanded=False):
        st.dataframe(
            directional,
            hide_index=True,
            width="stretch",
            height=_table_height(directional, bounded_height=420),
        )
    with st.expander("Complete descriptive comparisons", expanded=False):
        st.dataframe(
            descriptive,
            hide_index=True,
            width="stretch",
            height=_table_height(descriptive, bounded_height=420),
        )
    with st.expander("Complete structural verification", expanded=False):
        st.dataframe(
            structural,
            hide_index=True,
            width="stretch",
            height=_table_height(structural, bounded_height=420),
        )
    if comparison.warnings:
        warnings = [{"Warning": warning} for warning in comparison.warnings]
        with st.expander(
            f"Complete comparison warnings ({len(comparison.warnings)})", expanded=False
        ):
            st.dataframe(
                warnings,
                hide_index=True,
                width="stretch",
                height=_table_height(warnings, bounded_height=320),
            )


def render_before_after_comparisons(refactor) -> None:
    """Render comparison data or an explicit reason why it is unavailable."""
    refactor_state = classify_refactor_result(refactor)
    if refactor_state is RefactorResultState.NO_RESULT:
        return
    if refactor_state is RefactorResultState.VERIFIED_REFACTOR:
        st.markdown("### Full before-and-after comparisons")
        render_comparison_technical(refactor)
        return
    if refactor_state is RefactorResultState.MODEL_ABSTAINED:
        with st.container(border=True):
            st.markdown("### No before-and-after comparison")
            st.write(
                "CodeSage did not produce a targeted code change for this request, so there is "
                "no refactored file to compare."
            )
            if refactor.decision_reason:
                st.caption(refactor.decision_reason)
        return
    if getattr(refactor, "succeeded", False):
        with st.container(border=True):
            st.markdown("### Comparison data unavailable")
            st.write(
                "CodeSage recorded a refactor result, but its verified comparison data is "
                "missing. Generate the refactor again."
            )
        return
    with st.container(border=True):
        st.markdown("### No verified comparison available")
        st.write(
            "The refactor request did not produce code that passed CodeSage's verification checks."
        )


def _analysis_totals(analysis: AnalysisResult) -> tuple[int, int]:
    hotspot_count = sum(bool(unit.smells) for unit in analysis.units)
    finding_count = sum(len(unit.smells) for unit in analysis.units)
    return hotspot_count, finding_count


def _table_height(rows, *, bounded_height: int, content_limit: int = 12) -> int | str:
    """Size small tables to their content and bound larger result sets."""
    return "content" if len(rows) <= content_limit else bounded_height


def load_example_for_workspace(state) -> None:
    """Mark the example as explicitly loaded without analysing it."""
    load_example(state)
    state[EXAMPLE_LOADED_KEY] = True
    request_source_mode(state, EXAMPLE_MODE)
    navigate_to_workspace(state, "Overview")


def analyse_for_workspace(state, document: SourceDocument) -> None:
    """Run the existing deterministic action and open its Overview."""
    handle_actions(state, document, analyse_clicked=True, review_clicked=False)
    navigate_to_workspace(state, "Overview")


def render_landing(state) -> None:
    """Render the deliberate first-load workspace without result navigation."""
    with st.container(key="landing_workspace"):
        introduction, journey = st.columns([1.15, 1], gap="large")
        with introduction:
            st.title("CodeSage")
            st.subheader("Your Python maintainability coach")
            st.write(
                "CodeSage finds maintainability hotspots, explains the evidence behind them, "
                "and helps you explore targeted refactoring options."
            )
            st.markdown(
                '<p class="hero-safety">Static analysis only. CodeSage never executes your '
                "code.</p>",
                unsafe_allow_html=True,
            )
            st.button(
                "Try the built-in example",
                type="primary",
                on_click=load_example_for_workspace,
                args=(state,),
            )
            st.caption("Or choose Paste, Upload or GitHub from the source panel.")
        with journey:
            with st.container(border=True):
                st.subheader("How CodeSage helps")
                st.markdown("**1 Analyse**")
                st.write("Measure complexity, nesting and maintainability smells.")
                st.markdown("**2 Understand**")
                st.write("See why the measured findings matter.")
                st.markdown("**3 Refactor**")
                st.write("Explore a focused change and inspect the trade-offs.")

        value_cards = (
            ("Find hotspots", "Detect complexity, deep nesting and maintainability smells."),
            (
                "Understand why",
                "See explanations based on CodeSage's measured evidence.",
            ),
            (
                "Refactor carefully",
                "Generate a focused suggestion and inspect what changed.",
            ),
        )
        for column, (title, description) in zip(st.columns(3), value_cards, strict=True):
            with column:
                with st.container(border=True):
                    st.markdown(
                        '<span class="value-card-label">CODE COACH</span>', unsafe_allow_html=True
                    )
                    st.markdown(f"### {title}")
                    st.write(description)


def render_ready_to_analyse(document: SourceDocument, state) -> None:
    """Render a source preview and the single deterministic-analysis action."""
    with st.container(key="ready_workspace"):
        st.title("CodeSage")
        st.subheader("Your Python maintainability coach")
        st.caption(source_summary(document))
        preview, action = st.columns([3, 2], gap="large")
        with preview:
            with st.container(border=True):
                st.markdown("### Source preview")
                st.text(document.display_name)
                st.code(document.text, language="python", height=360)
        with action:
            with st.container(border=True):
                st.markdown("### Ready to analyse")
                st.write("CodeSage will measure:")
                st.markdown(
                    "- cyclomatic complexity\n- nesting depth\n- structural maintainability smells"
                )
                st.caption("Static analysis only. CodeSage never executes your code.")
                st.button(
                    "Analyse code",
                    type="primary",
                    use_container_width=True,
                    on_click=analyse_for_workspace,
                    args=(state, document),
                )


def _ai_review_status(document: SourceDocument, state) -> str:
    analysis = state[ANALYSIS_KEY]
    if REVIEW_KEY in state:
        return "Complete"
    if analysis.syntax_valid and document.ai_eligible:
        return "Optional"
    return "Unavailable for this source"


def render_workspace_header(document: SourceDocument, state) -> None:
    """Render the compact post-analysis identity and status strip."""
    analysis = state[ANALYSIS_KEY]
    hotspot_count, finding_count = _analysis_totals(analysis)
    identity, report_action = st.columns([5, 1], gap="medium")
    with identity:
        st.title("CodeSage")
        origin_label = source_summary(document).split(" · ", maxsplit=1)[0]
        st.caption(f"{document.display_name} · {origin_label}")
    with report_action:
        st.button(
            "Print-friendly report",
            type="secondary",
            use_container_width=True,
            on_click=set_print_mode,
            args=(state, True),
        )
    values = (
        ("Analysis", "Complete" if analysis.syntax_valid else "Syntax error"),
        ("Hotspots", hotspot_count),
        ("Static findings", finding_count),
        ("AI review", _ai_review_status(document, state)),
    )
    for column, (label, value) in zip(st.columns(4), values, strict=True):
        column.metric(label, value)


def render_safe_error_detail(result) -> None:
    """Render a fixed, privacy-safe message; never the raw API response body."""
    detail = getattr(result, "api_error_detail", None)
    if detail is not None:
        st.error(f"OpenAI could not complete this request (HTTP {detail.status_code}).")
        with st.expander("Technical details", expanded=False):
            if detail.request_id:
                st.write(f"Request ID: {detail.request_id}")
            else:
                st.write("No request ID was returned.")
    else:
        st.error(failure_message(result.error_code))
    if getattr(result, "grounding_correction_attempted", False):
        with st.expander("Technical details", expanded=False):
            st.write(
                "Initial validation failure: "
                f"{result.initial_grounding_failure_code or 'unavailable'}"
            )
            if result.initial_grounding_failure_detail:
                st.write(f"Offending evidence reference: {result.initial_grounding_failure_detail}")
            if result.correction_grounding_failure_code:
                st.write(
                    f"Correction validation failure: {result.correction_grounding_failure_code}"
                )


def _render_action_errors(state) -> None:
    review_error = state.get(REVIEW_ERROR_KEY)
    if review_error is not None:
        render_safe_error_detail(review_error)

    refactor_error = state.get(REFACTOR_ERROR_KEY)
    if refactor_error is not None:
        st.error("No verified refactor was produced.")
        st.write("No code change is recommended from this request.")
        if refactor_error.gate_explanations:
            for explanation in refactor_error.gate_explanations:
                st.write(f"- {explanation}")
        else:
            render_safe_error_detail(refactor_error)

    alternative_error = state.get(ALTERNATIVE_REFACTOR_ERROR_KEY)
    if alternative_error is not None:
        with st.container(key="alternative_refactor_attempt_status"):
            attempted_codes = (
                alternative_error.correction_failure_codes
                or alternative_error.initial_failure_codes
            )
            if "alternative_not_different" in attempted_codes:
                st.error("No verified different refactoring option was produced.")
                st.write(
                    "The current verified refactor shown above remains available and unchanged."
                )
            elif alternative_error.gate_explanations:
                st.error("Different refactor not produced")
                st.write(
                    "The alternative attempt did not pass CodeSage's maintainability checks. "
                    "The current verified refactor shown above remains available and unchanged."
                )
                for explanation in alternative_error.gate_explanations:
                    st.write(f"- {explanation}")
            else:
                st.error("Different refactor request could not be completed")
                st.write(
                    "The current verified refactor shown above remains available and unchanged."
                )
                render_safe_error_detail(alternative_error)


def ai_access_is_granted(state, configuration: AIAccessConfiguration | None = None) -> bool:
    """Return whether this browser session may use the configured hosted AI."""
    current = configuration or read_ai_access_configuration()
    return current.available and state.get(JUDGE_AI_ACCESS_GRANTED_KEY) is True


def authorise_judge_ai_access(state, submitted_code: str, *, verifier=None) -> bool:
    """Store only a session Boolean after a successful access-code comparison."""
    check = verify_judge_access_code if verifier is None else verifier
    if not check(submitted_code):
        return False
    state[JUDGE_AI_ACCESS_GRANTED_KEY] = True
    return True


def render_judge_ai_access(state, configuration: AIAccessConfiguration | None = None) -> bool:
    """Render the shared judging gate and return the current session authorisation."""
    current = configuration or read_ai_access_configuration()
    if not current.enabled:
        st.info(
            "Hosted AI features are temporarily unavailable. Deterministic analysis remains "
            "available."
        )
        return False
    if not current.available:
        st.info("Hosted AI features are not configured. Deterministic analysis remains available.")
        return False
    if ai_access_is_granted(state, current):
        st.success("AI features are unlocked for this session.")
        return True

    with st.container(border=True):
        st.markdown("### Judge AI access")
        st.write(
            "Enter the judging access code to use hosted AI features. Deterministic analysis "
            "remains publicly available."
        )
        with st.form("judge_ai_access", clear_on_submit=True):
            submitted_code = st.text_input(
                "Access code",
                type="password",
                key=JUDGE_ACCESS_CODE_WIDGET_KEY,
            )
            submitted = st.form_submit_button("Unlock AI features", type="primary")
        if submitted:
            if authorise_judge_ai_access(state, submitted_code):
                st.rerun()
            else:
                st.error("The access code was not recognised.")
    return False


def request_ai_review(state, document: SourceDocument) -> str | None:
    """Call the existing review handler only for an authorised browser session."""
    if not ai_access_is_granted(state):
        return "Unlock AI features before requesting an AI review."
    return handle_actions(
        state,
        document,
        analyse_clicked=False,
        review_clicked=True,
    )


def request_suggested_refactor(
    state,
    document: SourceDocument,
    *,
    optional_instructions: str,
    on_correction_start,
) -> str | None:
    """Call the existing refactor handler only for an authorised browser session."""
    if not ai_access_is_granted(state):
        return "Unlock AI features before generating a suggested refactor."
    return handle_refactor_action(
        state,
        document,
        refactor_clicked=True,
        optional_instructions=optional_instructions,
        on_correction_start=on_correction_start,
    )


def render_review_action(document: SourceDocument, state, *, empty_state: bool = False) -> None:
    """Render the shared explicit review action in an eligible workspace view."""
    analysis = state[ANALYSIS_KEY]
    if not analysis.syntax_valid:
        st.warning("Fix the syntax error in the selected source, then analyse it again.")
        return
    if not document.ai_eligible:
        st.info("This script is available for deterministic analysis only.")
        return
    if not render_judge_ai_access(state):
        return
    with st.container(border=True):
        if empty_state:
            st.markdown("### No AI review yet")
            st.write(
                "AI review is optional. If requested, it will explain prioritised findings "
                "using your code and CodeSage's measured evidence."
            )
        else:
            st.markdown("### Optional: get an evidence-based explanation")
            st.write(
                "Your deterministic analysis is complete. You can continue using the measured "
                "results without AI, or request an AI review for explanations, learning guidance "
                "and targeted refactoring options."
            )
            st.write(
                "CodeSage will send your complete eligible source and its measured results to "
                "OpenAI. The AI must base its findings on this evidence and reference the "
                "relevant code locations. This request explains the findings but does not "
                "rewrite your code."
            )
        st.caption(
            "CodeSage may make one additional request only when a parsed review's evidence "
            "references fail validation."
        )
        action_slot = st.empty()
        if action_slot.button("Get AI review", type="primary"):
            with st.spinner("Getting AI maintainability review…"):
                action_error = request_ai_review(state, document)
            if action_error:
                st.error(action_error)
            elif REVIEW_KEY in state and REVIEW_ERROR_KEY not in state:
                navigate_to_workspace(state, "AI review")
                action_slot.empty()
                st.rerun()
    _render_action_errors(state)


def render_refactor_action(
    document: SourceDocument,
    state,
    *,
    alternative: bool,
    empty_state: bool = False,
) -> None:
    """Render one explicit generation action in its relevant workspace view."""
    review = state.get(REVIEW_KEY)
    decision = refactor_availability(review)
    if decision.status is not RefactorAvailabilityStatus.AVAILABLE:
        return
    if not render_judge_ai_access(state):
        return
    with st.container(border=True):
        if empty_state:
            st.markdown("### No suggested refactor yet")
            st.write(
                "Review the findings, then generate a targeted refactor. CodeSage will preserve "
                "the rest of the file unchanged."
            )
        elif alternative:
            st.markdown("### Explore another refactoring option")
            st.write(
                "Ask CodeSage for a different approach to the same hotspot. Add specific "
                "instructions if you want to guide the next suggestion—for example, preserve "
                "the public signature, make the smallest possible change, keep comments and "
                "docstrings, or prefer early returns."
            )
        else:
            st.markdown("### Next step: Generate a suggested refactor")
            st.write(
                "CodeSage identified a supported maintainability opportunity for "
                f"{', '.join(decision.target_names)}. Any generated change must still pass "
                "CodeSage's independent static verification."
            )
        with st.expander("How CodeSage generates and checks the suggestion", expanded=False):
            st.write(
                "Generating a refactor makes a separate OpenAI request. CodeSage will not "
                "execute the generated code. It will check syntax and deterministic structure, "
                "but static verification does not prove runtime behaviour or equivalence. "
                "CodeSage may make one additional attempt only when the generated Python cannot "
                "be verified technically."
            )
        instructions_label = (
            "Instructions for the next refactor (optional — maximum "
            f"{REFACTOR_INSTRUCTION_CHARACTER_LIMIT} characters)"
            if alternative
            else "Instructions for this refactor (optional — maximum "
            f"{REFACTOR_INSTRUCTION_CHARACTER_LIMIT} characters)"
        )
        optional_instructions = st.text_area(
            instructions_label,
            key=REFACTOR_INSTRUCTIONS_KEY,
            max_chars=REFACTOR_INSTRUCTION_CHARACTER_LIMIT,
            placeholder=(
                "For example: Preserve the public signature and prefer early returns."
                if alternative
                else "For example: Keep the public signature unchanged and make the smallest "
                "practical change."
            ),
            help="Add specific instructions if you want to guide the suggestion.",
        )
        st.caption(
            f"{len(optional_instructions)}/{REFACTOR_INSTRUCTION_CHARACTER_LIMIT} characters"
        )
        label = "Generate a different refactor" if alternative else "Generate suggested refactor"
        if st.button(
            label,
            type="primary",
            key="try_different_refactor" if alternative else "generate_suggested_refactor",
        ):
            with st.spinner("Generating and checking the suggested refactor…"):
                action_error = request_suggested_refactor(
                    state,
                    document,
                    optional_instructions=optional_instructions,
                    on_correction_start=lambda _: st.info(
                        "The first generated version could not be verified. CodeSage is trying "
                        "once more to produce valid Python."
                    ),
                )
            if action_error:
                st.error(action_error)
            elif REFACTOR_KEY in state and REFACTOR_ERROR_KEY not in state:
                navigate_to_workspace(state, "Refactor")
                st.rerun()
    _render_action_errors(state)


def submit_coach_question(state, document: SourceDocument, *, question: str) -> None:
    """Make exactly one explicit "Ask CodeSage" request for this question."""
    if not ai_access_is_granted(state):
        return
    handle_coach_chat_action(state, document, message=question, submit_clicked=True)


def render_ask_codesage(document: SourceDocument, state) -> None:
    """Render the bounded, evidence-based follow-up chat for the current result.

    Available only after a successful AI review. The same conversation is shown beneath
    the AI review and beneath the current verified refactor, since both call sites read
    from the same COACH_CHAT_KEY session state.
    """
    review = state.get(REVIEW_KEY)
    if review is None or not review.succeeded:
        return
    if not render_judge_ai_access(state):
        return
    refactor = state.get(REFACTOR_KEY)
    refactor_available = classify_refactor_result(refactor) is RefactorResultState.VERIFIED_REFACTOR
    with st.container(border=True, key="ask_codesage_section"):
        st.markdown("### Ask CodeSage about this result")
        st.caption(
            "CodeSage answers questions using the current static analysis, AI review and "
            "verified comparison. It does not execute the code or prove runtime behaviour."
        )
        starters = coach_starter_questions(refactor_available=refactor_available)
        starter_columns = st.columns(2)
        for index, starter_question in enumerate(starters):
            with starter_columns[index % 2]:
                st.button(
                    starter_question,
                    key=f"coach_starter_{index}",
                    on_click=submit_coach_question,
                    args=(state, document),
                    kwargs={"question": starter_question},
                )

        history = state.get(COACH_CHAT_KEY, ())
        for message in history:
            speaker = "You" if message.role == "user" else "CodeSage"
            st.markdown(f"**{speaker}:** {message.content}")
            for limitation in message.limitations:
                st.caption(
                    f"CodeSage cannot determine that from the available static "
                    f"evidence: {limitation}"
                )

        chat_error = state.get(COACH_CHAT_ERROR_KEY)
        if chat_error is not None:
            render_safe_error_detail(chat_error)

        question_text = st.text_area(
            f"Ask a question about this result (optional — maximum "
            f"{COACH_MESSAGE_CHARACTER_LIMIT} characters)",
            key="codesage_coach_question_input",
            max_chars=COACH_MESSAGE_CHARACTER_LIMIT,
            placeholder="For example: Why does this issue matter?",
        )
        st.caption(f"{len(question_text)}/{COACH_MESSAGE_CHARACTER_LIMIT} characters")
        send_column, clear_column = st.columns(2)
        with send_column:
            if st.button("Send", type="secondary", key="coach_send_question"):
                with st.spinner("Asking CodeSage…"):
                    submit_coach_question(state, document, question=question_text)
                st.rerun()
        with clear_column:
            if st.button("Clear conversation", key="coach_clear_conversation"):
                clear_coach_chat(state)
                st.rerun()


def render_overview(document: SourceDocument | None, state) -> None:
    analysis = state.get(ANALYSIS_KEY)
    if document is None or analysis is None:
        st.info("Choose or load a Python script, then select Analyse code in the workspace.")
        return
    hotspot_count, static_findings = _analysis_totals(analysis)
    if not analysis.syntax_valid:
        ai_eligibility = "Unavailable"
    elif document.ai_eligible:
        ai_eligibility = "Not requested"
    else:
        ai_eligibility = "Deterministic only"
    review = state.get(REVIEW_KEY)
    refactor = state.get(REFACTOR_KEY)
    ai_status = "Complete" if review is not None else ai_eligibility
    values = (
        ("Syntax", "Valid" if analysis.syntax_valid else "Invalid"),
        ("Priority hotspots", hotspot_count),
        ("Static findings", static_findings),
        ("AI-review status", ai_status),
    )
    for column, (label, value) in zip(st.columns(4), values, strict=True):
        with column:
            with st.container(border=True):
                st.metric(label, value)
    if not analysis.syntax_valid:
        failure = analysis.syntax_failure
        st.error(failure.message if failure is not None else "The script contains invalid syntax.")
        return
    render_priority_hotspots(analysis, limit=1)
    if review is None:
        render_review_action(document, state)
        return
    render_review_ready_card(state)
    if classify_refactor_result(refactor) is RefactorResultState.VERIFIED_REFACTOR:
        with st.container(border=True):
            st.markdown("### Suggested-refactor snapshot")
            st.write(refactor_outcome_summary(refactor).label)
            st.success("Required unrelated static definitions were preserved.")
            st.button(
                "View suggested refactor",
                type="secondary",
                on_click=navigate_to_workspace,
                args=(state, "Refactor"),
            )


def render_review_evidence_technical(review) -> None:
    if review is None or review.response is None or review.evidence is None:
        return
    cited_ids = {
        evidence_id for finding in review.response.findings for evidence_id in finding.evidence_ids
    }
    rows = [
        {
            "Evidence ID": item.evidence_id,
            "Code location": item.source_reference,
            "Measured result": item.fact,
            "Value": str(item.value),
        }
        for item in review.evidence.items
        if item.evidence_id in cited_ids
    ]
    if rows:
        with st.expander(f"Evidence used by the AI review ({len(rows)})", expanded=False):
            st.dataframe(
                rows,
                hide_index=True,
                width="stretch",
                height=_table_height(rows, bounded_height=420),
            )


def request_scroll_to_top(state) -> None:
    """Request one static scroll after the destination has rendered."""
    state[SCROLL_TO_TOP_KEY] = True


def render_requested_scroll(state) -> bool:
    """Consume one scroll request and render the sole approved JavaScript helper."""
    if not state.pop(SCROLL_TO_TOP_KEY, False):
        return False
    variant = (state.get(SCROLL_SCRIPT_VARIANT_KEY, -1) + 1) % len(SCROLL_TO_TOP_SCRIPT_VARIANTS)
    state[SCROLL_SCRIPT_VARIANT_KEY] = variant
    st.html(SCROLL_TO_TOP_SCRIPT_VARIANTS[variant], unsafe_allow_javascript=True)
    return True


def request_source_mode(state, mode: str) -> None:
    """Request a source route without mutating the instantiated radio widget."""
    if mode in SOURCE_ROUTES:
        state[PENDING_SOURCE_MODE_KEY] = mode


def apply_pending_source_mode(state) -> None:
    """Apply one requested source route before the radio widget is instantiated."""
    pending = state.pop(PENDING_SOURCE_MODE_KEY, None)
    if pending in SOURCE_ROUTES:
        state[SOURCE_MODE_KEY] = pending
        state[SOURCE_ROUTE_MEMORY_KEY] = pending


def canonical_workspace_view(value) -> str:
    """Return one supported workspace view, preserving the legacy label alias."""
    canonical = WORKSPACE_VIEW_ALIASES.get(value, value)
    return canonical if canonical in WORKSPACE_VIEWS else "Overview"


def navigate_to_workspace(state, view: str) -> None:
    """Change permanent navigation state without mutating the widget-owned key."""
    state[WORKSPACE_VIEW_STATE_KEY] = canonical_workspace_view(view)
    request_scroll_to_top(state)


def store_workspace_widget_selection(state) -> None:
    """Copy a user-selected widget value into permanent application state."""
    selected = canonical_workspace_view(state.get(WORKSPACE_VIEW_WIDGET_KEY))
    state[WORKSPACE_VIEW_STATE_KEY] = selected
    request_scroll_to_top(state)


def synchronise_workspace_widget(state) -> str:
    """Populate the widget key from canonical state before widget creation."""
    canonical = canonical_workspace_view(state.get(WORKSPACE_VIEW_STATE_KEY))
    state[WORKSPACE_VIEW_STATE_KEY] = canonical
    state[WORKSPACE_VIEW_WIDGET_KEY] = canonical
    return canonical


def render_review_ready_card(state) -> None:
    decision = refactor_availability(
        state.get(REVIEW_KEY) or state.get(REVIEW_ERROR_KEY),
        state.get(REFACTOR_KEY),
    )
    with st.container(border=True):
        st.markdown("### AI review ready")
        st.write("CodeSage has completed the evidence-based review.")
        st.caption(f"Refactor: {decision.label} — {decision.explanation}")
        st.button(
            "View AI review",
            type="secondary",
            on_click=navigate_to_workspace,
            args=(state, "AI review"),
        )


def render_review_next_step(document: SourceDocument, state) -> None:
    """Render exactly one explicit post-review decision before the coach."""
    decision = refactor_availability(state.get(REVIEW_KEY), state.get(REFACTOR_KEY))
    refactor_state = classify_refactor_result(state.get(REFACTOR_KEY))
    if decision.status is RefactorAvailabilityStatus.ALREADY_VERIFIED:
        render_refactor_ready_card(state)
        return
    if refactor_state is not RefactorResultState.NO_RESULT:
        render_refactor_ready_card(state)
        return
    if decision.status is RefactorAvailabilityStatus.AVAILABLE:
        render_refactor_action(document, state, alternative=False)
        return
    with st.container(border=True, key="review_next_step"):
        if decision.status is RefactorAvailabilityStatus.NO_REFACTOR_NEEDED:
            st.markdown("### No refactor recommended")
            st.write(
                "The completed AI review did not identify a sufficiently useful targeted code "
                "change. You can continue using the measurements, explanation and suggested "
                "tests."
            )
        elif decision.status is RefactorAvailabilityStatus.INSUFFICIENT_EVIDENCE:
            st.markdown("### No refactor offered — insufficient evidence")
            st.write(
                "CodeSage could not justify a targeted code change from the available static "
                "evidence."
            )
        elif decision.status is RefactorAvailabilityStatus.UNSUPPORTED_RECOMMENDATION:
            st.markdown("### Refactor availability could not be determined")
            st.write(
                "The review recommended a refactor, but CodeSage could not validate the "
                "grounded target required to generate one. Request the AI review again."
            )
        else:
            st.markdown("### Complete an AI review first")
            st.write(decision.explanation)


def render_unavailable_refactor_state(decision) -> None:
    """Explain one canonical unavailable state in the Refactor workspace."""
    if decision.status is RefactorAvailabilityStatus.NO_REFACTOR_NEEDED:
        title = "No suggested refactor"
        explanation = "The AI review did not recommend a targeted refactor."
    elif decision.status is RefactorAvailabilityStatus.INSUFFICIENT_EVIDENCE:
        title = "No suggested refactor — insufficient evidence"
        explanation = (
            "The AI review could not justify a targeted refactor from the available evidence."
        )
    elif decision.status is RefactorAvailabilityStatus.UNSUPPORTED_RECOMMENDATION:
        title = "Refactor availability could not be determined"
        explanation = (
            "The review recommended a refactor, but its grounded target could not be validated."
        )
    else:
        title = "No suggested refactor yet"
        explanation = "Review the findings before requesting a targeted refactor."
    _render_stage_card(title, explanation, decision.explanation)


def render_refactor_ready_card(state) -> None:
    refactor_state = classify_refactor_result(state.get(REFACTOR_KEY))
    with st.container(border=True):
        if refactor_state is RefactorResultState.VERIFIED_REFACTOR:
            st.markdown("### Suggested refactor ready")
            st.write(
                "CodeSage generated and statically checked a targeted refactor. Review the "
                "changes, trade-offs and limitations in the Refactor workspace."
            )
        elif refactor_state is RefactorResultState.MODEL_ABSTAINED:
            st.markdown("### No change proposed")
            st.write("The model did not identify a better targeted option for this request.")
        else:
            st.markdown("### Refactor attempt failed")
            st.write("No generated code passed CodeSage's verification checks.")
        st.button(
            "View current verified refactor"
            if refactor_state is RefactorResultState.VERIFIED_REFACTOR
            else "View refactor result",
            type="secondary",
            on_click=navigate_to_workspace,
            args=(state, "Refactor"),
        )


def _render_stage_card(title: str, prerequisite: str, provides: str) -> None:
    with st.container(border=True):
        st.markdown(f"### {title}")
        st.write(prerequisite)
        st.caption(provides)


def render_workspace(document: SourceDocument | None, state) -> None:
    analysis = state.get(ANALYSIS_KEY)
    if analysis is None:
        return
    review = state.get(REVIEW_KEY)
    refactor = state.get(REFACTOR_KEY)
    refactor_state = classify_refactor_result(refactor)
    availability = refactor_availability(
        review if review is not None else state.get(REVIEW_ERROR_KEY),
        refactor,
    )
    selected_view = synchronise_workspace_widget(state)
    st.markdown("### Results workspace")
    with st.container(border=True, key="workspace_navigation"):
        st.segmented_control(
            "Results workspace",
            WORKSPACE_VIEWS,
            key=WORKSPACE_VIEW_WIDGET_KEY,
            selection_mode="single",
            width="stretch",
            label_visibility="collapsed",
            on_change=store_workspace_widget_selection,
            args=(state,),
        )
    selected_view = canonical_workspace_view(state.get(WORKSPACE_VIEW_STATE_KEY, selected_view))

    if selected_view == "Overview":
        render_overview(document, state)
    elif selected_view == "AI review":
        if review is None:
            if document is not None:
                render_review_action(document, state, empty_state=True)
        else:
            render_review(review)
            if document is not None:
                render_review_next_step(document, state)
            if document is not None and review.succeeded:
                render_ask_codesage(document, state)
    elif selected_view == "Refactor":
        if refactor_state is RefactorResultState.NO_RESULT:
            if REFACTOR_ERROR_KEY in state:
                with st.container(border=True):
                    st.markdown("### Refactor attempt failed")
                    st.warning("Code changed: No verified change was produced.")
            if document is not None and availability.status is RefactorAvailabilityStatus.AVAILABLE:
                render_refactor_action(
                    document,
                    state,
                    alternative=False,
                    empty_state=True,
                )
            else:
                render_unavailable_refactor_state(availability)
        elif document is not None:
            render_refactor(refactor, document.text)
            if refactor_state is RefactorResultState.VERIFIED_REFACTOR:
                with st.container(key="refactor_generation_action"):
                    render_refactor_action(document, state, alternative=True)
            if review is not None and review.succeeded:
                render_ask_codesage(document, state)
    else:
        st.subheader("Measurements & evidence")
        st.write(
            "Inspect the measurements behind CodeSage's findings, the thresholds it applied, "
            "evidence referenced by the AI review, and complete before-and-after comparisons."
        )
        render_analysis_technical(analysis)
        render_review_evidence_technical(review)
        comparison_result = refactor if refactor is not None else state.get(REFACTOR_ERROR_KEY)
        render_before_after_comparisons(comparison_result)


def set_print_mode(state, enabled: bool) -> None:
    if enabled:
        state[PRINT_MODE_KEY] = True
    else:
        state.pop(PRINT_MODE_KEY, None)
        request_scroll_to_top(state)


PRINT_TABLE_CHUNK_SIZE = 40


def _print_table_chunks(rows: list[dict], *, chunk_size: int = PRINT_TABLE_CHUNK_SIZE) -> None:
    """Render every row as one or more explicitly labelled static tables.

    Never silently shortens a table: every row is shown, split across clearly
    labelled "Part N of M" chunks when the inventory is large.
    """
    if not rows:
        st.write("None.")
        return
    total_parts = -(-len(rows) // chunk_size)
    if total_parts <= 1:
        st.table(rows, width="stretch")
        return
    for index in range(total_parts):
        chunk = rows[index * chunk_size : (index + 1) * chunk_size]
        st.markdown(f"**Part {index + 1} of {total_parts}**")
        st.table(chunk, width="stretch")


def render_print_measurements_appendix(analysis, review, refactor) -> None:
    """Render the complete, print-only Measurements & evidence appendix.

    Uses only static headings, text and st.table output — never expanders or interactive
    dataframes, which are not reliable printable content — and never truncates a row
    without labelling every chunk shown. This is a dedicated renderer; it does not call
    render_analysis_technical(), render_review_evidence_technical() or
    render_comparison_technical(), which remain the onscreen Measurements & evidence views.
    """
    st.markdown("## Measurements & evidence appendix")
    st.write("Detailed measurements supporting CodeSage's findings and verification.")

    inventory = unit_inventory_rows(analysis)
    st.markdown(f"### All analysed code units ({len(inventory)})")
    _print_table_chunks(inventory)

    st.markdown("### Configured hotspot thresholds")
    st.caption("These are configurable product defaults, not universal laws.")
    thresholds = [
        {"Threshold": name.replace("_", " ").title(), "Default": value}
        for name, value in THRESHOLDS.items()
    ]
    st.table(thresholds, width="stretch")

    st.markdown(f"### Analysis warnings ({len(analysis.analysis_warnings)})")
    if analysis.analysis_warnings:
        for warning in analysis.analysis_warnings:
            st.write(f"- {warning}")
    else:
        st.write("None.")
    st.markdown("### Analysis exclusions (0)")
    st.write("No exclusions apply to this Python script.")

    st.markdown("### Evidence used by the AI review")
    if review is None or review.response is None or review.evidence is None:
        st.write("No AI-review evidence is available because no AI review was requested.")
    else:
        cited_ids = {
            evidence_id
            for finding in review.response.findings
            for evidence_id in finding.evidence_ids
        }
        rows = [
            {
                "Evidence ID": item.evidence_id,
                "Code location": item.source_reference,
                "Measured fact": item.fact,
                "Value": str(item.value),
            }
            for item in review.evidence.items
            if item.evidence_id in cited_ids
        ]
        _print_table_chunks(rows)

    st.markdown("### Complete before-and-after measurements")
    verification = (
        refactor.verification
        if classify_refactor_result(refactor) is RefactorResultState.VERIFIED_REFACTOR
        else None
    )
    if verification is None or verification.comparison is None:
        st.write(
            "No before-and-after measurements are available because no verified suggested "
            "refactor is present."
        )
    else:
        comparison = verification.comparison
        st.markdown("#### Directional comparisons")
        _print_table_chunks(metric_rows(comparison.directional))
        st.markdown("#### Descriptive comparisons")
        _print_table_chunks(metric_rows(comparison.descriptive))
        st.markdown("#### Comparison warnings")
        if comparison.warnings:
            for warning in comparison.warnings:
                st.write(f"- {warning}")
        else:
            st.write("None.")

    st.markdown("### Structural verification results")
    if verification is None or verification.comparison is None:
        st.write(
            "No structural verification results are available because no verified suggested "
            "refactor is present."
        )
    else:
        structural = verification.comparison.structural
        _print_table_chunks(structural_rows(structural))
        counts = Counter(item.status.value for item in structural)
        st.write(
            f"Changed: {counts['changed']} · Unchanged: {counts['unchanged']} · "
            f"Added: {counts['added']} · Removed: {counts['removed']} · "
            f"Unresolved: {counts['unresolved']}"
        )
        st.caption(
            "Structural preservation is a static check. It does not establish behavioural "
            "equivalence."
        )


def report_state_matches_source(document, analysis, review, refactor) -> bool:
    """Return whether every printable result belongs to the exact active source digest."""
    if document is None or analysis is None:
        return False
    digest = document.source_digest
    if getattr(analysis, "source_digest", None) != digest:
        return False
    if (
        review is not None
        and getattr(getattr(review, "original_analysis", None), "source_digest", None) != digest
    ):
        return False
    return not (
        refactor is not None
        and getattr(getattr(refactor, "original_analysis", None), "source_digest", None) != digest
    )


def render_print_report(state, *, timestamp: datetime | None = None) -> bool:
    """Render one linear report; return False when the user requests app mode."""
    document = state.get(SOURCE_KEY)
    analysis = state.get(ANALYSIS_KEY)
    review = state.get(REVIEW_KEY)
    review_error = state.get(REVIEW_ERROR_KEY)
    refactor = state.get(REFACTOR_KEY)
    with st.container(key="screen_controls"):
        st.markdown(
            '<p class="screen-only">Print or save as PDF using Ctrl+P on Windows or Command+P '
            "on macOS.</p>",
            unsafe_allow_html=True,
        )
        if st.button(
            "Return to app",
            on_click=set_print_mode,
            args=(state, False),
        ):
            return False
    with st.container(key="print_report"):
        st.title("CodeSage report")
        if document is None or analysis is None:
            st.info("Analyse a Python script before opening the print-friendly report.")
            return True
        if not report_state_matches_source(document, analysis, review, refactor):
            st.error("The report state is stale. Analyse the current source again before printing.")
            return True
        st.markdown("## Source")
        st.write(
            f"{document.display_name} · {document.origin.value} · "
            f"{len(document.text):,} characters · {document.byte_count:,} bytes"
        )
        generated_at = timestamp or datetime.now().astimezone()
        st.caption(f"Report generated {generated_at:%d %B %Y at %H:%M %Z}")
        st.markdown("## Deterministic summary")
        st.table(
            [
                {"Measurement": label, "Result": str(value)}
                for label, value in analysis_summary(
                    analysis,
                    ai_eligible=document.ai_eligible and analysis.syntax_valid,
                ).items()
            ],
            width="stretch",
        )
        render_priority_hotspots(analysis, limit=1, print_mode=True)
        if review is not None:
            render_review(review, print_mode=True)
        elif review_error is not None:
            st.info(failure_message(review_error.error_code))
        else:
            st.info("No AI review was requested for this report.")
        if refactor is not None:
            include_complete_files = len(document.text) <= PRINT_COMPLETE_SOURCE_CHARACTER_LIMIT
            render_refactor(
                refactor,
                document.text,
                print_mode=True,
                include_complete_files=include_complete_files,
            )
        else:
            decision = refactor_availability(review or review_error)
            if decision.status is RefactorAvailabilityStatus.AVAILABLE:
                st.info("A targeted refactor is available but has not yet been generated.")
            elif decision.status is RefactorAvailabilityStatus.NO_REFACTOR_NEEDED:
                st.info("The AI review did not recommend a targeted refactor.")
            elif decision.status is RefactorAvailabilityStatus.INSUFFICIENT_EVIDENCE:
                st.info(
                    "The AI review could not justify a targeted refactor from the available "
                    "static evidence."
                )
            elif decision.status is RefactorAvailabilityStatus.UNSUPPORTED_RECOMMENDATION:
                st.info(
                    "The review recommended a refactor, but its grounded target could not be "
                    "validated."
                )
            else:
                st.info("No verified suggested refactor is available for this report.")
        render_print_measurements_appendix(analysis, review, refactor)
    return True


def render_sidebar(state) -> SourceDocument | None:
    with st.sidebar:
        st.title("CodeSage")
        apply_pending_source_mode(state)
        st.subheader("Choose your source")
        routes = SOURCE_ROUTES
        stored_document = state.get(SOURCE_KEY)
        origin_route = {
            "pasted": "Paste code",
            "uploaded": "Upload .py file",
            "github": "Public GitHub .py URL",
            "example": EXAMPLE_MODE,
        }
        remembered_route = state.get(SOURCE_ROUTE_MEMORY_KEY)
        if remembered_route not in routes and stored_document is not None:
            remembered_route = origin_route[stored_document.origin.value]
        if remembered_route not in routes:
            remembered_route = "Paste code"
        mode = st.radio(
            "Source input",
            routes,
            index=None if SOURCE_MODE_KEY in state else routes.index(remembered_route),
            key=SOURCE_MODE_KEY,
            label_visibility="collapsed",
        )
        mode = mode or remembered_route
        state[SOURCE_ROUTE_MEMORY_KEY] = mode
        document: SourceDocument | None = None
        try:
            if mode == "Paste code":
                initial_source = (
                    stored_document.text
                    if stored_document is not None and stored_document.origin.value == "pasted"
                    else ""
                )
                source = st.text_area(
                    "Python source (paste your code here)",
                    value=initial_source,
                    height=190,
                    max_chars=SOURCE_CHARACTER_LIMIT,
                    placeholder="Paste a complete Python script here…",
                    help=f"Maximum {SOURCE_CHARACTER_LIMIT:,} characters.",
                )
                document = normalise_pasted_source(source) if source else None
            elif mode == "Upload .py file":
                upload = st.file_uploader("Upload one Python file", type=["py"])
                if upload is not None:
                    document = normalise_uploaded_file(upload.name, upload.getvalue())
                elif stored_document is not None and stored_document.origin.value == "uploaded":
                    document = stored_document
            elif mode == "Public GitHub .py URL":
                initial_url = (
                    stored_document.external_reference
                    if stored_document is not None and stored_document.origin.value == "github"
                    else ""
                )
                with st.container(key="github_url_loader"):
                    github_url = st.text_input(
                        "Public GitHub .py file URL",
                        value=initial_url,
                        placeholder="https://github.com/owner/repo/blob/ref/path/file.py",
                    )
                    st.caption("Paste a public GitHub .py URL, then select Load GitHub file.")
                    loaded_document = state.get("github_source_document")
                    if (
                        loaded_document is not None
                        and loaded_document.external_reference != github_url
                    ):
                        state.pop("github_source_document", None)
                        loaded_document = None
                    if st.button("Load GitHub file"):
                        loaded_document = fetch_github_source(github_url)
                        state["github_source_document"] = loaded_document
                document = loaded_document
            else:
                stored_example = (
                    stored_document is not None and stored_document.origin.value == "example"
                )
                if state.get(EXAMPLE_LOADED_KEY) or stored_example or mode == EXAMPLE_MODE:
                    document = normalise_example_source()
                    state[EXAMPLE_LOADED_KEY] = True
                    st.success("✓ Built-in example loaded")
        except SourceIngestionError as error:
            st.error(error.message)
            document = None

        invalidate_stale_state(state, document)
        if document is not None:
            state[SOURCE_KEY] = document
            st.divider()
            st.caption("Active source")
            st.text(document.display_name)
            st.caption(source_summary(document))
        return document


def main() -> None:
    st.set_page_config(
        page_title="CodeSage",
        page_icon="🧭",
        layout="wide",
        initial_sidebar_state="expanded",
    )
    st.html(APP_STYLES)
    st.html(PAGE_TOP_ANCHOR)
    if st.session_state.get(PRINT_MODE_KEY):
        if render_print_report(st.session_state):
            return
    document = render_sidebar(st.session_state)
    if document is None:
        render_landing(st.session_state)
        render_requested_scroll(st.session_state)
        return
    if ANALYSIS_KEY not in st.session_state:
        render_ready_to_analyse(document, st.session_state)
        render_requested_scroll(st.session_state)
        return
    render_workspace_header(document, st.session_state)
    render_workflow(st.session_state)
    render_workspace(document, st.session_state)
    render_requested_scroll(st.session_state)


if __name__ == "__main__":
    main()
