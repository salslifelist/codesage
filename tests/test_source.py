from __future__ import annotations

import httpx
import pytest

import codesage.source as source_module
from codesage.analysis import analyse_script
from codesage.config import (
    DECODED_SOURCE_CHARACTER_LIMIT,
    MAX_VALIDATED_GITHUB_REDIRECTS,
    NOTEBOOK_AI_ANALYSABLE_CELL_LIMIT,
    NOTEBOOK_AI_CODE_CHARACTER_LIMIT,
    NOTEBOOK_DETERMINISTIC_CODE_CELL_LIMIT,
    PASTED_SOURCE_CHARACTER_LIMIT,
    SCRIPT_AI_REVIEW_CHARACTER_LIMIT,
    SOURCE_RESPONSE_BYTE_LIMIT,
)
from codesage.source import (
    BUILT_IN_EXAMPLE,
    SOURCE_INGESTION_LIMIT,
    SourceIngestionError,
    SourceOrigin,
    fetch_github_source,
    normalise_example_source,
    normalise_pasted_source,
    normalise_uploaded_file,
)


def github_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler))


def test_pasted_and_uploaded_sources_normalise_without_changing_text():
    text = "def first():\r\n    return 1\r\n"

    pasted = normalise_pasted_source(text)
    uploaded = normalise_uploaded_file("module.py", text.encode("utf-8"))

    assert pasted.text == uploaded.text == text
    assert pasted.origin is SourceOrigin.PASTED
    assert uploaded.origin is SourceOrigin.UPLOADED
    assert pasted.source_digest == uploaded.source_digest


def test_built_in_example_is_a_canonical_valid_script_with_a_hotspot():
    document = normalise_example_source()
    analysis = analyse_script(document.text)

    assert document.text == BUILT_IN_EXAMPLE
    assert document.origin is SourceOrigin.EXAMPLE
    assert document.display_name == "CodeSage example.py"
    assert document.ai_eligible
    assert analysis.syntax_valid


def test_built_in_example_is_a_realistic_complete_file_with_one_priority_hotspot():
    """The example must be realistic and demonstrate one clean, refactorable hotspot."""
    document = normalise_example_source()
    analysis = analyse_script(document.text)

    physical_lines = document.text.splitlines()
    assert 70 <= len(physical_lines) <= 120
    assert BUILT_IN_EXAMPLE.lstrip().startswith('"""')
    assert "@dataclass" in BUILT_IN_EXAMPLE

    non_module_units = [unit for unit in analysis.units if unit.qualified_name != "<module>"]
    assert 5 <= len(non_module_units) <= 8

    assert [item.qualified_name for item in analysis.hotspots] == ["choose_next_delivery"]
    hotspot = analysis.hotspots[0]
    assert {smell.code for smell in hotspot.smells} == {"deep_nesting"}
    assert hotspot.nesting_depth is not None and hotspot.nesting_depth >= 4
    assert hotspot.complexity is not None and hotspot.complexity < 11
    assert hotspot.parameter_count == 1

    other_units = [
        unit for unit in non_module_units if unit.qualified_name != "choose_next_delivery"
    ]
    assert other_units
    assert all(not unit.smells for unit in other_units)


def test_built_in_example_hotspot_is_refactorable_by_guard_clauses_without_regression():
    """Converting the nested ifs to guard clauses must lower nesting, not complexity."""
    document = normalise_example_source()
    nested_body = (
        "    for order in orders:\n"
        "        if order.status == PENDING_STATUS:\n"
        '            if order.priority == "urgent":\n'
        "                if order.distance_km <= MAX_URGENT_DISTANCE_KM:\n"
        "                    return order\n"
        "    return None\n"
    )
    guard_clause_body = (
        "    for order in orders:\n"
        "        if order.status != PENDING_STATUS:\n"
        "            continue\n"
        '        if order.priority != "urgent":\n'
        "            continue\n"
        "        if order.distance_km > MAX_URGENT_DISTANCE_KM:\n"
        "            continue\n"
        "        return order\n"
        "    return None\n"
    )
    assert nested_body in document.text
    refactored_text = document.text.replace(nested_body, guard_clause_body)
    assert refactored_text != document.text

    original_hotspot = analyse_script(document.text).hotspots[0]
    refactored_units = analyse_script(refactored_text).units
    refactored_unit = next(
        unit for unit in refactored_units if unit.qualified_name == "choose_next_delivery"
    )

    assert refactored_unit.nesting_depth is not None and refactored_unit.nesting_depth < 4
    assert refactored_unit.complexity is not None
    assert refactored_unit.complexity <= original_hotspot.complexity
    assert not any(smell.code == "deep_nesting" for smell in refactored_unit.smells)
    assert not refactored_unit.smells


