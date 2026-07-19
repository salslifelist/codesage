"""CodeSage Streamlit entry point for bounded single-script review."""

from __future__ import annotations

import streamlit as st

from codesage.models import AnalysisResult
from codesage.source import (
    AI_REVIEW_CHARACTER_LIMIT,
    SourceDocument,
    SourceIngestionError,
    fetch_github_source,
    normalise_pasted_source,
    normalise_uploaded_file,
)
from codesage.ui import (
    ANALYSIS_KEY,
    REVIEW_KEY,
    SOURCE_CHARACTER_LIMIT,
    failure_message,
    handle_actions,
    invalidate_stale_state,
    metric_rows,
    structural_rows,
    unit_measurements,
)


def render_analysis(analysis: AnalysisResult, *, heading: str = "Deterministic analysis") -> None:
    st.subheader(heading)
    st.write("Syntax:", "valid" if analysis.syntax_valid else "invalid")
    st.write({"Physical lines": analysis.physical_lines, "SLOC": analysis.sloc})
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
    if analysis.hotspots:
        st.write("Ordered hotspots")
        for position, hotspot in enumerate(analysis.hotspots, start=1):
            st.markdown(
                f"**{position}. {hotspot.qualified_name}** — lines "
                f"{hotspot.line}–{hotspot.end_line}"
            )
            st.write(unit_measurements(hotspot))
            for smell in hotspot.smells:
                st.write(f"{smell.code} · {smell.severity.value}: {smell.message}")
    else:
        st.info("No deterministic maintainability hotspots were found.")
    for warning in analysis.analysis_warnings:
        st.warning(warning)


def render_review(review) -> None:
    st.subheader("Grounded complete-file AI review")
    if not review.succeeded:
        st.error(failure_message(review.error_code))
        return
    response = review.response
    if response is None:
        st.error("The AI review returned no response.")
        return
    st.write("Outcome:", response.outcome.value)
    st.write(response.summary)
    for finding in response.findings:
        st.markdown(f"**{finding.title}** — {finding.priority}")
        st.write(finding.explanation)
        st.write("Recommendation:", finding.recommendation)
        st.write("Learning takeaway:", finding.learning_takeaway)
        st.write("Uncertainty:", finding.uncertainty)
        st.write("Source reference:", finding.source_reference)
        st.write("Evidence IDs:", ", ".join(finding.evidence_ids))
    if response.suggested_tests:
        st.write("Suggested tests")
        for suggested_test in response.suggested_tests:
            st.write(f"- {suggested_test}")
    if review.candidate_issue_code is not None:
        st.warning(failure_message(review.candidate_issue_code))
        return
    if response.candidate is None:
        return
    st.subheader("Complete rewritten file candidate")
    st.caption(
        "This candidate represents the complete file; unaffected source should be preserved."
    )
    st.code(response.candidate, language="python")
    verification = review.candidate_verification
    if verification is None:
        st.error("Candidate verification is unavailable.")
        return
    st.write("Candidate syntax:", "valid" if verification.syntax_valid else "invalid")
    if not verification.syntax_valid:
        st.error(verification.syntax_error or "The candidate contains invalid syntax.")
    elif verification.analysis is None or verification.comparison is None:
        st.error("Candidate analysis or comparison is unavailable.")
    else:
        render_analysis(verification.analysis, heading="Candidate deterministic analysis")
        comparison = verification.comparison
        st.write("Directional comparisons")
        st.dataframe(metric_rows(comparison.directional), use_container_width=True)
        st.write("Descriptive comparisons")
        st.dataframe(metric_rows(comparison.descriptive), use_container_width=True)
        st.write("Structural changes")
        st.dataframe(structural_rows(comparison.structural), use_container_width=True)
        st.write("Smells introduced:", list(comparison.smells_introduced))
        st.write("Smells removed:", list(comparison.smells_removed))
        for warning in comparison.warnings:
            st.warning(warning)
    st.warning(verification.non_equivalence_notice)


def main() -> None:
    st.set_page_config(page_title="CodeSage")
    st.title("CodeSage")
    st.caption("Deterministic Python maintainability analysis with optional grounded AI guidance.")
    mode = st.radio("Source input", ("Paste code", "Upload .py file", "GitHub file"))
    document: SourceDocument | None = None
    ingestion_error: str | None = None
    try:
        if mode == "Paste code":
            source = st.text_area(
                "Python source",
                height=320,
                max_chars=SOURCE_CHARACTER_LIMIT,
                help=f"Maximum {SOURCE_CHARACTER_LIMIT:,} characters. Source is never executed.",
            )
            document = normalise_pasted_source(source)
        elif mode == "Upload .py file":
            upload = st.file_uploader("Upload one Python file", type=["py"])
            if upload is not None:
                document = normalise_uploaded_file(upload.name, upload.getvalue())
        else:
            github_url = st.text_input(
                "Public GitHub .py file URL",
                placeholder="https://github.com/owner/repo/blob/ref/path/file.py",
            )
            loaded_document = st.session_state.get("github_source_document")
            if loaded_document is not None and loaded_document.external_reference != github_url:
                st.session_state.pop("github_source_document", None)
                loaded_document = None
            if st.button("Load GitHub file"):
                loaded_document = fetch_github_source(github_url)
                st.session_state["github_source_document"] = loaded_document
            document = loaded_document
    except SourceIngestionError as error:
        ingestion_error = error.message
        document = None

    invalidate_stale_state(st.session_state, document)
    if ingestion_error:
        st.error(ingestion_error)
    if document is not None:
        origin = document.origin.value
        st.caption(f"Active source: {document.display_name} ({origin})")
    analyse_clicked = st.button("Analyse script", type="primary", disabled=document is None)
    if document is None:
        return
    action_error = handle_actions(
        st.session_state,
        document,
        analyse_clicked=analyse_clicked,
        review_clicked=False,
    )
    if action_error:
        st.error(action_error)
    analysis = st.session_state.get(ANALYSIS_KEY)
    if analysis is None:
        return
    render_analysis(analysis)
    if not analysis.syntax_valid:
        return
    if len(document.text) > AI_REVIEW_CHARACTER_LIMIT:
        st.info(
            f"Complete-file AI review is unavailable above "
            f"{AI_REVIEW_CHARACTER_LIMIT:,} characters. Deterministic analysis remains available."
        )
        return
    review_clicked = st.button("Request AI review")
    action_error = None
    if review_clicked:
        with st.spinner("Requesting grounded AI review…"):
            action_error = handle_actions(
                st.session_state,
                document,
                analyse_clicked=False,
                review_clicked=True,
            )
    if action_error:
        st.error(action_error)
    review = st.session_state.get(REVIEW_KEY)
    if review is not None:
        render_review(review)


if __name__ == "__main__":
    main()
