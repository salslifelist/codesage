from codesage.analysis import analyse_script
from codesage.comparison import (
    DescriptiveStatus,
    DirectionalStatus,
    StructuralStatus,
    compare_scripts,
)


def metric(comparisons, name, metric_name):
    return next(
        item for item in comparisons if item.qualified_name == name and item.metric == metric_name
    )


def structural(comparison, category, name):
    return next(
        item for item in comparison.structural if item.category == category and item.name == name
    )


def test_directional_descriptive_and_unresolved_comparisons():
    original = analyse_script(
        "def improved(value):\n"
        "    if value > 0:\n        return 1\n"
        "    if value < 0:\n        return -1\n"
        "    return 0\n\n"
        "def regressed(value):\n    return value\n\n"
        "def unchanged(value):\n    return value\n\n"
        "def removed(value):\n    return value\n"
    )
    candidate = analyse_script(
        "def improved(value):\n"
        "    if value:\n        return 1\n"
        "    return 0\n\n"
        "def regressed(value):\n    if value:\n        return value\n    return None\n\n"
        "def unchanged(value):\n    return value\n\n"
        "def added(value):\n    return value\n"
    )

    result = compare_scripts(original, candidate)

    assert metric(result.directional, "improved", "complexity").status is DirectionalStatus.IMPROVED
    assert (
        metric(result.directional, "regressed", "complexity").status is DirectionalStatus.REGRESSED
    )
    assert (
        metric(result.directional, "unchanged", "complexity").status is DirectionalStatus.UNCHANGED
    )
    assert (
        metric(result.directional, "removed", "complexity").status is DirectionalStatus.UNRESOLVED
    )
    assert metric(result.descriptive, "improved", "sloc").status is DescriptiveStatus.DECREASED
    assert metric(result.descriptive, "regressed", "sloc").status is DescriptiveStatus.INCREASED
    assert metric(result.descriptive, "unchanged", "sloc").status is DescriptiveStatus.UNCHANGED
    assert metric(result.descriptive, "removed", "sloc").status is DescriptiveStatus.UNRESOLVED
    assert (
        metric(result.descriptive, "<script>", "function_count").status
        is DescriptiveStatus.UNCHANGED
    )
    assert any("removed is absent" in warning for warning in result.warnings)
    assert structural(result, "function", "unchanged").status is StructuralStatus.UNCHANGED


def test_structural_inventory_uses_exact_names_and_does_not_infer_renames():
    original = analyse_script(
        "import os\nfrom shared import item\n"
        "class RemovedClass:\n    pass\n"
        "class StableClass:\n    pass\n"
        "def renamed_old(value):\n    return value\n"
        "def signature(value) -> int:\n    return value\n"
        "class Container:\n    def removed_method(self):\n        return 1\n"
    )
    candidate = analyse_script(
        "import sys\nfrom shared import item\n"
        "class AddedClass:\n    pass\n"
        "class StableClass:\n    pass\n"
        "def renamed_new(value):\n    return value\n"
        "def signature(value, extra=1) -> str:\n    return str(value + extra)\n"
        "class Container:\n    def added_method(self):\n        return 1\n"
    )

    result = compare_scripts(original, candidate)

    assert structural(result, "function", "renamed_old").status is StructuralStatus.REMOVED
    assert structural(result, "function", "renamed_new").status is StructuralStatus.ADDED
    assert (
        structural(result, "method", "Container.removed_method").status is StructuralStatus.REMOVED
    )
    assert structural(result, "method", "Container.added_method").status is StructuralStatus.ADDED
    assert structural(result, "class", "RemovedClass").status is StructuralStatus.REMOVED
    assert structural(result, "class", "AddedClass").status is StructuralStatus.ADDED
    assert structural(result, "signature", "signature").status is StructuralStatus.CHANGED
    assert any("signature has a changed signature" in warning for warning in result.warnings)
    assert structural(result, "import", ":os").status is StructuralStatus.REMOVED
    assert structural(result, "import", ":sys").status is StructuralStatus.ADDED
    assert structural(result, "import", "shared:item").status is StructuralStatus.UNCHANGED