def test_empty_pasted_source_is_preserved_for_the_no_input_interface_state():
    document = normalise_pasted_source("")
    assert document.text == ""
    assert document.byte_count == 0
    assert document.origin is SourceOrigin.PASTED


def test_utf8_bom_upload_decodes_without_retaining_bom():
    document = normalise_uploaded_file("bom.py", b"\xef\xbb\xbfvalue = 1\n")

    assert document.text == "value = 1\n"


@pytest.mark.parametrize(
    ("filename", "content", "code"),
    [
        ("module.txt", b"value = 1\n", "invalid_extension"),
        ("module.py", b"", "empty_source"),
        ("module.py", b"\xff\xfe", "decode_error"),
    ],
)
def test_invalid_uploads_are_rejected(filename, content, code):
    with pytest.raises(SourceIngestionError) as caught:
        normalise_uploaded_file(filename, content)

    assert caught.value.code == code


def test_oversized_upload_is_rejected():
    with pytest.raises(SourceIngestionError) as caught:
        normalise_uploaded_file("module.py", b"#" * (SOURCE_INGESTION_LIMIT + 1))

    assert caught.value.code == "source_too_large"


def test_exact_pasted_and_upload_acquisition_boundaries_are_not_truncated():
    pasted = "#" * PASTED_SOURCE_CHARACTER_LIMIT
    pasted_document = normalise_pasted_source(pasted)
    assert pasted_document.text == pasted
    assert len(pasted_document.text) == PASTED_SOURCE_CHARACTER_LIMIT

    upload = b"#" + (b"a" * (SOURCE_RESPONSE_BYTE_LIMIT - 2)) + b"\n"
    upload_document = normalise_uploaded_file("limit.py", upload)
    assert upload_document.text == upload.decode("utf-8")
    assert upload_document.byte_count == SOURCE_RESPONSE_BYTE_LIMIT

    with pytest.raises(SourceIngestionError) as pasted_error:
        normalise_pasted_source(pasted + "x")
    assert pasted_error.value.code == "source_too_large"

    with pytest.raises(SourceIngestionError) as upload_error:
        normalise_uploaded_file("limit.py", upload + b"x")
    assert upload_error.value.code == "source_too_large"


def test_script_ai_eligibility_boundary_is_independent_of_acquisition():
    eligible = normalise_pasted_source("#" * SCRIPT_AI_REVIEW_CHARACTER_LIMIT)
    deterministic_only = normalise_pasted_source("#" * (SCRIPT_AI_REVIEW_CHARACTER_LIMIT + 1))

    assert eligible.ai_eligible is True
    assert deterministic_only.ai_eligible is False
    assert len(deterministic_only.text) == SCRIPT_AI_REVIEW_CHARACTER_LIMIT + 1


def test_future_notebook_limits_remain_unchanged():
    assert NOTEBOOK_DETERMINISTIC_CODE_CELL_LIMIT == 50
    assert NOTEBOOK_AI_ANALYSABLE_CELL_LIMIT == 20
    assert NOTEBOOK_AI_CODE_CHARACTER_LIMIT == 30_000


