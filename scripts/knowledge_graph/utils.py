"""Shared utility functions for the temporal knowledge graph loader."""

from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Iterator, Sequence, TypeVar

T = TypeVar("T")


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
    """Return a normalized ISO timestamp string when parsing succeeds."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
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


def read_jsonl(path: Path) -> Iterator[dict[str, Any]]:
    """Yield JSON objects from a JSONL file."""
    with path.open("r", encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            stripped = line.strip()
            if not stripped:
                continue
            try:
                yield json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON in {path}:{line_number}: {exc}") from exc


def list_jsonl_files(input_dir: Path) -> list[Path]:
    """Return sorted JSONL files from an input directory."""
    if not input_dir.exists():
        return []
    return sorted(input_dir.glob("*.jsonl"))

