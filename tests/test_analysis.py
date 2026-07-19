from __future__ import annotations

import hashlib
import textwrap

import pytest

import codesage.analysis as analysis_module
from codesage.analysis import HOTSPOTS_FOUND, NO_HOTSPOTS, SYNTAX_ERROR, analyse_script
from codesage.models import Severity, UnitKind
from codesage.thresholds import (
    COMPLEX_BOOLEAN_LEAVES,
    DEEP_NESTING_DEPTH,
    EXCESSIVE_TOP_LEVEL_STATEMENTS,
    HIGH_COMPLEXITY,
    LONG_FUNCTION_SLOC,
    OVERSIZED_PROCEDURAL_SLOC,
    TOO_MANY_PARAMETERS,
)


def unit(result, name):
    return next(item for item in result.units if item.qualified_name == name)


def smell_codes(item):
    return {smell.code for smell in item.smells}


def test_clean_script_returns_explicit_zero_hotspot_result():
    result = analyse_script("def add(left, right):\n    return left + right\n")

    assert result.syntax_valid
    assert result.outcome == NO_HOTSPOTS
    assert result.hotspots == ()
    assert unit(result, "add").complexity == 1
    assert (
        result.source_digest
        == hashlib.sha256(
            "def add(left, right):\n    return left + right\n".encode("utf-8")
        ).hexdigest()
    )


def test_syntax_failure_is_reported_without_units():
    result = analyse_script("def broken(:\n    pass\n")

    assert not result.syntax_valid
    assert result.outcome == SYNTAX_ERROR
    assert result.syntax_failure is not None
    assert result.syntax_failure.line == 1
    assert result.classes == ()
    assert result.units == ()
    assert (
        result.source_digest
        == hashlib.sha256("def broken(:\n    pass\n".encode("utf-8")).hexdigest()
    )


def test_sloc_does_not_count_blank_lines_inside_multiline_strings():
    result = analyse_script('message = """first\n\nsecond"""\n')

    assert result.sloc == 2


def test_qualified_functions_methods_and_effective_parameters():
    source = textwrap.dedent(
        """
        def outer(a):
            def inner(b):
                return b
            return inner(a)

        class Service:
            def method(self, a, b, c, d, e, f):
                return a

            @classmethod
            def build(cls, a, b, c, d, e):
                return cls()
        """
    )
    result = analyse_script(source)

    assert unit(result, "outer").kind is UnitKind.FUNCTION
    assert unit(result, "outer.inner").kind is UnitKind.FUNCTION
    method = unit(result, "Service.method")
    assert method.kind is UnitKind.METHOD
    assert method.parameter_count == 6
    assert "too_many_parameters" in smell_codes(method)
    assert unit(result, "Service.build").parameter_count == 5


def test_classes_are_structural_inventory_with_qualified_names_and_locations():
    source = textwrap.dedent(
        """\
        class TopLevel:
            class Nested:
                def method(self):
                    return 1

        def factory():
            class Local:
                pass
            return Local
        """
    )
    result = analyse_script(source)

    assert [definition.qualified_name for definition in result.classes] == [
        "TopLevel",
        "TopLevel.Nested",
        "factory.Local",
    ]
    top_level, nested, local = result.classes
    assert (top_level.line, top_level.end_line) == (1, 4)
    assert (nested.line, nested.end_line) == (2, 4)
    assert (local.line, local.end_line) == (7, 8)
    assert top_level.key == "class:TopLevel:1"
    assert unit(result, "TopLevel.Nested.method").kind is UnitKind.METHOD
    class_names = {definition.qualified_name for definition in result.classes}
    assert not class_names & {hotspot.qualified_name for hotspot in result.hotspots}


def test_signature_and_import_inventories_are_stable_and_complete():
    result = analyse_script(
        "import os as operating_system\n"
        "from .shared import item as shared_item\n"
        "def convert(value: int, *, flag=False) -> str:\n"
        "    import decimal\n"
        "    return str(value)\n"
    )

    assert unit(result, "convert").signature == "(value: int, *, flag=False) -> str"
    assert [(item.module, item.names, item.line) for item in result.imports] == [
        ("", ("os as operating_system",), 1),
        (".shared", ("item as shared_item",), 2),
        ("", ("decimal",), 4),
    ]


def test_radon_matches_every_supported_function_scope():
    source = textwrap.dedent(
        """
        def duplicate(value):
            if value:
                return value

        class Service:
            def duplicate(self, value):
                if value:
                    return value

        def outer():
            def duplicate(value):
                if value:
                    return value
            return duplicate

        async def asynchronous(value):
            if value:
                return value
        """
    )
    result = analyse_script(source)

    assert not result.analysis_warnings
    for name in ("duplicate", "Service.duplicate", "outer.duplicate", "asynchronous"):
        item = unit(result, name)
        assert item.complexity == 2
        assert item.complexity_rank == "A"