def test_decoded_content_limit_is_enforced_independently(monkeypatch):
    monkeypatch.setattr(source_module, "DECODED_SOURCE_CHARACTER_LIMIT", 3)

    with pytest.raises(SourceIngestionError) as caught:
        normalise_uploaded_file("module.py", b"pass")

    assert caught.value.code == "decoded_source_too_large"
    assert DECODED_SOURCE_CHARACTER_LIMIT == 200_000


def test_valid_github_blob_url_fetches_one_raw_python_file():
    requested = []

    def handler(request):
        requested.append(str(request.url))
        return httpx.Response(200, content=b"def loaded():\n    return 1\n")

    original = "https://github.com/owner/repo/blob/main/src/module.py"
    document = fetch_github_source(original, client=github_client(handler))

    assert requested == ["https://raw.githubusercontent.com/owner/repo/main/src/module.py"]
    assert document.origin is SourceOrigin.GITHUB
    assert document.display_name == "module.py"
    assert document.external_reference == original


def test_valid_raw_github_url_is_supported():
    url = "https://raw.githubusercontent.com/owner/repo/main/module.py"
    document = fetch_github_source(
        url,
        client=github_client(lambda request: httpx.Response(200, content=b"value = 1\n")),
    )

    assert document.text == "value = 1\n"
    assert document.external_reference == url


@pytest.mark.parametrize(
    ("url", "code"),
    [
        ("https://example.com/module.py", "invalid_host"),
        ("http://github.com/owner/repo/blob/main/module.py", "invalid_url"),
        ("https://github.com/owner/repo", "invalid_github_path"),
        ("https://github.com/owner/repo/tree/main/src", "invalid_github_path"),
        ("https://github.com/owner/repo/blob/main/readme.md", "invalid_github_path"),
    ],
)
def test_invalid_github_urls_are_rejected_before_network(url, code):
    client = github_client(lambda request: pytest.fail("network must not be used"))

    with pytest.raises(SourceIngestionError) as caught:
        fetch_github_source(url, client=client)

    assert caught.value.code == code


@pytest.mark.parametrize(("status", "code"), [(404, "not_found"), (429, "rate_limited")])
def test_github_status_failures_are_typed(status, code):
    client = github_client(lambda request: httpx.Response(status))

    with pytest.raises(SourceIngestionError) as caught:
        fetch_github_source(
            "https://raw.githubusercontent.com/owner/repo/main/module.py", client=client
        )

    assert caught.value.code == code


def test_github_timeout_is_typed():
    def handler(request):
        raise httpx.ReadTimeout("timed out", request=request)

    with pytest.raises(SourceIngestionError) as caught:
        fetch_github_source(
            "https://raw.githubusercontent.com/owner/repo/main/module.py",
            client=github_client(handler),
        )

    assert caught.value.code == "timeout"


def test_github_network_failure_is_typed():
    def handler(request):
        raise httpx.ConnectError("offline", request=request)

    with pytest.raises(SourceIngestionError) as caught:
        fetch_github_source(
            "https://raw.githubusercontent.com/owner/repo/main/module.py",
            client=github_client(handler),
        )

    assert caught.value.code == "network_error"


@pytest.mark.parametrize(
    ("content", "code"),
    [(b"", "empty_source"), (b"\xff", "decode_error")],
)
def test_invalid_remote_content_is_rejected(content, code):
    with pytest.raises(SourceIngestionError) as caught:
        fetch_github_source(
            "https://raw.githubusercontent.com/owner/repo/main/module.py",
            client=github_client(lambda request: httpx.Response(200, content=content)),
        )
    assert caught.value.code == code


def test_oversized_remote_response_is_rejected():
    client = github_client(
        lambda request: httpx.Response(200, content=b"#" * (SOURCE_INGESTION_LIMIT + 1))
    )

    with pytest.raises(SourceIngestionError) as caught:
        fetch_github_source(
            "https://raw.githubusercontent.com/owner/repo/main/module.py", client=client
        )

    assert caught.value.code == "source_too_large"


