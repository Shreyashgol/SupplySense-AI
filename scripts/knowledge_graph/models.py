"""Dataclasses used by the temporal knowledge graph pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass(frozen=True)
class ProcessedRecord:
    """Validated Part B record consumed by the graph transformer."""

    data: dict[str, Any]
    source_file: str
    line_number: int

    @property
    def domain(self) -> str:
        return str(self.data.get("domain") or "unknown")

    @property
    def timestamp(self) -> str | None:
        value = self.data.get("timestamp_utc")
        return str(value) if value else None

    @property
    def anomaly_flag(self) -> bool:
        """Always-present Part B boolean flag marking anomalous readings."""
        return bool(self.data.get("anomaly_flag", False))

    @property
    def linked_event_id(self) -> str | None:
        """Cluster key propagated by Part B entity resolution."""
        return self.data.get("linked_event_id") or None


@dataclass(frozen=True)
class GraphNode:
    """A Neo4j node to be upserted."""

    label: str
    key_property: str
    key_value: str
    properties: dict[str, Any] = field(default_factory=dict)

    def as_payload(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "key_property": self.key_property,
            "key_value": self.key_value,
            "properties": self.properties,
        }


@dataclass(frozen=True)
class GraphRelationship:
    """A Neo4j relationship to be upserted between two known nodes."""

    start_label: str
    start_key_property: str
    start_key_value: str
    relationship_type: str
    end_label: str
    end_key_property: str
    end_key_value: str
    properties: dict[str, Any] = field(default_factory=dict)

    def as_payload(self) -> dict[str, Any]:
        return {
            "start_label": self.start_label,
            "start_key_property": self.start_key_property,
            "start_key_value": self.start_key_value,
            "relationship_type": self.relationship_type,
            "end_label": self.end_label,
            "end_key_property": self.end_key_property,
            "end_key_value": self.end_key_value,
            "properties": self.properties,
        }


@dataclass(frozen=True)
class GraphBatch:
    """Collection of graph objects produced from processed records."""

    nodes: list[GraphNode]
    relationships: list[GraphRelationship]

