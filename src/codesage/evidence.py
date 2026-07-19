"""Stable deterministic evidence supplied to the review model."""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from codesage.models import AnalysisResult, AnalysedUnit
from codesage.thresholds import (
    COMPLEX_BOOLEAN_LEAVES,
    DEEP_NESTING_DEPTH,
    EXCESSIVE_TOP_LEVEL_STATEMENTS,
    HIGH_COMPLEXITY,
    LONG_FUNCTION_SLOC,
    OVERSIZED_PROCEDURAL_SLOC,
    TOO_MANY_PARAMETERS,
)

PROMPT_VERSION = "script-review-v1"
GROUNDING_VERSION = "deterministic-evidence-v1"

THRESHOLDS = {
    "complex_boolean_leaves": COMPLEX_BOOLEAN_LEAVES,
    "deep_nesting_depth": DEEP_NESTING_DEPTH,
    "excessive_top_level_statements": EXCESSIVE_TOP_LEVEL_STATEMENTS,
    "high_complexity": HIGH_COMPLEXITY,
    "long_function_sloc": LONG_FUNCTION_SLOC,
    "oversized_procedural_sloc": OVERSIZED_PROCEDURAL_SLOC,
    "too_many_parameters": TOO_MANY_PARAMETERS,
}


@dataclass(frozen=True, slots=True)
class EvidenceItem:
    evidence_id: str
    source_reference: str
    fact: str
    value: Any


@dataclass(frozen=True, slots=True)
class EvidencePackage:
    prompt_version: str
    grounding_version: str
    thresholds: tuple[tuple[str, int], ...]
    items: tuple[EvidenceItem, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def source_reference(unit: AnalysedUnit) -> str:
    return f"{unit.key}@L{unit.line}-L{unit.end_line}"


def build_evidence_package(analysis: AnalysisResult) -> EvidencePackage:
    """Create deterministically ordered, uniquely identified review evidence."""
    facts: list[tuple[str, str, Any]] = []
    for unit in sorted(analysis.units, key=lambda item: (item.line, item.key)):
        reference = source_reference(unit)
        measurements = (
            ("unit.kind", unit.kind.value),
            ("unit.sloc", unit.sloc),
            ("unit.statement_count", unit.statement_count),
            ("unit.complexity", unit.complexity),
            ("unit.complexity_rank", unit.complexity_rank),
            ("unit.nesting_depth", unit.nesting_depth),
            ("unit.parameter_count", unit.parameter_count),
        )
        facts.extend((reference, name, value) for name, value in measurements)
        for smell in unit.smells:
            facts.append(
                (
                    reference,
                    f"smell.{smell.code}",
                    {"severity": smell.severity.value, "message": smell.message},
                )
            )
    for definition in sorted(analysis.classes, key=lambda item: (item.line, item.key)):
        reference = f"{definition.key}@L{definition.line}-L{definition.end_line}"
        facts.extend(
            (
                (reference, "class.qualified_name", definition.qualified_name),
                (reference, "class.bases", definition.bases),
                (reference, "class.keywords", definition.keywords),
                (reference, "class.decorators", definition.decorators),
            )
        )
    for position, hotspot in enumerate(analysis.hotspots, start=1):
        facts.append(
            (
                source_reference(hotspot),
                "hotspot.selection_position",
                position,
            )
        )
    items = tuple(
        EvidenceItem(f"E{index:04d}", reference, fact, value)
        for index, (reference, fact, value) in enumerate(facts, start=1)
    )
    return EvidencePackage(
        prompt_version=PROMPT_VERSION,
        grounding_version=GROUNDING_VERSION,
        thresholds=tuple(sorted(THRESHOLDS.items())),
        items=items,
    )
