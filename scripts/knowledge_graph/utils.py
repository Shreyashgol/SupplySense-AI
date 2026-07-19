"""Shared utility functions for the temporal knowledge graph loader."""

from __future__ import annotations

import hashlib
import json
import logging
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence, TypeVar

T = TypeVar("T")

LOGGER = logging.getLogger(__name__)



def utc_now_iso() -> str:
    """Return the current UTC timestamp as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def stable_id(prefix: str, parts: Sequence[Any]) -> str:
    """Build a deterministic identifier from ordered values."""
    payload = "|".join("" if part is None else str(part).strip() for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def slug(value: Any) -> str:
    """Normalize a value into a lowercase key fragment."""
    text = str(value or "").strip().lower()
    text = re.sub(r"[^a-z0-9]+", "_", text)
    return text.strip("_") or "unknown"


def parse_datetime(value: Any) -> str | None:
    """Return a normalized ISO timestamp string when parsing succeeds.

    Handles three formats emitted by Part B:
    - Epoch-milliseconds integer (13 digits):  1752883200000
    - Epoch-seconds integer (10 digits):        1752883200
    - ISO-8601 string:                          "2025-07-19T00:00:00Z"
    """
    if value is None:
        return None
    # Handle numeric epoch values passed as int/float directly.
    if isinstance(value, (int, float)) and not isinstance(value, bool):
        ms = float(value)
        # Part B always uses milliseconds; values > 1e10 are ms-epoch.
        if ms > 1e10:
            ms /= 1000.0
        return datetime.fromtimestamp(ms, tz=timezone.utc).isoformat()
    text = str(value).strip()
    if not text:
        return None
    # Pure numeric string — epoch ms (13 digits) or epoch seconds (10 digits).
    if text.lstrip("-").isdigit():
        ms = float(text)
        if ms > 1e10:
            ms /= 1000.0
        return datetime.fromtimestamp(ms, tz=timezone.utc).isoformat()
    try:
        normalized = text.replace("Z", "+00:00")
        return datetime.fromisoformat(normalized).isoformat()
    except ValueError:
        return text


def coerce_float(value: Any) -> float | None:
    """Convert numeric-looking values to float, otherwise return None."""
    if value is None or value == "":
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def compact_dict(data: dict[str, Any]) -> dict[str, Any]:
    """Remove None values and empty collections from a dictionary."""
    return {
        key: value
        for key, value in data.items()
        if value is not None and value != [] and value != {}
    }


def chunks(items: Sequence[T], size: int) -> Iterator[list[T]]:
    """Yield fixed-size chunks from a sequence."""
    for index in range(0, len(items), size):
        yield list(items[index : index + size])


def read_jsonl(path: Path) -> Iterator[tuple[dict[str, Any] | None, bool]]:
    """Yield (row, ok) pairs from a JSONL file.

    Malformed lines yield ``(None, False)`` so callers can count and log
    skipped lines without aborting the rest of the file.
    """
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                yield json.loads(stripped), True
            except json.JSONDecodeError as exc:
                LOGGER.warning(
                    "Skipping malformed JSON at %s:%d — %s",
                    path,
                    line_number,
                    exc,
                )
                yield None, False


def list_jsonl_files(input_dir: Path) -> list[Path]:
    """Dynamically discover all Part B resolved JSONL files under *input_dir*.

    Only files matching ``*_resolved.jsonl`` are returned so that transient
    debug dumps or other JSONL artefacts in the same directory are not
    accidentally ingested.
    """
    if not input_dir.exists():
        return []
    return sorted(input_dir.glob("*_resolved.jsonl"))