def test_unmatched_radon_result_is_explicitly_unresolved(monkeypatch):
    monkeypatch.setattr(analysis_module, "_radon_complexities", lambda source: {})

    result = analyse_script("def missing():\n    return 1\n")
    item = unit(result, "missing")

    assert item.complexity is None
    assert item.complexity_rank is None
    assert "complexity 1" not in " ".join(smell.message for smell in item.smells)
    assert result.analysis_warnings == (
        "Cyclomatic complexity unresolved for missing at line 1: no matching Radon result.",
    )


def test_statement_count_excludes_nested_definition_bodies():
    source = textwrap.dedent(
        """
        def outer(flag):
            value = 1
            def inner():
                first = 1
                second = 2
                return first + second
            if flag:
                value += 1
            return value
        """
    )

    assert unit(analyse_script(source), "outer").statement_count == 5


def test_elif_chain_stays_at_one_logical_level():
    source = textwrap.dedent(
        """
        def classify(a, b):
            if a:
                return 1
            elif b:
                return 2
            return 0
        """
    )

    assert unit(analyse_script(source), "classify").nesting_depth == 1


def test_if_nested_inside_else_adds_a_logical_level():
    source = textwrap.dedent(
        """
        def classify(a, b):
            if a:
                return 1
            else:
                if b:
                    return 2
            return 0
        """
    )

    assert unit(analyse_script(source), "classify").nesting_depth == 2


def test_nested_if_inside_elif_adds_a_logical_level():
    source = textwrap.dedent(
        """
        def classify(a, b, c):
            if a:
                return 1
            elif b:
                if c:
                    return 2
            return 0
        """
    )

    assert unit(analyse_script(source), "classify").nesting_depth == 2


def test_receiver_names_are_excluded_only_for_non_static_methods():
    source = textwrap.dedent(
        """
        def ordinary(self, value):
            def nested(cls, value):
                return value
            return nested(self, value)

        class Service:
            def instance(self, value):
                return value

            @classmethod
            def construct(cls, value):
                return cls()

            @staticmethod
            def static_self(self, value):
                return value

            @staticmethod
            def static_cls(cls, value):
                return value
        """
    )
    result = analyse_script(source)

    assert unit(result, "ordinary").parameter_count == 2
    assert unit(result, "ordinary.nested").parameter_count == 2
    assert unit(result, "Service.instance").parameter_count == 1
    assert unit(result, "Service.construct").parameter_count == 1
    assert unit(result, "Service.static_self").parameter_count == 2
    assert unit(result, "Service.static_cls").parameter_count == 2


def test_async_nesting_constructs_reach_threshold():
    source = textwrap.dedent(
        """
        async def process(items, manager):
            async with manager:
                async for item in items:
                    while item:
                        if item.ready:
                            return item
        """
    )
    item = unit(analyse_script(source), "process")

    assert item.nesting_depth == 4
    assert "deep_nesting" in smell_codes(item)


def test_try_star_counts_towards_nesting_on_python_311():
    source = textwrap.dedent(
        """
        def handle(group):
            try:
                raise group
            except* ValueError:
                for item in group.exceptions:
                    while item:
                        if item:
                            break
        """
    )
    item = unit(analyse_script(source), "handle")

    assert item.nesting_depth == 4
    assert "deep_nesting" in smell_codes(item)


def test_boolean_leaf_flattening_and_not_rule():
    source = textwrap.dedent(
        """
        def choose(a, b, c, d):
            if not (a and b) or (c and not d):
                return True
            return False
        """
    )

    assert "complex_boolean_expression" in smell_codes(unit(analyse_script(source), "choose"))


def test_match_guard_contributes_boolean_leaves():
    source = textwrap.dedent(
        """
        def choose(value, a, b, c, d):
            match value:
                case item if a and b and c and d:
                    return item
            return None
        """
    )

    assert "complex_boolean_expression" in smell_codes(unit(analyse_script(source), "choose"))


@pytest.mark.parametrize(
    ("signature", "expected"),
    [
        ("value=[]", True),
        ("value={}", True),
        ("value=set()", True),
        ("value=tuple()", False),
    ],
)
def test_mutable_defaults(signature, expected):
    result = analyse_script(f"def build({signature}):\n    return value\n")
    assert ("mutable_default" in smell_codes(unit(result, "build"))) is expected


def test_bare_and_broad_exception_smells_are_distinct():
    source = textwrap.dedent(
        """
        def recover():
            try:
                work()
            except:
                pass
            try:
                work()
            except (ValueError, Exception):
                pass
        """
    )
    codes = smell_codes(unit(analyse_script(source), "recover"))

    assert {"bare_exception", "broad_exception"} <= codes


def test_complexity_threshold_and_rank_are_from_radon():
    branches = "\n".join(f"    if value == {number}: return {number}" for number in range(10))
    item = unit(analyse_script(f"def decide(value):\n{branches}\n    return -1\n"), "decide")

    assert item.complexity == 11
    assert item.complexity_rank == "C"
    assert "high_cyclomatic_complexity" in smell_codes(item)


