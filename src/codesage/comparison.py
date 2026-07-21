"""Static comparison of original and candidate script analysis."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from codesage.models import AnalysisResult, AnalysedUnit, ImportDefinition, Severity


class DirectionalStatus(StrEnum):
    IMPROVED = "improved"
    REGRESSED = "regressed"
    UNCHANGED = "unchanged"
    UNRESOLVED = "unresolved"


class DescriptiveStatus(StrEnum):
    INCREASED = "increased"
    DECREASED = "decreased"
    UNCHANGED = "unchanged"
    UNRESOLVED = "unresolved"


class StructuralStatus(StrEnum):
    ADDED = "added"
    REMOVED = "removed"
    CHANGED = "changed"
    UNCHANGED = "unchanged"
    UNRESOLVED = "unresolved"


@dataclass(frozen=True, slots=True)
class MetricComparison:
    qualified_name: str
    metric: str
    before: int | None
    after: int | None
    status: DirectionalStatus | DescriptiveStatus


@dataclass(frozen=True, slots=True)
class StructuralChange:
    category: str
    name: str
    status: StructuralStatus


@dataclass(frozen=True, slots=True)
class ScriptComparison:
    directional: tuple[MetricComparison, ...]
    descriptive: tuple[MetricComparison, ...]
    structural: tuple[StructuralChange, ...]
    smells_introduced: tuple[str, ...]
    smells_removed: tuple[str, ...]
    warnings: tuple[str, ...]


def _direction(before: int | None, after: int | None) -> DirectionalStatus:
    if before is None or after is None:
        return DirectionalStatus.UNRESOLVED
    if after < before:
        return DirectionalStatus.IMPROVED
    if after > before:
        return DirectionalStatus.REGRESSED
    return DirectionalStatus.UNCHANGED


def _description(before: int | None, after: int | None) -> DescriptiveStatus:
    if before is None or after is None:
        return DescriptiveStatus.UNRESOLVED
    if after > before:
        return DescriptiveStatus.INCREASED
    if after < before:
        return DescriptiveStatus.DECREASED
    return DescriptiveStatus.UNCHANGED


def _symbol_units(analysis: AnalysisResult) -> dict[str, AnalysedUnit]:
    return {
        unit.qualified_name: unit for unit in analysis.units if unit.qualified_name != "<module>"
    }


def _import_names(imports: tuple[ImportDefinition, ...]) -> set[str]:
    return {f"{item.module}:{name}" for item in imports for name in item.names}


def _unit_fingerprint(unit: AnalysedUnit) -> tuple[object, ...]:
    return (
        unit.kind,
        unit.definition_kind,
        unit.method_kind,
        unit.decorators,
        unit.signature,
    )


def _class_fingerprint(item: object) -> tuple[object, ...]:
    return (item.bases, item.keywords, item.decorators)  # type: ignore[attr-defined]


def compare_scripts(original: AnalysisResult, candidate: AnalysisResult) -> ScriptComparison:
    """Compare exact qualified names only; never infer renames or equivalence."""
    before_units = _symbol_units(original)
    after_units = _symbol_units(candidate)
    directional: list[MetricComparison] = []
    descriptive: list[MetricComparison] = []
    structural: list[StructuralChange] = []
    warnings: list[str] = []

    for name in sorted(before_units):
        before = before_units[name]
        after = after_units.get(name)
        for metric in ("complexity", "nesting_depth"):
            before_value = getattr(before, metric)
            after_value = getattr(after, metric) if after is not None else None
            directional.append(
                MetricComparison(
                    name, metric, before_value, after_value, _direction(before_value, after_value)
                )
            )
        before_smells = len(before.smells)
        after_smells = len(after.smells) if after is not None else None
        directional.append(
            MetricComparison(
                name,
                "smell_count",
                before_smells,
                after_smells,
                _direction(before_smells, after_smells),
            )
        )
        for severity in (Severity.HIGH, Severity.MEDIUM):
            before_count = sum(smell.severity is severity for smell in before.smells)
            after_count = (
                sum(smell.severity is severity for smell in after.smells)
                if after is not None
                else None
            )
            directional.append(
                MetricComparison(
                    name,
                    f"{severity.value}_severity_smell_count",
                    before_count,
                    after_count,
                    _direction(before_count, after_count),
                )
            )
        before_codes = {smell.code for smell in before.smells}
        after_codes = {smell.code for smell in after.smells} if after is not None else set()
        for code in sorted(before_codes | after_codes):
            after_presence = int(code in after_codes) if after is not None else None
            directional.append(
                MetricComparison(
                    name,
                    f"smell.{code}",
                    int(code in before_codes),
                    after_presence,
                    _direction(int(code in before_codes), after_presence),
                )
            )
        for metric in ("sloc", "statement_count", "parameter_count", "length"):
            if metric == "length":
                before_value = before.end_line - before.line + 1
                after_value = after.end_line - after.line + 1 if after is not None else None
            else:
                before_value = getattr(before, metric)
                after_value = getattr(after, metric) if after is not None else None
            descriptive.append(
                MetricComparison(
                    name, metric, before_value, after_value, _description(before_value, after_value)
                )
            )
        if after is None:
            warnings.append(
                f"{name} is absent under the same qualified name; metric comparisons are unresolved."
            )
        else:
            status = (
                StructuralStatus.UNCHANGED
                if before.signature == after.signature
                else StructuralStatus.CHANGED
            )
            structural.append(StructuralChange("signature", name, status))
            if status is StructuralStatus.CHANGED:
                before_codes = {smell.code for smell in before.smells}
                after_codes = {smell.code for smell in after.smells}
                if "mutable_default" in before_codes - after_codes:
                    warnings.append(
                        f"A default value in `{name}` changed from a shared mutable value to a "
                        "non-mutable sentinel. Test callers that may depend on state being retained "
                        "between calls."
                    )
                else:
                    warnings.append(
                        f"`{name}` has a changed signature. Test callers that depend on the "
                        "previous interface."
                    )
            before_identity = _unit_fingerprint(before)[:-1]
            after_identity = _unit_fingerprint(after)[:-1]
            if before_identity != after_identity:
                warnings.append(
                    f"{name} has changed structural identity; metric comparability is limited."
                )

    before_function_count = sum(unit.kind.value == "function" for unit in before_units.values())
    after_function_count = sum(unit.kind.value == "function" for unit in after_units.values())
    script_counts = (
        ("physical_lines", original.physical_lines, candidate.physical_lines),
        ("sloc", original.sloc, candidate.sloc),
        ("import_count", len(original.imports), len(candidate.imports)),
        ("function_count", before_function_count, after_function_count),
        ("class_count", len(original.classes), len(candidate.classes)),
    )
    descriptive.extend(
        MetricComparison("<script>", metric, before, after, _description(before, after))
        for metric, before, after in script_counts
    )

    for category, before_names, after_names in (
        ("import", _import_names(original.imports), _import_names(candidate.imports)),
    ):
        for name in sorted(before_names | after_names):
            if name not in before_names:
                status = StructuralStatus.ADDED
            elif name not in after_names:
                status = StructuralStatus.REMOVED
            else:
                status = StructuralStatus.UNCHANGED
            structural.append(StructuralChange(category, name, status))

    for name in sorted(set(before_units) | set(after_units)):
        before = before_units.get(name)
        after = after_units.get(name)
        category = (after or before).kind.value  # type: ignore[union-attr]
        if before is None:
            status = StructuralStatus.ADDED
        elif after is None:
            status = StructuralStatus.REMOVED
        elif _unit_fingerprint(before) != _unit_fingerprint(after):
            status = StructuralStatus.CHANGED
        else:
            status = StructuralStatus.UNCHANGED
        structural.append(StructuralChange(category, name, status))

    before_classes = {item.qualified_name: item for item in original.classes}
    after_classes = {item.qualified_name: item for item in candidate.classes}
    for name in sorted(set(before_classes) | set(after_classes)):
        before = before_classes.get(name)
        after = after_classes.get(name)
        if before is None:
            status = StructuralStatus.ADDED
        elif after is None:
            status = StructuralStatus.REMOVED
        elif _class_fingerprint(before) != _class_fingerprint(after):
            status = StructuralStatus.CHANGED
            warnings.append(
                f"{name} has changed class structure; runtime compatibility is not established."
            )
        else:
            status = StructuralStatus.UNCHANGED
        structural.append(StructuralChange("class", name, status))

    comparable_names = set(before_units) & set(after_units)
    before_smells = {
        f"{unit.qualified_name}:{smell.code}"
        for unit in original.units
        if unit.qualified_name in comparable_names or unit.qualified_name == "<module>"
        for smell in unit.smells
    }
    after_smells = {
        f"{unit.qualified_name}:{smell.code}"
        for unit in candidate.units
        if unit.qualified_name in comparable_names or unit.qualified_name == "<module>"
        for smell in unit.smells
    }
    return ScriptComparison(
        directional=tuple(directional),
        descriptive=tuple(descriptive),
        structural=tuple(structural),
        smells_introduced=tuple(sorted(after_smells - before_smells)),
        smells_removed=tuple(sorted(before_smells - after_smells)),
        warnings=tuple(warnings),
    )
