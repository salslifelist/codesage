"""Canonical source documents and bounded, non-persisting ingestion."""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from pathlib import PurePath
from urllib.parse import urljoin, urlsplit, urlunsplit

import httpx

from codesage.analysis import source_digest
from codesage.config import (
    DECODED_SOURCE_CHARACTER_LIMIT,
    GITHUB_REQUEST_TIMEOUT_SECONDS,
    MAX_VALIDATED_GITHUB_REDIRECTS,
    PASTED_SOURCE_CHARACTER_LIMIT,
    SCRIPT_AI_REVIEW_CHARACTER_LIMIT,
    SOURCE_RESPONSE_BYTE_LIMIT,
)

# Compatibility names remain importable while callers migrate to the precise
# canonical names above.
SOURCE_INGESTION_LIMIT = PASTED_SOURCE_CHARACTER_LIMIT
AI_REVIEW_CHARACTER_LIMIT = SCRIPT_AI_REVIEW_CHARACTER_LIMIT
GITHUB_TIMEOUT_SECONDS = GITHUB_REQUEST_TIMEOUT_SECONDS
MAX_GITHUB_REDIRECTS = MAX_VALIDATED_GITHUB_REDIRECTS
APPROVED_GITHUB_HOSTS = {"github.com", "raw.githubusercontent.com"}
BUILT_IN_EXAMPLE = '''"""Delivery dispatch prioritisation for a small last-mile courier service.

This module models a simple queue of customer orders and picks which order a
courier should attempt to deliver next. It is intentionally small: it exists
to demonstrate CodeSage's static analysis on a realistic, runnable script
rather than to model a production dispatch system.
"""

from __future__ import annotations

from dataclasses import dataclass, replace
from statistics import mean

MAX_URGENT_DISTANCE_KM = 15.0
STANDARD_WEIGHT_LIMIT_KG = 25.0
PENDING_STATUS = "pending"
DISPATCHED_STATUS = "dispatched"


@dataclass
class Order:
    """One customer order waiting to be delivered."""

    order_id: str
    customer_name: str
    status: str
    priority: str
    distance_km: float
    weight_kg: float


def filter_pending_orders(orders: list[Order]) -> list[Order]:
    """Return only the orders that are still waiting to be dispatched."""
    return [order for order in orders if order.status == PENDING_STATUS]


def total_weight_kg(orders: list[Order]) -> float:
    """Return the combined weight of the supplied orders."""
    return sum(order.weight_kg for order in orders)


def average_distance_km(orders: list[Order]) -> float:
    """Return the mean delivery distance, or zero for an empty list."""
    if not orders:
        return 0.0
    return mean(order.distance_km for order in orders)


def choose_next_delivery(orders: list[Order]) -> Order | None:
    """Pick the first pending, urgent order that a courier can reach quickly.

    A courier can only carry one urgent order at a time, so this walks the
    queue in order and returns the first order that clears every urgent
    dispatch rule. It returns None when nothing currently qualifies.
    """
    for order in orders:
        if order.status == PENDING_STATUS:
            if order.priority == "urgent":
                if order.distance_km <= MAX_URGENT_DISTANCE_KM:
                    return order
    return None


def mark_order_dispatched(order: Order) -> Order:
    """Return a copy of the order marked as dispatched."""
    return replace(order, status=DISPATCHED_STATUS)


def summarise_orders(orders: list[Order]) -> dict[str, int]:
    """Return a count of orders grouped by their current status."""
    summary: dict[str, int] = {}
    for order in orders:
        summary[order.status] = summary.get(order.status, 0) + 1
    return summary


def build_dispatch_report(orders: list[Order]) -> dict[str, object]:
    """Combine the helpers above into one small daily dispatch report."""
    pending = filter_pending_orders(orders)
    return {
        "pending_orders": len(pending),
        "pending_weight_kg": total_weight_kg(pending),
        "average_distance_km": average_distance_km(pending),
        "status_counts": summarise_orders(orders),
        "next_delivery": choose_next_delivery(orders),
    }
'''


class SourceOrigin(StrEnum):
    PASTED = "pasted"
    UPLOADED = "uploaded"
    GITHUB = "github"
    EXAMPLE = "example"


