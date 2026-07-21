"""Validation of Part B processed JSONL records.

Real Part B schema (as emitted by the entity-resolution step):
  Always present  : source, domain, sub_category, region, timestamp_utc,
                    retrieved_at, raw_value, unit, raw_text, url,
                    anomaly_flag, resolved_entities, geo_tags, linked_event_id
  Optional (NLP)  : entities, sentiment_score, urgency_score, event_category
                    (absent in domains that skip the NLP enrichment step, e.g.
                    historical_resolved.jsonl and inventory_resolved.jsonl)
"""

from __future__ import annotations

from typing import Any

from .models import ProcessedRecord


# Fields that must be present and non-empty in every Part B record.
# NOTE: `region` is intentionally NOT required here.  GDELT and some other
# upstream sources occasionally emit null region for records whose geographic
# scope cannot be determined.  The transformer's _location_node() already
# returns None for a falsy region, so those records are ingested in full
# (Record + Event + Entity nodes) and simply have no Location node attached.
# Rejecting them would silently discard valid provenance.
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
    """Validate a raw JSON object and return a ProcessedRecord.

    Accepts records with or without the optional NLP enrichment fields
    (``entities``, ``sentiment_score``, ``urgency_score``, ``event_category``).
    Raises ``RecordValidationError`` only for genuinely broken records.
    """
    missing = sorted(field for field in REQUIRED_FIELDS if data.get(field) in (None, ""))
    if missing:
        raise RecordValidationError(
            f"{source_file}:{line_number} missing required field(s): {', '.join(missing)}"
        )

    # anomaly_flag is always emitted by Part B; validate its type when present.
    if "anomaly_flag" in data and not isinstance(data["anomaly_flag"], bool):
        raise RecordValidationError(
            f"{source_file}:{line_number} anomaly_flag must be a boolean, "
            f"got {type(data['anomaly_flag']).__name__!r}."
        )

    if "resolved_entities" in data and not isinstance(data["resolved_entities"], list):
        raise RecordValidationError(f"{source_file}:{line_number} resolved_entities must be a list.")

    if "geo_tags" in data and not isinstance(data["geo_tags"], list):
        raise RecordValidationError(f"{source_file}:{line_number} geo_tags must be a list.")

    # entities is optional but, when present, must be a list of dicts.
    if "entities" in data and not isinstance(data["entities"], list):
        raise RecordValidationError(f"{source_file}:{line_number} entities must be a list.")

    return ProcessedRecord(data=data, source_file=source_file, line_number=line_number)


