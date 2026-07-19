"""Canonical source documents and bounded, non-persisting ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePath
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from codesage.analysis import source_digest

SOURCE_INGESTION_LIMIT = 200_000
AI_REVIEW_CHARACTER_LIMIT = 20_000
GITHUB_TIMEOUT_SECONDS = 10.0
MAX_GITHUB_REDIRECTS = 3
APPROVED_GITHUB_HOSTS = {"github.com", "raw.githubusercontent.com"}


class SourceOrigin(StrEnum):
    PASTED = "pasted"
    UPLOADED = "uploaded"
    GITHUB = "github"


@dataclass(frozen=True, slots=True)
class SourceDocument:
    text: str
    display_name: str
    origin: SourceOrigin
    external_reference: str | None
    source_digest: str

    @classmethod
    def create(
        cls,
        text: str,
        display_name: str,
        origin: SourceOrigin,
        external_reference: str | None = None,
    ) -> SourceDocument:
        return cls(text, display_name, origin, external_reference, source_digest(text))

    @property
    def identity(self) -> tuple[str, SourceOrigin, str, str | None]:
        return (self.source_digest, self.origin, self.display_name, self.external_reference)


class SourceIngestionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _validate_text_size(text: str) -> None:
    if len(text) > SOURCE_INGESTION_LIMIT:
        raise SourceIngestionError(
            "source_too_large",
            f"Source must not exceed {SOURCE_INGESTION_LIMIT:,} characters.",
        )


def normalise_pasted_source(text: str) -> SourceDocument:
    _validate_text_size(text)
    return SourceDocument.create(text, "Pasted source", SourceOrigin.PASTED)


def normalise_uploaded_file(filename: str, content: bytes) -> SourceDocument:
    display_name = PurePath(filename).name
    if not display_name.lower().endswith(".py"):
        raise SourceIngestionError("invalid_extension", "Upload one .py file.")
    if not content:
        raise SourceIngestionError("empty_source", "The uploaded Python file is empty.")
    if len(content) > SOURCE_INGESTION_LIMIT:
        raise SourceIngestionError(
            "source_too_large",
            f"Upload must not exceed {SOURCE_INGESTION_LIMIT:,} bytes.",
        )
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise SourceIngestionError(
            "decode_error", "The uploaded file is not valid UTF-8 or UTF-8 with BOM."
        ) from error
    if not text:
        raise SourceIngestionError("empty_source", "The uploaded Python file is empty.")
    _validate_text_size(text)
    return SourceDocument.create(text, display_name, SourceOrigin.UPLOADED)


def _validated_github_fetch_url(url: str) -> str:
    parsed = urlsplit(url)
    if parsed.scheme != "https":
        raise SourceIngestionError("invalid_url", "GitHub file URLs must use HTTPS.")
    if parsed.username or parsed.password or parsed.port not in {None, 443}:
        raise SourceIngestionError(
            "invalid_url", "The GitHub URL contains unsupported authority data."
        )
    hostname = (parsed.hostname or "").lower()
    if hostname not in APPROVED_GITHUB_HOSTS:
        raise SourceIngestionError("invalid_host", "Only approved GitHub file hosts are supported.")
    parts = [part for part in parsed.path.split("/") if part]
    if hostname == "github.com":
        if len(parts) < 6 or parts[2] != "blob" or not parts[-1].lower().endswith(".py"):
            raise SourceIngestionError(
                "invalid_github_path", "Use a GitHub blob URL for one specific .py file."
            )
        owner, repository, _, reference, *file_parts = parts
        raw_path = "/".join([owner, repository, reference, *file_parts])
        return urlunsplit(("https", "raw.githubusercontent.com", f"/{raw_path}", "", ""))
    if len(parts) < 4 or not parts[-1].lower().endswith(".py"):
        raise SourceIngestionError(
            "invalid_github_path", "Use a raw GitHub URL for one specific .py file."
        )
    return urlunsplit(("https", hostname, parsed.path, parsed.query, ""))


def fetch_github_source(url: str, *, client: httpx.Client | None = None) -> SourceDocument:
    original_url = url
    current_url = _validated_github_fetch_url(url)
    owns_client = client is None
    if client is None:
        client = httpx.Client(timeout=GITHUB_TIMEOUT_SECONDS, follow_redirects=False)
    try:
        for redirect_count in range(MAX_GITHUB_REDIRECTS + 1):
            try:
                with client.stream(
                    "GET",
                    current_url,
                    timeout=GITHUB_TIMEOUT_SECONDS,
                    follow_redirects=False,
                ) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        if redirect_count == MAX_GITHUB_REDIRECTS:
                            raise SourceIngestionError(
                                "too_many_redirects",
                                "The GitHub response redirected too many times.",
                            )
                        location = response.headers.get("location")
                        if not location:
                            raise SourceIngestionError(
                                "unsafe_redirect",
                                "The GitHub response contained an invalid redirect.",
                            )
                        try:
                            current_url = _validated_github_fetch_url(
                                urljoin(current_url, location)
                            )
                        except SourceIngestionError as error:
                            raise SourceIngestionError(
                                "unsafe_redirect",
                                "The GitHub response redirected outside an approved Python file URL.",
                            ) from error
                        continue
                    if response.status_code == 404:
                        raise SourceIngestionError(
                            "not_found", "The public GitHub Python file was not found."
                        )
                    if response.status_code == 429:
                        raise SourceIngestionError(
                            "rate_limited", "GitHub rate-limited the file request."
                        )
                    if response.status_code in {401, 403}:
                        raise SourceIngestionError(
                            "unavailable", "The GitHub file is private or unavailable."
                        )
                    if not 200 <= response.status_code < 300:
                        raise SourceIngestionError(
                            "github_error", "GitHub could not provide the requested file."
                        )
                    declared_length = response.headers.get("content-length")
                    if declared_length and int(declared_length) > SOURCE_INGESTION_LIMIT:
                        raise SourceIngestionError(
                            "source_too_large",
                            f"Remote file must not exceed {SOURCE_INGESTION_LIMIT:,} bytes.",
                        )
                    chunks: list[bytes] = []
                    byte_count = 0
                    for chunk in response.iter_bytes():
                        byte_count += len(chunk)
                        if byte_count > SOURCE_INGESTION_LIMIT:
                            raise SourceIngestionError(
                                "source_too_large",
                                f"Remote file must not exceed {SOURCE_INGESTION_LIMIT:,} bytes.",
                            )
                        chunks.append(chunk)
                    content = b"".join(chunks)
                    if not content:
                        raise SourceIngestionError(
                            "empty_source", "The GitHub Python file is empty."
                        )
                    try:
                        text = content.decode("utf-8-sig")
                    except UnicodeDecodeError as error:
                        raise SourceIngestionError(
                            "decode_error",
                            "The GitHub file is not valid UTF-8 or UTF-8 with BOM.",
                        ) from error
                    _validate_text_size(text)
                    display_name = PurePath(urlsplit(current_url).path).name
                    return SourceDocument.create(
                        text, display_name, SourceOrigin.GITHUB, original_url
                    )
            except httpx.TimeoutException as error:
                raise SourceIngestionError(
                    "timeout", "The GitHub file request timed out."
                ) from error
            except httpx.NetworkError as error:
                raise SourceIngestionError(
                    "network_error", "The GitHub file could not be downloaded."
                ) from error
        raise SourceIngestionError(
            "too_many_redirects", "The GitHub response redirected too many times."
        )
    finally:
        if owns_client:
            client.close()