@dataclass(frozen=True, slots=True)
class SourceDocument:
    text: str
    display_name: str
    origin: SourceOrigin
    external_reference: str | None
    source_digest: str
    byte_count: int

    @classmethod
    def create(
        cls,
        text: str,
        display_name: str,
        origin: SourceOrigin,
        external_reference: str | None = None,
        byte_count: int | None = None,
    ) -> SourceDocument:
        resolved_byte_count = len(text.encode("utf-8")) if byte_count is None else byte_count
        return cls(
            text,
            display_name,
            origin,
            external_reference,
            source_digest(text),
            resolved_byte_count,
        )

    @property
    def identity(self) -> tuple[str, SourceOrigin, str, str | None]:
        return (self.source_digest, self.origin, self.display_name, self.external_reference)

    @property
    def ai_eligible(self) -> bool:
        return len(self.text) <= SCRIPT_AI_REVIEW_CHARACTER_LIMIT


class SourceIngestionError(ValueError):
    def __init__(self, code: str, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


def _validate_pasted_text_size(text: str) -> None:
    if len(text) > PASTED_SOURCE_CHARACTER_LIMIT:
        raise SourceIngestionError(
            "source_too_large",
            f"Pasted source must not exceed {PASTED_SOURCE_CHARACTER_LIMIT:,} characters.",
        )


def _validate_decoded_text_size(text: str) -> None:
    if len(text) > DECODED_SOURCE_CHARACTER_LIMIT:
        raise SourceIngestionError(
            "decoded_source_too_large",
            f"Decoded source must not exceed {DECODED_SOURCE_CHARACTER_LIMIT:,} characters.",
        )


def normalise_pasted_source(text: str) -> SourceDocument:
    _validate_pasted_text_size(text)
    return SourceDocument.create(text, "Pasted source", SourceOrigin.PASTED)


def normalise_example_source() -> SourceDocument:
    """Return the small, original script used for no-setup product exploration."""
    return SourceDocument.create(
        BUILT_IN_EXAMPLE,
        "CodeSage example.py",
        SourceOrigin.EXAMPLE,
    )


def normalise_uploaded_file(filename: str, content: bytes) -> SourceDocument:
    display_name = PurePath(filename).name
    if not display_name.lower().endswith(".py"):
        raise SourceIngestionError("invalid_extension", "Upload one .py file.")
    if not content:
        raise SourceIngestionError("empty_source", "The uploaded Python file is empty.")
    if len(content) > SOURCE_RESPONSE_BYTE_LIMIT:
        raise SourceIngestionError(
            "source_too_large",
            f"Upload must not exceed {SOURCE_RESPONSE_BYTE_LIMIT:,} bytes.",
        )
    try:
        text = content.decode("utf-8-sig")
    except UnicodeDecodeError as error:
        raise SourceIngestionError(
            "decode_error", "The uploaded file is not valid UTF-8 or UTF-8 with BOM."
        ) from error
    if not text:
        raise SourceIngestionError("empty_source", "The uploaded Python file is empty.")
    _validate_decoded_text_size(text)
    return SourceDocument.create(text, display_name, SourceOrigin.UPLOADED, byte_count=len(content))


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
        client = httpx.Client(timeout=GITHUB_REQUEST_TIMEOUT_SECONDS, follow_redirects=False)
    try:
        for redirect_count in range(MAX_VALIDATED_GITHUB_REDIRECTS + 1):
            try:
                with client.stream(
                    "GET",
                    current_url,
                    timeout=GITHUB_REQUEST_TIMEOUT_SECONDS,
                    follow_redirects=False,
                ) as response:
                    if response.status_code in {301, 302, 303, 307, 308}:
                        if redirect_count == MAX_VALIDATED_GITHUB_REDIRECTS:
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
                    if declared_length and int(declared_length) > SOURCE_RESPONSE_BYTE_LIMIT:
                        raise SourceIngestionError(
                            "source_too_large",
                            f"Remote file must not exceed {SOURCE_RESPONSE_BYTE_LIMIT:,} bytes.",
                        )
                    chunks: list[bytes] = []
                    byte_count = 0
                    for chunk in response.iter_bytes():
                        byte_count += len(chunk)
                        if byte_count > SOURCE_RESPONSE_BYTE_LIMIT:
                            raise SourceIngestionError(
                                "source_too_large",
                                f"Remote file must not exceed {SOURCE_RESPONSE_BYTE_LIMIT:,} bytes.",
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
                    _validate_decoded_text_size(text)
                    display_name = PurePath(urlsplit(current_url).path).name
                    return SourceDocument.create(
                        text,
                        display_name,
                        SourceOrigin.GITHUB,
                        original_url,
                        byte_count=len(content),
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
