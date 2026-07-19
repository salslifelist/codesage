"""Deterministic Python script analysis. Source is parsed, never executed."""

from __future__ import annotations

import ast
import hashlib
import io
import tokenize
from collections.abc import Iterable

from radon.complexity import cc_rank, cc_visit

from codesage.models import (
    AnalysedUnit,
    AnalysisResult,
    ClassDefinition,
    ImportDefinition,
    Severity,
    Smell,
    SyntaxFailure,
    UnitKind,
)
from codesage.thresholds import (
    COMPLEX_BOOLEAN_LEAVES,
    DEEP_NESTING_DEPTH,
    EXCESSIVE_TOP_LEVEL_STATEMENTS,
    HIGH_COMPLEXITY,
    LONG_FUNCTION_SLOC,
    OVERSIZED_PROCEDURAL_SLOC,
    TOO_MANY_PARAMETERS,
)

NO_HOTSPOTS = "NO_HOTSPOTS_ABOVE_THRESHOLDS"
HOTSPOTS_FOUND = "HOTSPOTS_FOUND"
SYNTAX_ERROR = "SYNTAX_ERROR"

_NESTING_NODES = (
    ast.If,
    ast.For,
    ast.AsyncFor,
    ast.While,
    ast.With,
    ast.AsyncWith,
    ast.Try,
    ast.TryStar,
    ast.Match,
)
_DEFINITION_NODES = (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)


def _code_lines(source: str) -> set[int]:
    """Return non-blank, non-comment source lines using Python tokenisation."""
    code_lines: set[int] = set()
    ignored = {
        tokenize.ENCODING,
        tokenize.ENDMARKER,
        tokenize.INDENT,
        tokenize.DEDENT,
        tokenize.NEWLINE,
        tokenize.NL,
        tokenize.COMMENT,
    }
    try:
        tokens = tokenize.generate_tokens(io.StringIO(source).readline)
        for token in tokens:
            if token.type not in ignored:
                code_lines.update(range(token.start[0], token.end[0] + 1))
    except (IndentationError, tokenize.TokenError):
        # ast.parse supplies the user-facing syntax error. Partial tokenisation is enough
        # for document-level metadata on invalid source.
        pass
    physical_lines = source.splitlines()
    return {
        line
        for line in code_lines
        if line <= len(physical_lines) and physical_lines[line - 1].strip()
    }


def _lines_for_node(node: ast.AST, code_lines: set[int]) -> set[int]:
    end_line = getattr(node, "end_lineno", getattr(node, "lineno", 0))
    return set(range(getattr(node, "lineno", 0), end_line + 1)) & code_lines


