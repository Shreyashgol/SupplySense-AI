"""Transform Part B processed records into graph nodes and relationships."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from .graph_schema import (
    ASSET_TYPE_TO_LABEL,
    DOMAIN_EVENT_CATEGORY,
    EVENT_CATEGORY_ORDER,
    NODE_KEY_PROPERTY,
)
from .geodata import resolve_country_centroid
from .models import GraphBatch, GraphNode, GraphRelationship, ProcessedRecord
from .utils import coerce_float, compact_dict, parse_datetime, slug, stable_id, utc_now_iso

LOGGER = logging.getLogger(__name__)

try:
    import yaml
except ModuleNotFoundError:  # pragma: no cover - exercised only in minimal runtimes
    yaml = None


class GraphTransformer:
    """Convert processed records into an asset-centric temporal graph."""

    def __init__(self, energy_entities_path: Path) -> None:
        self.energy_entities = self._load_energy_entities(energy_entities_path)

    def transform_records(self, records: list[ProcessedRecord]) -> GraphBatch:
        """Transform a list of records and add temporal links between events."""
        nodes_by_key: dict[tuple[str, str], GraphNode] = {}
        rels_by_key: dict[tuple[str, str, str, str], GraphRelationship] = {}
        events_for_timeline: list[GraphNode] = []

        for record in records:
            batch = self.transform_record(record)
            for node in batch.nodes:
                nodes_by_key[(node.label, node.key_value)] = self._merge_node(
                    nodes_by_key.get((node.label, node.key_value)), node
                )
                if node.label == "Event":
                    events_for_timeline.append(node)
            for rel in batch.relationships:
                key = (
                    f"{rel.start_label}:{rel.start_key_value}",
                    rel.relationship_type,
                    f"{rel.end_label}:{rel.end_key_value}",
                    str(rel.properties.get("valid_from", "")),
                )
                rels_by_key[key] = self._merge_relationship(rels_by_key.get(key), rel)

        for rel in self.build_temporal_links(events_for_timeline):
            key = (
                f"{rel.start_label}:{rel.start_key_value}",
                rel.relationship_type,
                f"{rel.end_label}:{rel.end_key_value}",
                str(rel.properties.get("valid_from", "")),
            )
            rels_by_key[key] = self._merge_relationship(rels_by_key.get(key), rel)

        return GraphBatch(nodes=list(nodes_by_key.values()), relationships=list(rels_by_key.values()))

    def transform_record(self, record: ProcessedRecord) -> GraphBatch:
        """Transform one validated Part B record into graph payloads."""
        row = record.data
        timestamp = parse_datetime(row.get("timestamp_utc"))
        retrieved_at = parse_datetime(row.get("retrieved_at"))
        record_id = self._record_id(row)
        domain = str(row.get("domain"))
        event_category = self._event_category(row)
        linked_event_id = row.get("linked_event_id") or stable_id(
            "event",
            [domain, row.get("sub_category"), row.get("region"), row.get("timestamp_utc"), row.get("raw_text")],
        )
        cluster_id = str(linked_event_id)

        severity = self._severity(row)
        confidence = self._confidence(row)

        record_node = GraphNode(
            label="Record",
            key_property=NODE_KEY_PROPERTY["Record"],
            key_value=record_id,
            properties=compact_dict(
                {
                    "record_id": record_id,
                    "source": row.get("source"),
                    "domain": domain,
                    "sub_category": row.get("sub_category"),
                    "region": row.get("region"),
                    "timestamp": timestamp,
                    "timestamp_utc": timestamp,
                    "retrieved_at": retrieved_at,
                    "raw_value": row.get("raw_value"),
                    "raw_value_numeric": coerce_float(row.get("raw_value")),
                    "unit": row.get("unit"),
                    "raw_text": row.get("raw_text"),
                    "url": row.get("url"),
                    # anomaly_flag: always present in Part B output (bool).
                    "anomaly_flag": row.get("anomaly_flag"),
                    "linked_event_id": row.get("linked_event_id"),
                    "source_file": record.source_file,
                    "source_line": record.line_number,
                    "loaded_at": utc_now_iso(),
                }
            ),
        )
        event_node = GraphNode(
            label="Event",
            key_property=NODE_KEY_PROPERTY["Event"],
            key_value=str(linked_event_id),
            properties=compact_dict(
                {
                    "event_id": str(linked_event_id),
                    "event_type": event_category,
                    "domain": domain,
                    "sub_category": row.get("sub_category"),
                    "timestamp": timestamp,
                    "valid_from": timestamp,
                    "valid_to": None,
                    "confidence": confidence,
                    "severity": severity,
                    "sentiment_score": coerce_float(row.get("sentiment_score")),
                    "urgency_score": coerce_float(row.get("urgency_score")),
                    "summary": str(row.get("raw_text") or "")[:500],
                    "source": row.get("source"),
                    "url": row.get("url"),
                    "loaded_at": utc_now_iso(),
                }
            ),
        )
        cluster_node = GraphNode(
            label="EventCluster",
            key_property=NODE_KEY_PROPERTY["EventCluster"],
            key_value=cluster_id,
            properties=compact_dict(
                {
                    "cluster_id": cluster_id,
                    "event_type": event_category,
                    "first_seen_at": timestamp,
                    "last_seen_at": timestamp,
                    "confidence": confidence,
                    "severity": severity,
                    "loaded_at": utc_now_iso(),
                }
            ),
        )

        nodes = [record_node, event_node, cluster_node]
        rels = [
            self._relationship(event_node, "EVIDENCED_BY", record_node, record_id, timestamp, confidence, severity),
            self._relationship(event_node, "PART_OF_CLUSTER", cluster_node, record_id, timestamp, confidence, severity),
        ]

        region_node = self._location_node(row.get("region"), record_id, timestamp)
        if region_node:
            nodes.append(region_node)
            rels.extend(
                [
                    self._relationship(record_node, "OBSERVED_IN", region_node, record_id, timestamp, confidence, severity),
                    self._relationship(event_node, "AFFECTS", region_node, record_id, timestamp, confidence, severity),
                    self._relationship(region_node, "EVIDENCED_BY", record_node, record_id, timestamp, confidence, severity),
                ]
            )

        for geo_tag in row.get("geo_tags") or []:
            geo_node = self._geo_tag_node(geo_tag, record_id, timestamp)
            if not geo_node:
                continue
            nodes.append(geo_node)
            rels.extend(
                [
                    self._relationship(event_node, "AFFECTS", geo_node, record_id, timestamp, confidence, severity),
                    self._relationship(geo_node, "EVIDENCED_BY", record_node, record_id, timestamp, confidence, severity),
                ]
            )

        for entity_name in row.get("resolved_entities") or []:
            entity_node = self._entity_node(entity_name, record_id, timestamp)
            nodes.append(entity_node)
            rels.extend(
                [
                    self._relationship(record_node, "MENTIONS", entity_node, record_id, timestamp, confidence, severity),
                    self._relationship(event_node, "AFFECTS", entity_node, record_id, timestamp, confidence, severity),
                    self._relationship(entity_node, "EVIDENCED_BY", record_node, record_id, timestamp, confidence, severity),
                ]
            )

        # NLP entities from the `entities` field emitted by the enrichment step.
        # Each entry is {"text": "...", "label": "<spaCy NER label>"}.  This
        # field is absent in domains that skip NLP enrichment (e.g. historical,
        # inventory) — safe to iterate over an empty list.
        for nlp_ent in row.get("entities") or []:
            nlp_node = self._nlp_entity_node(nlp_ent, record_id, timestamp)
            if nlp_node is None:
                continue
            nodes.append(nlp_node)
            rels.extend(
                [
                    self._relationship(record_node, "MENTIONS", nlp_node, record_id, timestamp, confidence, severity),
                    self._relationship(event_node, "AFFECTS", nlp_node, record_id, timestamp, confidence, severity),
                    self._relationship(nlp_node, "EVIDENCED_BY", record_node, record_id, timestamp, confidence, severity),
                ]
            )

        commodity_node = self._commodity_node(row)
        if commodity_node:
            nodes.append(commodity_node)
            rels.extend(
                [
                    self._relationship(event_node, "AFFECTS", commodity_node, record_id, timestamp, confidence, severity),
                    self._relationship(commodity_node, "EVIDENCED_BY", record_node, record_id, timestamp, confidence, severity),
                ]
            )

        rels.extend(self._physical_flow_relationships(nodes, record_node, record_id, timestamp, confidence, severity))
        return GraphBatch(nodes=nodes, relationships=rels)

    def build_temporal_links(self, events: list[GraphNode]) -> list[GraphRelationship]:
        """Create temporal event chain edges ordered by timestamp and category."""
        unique: dict[str, GraphNode] = {event.key_value: event for event in events}
        ordered = sorted(
            unique.values(),
            key=lambda node: (
                str(node.properties.get("timestamp") or ""),
                EVENT_CATEGORY_ORDER.get(str(node.properties.get("event_type")), 999),
                node.key_value,
            ),
        )
        rels: list[GraphRelationship] = []
        for previous, current in zip(ordered, ordered[1:]):
            if previous.key_value == current.key_value:
                continue
            props = compact_dict(
                {
                    "timestamp": current.properties.get("timestamp"),
                    "valid_from": previous.properties.get("timestamp"),
                    "valid_to": current.properties.get("timestamp"),
                    "confidence": min(
                        float(previous.properties.get("confidence", 0.5)),
                        float(current.properties.get("confidence", 0.5)),
                    ),
                    "severity": max(
                        float(previous.properties.get("severity", 0.0)),
                        float(current.properties.get("severity", 0.0)),
                    ),
                }
            )
            rels.append(self._direct_relationship(previous, "PRECEDES", current, props))
            rels.append(self._direct_relationship(previous, "NEXT_EVENT", current, props))
            if self._may_trigger(previous, current):
                rels.append(self._direct_relationship(previous, "TRIGGERS", current, props))
        return rels

    def _load_energy_entities(self, path: Path) -> dict[str, dict[str, Any]]:
        if not path.exists():
            LOGGER.warning("Energy entity gazetteer not found: %s", path)
            return {}
        with path.open("r", encoding="utf-8") as handle:
            if yaml is not None:
                return yaml.safe_load(handle) or {}
            return self._parse_simple_energy_yaml(handle.read())

    def _parse_simple_energy_yaml(self, text: str) -> dict[str, dict[str, Any]]:
        """Parse the project's simple entity YAML when PyYAML is unavailable."""
        entities: dict[str, dict[str, Any]] = {}
        current: str | None = None
        for raw_line in text.splitlines():
            line = raw_line.split("#", 1)[0].rstrip()
            if not line.strip():
                continue
            if not line.startswith(" ") and line.endswith(":"):
                current = line[:-1].strip()
                entities[current] = {}
                continue
            if current is None or ":" not in line:
                continue
            key, value = line.strip().split(":", 1)
            value = value.strip()
            if value.startswith("[") and value.endswith("]"):
                entities[current][key] = [
                    item.strip().strip('"').strip("'")
                    for item in value[1:-1].split(",")
                    if item.strip()
                ]
            else:
                numeric_value = coerce_float(value)
                entities[current][key] = numeric_value if numeric_value is not None else value.strip('"').strip("'")
        return entities

    def _record_id(self, row: dict[str, Any]) -> str:
        return stable_id(
            "record",
            [
                row.get("source"),
                row.get("domain"),
                row.get("sub_category"),
                row.get("timestamp_utc"),
                row.get("url"),
                row.get("raw_text"),
                row.get("raw_value"),
            ],
        )

    def _event_category(self, row: dict[str, Any]) -> str:
        category = row.get("event_category") or DOMAIN_EVENT_CATEGORY.get(str(row.get("domain")), "supply_chain_signal")
        return slug(category)

    def _severity(self, row: dict[str, Any]) -> float:
        urgency = coerce_float(row.get("urgency_score")) or 0.0
        value = coerce_float(row.get("raw_value"))
        if urgency:
            return max(0.0, min(1.0, urgency))
        if value is None:
            return 0.3
        return max(0.0, min(1.0, abs(value) / 100.0))

    def _confidence(self, row: dict[str, Any]) -> float:
        score = 0.55
        if row.get("resolved_entities"):
            score += 0.2
        if row.get("geo_tags"):
            score += 0.1
        if row.get("linked_event_id"):
            score += 0.1
        if row.get("url"):
            score += 0.05
        return min(score, 0.98)

    def _entity_node(self, name: Any, record_id: str, timestamp: str | None) -> GraphNode:
        canonical = str(name).strip()
        metadata = self.energy_entities.get(canonical, {}) or {}
        entity_type = str(metadata.get("type") or "organization")
        label = ASSET_TYPE_TO_LABEL.get(slug(entity_type), "Organization")
        lat, lon = metadata.get("lat"), metadata.get("lon")
        if lat is None and label == "Country":
            centroid = resolve_country_centroid(canonical)
            if centroid:
                lat, lon = centroid
        return GraphNode(
            label=label,
            key_property=NODE_KEY_PROPERTY[label],
            key_value=stable_id(slug(label), [canonical]),
            properties=compact_dict(
                {
                    "entity_key": stable_id(slug(label), [canonical]),
                    "name": canonical,
                    "canonical_name": canonical,
                    "entity_type": entity_type,
                    "aliases": metadata.get("aliases"),
                    "lat": lat,
                    "lon": lon,
                    "valid_from": timestamp,
                    "first_seen_at": timestamp,
                    "record_ids": [record_id],
                }
            ),
        )

    def _location_node(self, region: Any, record_id: str, timestamp: str | None) -> GraphNode | None:
        if not region:
            return None
        name = str(region).strip()
        label = "Country" if "," not in name and len(name.split()) <= 3 else "Port"
        # Geospatial evidence: resolve a real centroid whenever the region
        # text names (or embeds) a known country, e.g. "Kyiv, Kyyiv, Misto,
        # Ukraine" -> Ukraine's centroid. Left as None (never fabricated)
        # when nothing resolves — see geodata.py for the matching rules.
        centroid = resolve_country_centroid(name)
        return GraphNode(
            label=label,
            key_property=NODE_KEY_PROPERTY[label],
            key_value=stable_id(slug(label), [name]),
            properties=compact_dict(
                {
                    "entity_key": stable_id(slug(label), [name]),
                    "name": name,
                    "entity_type": "region" if label == "Country" else "location",
                    "lat": centroid[0] if centroid else None,
                    "lon": centroid[1] if centroid else None,
                    "valid_from": timestamp,
                    "first_seen_at": timestamp,
                    "record_ids": [record_id],
                }
            ),
        )

    def _geo_tag_node(self, geo_tag: dict[str, Any], record_id: str, timestamp: str | None) -> GraphNode | None:
        name = geo_tag.get("name")
        if not name:
            return None
        entity_type = str(geo_tag.get("type") or "location")
        label = ASSET_TYPE_TO_LABEL.get(slug(entity_type), "Port")
        return GraphNode(
            label=label,
            key_property=NODE_KEY_PROPERTY[label],
            key_value=stable_id(slug(label), [name]),
            properties=compact_dict(
                {
                    "entity_key": stable_id(slug(label), [name]),
                    "name": name,
                    "entity_type": entity_type,
                    "lat": geo_tag.get("lat"),
                    "lon": geo_tag.get("lon"),
                    "valid_from": timestamp,
                    "first_seen_at": timestamp,
                    "record_ids": [record_id],
                }
            ),
        )

    # spaCy NER label → graph node label mapping.
    # Only labels actually observed in Part B data are mapped; everything else
    # falls through to ``Organization`` as a safe catch-all.
    _SPACY_LABEL_TO_GRAPH_LABEL: dict[str, str] = {
        "GPE": "Country",    # Geo-political entity (country / city / region)
        "LOC": "Port",       # Non-GPE location (mountain, water body, etc.)
        "FAC": "Terminal",   # Facility (airport, terminal, refinery)
        "ORG": "Organization",
        "PERSON": "Organization",  # individuals → generic org node
        "NORP": "Organization",    # nationalities / religious / political groups
    }

    def _nlp_entity_node(
        self, nlp_ent: dict[str, Any], record_id: str, timestamp: str | None
    ) -> GraphNode | None:
        """Build a graph node from a spaCy NER entity dict ``{text, label}``.

        Returns ``None`` for entries with an empty or whitespace-only text
        so the caller can safely skip them.
        """
        text = str(nlp_ent.get("text") or "").strip()
        if not text:
            return None
        spacy_label = str(nlp_ent.get("label") or "").upper()
        graph_label = self._SPACY_LABEL_TO_GRAPH_LABEL.get(spacy_label, "Organization")
        # Look up gazetteer for enrichment; fall back gracefully when absent.
        metadata = self.energy_entities.get(text, {}) or {}
        gazetteer_type = str(metadata.get("type") or "").strip()
        if gazetteer_type:
            graph_label = ASSET_TYPE_TO_LABEL.get(slug(gazetteer_type), graph_label)
        lat, lon = metadata.get("lat"), metadata.get("lon")
        if lat is None and graph_label == "Country":
            centroid = resolve_country_centroid(text)
            if centroid:
                lat, lon = centroid
        key_prop = NODE_KEY_PROPERTY[graph_label]
        key_value = stable_id(slug(graph_label), [text])
        return GraphNode(
            label=graph_label,
            key_property=key_prop,
            key_value=key_value,
            properties=compact_dict(
                {
                    "entity_key": key_value,
                    "name": text,
                    "canonical_name": text,
                    "entity_type": spacy_label.lower() or "nlp_entity",
                    "lat": lat,
                    "lon": lon,
                    "valid_from": timestamp,
                    "first_seen_at": timestamp,
                    "record_ids": [record_id],
                }
            ),
        )

    def _commodity_node(self, row: dict[str, Any]) -> GraphNode | None:
        text = " ".join(str(row.get(key) or "") for key in ("raw_text", "sub_category", "unit")).lower()
        commodity = None
        if "brent" in text:
            commodity = "Brent Crude"
        elif "wti" in text:
            commodity = "WTI Crude"
        elif "crude" in text or "oil" in text:
            commodity = "Crude Oil"
        elif "natural gas" in text or "lng" in text:
            commodity = "Natural Gas"
        if not commodity:
            return None
        key = stable_id("commodity", [commodity])
        return GraphNode(
            label="Commodity",
            key_property=NODE_KEY_PROPERTY["Commodity"],
            key_value=key,
            properties={"entity_key": key, "name": commodity, "entity_type": "commodity"},
        )

    def _relationship(
        self,
        start: GraphNode,
        rel_type: str,
        end: GraphNode,
        record_id: str,
        timestamp: str | None,
        confidence: float,
        severity: float,
    ) -> GraphRelationship:
        props = compact_dict(
            {
                "timestamp": timestamp,
                "valid_from": timestamp,
                "confidence": confidence,
                "severity": severity,
                "record_ids": [record_id],
                "evidence_count": 1,
            }
        )
        return self._direct_relationship(start, rel_type, end, props)

    def _direct_relationship(
        self, start: GraphNode, rel_type: str, end: GraphNode, properties: dict[str, Any]
    ) -> GraphRelationship:
        return GraphRelationship(
            start_label=start.label,
            start_key_property=start.key_property,
            start_key_value=start.key_value,
            relationship_type=rel_type,
            end_label=end.label,
            end_key_property=end.key_property,
            end_key_value=end.key_value,
            properties=properties,
        )

    def _physical_flow_relationships(
        self,
        nodes: list[GraphNode],
        record_node: GraphNode,
        record_id: str,
        timestamp: str | None,
        confidence: float,
        severity: float,
    ) -> list[GraphRelationship]:
        rels: list[GraphRelationship] = []
        by_label: dict[str, list[GraphNode]] = {}
        for node in nodes:
            by_label.setdefault(node.label, []).append(node)

        for country in by_label.get("Country", []):
            for port in by_label.get("Port", []):
                rels.append(self._relationship(country, "HAS_PORT", port, record_id, timestamp, confidence, severity))
        for port in by_label.get("Port", []):
            for route in by_label.get("ShippingRoute", []):
                rels.append(self._relationship(port, "CONNECTS_TO", route, record_id, timestamp, confidence, severity))
        for route in by_label.get("ShippingRoute", []):
            for terminal in by_label.get("Terminal", []):
                rels.append(self._relationship(route, "SUPPLIES", terminal, record_id, timestamp, confidence, severity))
        for terminal in by_label.get("Terminal", []):
            for refinery in by_label.get("Refinery", []):
                rels.append(self._relationship(terminal, "SUPPLIES", refinery, record_id, timestamp, confidence, severity))
        for refinery in by_label.get("Refinery", []):
            for storage in by_label.get("StorageTerminal", []):
                rels.append(self._relationship(refinery, "STORES_IN", storage, record_id, timestamp, confidence, severity))
        for storage in by_label.get("StorageTerminal", []):
            for power in by_label.get("PowerIndustry", []):
                rels.append(self._relationship(storage, "SUPPLIES", power, record_id, timestamp, confidence, severity))
        for power in by_label.get("PowerIndustry", []):
            for consumer in by_label.get("Consumer", []):
                rels.append(self._relationship(power, "SERVES", consumer, record_id, timestamp, confidence, severity))
        for supplier in by_label.get("Supplier", []):
            for refinery in by_label.get("Refinery", []):
                rels.append(self._relationship(supplier, "SUPPLIES", refinery, record_id, timestamp, confidence, severity))
        for commodity in by_label.get("Commodity", []):
            for route in by_label.get("ShippingRoute", []):
                rels.append(self._relationship(commodity, "TRANSPORTED_VIA", route, record_id, timestamp, confidence, severity))
        for rel in list(rels):
            rels.append(
                GraphRelationship(
                    start_label=rel.start_label,
                    start_key_property=rel.start_key_property,
                    start_key_value=rel.start_key_value,
                    relationship_type="EVIDENCED_BY",
                    end_label=record_node.label,
                    end_key_property=record_node.key_property,
                    end_key_value=record_node.key_value,
                    properties=rel.properties,
                )
            )
        return rels

    def _may_trigger(self, previous: GraphNode, current: GraphNode) -> bool:
        previous_order = EVENT_CATEGORY_ORDER.get(str(previous.properties.get("event_type")), 999)
        current_order = EVENT_CATEGORY_ORDER.get(str(current.properties.get("event_type")), 999)
        return previous_order < current_order

    def _merge_node(self, existing: GraphNode | None, incoming: GraphNode) -> GraphNode:
        if existing is None:
            return incoming
        props = dict(existing.properties)
        for key, value in incoming.properties.items():
            if key == "record_ids":
                props[key] = sorted(set(props.get(key, []) + value))
            elif key in {"last_seen_at", "valid_to"}:
                props[key] = max(str(props.get(key, "") or ""), str(value or "")) or value
            elif key in {"first_seen_at", "valid_from"}:
                current = str(props.get(key, "") or "")
                props[key] = min(current, str(value)) if current else value
            elif key in {"severity", "confidence"}:
                props[key] = max(float(props.get(key, 0.0)), float(value))
            elif props.get(key) in (None, "", []):
                props[key] = value
        return GraphNode(existing.label, existing.key_property, existing.key_value, compact_dict(props))

    def _merge_relationship(
        self, existing: GraphRelationship | None, incoming: GraphRelationship
    ) -> GraphRelationship:
        if existing is None:
            return incoming
        props = dict(existing.properties)
        record_ids = set(props.get("record_ids", []))
        record_ids.update(incoming.properties.get("record_ids", []))
        props["record_ids"] = sorted(record_ids)
        props["evidence_count"] = len(record_ids)
        props["confidence"] = max(float(props.get("confidence", 0.0)), float(incoming.properties.get("confidence", 0.0)))
        props["severity"] = max(float(props.get("severity", 0.0)), float(incoming.properties.get("severity", 0.0)))
        return GraphRelationship(
            existing.start_label,
            existing.start_key_property,
            existing.start_key_value,
            existing.relationship_type,
            existing.end_label,
            existing.end_key_property,
            existing.end_key_value,
            compact_dict(props),
        )