def test_exact_remote_response_boundary_is_accepted_without_truncation():
    content = b"#" + (b"a" * (SOURCE_RESPONSE_BYTE_LIMIT - 2)) + b"\n"
    document = fetch_github_source(
        "https://raw.githubusercontent.com/owner/repo/main/module.py",
        client=github_client(lambda request: httpx.Response(200, content=content)),
    )

    assert document.byte_count == SOURCE_RESPONSE_BYTE_LIMIT
    assert document.text.encode("utf-8") == content


def test_unsafe_redirect_is_rejected():
    client = github_client(
        lambda request: httpx.Response(302, headers={"location": "https://example.com/steal.py"})
    )

    with pytest.raises(SourceIngestionError) as caught:
        fetch_github_source(
            "https://raw.githubusercontent.com/owner/repo/main/module.py", client=client
        )

    assert caught.value.code == "unsafe_redirect"


def test_safe_redirects_are_manually_revalidated_and_bounded():
    requests = []

    def handler(request):
        requests.append(str(request.url))
        hop = len(requests)
        if hop <= MAX_VALIDATED_GITHUB_REDIRECTS:
            return httpx.Response(
                302,
                headers={
                    "location": (f"https://raw.githubusercontent.com/owner/repo/main/hop{hop}.py")
                },
            )
        return httpx.Response(200, content=b"value = 1\n")

    document = fetch_github_source(
        "https://raw.githubusercontent.com/owner/repo/main/module.py",
        client=github_client(handler),
    )

    assert document.text == "value = 1\n"
    assert len(requests) == MAX_VALIDATED_GITHUB_REDIRECTS + 1


def test_fourth_redirect_is_rejected_without_another_hop():
    requests = []

    def handler(request):
        requests.append(str(request.url))
        hop = len(requests)
        return httpx.Response(
            302,
            headers={"location": f"https://raw.githubusercontent.com/owner/repo/main/hop{hop}.py"},
        )

    with pytest.raises(SourceIngestionError) as caught:
        fetch_github_source(
            "https://raw.githubusercontent.com/owner/repo/main/module.py",
            client=github_client(handler),
        )

    assert caught.value.code == "too_many_redirects"
    assert len(requests) == MAX_VALIDATED_GITHUB_REDIRECTS + 1


def test_owned_github_client_disables_automatic_redirects(monkeypatch):
    constructor_options = []
    stream_options = []
    inner = github_client(lambda request: httpx.Response(200, content=b"value = 1\n"))

    class RecordingClient:
        def stream(self, *args, **kwargs):
            stream_options.append(kwargs)
            return inner.stream(*args, **kwargs)

        def close(self):
            inner.close()

    def client_factory(**kwargs):
        constructor_options.append(kwargs)
        return RecordingClient()

    monkeypatch.setattr(source_module.httpx, "Client", client_factory)
    fetch_github_source("https://raw.githubusercontent.com/owner/repo/main/module.py")

    assert constructor_options[0]["follow_redirects"] is False
    assert stream_options[0]["follow_redirects"] is False


def test_insecure_redirect_is_rejected():
    client = github_client(
        lambda request: httpx.Response(
            302,
            headers={"location": "http://raw.githubusercontent.com/owner/repo/main/module.py"},
        )
    )

    with pytest.raises(SourceIngestionError) as caught:
        fetch_github_source(
            "https://raw.githubusercontent.com/owner/repo/main/module.py", client=client
        )

    assert caught.value.code == "unsafe_redirect"


def test_identical_code_from_every_origin_has_identical_analysis():
    text = "def shared(value=[]):\n    return value\n"
    pasted = normalise_pasted_source(text)
    uploaded = normalise_uploaded_file("shared.py", text.encode())
    github = fetch_github_source(
        "https://raw.githubusercontent.com/owner/repo/main/shared.py",
        client=github_client(lambda request: httpx.Response(200, content=text.encode())),
    )

    assert (
        analyse_script(pasted.text) == analyse_script(uploaded.text) == analyse_script(github.text)
    )