class _FunctionCollector(ast.NodeVisitor):
    def __init__(self) -> None:
        self.scope: list[tuple[str, str]] = []
        self.functions: list[
            tuple[ast.FunctionDef | ast.AsyncFunctionDef, str, UnitKind, bool, str | None]
        ] = []
        self.classes: list[ClassDefinition] = []

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        qualified_name = ".".join([*(name for name, _ in self.scope), node.name])
        self.classes.append(
            ClassDefinition(
                key=f"class:{qualified_name}:{node.lineno}",
                qualified_name=qualified_name,
                line=node.lineno,
                end_line=node.end_lineno or node.lineno,
                bases=tuple(ast.unparse(base) for base in node.bases),
                keywords=tuple(
                    f"{keyword.arg}={ast.unparse(keyword.value)}"
                    if keyword.arg is not None
                    else f"**{ast.unparse(keyword.value)}"
                    for keyword in node.keywords
                ),
                decorators=tuple(ast.unparse(item) for item in node.decorator_list),
            )
        )
        self.scope.append((node.name, "class"))
        self.generic_visit(node)
        self.scope.pop()

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        self._visit_function(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self._visit_function(node)

    def _visit_function(self, node: ast.FunctionDef | ast.AsyncFunctionDef) -> None:
        qualified_name = ".".join([*(name for name, _ in self.scope), node.name])
        parent_kind = self.scope[-1][1] if self.scope else None
        kind = UnitKind.METHOD if parent_kind == "class" else UnitKind.FUNCTION
        method_kind: str | None = None
        if kind is UnitKind.METHOD:
            if _has_decorator(node, "staticmethod"):
                method_kind = "static"
            elif _has_decorator(node, "classmethod"):
                method_kind = "class"
            else:
                method_kind = "instance"
        exclude_receiver = kind is UnitKind.METHOD and method_kind != "static"
        self.functions.append((node, qualified_name, kind, exclude_receiver, method_kind))
        self.scope.append((node.name, "function"))
        self.generic_visit(node)
        self.scope.pop()


def _statement_count(function: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    count = 0

    def visit(node: ast.AST) -> None:
        nonlocal count
        if isinstance(node, ast.stmt):
            count += 1
        if isinstance(node, _DEFINITION_NODES):
            return
        for child in ast.iter_child_nodes(node):
            visit(child)

    for statement in function.body:
        visit(statement)
    return count


def _has_decorator(function: ast.FunctionDef | ast.AsyncFunctionDef, decorator_name: str) -> bool:
    for decorator in function.decorator_list:
        target = decorator.func if isinstance(decorator, ast.Call) else decorator
        if isinstance(target, ast.Name) and target.id == decorator_name:
            return True
        if isinstance(target, ast.Attribute) and target.attr == decorator_name:
            return True
    return False


def _nesting_depth(function: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    maximum = 0

    def visit(node: ast.AST, depth: int) -> None:
        nonlocal maximum
        if isinstance(node, _DEFINITION_NODES):
            return
        if isinstance(node, _NESTING_NODES):
            current = depth + 1
            maximum = max(maximum, current)
            if isinstance(node, ast.If):
                for child in node.body:
                    visit(child, current)
                if (
                    len(node.orelse) == 1
                    and isinstance(node.orelse[0], ast.If)
                    and node.orelse[0].col_offset == node.col_offset
                ):
                    # AST uses an If in orelse for both forms. Only a child at the
                    # same indentation as its parent is a lexical elif.
                    visit(node.orelse[0], depth)
                else:
                    for child in node.orelse:
                        visit(child, current)
                visit(node.test, current)
                return
            for child in ast.iter_child_nodes(node):
                visit(child, current)
            return
        for child in ast.iter_child_nodes(node):
            visit(child, depth)

    for statement in function.body:
        visit(statement, 0)
    return maximum


def _effective_parameter_count(
    function: ast.FunctionDef | ast.AsyncFunctionDef, *, exclude_receiver: bool
) -> int:
    arguments = function.args
    positional = [*arguments.posonlyargs, *arguments.args]
    if exclude_receiver and positional and positional[0].arg in {"self", "cls"}:
        positional = positional[1:]
    return (
        len(positional)
        + len(arguments.kwonlyargs)
        + int(arguments.vararg is not None)
        + int(arguments.kwarg is not None)
    )


def _function_signature(function: ast.FunctionDef | ast.AsyncFunctionDef) -> str:
    signature = f"({ast.unparse(function.args)})"
    if function.returns is not None:
        signature += f" -> {ast.unparse(function.returns)}"
    return signature


def _boolean_leaves(node: ast.AST) -> int:
    if isinstance(node, ast.BoolOp):
        return sum(_boolean_leaves(value) for value in node.values)
    if isinstance(node, ast.UnaryOp) and isinstance(node.op, ast.Not):
        return _boolean_leaves(node.operand)
    return 1


class _FunctionSmellVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.maximum_boolean_leaves = 0
        self.mutable_default = False
        self.bare_exception = False
        self.broad_exception = False

    def _skip_nested_definition(self, node: ast.AST) -> None:
        return None

    visit_FunctionDef = _skip_nested_definition
    visit_AsyncFunctionDef = _skip_nested_definition
    visit_ClassDef = _skip_nested_definition

    def _record_condition(self, condition: ast.AST) -> None:
        self.maximum_boolean_leaves = max(self.maximum_boolean_leaves, _boolean_leaves(condition))

    def visit_If(self, node: ast.If) -> None:
        self._record_condition(node.test)
        self.generic_visit(node)

    def visit_While(self, node: ast.While) -> None:
        self._record_condition(node.test)
        self.generic_visit(node)

    def visit_IfExp(self, node: ast.IfExp) -> None:
        self._record_condition(node.test)
        self.generic_visit(node)

    def visit_Assert(self, node: ast.Assert) -> None:
        self._record_condition(node.test)
        self.generic_visit(node)

    def visit_comprehension(self, node: ast.comprehension) -> None:
        for condition in node.ifs:
            self._record_condition(condition)
        self.generic_visit(node)

    def visit_match_case(self, node: ast.match_case) -> None:
        if node.guard is not None:
            self._record_condition(node.guard)
        self.generic_visit(node)

    def visit_ExceptHandler(self, node: ast.ExceptHandler) -> None:
        if node.type is None:
            self.bare_exception = True
        elif _contains_exception_name(node.type):
            self.broad_exception = True
        self.generic_visit(node)


def _contains_exception_name(node: ast.AST) -> bool:
    if isinstance(node, ast.Name):
        return node.id == "Exception"
    if isinstance(node, ast.Tuple):
        return any(_contains_exception_name(element) for element in node.elts)
    return False


def _is_mutable_default(node: ast.AST) -> bool:
    if isinstance(node, (ast.List, ast.Dict, ast.Set, ast.ListComp, ast.DictComp, ast.SetComp)):
        return True
    return (
        isinstance(node, ast.Call)
        and isinstance(node.func, ast.Name)
        and node.func.id
        in {
            "list",
            "dict",
            "set",
        }
    )


def _function_smells(
    function: ast.FunctionDef | ast.AsyncFunctionDef,
    *,
    sloc: int,
    complexity: int | None,
    nesting: int,
    parameters: int,
) -> tuple[Smell, ...]:
    visitor = _FunctionSmellVisitor()
    for statement in function.body:
        visitor.visit(statement)
    defaults = [*function.args.defaults, *(item for item in function.args.kw_defaults if item)]
    visitor.mutable_default = any(_is_mutable_default(item) for item in defaults)

    smells: list[Smell] = []
    if sloc > LONG_FUNCTION_SLOC:
        smells.append(Smell("long_function", Severity.HIGH, f"SLOC {sloc} > {LONG_FUNCTION_SLOC}"))
    if nesting >= DEEP_NESTING_DEPTH:
        smells.append(
            Smell(
                "deep_nesting",
                Severity.HIGH,
                f"nesting {nesting} >= {DEEP_NESTING_DEPTH}",
            )
        )
    if complexity is not None and complexity >= HIGH_COMPLEXITY:
        smells.append(
            Smell(
                "high_cyclomatic_complexity",
                Severity.HIGH,
                f"complexity {complexity} >= {HIGH_COMPLEXITY}",
            )
        )
    if parameters > TOO_MANY_PARAMETERS:
        smells.append(
            Smell(
                "too_many_parameters",
                Severity.MEDIUM,
                f"parameters {parameters} > {TOO_MANY_PARAMETERS}",
            )
        )
    if visitor.maximum_boolean_leaves >= COMPLEX_BOOLEAN_LEAVES:
        smells.append(
            Smell(
                "complex_boolean_expression",
                Severity.MEDIUM,
                f"Boolean leaves {visitor.maximum_boolean_leaves} >= {COMPLEX_BOOLEAN_LEAVES}",
            )
        )
    if visitor.mutable_default:
        smells.append(Smell("mutable_default", Severity.MEDIUM, "mutable default argument"))
    if visitor.bare_exception:
        smells.append(Smell("bare_exception", Severity.MEDIUM, "bare exception handler"))
    if visitor.broad_exception:
        smells.append(Smell("broad_exception", Severity.MEDIUM, "broad Exception handler"))
    return tuple(smells)


def _radon_complexities(source: str) -> dict[tuple[int, str], int]:
    complexities: dict[tuple[int, str], int] = {}

    def record(block: object) -> None:
        if getattr(block, "letter", None) in {"F", "M"}:
            complexities[(block.lineno, block.name)] = block.complexity  # type: ignore[attr-defined]
        for closure in getattr(block, "closures", ()):
            record(closure)

    for block in cc_visit(source):
        record(block)
    return complexities


def _complete_definition_lines(node: ast.AST, code_lines: set[int]) -> set[int]:
    start_line = getattr(node, "lineno", 0)
    decorators = getattr(node, "decorator_list", ())
    if decorators:
        start_line = min(start_line, *(decorator.lineno for decorator in decorators))
    end_line = getattr(node, "end_lineno", start_line)
    return set(range(start_line, end_line + 1)) & code_lines


def _definition_lines(node: ast.AST, code_lines: set[int]) -> set[int]:
    excluded: set[int] = set()
    for descendant in ast.walk(node):
        if isinstance(descendant, _DEFINITION_NODES):
            excluded |= _complete_definition_lines(descendant, code_lines)
    return excluded


def _is_docstring(statement: ast.stmt, index: int) -> bool:
    return (
        index == 0
        and isinstance(statement, ast.Expr)
        and isinstance(statement.value, ast.Constant)
        and isinstance(statement.value.value, str)
    )


def _procedural_module_unit(module: ast.Module, code_lines: set[int]) -> AnalysedUnit:
    qualifying: list[ast.stmt] = []
    covered_lines: set[int] = set()
    for index, statement in enumerate(module.body):
        if isinstance(statement, (ast.Import, ast.ImportFrom, *_DEFINITION_NODES)):
            continue
        if _is_docstring(statement, index):
            continue
        qualifying.append(statement)
        covered_lines |= _lines_for_node(statement, code_lines) - _definition_lines(
            statement, code_lines
        )

    sloc = len(covered_lines)
    statement_count = len(qualifying)
    smells: list[Smell] = []
    if sloc > OVERSIZED_PROCEDURAL_SLOC:
        smells.append(
            Smell(
                "oversized_procedural_module",
                Severity.HIGH,
                f"procedural SLOC {sloc} > {OVERSIZED_PROCEDURAL_SLOC}",
            )
        )
    if statement_count > EXCESSIVE_TOP_LEVEL_STATEMENTS:
        smells.append(
            Smell(
                "excessive_top_level_structure",
                Severity.HIGH,
                f"direct statements {statement_count} > {EXCESSIVE_TOP_LEVEL_STATEMENTS}",
            )
        )
    end_line = max((getattr(statement, "end_lineno", 1) for statement in module.body), default=1)
    return AnalysedUnit(
        key="module:<module>",
        kind=UnitKind.MODULE,
        qualified_name="<module>",
        line=1,
        end_line=end_line,
        sloc=sloc,
        statement_count=statement_count,
        complexity=None,
        complexity_rank=None,
        nesting_depth=None,
        parameter_count=None,
        signature=None,
        definition_kind=None,
        method_kind=None,
        decorators=(),
        smells=tuple(smells),
    )


def _import_inventory(module: ast.Module) -> tuple[ImportDefinition, ...]:
    imports: list[ImportDefinition] = []
    for node in ast.walk(module):
        if isinstance(node, ast.Import):
            module_name = ""
            names = tuple(
                alias.name if alias.asname is None else f"{alias.name} as {alias.asname}"
                for alias in node.names
            )
        elif isinstance(node, ast.ImportFrom):
            module_name = f"{'.' * node.level}{node.module or ''}"
            names = tuple(
                alias.name if alias.asname is None else f"{alias.name} as {alias.asname}"
                for alias in node.names
            )
        else:
            continue
        rendered = f"{module_name}:{','.join(names)}"
        imports.append(
            ImportDefinition(
                key=f"import:{node.lineno}:{rendered}",
                module=module_name,
                names=names,
                line=node.lineno,
            )
        )
    return tuple(sorted(imports, key=lambda item: (item.line, item.key)))


def _severity_value(smells: Iterable[Smell]) -> int:
    return max((2 if smell.severity is Severity.HIGH else 1 for smell in smells), default=0)


def _hotspot_sort_key(unit: AnalysedUnit) -> tuple[int, int, int, int, int, str]:
    # Negative numeric fields implement descending order. None complexity is lower
    # than Radon's minimum valid function score of one.
    complexity = unit.complexity if unit.complexity is not None else 0
    return (
        -_severity_value(unit.smells),
        -len({smell.code for smell in unit.smells}),
        -complexity,
        -unit.sloc,
        unit.line,
        unit.qualified_name,
    )


def analyse_script(source: str) -> AnalysisResult:
    """Analyse one Python script without importing or executing it."""
    physical_lines = len(source.splitlines())
    source_digest = hashlib.sha256(source.encode("utf-8")).hexdigest()
    code_lines = _code_lines(source)
    try:
        module = ast.parse(source)
    except SyntaxError as error:
        return AnalysisResult(
            syntax_valid=False,
            source_digest=source_digest,
            physical_lines=physical_lines,
            sloc=len(code_lines),
            classes=(),
            imports=(),
            units=(),
            hotspots=(),
            outcome=SYNTAX_ERROR,
            syntax_failure=SyntaxFailure(error.msg, error.lineno, error.offset),
        )

    collector = _FunctionCollector()
    collector.visit(module)
    complexities = _radon_complexities(source)
    units: list[AnalysedUnit] = []
    analysis_warnings: list[str] = []
    for function, qualified_name, kind, exclude_receiver, method_kind in collector.functions:
        sloc = len(_lines_for_node(function, code_lines))
        complexity = complexities.get((function.lineno, function.name))
        if complexity is None:
            analysis_warnings.append(
                "Cyclomatic complexity unresolved for "
                f"{qualified_name} at line {function.lineno}: no matching Radon result."
            )
        nesting = _nesting_depth(function)
        parameters = _effective_parameter_count(function, exclude_receiver=exclude_receiver)
        units.append(
            AnalysedUnit(
                key=f"{kind.value}:{qualified_name}:{function.lineno}",
                kind=kind,
                qualified_name=qualified_name,
                line=function.lineno,
                end_line=function.end_lineno or function.lineno,
                sloc=sloc,
                statement_count=_statement_count(function),
                complexity=complexity,
                complexity_rank=cc_rank(complexity) if complexity is not None else None,
                nesting_depth=nesting,
                parameter_count=parameters,
                signature=_function_signature(function),
                definition_kind=("async" if isinstance(function, ast.AsyncFunctionDef) else "sync"),
                method_kind=method_kind,
                decorators=tuple(ast.unparse(item) for item in function.decorator_list),
                smells=_function_smells(
                    function,
                    sloc=sloc,
                    complexity=complexity,
                    nesting=nesting,
                    parameters=parameters,
                ),
            )
        )

    units.append(_procedural_module_unit(module, code_lines))
    hotspots = tuple(sorted((unit for unit in units if unit.smells), key=_hotspot_sort_key)[:3])
    return AnalysisResult(
        syntax_valid=True,
        source_digest=source_digest,
        physical_lines=physical_lines,
        sloc=len(code_lines),
        classes=tuple(collector.classes),
        imports=_import_inventory(module),
        units=tuple(units),
        hotspots=hotspots,
        outcome=HOTSPOTS_FOUND if hotspots else NO_HOTSPOTS,
        analysis_warnings=tuple(analysis_warnings),
    )
