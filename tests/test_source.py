from __future__ import annotations

import httpx
import pytest

from codesage.analysis import analyse_script
from codesage.source import (
    SOURCE_INGESTION_LIMIT,
    SourceIngestionError,
    SourceOrigin,
    fetch_github_source,
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


def test_oversized_remote_response_is_rejected():
    client = github_client(
        lambda request: httpx.Response(200, content=b"#" * (SOURCE_INGESTION_LIMIT + 1))
    )

    with pytest.raises(SourceIngestionError) as caught:
        fetch_github_source(
            "https://raw.githubusercontent.com/owner/repo/main/module.py", client=client
        )

    assert caught.value.code == "source_too_large"


def test_unsafe_redirect_is_rejected():
    client = github_client(
        lambda request: httpx.Response(302, headers={"location": "https://example.com/steal.py"})
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
