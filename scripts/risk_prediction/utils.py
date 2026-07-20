"""Shared utility functions for the Part D risk prediction module."""

from __future__ import annotations

import hashlib
import json
import logging
from datetime import datetime, timezone
from typing import Any, Iterator, Sequence, TypeVar

LOGGER = logging.getLogger(__name__)

T = TypeVar("T")

# Ordered list of asset labels (used for integer encoding of asset_type)
ASSET_LABEL_ENCODING: dict[str, int] = {
    "Country": 0,
    "Port": 1,
    "Terminal": 2,
    "Refinery": 3,
    "StorageTerminal": 4,
    "Pipeline": 5,
    "PowerIndustry": 6,
    "Consumer": 7,
    "Supplier": 8,
    "Commodity": 9,
    "ShippingRoute": 10,
    "Organization": 11,
}

# All supply chain asset labels (excludes Event, EventCluster, Record)
ASSET_LABELS: list[str] = list(ASSET_LABEL_ENCODING.keys())


def utc_now_iso() -> str:
    """Return the current UTC timestamp as an ISO-8601 string."""
    return datetime.now(timezone.utc).isoformat()


def stable_id(prefix: str, parts: Sequence[Any]) -> str:
    """Build a deterministic identifier from ordered values."""
    payload = "|".join("" if part is None else str(part).strip() for part in parts)
    digest = hashlib.sha256(payload.encode("utf-8")).hexdigest()[:24]
    return f"{prefix}_{digest}"


def assessment_id_for(asset_id: str) -> str:
    """Deterministic RiskAssessment node ID (one per asset, always merged)."""
    return stable_id("risk", [asset_id])


def safe_float(value: Any, default: float = 0.0) -> float:
    """Coerce a value to float, returning *default* on failure."""
    if value is None:
        return default
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def safe_int(value: Any, default: int = 0) -> int:
    """Coerce a value to int, returning *default* on failure."""
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def days_since(iso_timestamp: str | None) -> float:
    """Return the number of days elapsed since *iso_timestamp* (UTC).

    Returns 0.0 when the timestamp is None or unparseable.
    """
    if not iso_timestamp:
        return 0.0
    try:
        normalized = iso_timestamp.replace("Z", "+00:00")
        then = datetime.fromisoformat(normalized)
        if then.tzinfo is None:
            then = then.replace(tzinfo=timezone.utc)
        now = datetime.now(timezone.utc)
        delta = now - then
        return max(delta.total_seconds() / 86400.0, 0.0)
    except (ValueError, OverflowError):
        return 0.0


def encode_asset_type(label: str) -> int:
    """Convert an asset label to its integer code."""
    return ASSET_LABEL_ENCODING.get(label, len(ASSET_LABEL_ENCODING))


def chunks(items: Sequence[T], size: int) -> Iterator[list[T]]:
    """Yield fixed-size chunks from a sequence."""
    for index in range(0, len(items), size):
        yield list(items[index : index + size])


def to_json_str(obj: Any) -> str:
    """Serialize *obj* to a compact JSON string (safe for Neo4j string property)."""
    try:
        return json.dumps(obj, default=str, separators=(",", ":"))
    except (TypeError, ValueError):
        return "{}"


def clip(value: float, lo: float = 0.0, hi: float = 1.0) -> float:
    """Clip *value* to [lo, hi]."""
    return max(lo, min(hi, value))
