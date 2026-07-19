from codesage.analysis import analyse_script
from codesage.evidence import GROUNDING_VERSION, PROMPT_VERSION, build_evidence_package


def test_evidence_ids_are_stable_unique_and_source_tied():
    source = "def choose(a, b, c, d):\n    if a and b and c and d:\n        return True\n"
    analysis = analyse_script(source)

    first = build_evidence_package(analysis)
    second = build_evidence_package(analysis)

    assert first == second
    assert first.prompt_version == PROMPT_VERSION
    assert first.grounding_version == GROUNDING_VERSION
    ids = [item.evidence_id for item in first.items]
    assert ids == [f"E{index:04d}" for index in range(1, len(ids) + 1)]
    assert len(ids) == len(set(ids))
    valid_references = {f"{unit.key}@L{unit.line}-L{unit.end_line}" for unit in analysis.units}
    valid_references.update(
        f"{definition.key}@L{definition.line}-L{definition.end_line}"
        for definition in analysis.classes
    )
    assert {item.source_reference for item in first.items} <= valid_references
    assert any(item.fact.startswith("smell.") for item in first.items)
    assert any(item.fact == "hotspot.selection_position" for item in first.items)
    assert tuple(name for name, _ in first.thresholds) == tuple(
        sorted(name for name, _ in first.thresholds)
    )