def test_import_bindings_ignore_statement_grouping_and_order():
    original = analyse_script("import os, sys\nfrom package import first, second\n")
    candidate = analyse_script(
        "import sys, os\nfrom package import second\nfrom package import first\n"
    )

    result = compare_scripts(original, candidate)

    for binding in (":os", ":sys", "package:first", "package:second"):
        assert structural(result, "import", binding).status is StructuralStatus.UNCHANGED
    assert not any(
        item.status in {StructuralStatus.ADDED, StructuralStatus.REMOVED}
        for item in result.structural
        if item.category == "import"
    )


def test_import_binding_addition_and_alias_change_are_explicit():
    original = analyse_script("import os as operating_system\n")
    candidate = analyse_script("import os as platform_os\nimport sys\n")

    result = compare_scripts(original, candidate)

    assert (
        structural(result, "import", ":os as operating_system").status is StructuralStatus.REMOVED
    )
    assert structural(result, "import", ":os as platform_os").status is StructuralStatus.ADDED
    assert structural(result, "import", ":sys").status is StructuralStatus.ADDED


def test_smells_introduced_and_removed_are_reported_without_overall_verdict():
    original = analyse_script("def old(value=[]):\n    return value\n")
    candidate = analyse_script("def old(value=None):\n    return value\n")

    result = compare_scripts(original, candidate)

    assert result.smells_removed == ("old:mutable_default",)
    assert result.smells_introduced == ()
    assert not hasattr(result, "overall_verdict")


def test_structural_fingerprints_detect_definition_method_and_class_changes():
    original = analyse_script(
        "@trace\n"
        "def task(value):\n    return value\n"
        "class Container:\n"
        "    def run(self, value):\n        return value\n"
        "class Based(OldBase):\n    pass\n"
        "@old_decorator\nclass Decorated:\n    pass\n"
        "@stable\nclass Stable(Base, metaclass=Meta):\n    pass\n"
    )
    candidate = analyse_script(
        "@trace\n"
        "async def task(value):\n    return value\n"
        "class Container:\n"
        "    @staticmethod\n"
        "    def run(value):\n        return value\n"
        "class Based(NewBase):\n    pass\n"
        "@new_decorator\nclass Decorated:\n    pass\n"
        "@stable\nclass Stable(Base, metaclass=Meta):\n    pass\n"
    )

    result = compare_scripts(original, candidate)

    assert structural(result, "function", "task").status is StructuralStatus.CHANGED
    assert structural(result, "method", "Container.run").status is StructuralStatus.CHANGED
    assert structural(result, "class", "Based").status is StructuralStatus.CHANGED
    assert structural(result, "class", "Decorated").status is StructuralStatus.CHANGED
    assert structural(result, "class", "Stable").status is StructuralStatus.UNCHANGED
    assert any("task has changed structural identity" in warning for warning in result.warnings)
    assert any("Based has changed class structure" in warning for warning in result.warnings)


def test_smell_comparison_is_severity_and_smell_specific():
    original = analyse_script("def focused(value=[]):\n    return value\n")
    candidate = analyse_script(
        "def focused(value=None):\n"
        "    if value:\n"
        "        for item in value:\n"
        "            while item:\n"
        "                if item:\n"
        "                    return item\n"
    )

    result = compare_scripts(original, candidate)

    assert (
        metric(result.directional, "focused", "medium_severity_smell_count").status
        is DirectionalStatus.IMPROVED
    )
    assert (
        metric(result.directional, "focused", "high_severity_smell_count").status
        is DirectionalStatus.REGRESSED
    )
    assert (
        metric(result.directional, "focused", "smell.mutable_default").status
        is DirectionalStatus.IMPROVED
    )
    assert (
        metric(result.directional, "focused", "smell.deep_nesting").status
        is DirectionalStatus.REGRESSED
    )
