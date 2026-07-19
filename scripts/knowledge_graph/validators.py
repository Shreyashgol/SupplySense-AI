"""Validation of Part B processed JSONL records."""

from __future__ import annotations

from typing import Any

from .models import ProcessedRecord


REQUIRED_FIELDS = {
    "source",
    "domain",
    "sub_category",
    "timestamp_utc",
    "retrieved_at",
    "raw_text",
}


class RecordValidationError(ValueError):
    """Raised when a processed record cannot be loaded into the graph."""


def validate_raw_record(data: dict[str, Any], source_file: str, line_number: int) -> ProcessedRecord:
    """Validate a raw JSON object and return a ProcessedRecord."""
    missing = sorted(field for field in REQUIRED_FIELDS if data.get(field) in (None, ""))
    if missing:
        raise RecordValidationError(
            f"{source_file}:{line_number} missing required field(s): {', '.join(missing)}"
        )

    if "resolved_entities" in data and not isinstance(data["resolved_entities"], list):
        raise RecordValidationError(f"{source_file}:{line_number} resolved_entities must be a list.")

    if "geo_tags" in data and not isinstance(data["geo_tags"], list):
        raise RecordValidationError(f"{source_file}:{line_number} geo_tags must be a list.")

    return ProcessedRecord(data=data, source_file=source_file, line_number=line_number)