def test_long_function_boundary_is_strictly_greater_than_fifty_sloc():
    body_49 = "\n".join(f"    value_{index} = {index}" for index in range(49))
    at_fifty = unit(analyse_script(f"def exact():\n{body_49}\n"), "exact")
    body_50 = body_49 + "\n    final = 50"
    over_fifty = unit(analyse_script(f"def over():\n{body_50}\n"), "over")

    assert at_fifty.sloc == 50
    assert "long_function" not in smell_codes(at_fifty)
    assert over_fifty.sloc == 51
    assert "long_function" in smell_codes(over_fifty)


def test_procedural_module_excludes_import_docstring_and_definitions_without_overlap():
    nested_body = "\n".join(f"        hidden_{index} = {index}" for index in range(60))
    source = (
        '"""module docs"""\n'
        "import os\n"
        "if enabled:\n"
        "    visible = 1\n"
        "    def hidden():\n"
        f"{nested_body}\n"
        "        return hidden_0\n"
        "    visible += 1\n"
    )
    module = unit(analyse_script(source), "<module>")

    assert module.sloc == 3
    assert module.statement_count == 1
    assert module.complexity is None
    assert not module.smells


def test_procedural_module_excludes_decorators_on_nested_definitions():
    source = textwrap.dedent(
        """
        if enabled:
            @function_decorator
            def hidden_function():
                return 1

            @class_decorator
            class HiddenClass:
                value = 1

            visible = 1
        """
    )
    module = unit(analyse_script(source), "<module>")

    assert module.sloc == 2
    assert module.statement_count == 1


def test_top_level_statement_threshold_is_strictly_greater_than_thirty():
    thirty = "\n".join(f"value_{index} = {index}" for index in range(30))
    thirty_one = thirty + "\nextra = 31\n"

    assert "excessive_top_level_structure" not in smell_codes(
        unit(analyse_script(thirty), "<module>")
    )
    assert "excessive_top_level_structure" in smell_codes(
        unit(analyse_script(thirty_one), "<module>")
    )


def test_hotspots_are_limited_and_ordered_by_approved_lexicographic_rules():
    source = textwrap.dedent(
        """
        def medium_first(a=[]):
            return a

        def high_later(a):
            if a:
                for b in a:
                    while b:
                        if b:
                            return b

        def medium_second(a, b, c, d, e, f):
            return a

        def medium_third(a={}):
            return a
        """
    )
    result = analyse_script(source)

    assert result.outcome == HOTSPOTS_FOUND
    assert [item.qualified_name for item in result.hotspots] == [
        "high_later",
        "medium_first",
        "medium_second",
    ]
    assert result.hotspots[0].smells[0].severity is Severity.HIGH


def test_module_complexity_is_lower_than_valid_function_complexity_in_tie():
    # This directly checks the documented sentinel through the observable stable order:
    # both units have one high-severity smell, so valid complexity decides before SLOC.
    branches = "\n".join(f"    if value == {number}: return {number}" for number in range(10))
    assignments = "\n".join(f"    item_{number} = {number}" for number in range(51))
    result = analyse_script(
        f"def decide(value):\n{branches}\n    return -1\nif enabled:\n{assignments}\n"
    )

    assert result.hotspots[0].qualified_name == "decide"


def test_threshold_messages_use_the_configured_constants():
    branches = "\n".join(f"    if value == {number}: return {number}" for number in range(10))
    long_body = "\n".join(f"    value_{number} = {number}" for number in range(50))
    source = (
        "def combined(a, b, c, d, e, f):\n"
        f"{branches}\n"
        f"{long_body}\n"
        "    if a and b and c and d:\n"
        "        for item in e:\n"
        "            while item:\n"
        "                if f:\n"
        "                    return item\n"
    )
    messages = {
        smell.code: smell.message for smell in unit(analyse_script(source), "combined").smells
    }

    assert str(LONG_FUNCTION_SLOC) in messages["long_function"]
    assert str(DEEP_NESTING_DEPTH) in messages["deep_nesting"]
    assert str(HIGH_COMPLEXITY) in messages["high_cyclomatic_complexity"]
    assert str(TOO_MANY_PARAMETERS) in messages["too_many_parameters"]
    assert str(COMPLEX_BOOLEAN_LEAVES) in messages["complex_boolean_expression"]

    assignments = "\n".join(
        f"value_{number} = {number}" for number in range(OVERSIZED_PROCEDURAL_SLOC + 1)
    )
    module_messages = {
        smell.code: smell.message for smell in unit(analyse_script(assignments), "<module>").smells
    }
    assert str(OVERSIZED_PROCEDURAL_SLOC) in module_messages["oversized_procedural_module"]
    assert str(EXCESSIVE_TOP_LEVEL_STATEMENTS) in module_messages["excessive_top_level_structure"]
