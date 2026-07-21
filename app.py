"""CodeSage Streamlit entry point for bounded single-script review."""

from __future__ import annotations

from collections import Counter
from dataclasses import asdict
from datetime import datetime
from difflib import unified_diff

import streamlit as st

from codesage.ai import CorrectionStatus, review_allows_refactor
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
    ANALYSIS_KEY,
    EXAMPLE_MODE,
    REFACTOR_ERROR_KEY,
    REFACTOR_INSTRUCTIONS_KEY,
    REFACTOR_KEY,
    REVIEW_ERROR_KEY,
    REVIEW_KEY,
    SOURCE_KEY,
    SOURCE_MODE_KEY,
    SOURCE_CHARACTER_LIMIT,
    analysis_summary,
    failure_message,
    handle_actions,
    handle_refactor_action,
    invalidate_stale_state,
    load_example,
    metric_rows,
    readable_outcome,
    readable_smell,
    readable_source_reference,
    refactor_action_label,
    refactor_outcome_summary,
    source_summary,
    structural_rows,
    unit_inventory_rows,
    unit_measurements,
    workflow_statuses,
)

PRINT_MODE_KEY = "print_friendly_report"
SOURCE_ROUTE_MEMORY_KEY = "source_route_memory"
APP_STYLES = """
<style>
  [data-testid="stAppViewContainer"] { background: #f3f6fa; }
  [data-testid="stSidebar"] {
    background: #f8fafc;
    border-right: 1px solid #dbe3ee;
  }
  [data-testid="stSidebar"] h1,
  [data-testid="stSidebar"] h2,
  [data-testid="stSidebar"] h3,
  [data-testid="stSidebar"] p,
  [data-testid="stSidebar"] label { color: #172033; }
  [data-testid="stSidebar"] input,
  [data-testid="stSidebar"] textarea { color: #172033; }
  [data-testid="stVerticalBlockBorderWrapper"] {
    background: #ffffff;
    border-radius: 0.55rem;
  }
  .severity-badge {
    display: inline-block;
    border-radius: 999px;
    font-size: 0.76rem;
    font-weight: 700;
    letter-spacing: 0.025em;
    padding: 0.2rem 0.55rem;
    margin-bottom: 0.35rem;
  }
  .severity-high { background: #ffedd5; color: #9a3412; border: 1px solid #fdba74; }
  .severity-medium { background: #fef3c7; color: #854d0e; border: 1px solid #fcd34d; }
  .severity-low { background: #dbeafe; color: #1e40af; border: 1px solid #93c5fd; }
  .status-label { font-size: 0.78rem; font-weight: 700; }
  .status-improved, .status-addressed { color: #166534; }
  .status-trade-off, .status-partially-addressed { color: #92400e; }
  .status-not-comparable, .status-unchanged { color: #475569; }
  .st-key-print_report { max-width: 920px; margin: 0 auto; }
  @media print {
    [data-testid="stSidebar"],
    [data-testid="stHeader"],
    [data-testid="stToolbar"],
    [data-testid="stMainMenu"],
    [data-testid="stButton"],
    [data-testid="stTabs"],
    [data-testid="stTextInput"],
    [data-testid="stTextArea"],
    [data-testid="stFileUploader"],
    [data-testid="stRadio"],
    .st-key-landing_workspace,
    .st-key-ready_workspace,
    .st-key-screen_controls,
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


def render_priority_hotspots(analysis: AnalysisResult, *, limit: int | None = None) -> None:
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
            metric_values = (
                ("Nesting depth", measurements["Nesting depth"]),
                ("Complexity", measurements["Complexity"]),
                ("Complexity rank", measurements["Complexity rank"]),
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
    with st.expander(f"Analysable units ({len(inventory)})", expanded=False):
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
    with st.expander("Configured thresholds", expanded=False):
        st.caption("These are configurable product defaults, not universal laws.")
        st.dataframe(
            thresholds,
            hide_index=True,
            width="stretch",
            height=_table_height(thresholds, bounded_height=320),
        )

    with st.expander(
        f"Warnings ({len(analysis.analysis_warnings)})",
        expanded=bool(analysis.analysis_warnings),
    ):
        if not analysis.analysis_warnings:
            st.write("None.")
        for warning in analysis.analysis_warnings:
            st.warning(warning)

    with st.expander("Exclusions (0)", expanded=False):
        st.write("No exclusions apply to this Python script.")

    with st.expander("Technical details", expanded=False):
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
    st.markdown("### Workflow")
    st.caption("1 Analyse code  →  2 AI review  →  3 Suggested refactor")
    labels = ("1 · Analyse code", "2 · AI review", "3 · Suggested refactor")
    statuses = workflow_statuses(state)
    if compact:
        for label, status in zip(labels, statuses, strict=True):
            st.markdown(f"**{label}:** {status}")
        return
    for column, label, status in zip(
        st.columns(3),
        labels,
        statuses,
        strict=True,
    ):
        with column:
            st.markdown(f"**{label}**")
            st.caption(status)


def refresh_workflow(workflow_slot, state, *, compact: bool = False) -> None:
    """Refresh the fixed-position workflow indicator after an explicit action."""
    workflow_slot.empty()
    with workflow_slot.container():
        render_workflow(state, compact=compact)


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


def render_refactor(refactor, original_source: str, *, print_mode: bool = False) -> None:
    if not refactor.succeeded or refactor.suggested_refactor is None:
        return
    verification = refactor.verification
    if verification is None or verification.analysis is None or verification.comparison is None:
        return
    st.subheader("Suggested refactor")
    if refactor.correction_status is CorrectionStatus.SUCCEEDED:
        st.info("CodeSage needed one extra attempt to produce verifiable Python.")
    st.caption(
        "CodeSage verified that this is valid Python and that the required static definitions "
        "were preserved. Static checks do not prove runtime behaviour or equivalence."
    )
    outcome_summary = refactor_outcome_summary(refactor)
    comparison = verification.comparison
    targets = verification.target_names
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
    structural_counts = Counter(item.status.value for item in comparison.structural)
    st.caption(
        f"Static structure: {structural_counts['changed']} changed · "
        f"{structural_counts['unchanged']} unchanged · "
        f"{structural_counts['added']} added · {structural_counts['removed']} removed · "
        f"{structural_counts['unresolved']} unresolved"
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

    st.markdown("### Changed hotspot")
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
        st.markdown("### Re-run your safety checks")
        st.write(
            "CodeSage has checked the refactor statically but has not executed it. Run the same "
            "checks against the refactored code and compare the results."
        )
    else:
        with st.expander("View complete files", expanded=False):
            code_comparison()
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
    with st.expander("Complete structural changes", expanded=False):
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


def refresh_refactor_action(action_slot, state, initial_label: str) -> None:
    """Replace the just-used generation action after verified state changes."""
    if refactor_action_label(state) == initial_label:
        return
    action_slot.empty()
    action_slot.button("Try a different refactor", type="primary", key="try_different_refactor")


def current_stage(state) -> str:
    if REFACTOR_KEY in state:
        return "Suggested refactor"
    if REVIEW_KEY in state:
        return "AI review"
    if ANALYSIS_KEY in state:
        return "Analysis complete"
    return "Ready to analyse"


def _analysis_totals(analysis: AnalysisResult) -> tuple[int, int]:
    hotspot_count = sum(bool(unit.smells) for unit in analysis.units)
    finding_count = sum(len(unit.smells) for unit in analysis.units)
    return hotspot_count, finding_count


def _table_height(rows, *, bounded_height: int, content_limit: int = 12) -> int | str:
    """Size small tables to their content and bound larger result sets."""
    return "content" if len(rows) <= content_limit else bounded_height


def render_landing(state) -> None:
    """Render the deliberate first-load workspace without result navigation."""
    with st.container(key="landing_workspace"):
        introduction, journey = st.columns([1.15, 1], gap="large")
        with introduction:
            st.title("CodeSage")
            st.subheader("Your Python maintainability coach")
            st.write(
                "CodeSage finds maintainability hotspots, explains the evidence behind them, "
                "and helps you explore focused refactors."
            )
            st.markdown("**Static analysis only. CodeSage never executes your code.**")
            st.button(
                "Load built-in example",
                type="primary",
                use_container_width=True,
                on_click=load_example,
                args=(state,),
            )
            st.caption(
                "Prefer your own code? Select a complete Python script from another source route "
                "in the sidebar."
            )
        with journey:
            with st.container(border=True):
                st.subheader("How CodeSage helps")
                st.markdown("**1. Analyse**")
                st.write("Measure complexity, nesting and maintainability smells.")
                st.markdown("**2. Understand**")
                st.write("See why the measured findings matter.")
                st.markdown("**3. Refactor**")
                st.write("Explore a focused change and inspect the trade-offs.")

        value_cards = (
            (
                "Find hotspots",
                "Prioritise measured structure that crosses CodeSage's configured thresholds.",
            ),
            (
                "Understand why",
                "Connect each explanation to a code location and deterministic evidence.",
            ),
            (
                "Refactor carefully",
                "Inspect a focused suggestion, static changes and explicit limitations.",
            ),
        )
        for column, (title, description) in zip(st.columns(3), value_cards, strict=True):
            with column:
                with st.container(border=True):
                    st.markdown(f"### {title}")
                    st.write(description)


def render_ready_to_analyse(document: SourceDocument, state) -> None:
    """Render a source preview and the single deterministic-analysis action."""
    with st.container(key="ready_workspace"):
        st.title("CodeSage")
        st.subheader("Your Python maintainability coach")
        st.caption("Static analysis only. CodeSage never executes your code.")
        preview, action = st.columns([3, 2], gap="large")
        with preview:
            with st.container(border=True):
                st.markdown("### Active source")
                st.text(document.display_name)
                st.caption(source_summary(document))
                st.code(document.text, language="python", height=360)
        with action:
            with st.container(border=True):
                st.markdown("### Ready to analyse")
                st.write("CodeSage will measure:")
                st.markdown(
                    "- cyclomatic complexity\n"
                    "- nesting depth\n"
                    "- function and method structure\n"
                    "- threshold-based maintainability smells"
                )
                st.button(
                    "Analyse code",
                    type="primary",
                    use_container_width=True,
                    on_click=handle_actions,
                    args=(state, document),
                    kwargs={"analyse_clicked": True, "review_clicked": False},
                )


def _ai_review_status(document: SourceDocument, state) -> str:
    analysis = state[ANALYSIS_KEY]
    if REVIEW_KEY in state:
        return "Complete"
    if analysis.syntax_valid and document.ai_eligible:
        return "Available"
    return "Unavailable"


def render_workspace_header(document: SourceDocument, state) -> None:
    """Render the compact post-analysis identity and status strip."""
    analysis = state[ANALYSIS_KEY]
    hotspot_count, finding_count = _analysis_totals(analysis)
    identity, report_action = st.columns([5, 1], gap="medium")
    with identity:
        st.title("CodeSage")
        st.caption(f"Active source: {document.display_name}")
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


def render_stage_action(document: SourceDocument, state) -> None:
    """Render the one primary action currently available after analysis."""
    analysis = state[ANALYSIS_KEY]
    review = state.get(REVIEW_KEY)
    if not analysis.syntax_valid:
        st.warning("Fix the syntax error in the selected source, then analyse it again.")
    elif not document.ai_eligible:
        st.info("This script is available for deterministic analysis only.")
    elif review is None:
        with st.container(border=True):
            st.write(
                "Your complete eligible source and measured results will be sent to OpenAI only "
                "when you select Get AI review. The AI must base its findings on this evidence "
                "and reference the relevant code locations. This request explains findings and "
                "does not rewrite your code."
            )
            action_slot = st.empty()
            if action_slot.button("Get AI review", type="primary"):
                with st.spinner("Getting AI maintainability review…"):
                    action_error = handle_actions(
                        state,
                        document,
                        analyse_clicked=False,
                        review_clicked=True,
                    )
                if action_error:
                    st.error(action_error)
                elif REVIEW_KEY in state:
                    action_slot.empty()
                    st.rerun()
    elif review_allows_refactor(review):
        with st.container(border=True):
            st.write(
                "Generating a refactor makes a separate OpenAI request. CodeSage rewrites only "
                "the selected hotspot and does not execute the result."
            )
            optional_instructions = st.text_area(
                "Optional instructions",
                key=REFACTOR_INSTRUCTIONS_KEY,
                max_chars=500,
                help="Describe a preference such as keeping the change as small as practical.",
            )
            initial_label = refactor_action_label(state)
            action_slot = st.empty()
            if action_slot.button(
                initial_label,
                type="primary",
                key=(
                    "try_different_refactor"
                    if REFACTOR_KEY in state
                    else "generate_suggested_refactor"
                ),
            ):
                with st.spinner("Generating and checking the suggested refactor…"):
                    action_error = handle_refactor_action(
                        state,
                        document,
                        refactor_clicked=True,
                        optional_instructions=optional_instructions,
                        on_correction_start=lambda _: st.info(
                            "The first generated version could not be verified. CodeSage is "
                            "trying once more to produce valid Python."
                        ),
                    )
                if action_error:
                    st.error(action_error)
            refresh_refactor_action(action_slot, state, initial_label)
    else:
        st.info("This AI review does not recommend generating a refactor.")

    review_error = state.get(REVIEW_ERROR_KEY)
    if review_error is not None:
        st.error(failure_message(review_error.error_code))
    refactor_error = state.get(REFACTOR_ERROR_KEY)
    if refactor_error is not None:
        st.error(failure_message(refactor_error.error_code))


def render_overview(document: SourceDocument | None, state) -> None:
    analysis = state.get(ANALYSIS_KEY)
    if document is None or analysis is None:
        st.info("Choose or load a Python script, then select Analyse code in the workspace.")
        return
    hotspot_count, static_findings = _analysis_totals(analysis)
    if not analysis.syntax_valid:
        ai_eligibility = "Unavailable"
    elif document.ai_eligible:
        ai_eligibility = "Available"
    else:
        ai_eligibility = "Deterministic only"
    values = (
        ("Active source", document.display_name),
        ("Syntax", "Valid" if analysis.syntax_valid else "Invalid"),
        ("Hotspots", hotspot_count),
        ("Static findings", static_findings),
        ("AI eligibility", ai_eligibility),
        ("Current stage", current_stage(state)),
    )
    for start in range(0, len(values), 3):
        for column, (label, value) in zip(st.columns(3), values[start : start + 3], strict=True):
            column.metric(label, value)
    if not analysis.syntax_valid:
        failure = analysis.syntax_failure
        st.error(failure.message if failure is not None else "The script contains invalid syntax.")
        return
    render_priority_hotspots(analysis, limit=1)


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
        with st.expander(f"Evidence references ({len(rows)})", expanded=False):
            st.dataframe(
                rows,
                hide_index=True,
                width="stretch",
                height=_table_height(rows, bounded_height=420),
            )


def render_workspace(document: SourceDocument | None, state) -> None:
    analysis = state.get(ANALYSIS_KEY)
    if analysis is None:
        return
    review = state.get(REVIEW_KEY)
    refactor = state.get(REFACTOR_KEY)
    overview_tab, review_tab, refactor_tab, technical_tab = st.tabs(
        ("Overview", "AI review", "Suggested refactor", "Technical details")
    )
    with overview_tab:
        render_overview(document, state)
    with review_tab:
        if review is None:
            st.info("Select Get AI review above when you are ready for an evidence-based review.")
        else:
            render_review(review)
    with refactor_tab:
        if refactor is None:
            st.info(
                "A verified suggested refactor will appear here when the AI review recommends "
                "one and you explicitly request it above."
            )
        elif document is not None:
            render_refactor(refactor, document.text)
    with technical_tab:
        if analysis is None:
            st.info("Technical analysis details become available after Analyse code.")
        else:
            render_analysis_technical(analysis)
            render_review_evidence_technical(review)
            if refactor is not None:
                render_comparison_technical(refactor)


def set_print_mode(state, enabled: bool) -> None:
    if enabled:
        state[PRINT_MODE_KEY] = True
    else:
        state.pop(PRINT_MODE_KEY, None)


def render_print_report(state, *, timestamp: datetime | None = None) -> bool:
    """Render one linear report; return False when the user requests app mode."""
    document = state.get(SOURCE_KEY)
    analysis = state.get(ANALYSIS_KEY)
    review = state.get(REVIEW_KEY)
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
        render_priority_hotspots(analysis, limit=1)
        if review is not None:
            render_review(review, print_mode=True)
        else:
            st.info("No AI review was requested for this report.")
        if refactor is not None:
            render_refactor(refactor, document.text, print_mode=True)
        else:
            st.info("No verified suggested refactor is available for this report.")
    return True


def render_sidebar(state) -> SourceDocument | None:
    with st.sidebar:
        st.title("CodeSage")
        st.caption("Source panel")
        routes = ("Paste code", "Upload .py file", "Public GitHub .py URL", EXAMPLE_MODE)
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
            index=routes.index(remembered_route),
            key=SOURCE_MODE_KEY,
        )
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
                    "Python source",
                    value=initial_source,
                    height=190,
                    max_chars=SOURCE_CHARACTER_LIMIT,
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
                github_url = st.text_input(
                    "Public GitHub .py file URL",
                    value=initial_url,
                    placeholder="https://github.com/owner/repo/blob/ref/path/file.py",
                )
                loaded_document = state.get("github_source_document")
                if loaded_document is not None and loaded_document.external_reference != github_url:
                    state.pop("github_source_document", None)
                    loaded_document = None
                if st.button("Load GitHub file"):
                    loaded_document = fetch_github_source(github_url)
                    state["github_source_document"] = loaded_document
                document = loaded_document
            else:
                document = normalise_example_source()
        except SourceIngestionError as error:
            st.error(error.message)
            document = None

        invalidate_stale_state(state, document)
        if document is not None:
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
    if st.session_state.get(PRINT_MODE_KEY):
        if render_print_report(st.session_state):
            return
    document = render_sidebar(st.session_state)
    if document is None:
        render_landing(st.session_state)
        return
    if ANALYSIS_KEY not in st.session_state:
        render_ready_to_analyse(document, st.session_state)
        return
    render_workspace_header(document, st.session_state)
    render_stage_action(document, st.session_state)
    render_workspace(document, st.session_state)


if __name__ == "__main__":
    main()
