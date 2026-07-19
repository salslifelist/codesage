"""Value objects returned by the deterministic analyser."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum


class Severity(StrEnum):
    """Ordering severity; it is not a runtime-risk or quality judgement."""

    MEDIUM = "medium"
    HIGH = "high"


class UnitKind(StrEnum):
    FUNCTION = "function"
    METHOD = "method"
    MODULE = "module"


@dataclass(frozen=True, slots=True)
class Smell:
    code: str
    severity: Severity
    message: str


@dataclass(frozen=True, slots=True)
class AnalysedUnit:
    key: str
    kind: UnitKind
    qualified_name: str
    line: int
    end_line: int
    sloc: int
    statement_count: int
    complexity: int | None
    complexity_rank: str | None
    nesting_depth: int | None
    parameter_count: int | None
    signature: str | None
    definition_kind: str | None
    method_kind: str | None
    decorators: tuple[str, ...]
    smells: tuple[Smell, ...]


@dataclass(frozen=True, slots=True)
class SyntaxFailure:
    message: str
    line: int | None
    offset: int | None


@dataclass(frozen=True, slots=True)
class ClassDefinition:
    key: str
    qualified_name: str
    line: int
    end_line: int
    bases: tuple[str, ...]
    keywords: tuple[str, ...]
    decorators: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class ImportDefinition:
    key: str
    module: str
    names: tuple[str, ...]
    line: int


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    syntax_valid: bool
    source_digest: str
    physical_lines: int
    sloc: int
    classes: tuple[ClassDefinition, ...]
    imports: tuple[ImportDefinition, ...]
    units: tuple[AnalysedUnit, ...]
    hotspots: tuple[AnalysedUnit, ...]
    outcome: str
    syntax_failure: SyntaxFailure | None = None
    analysis_warnings: tuple[str, ...] = ()
