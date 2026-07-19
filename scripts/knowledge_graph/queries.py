"""Reusable Cypher queries for downstream analysis and validation."""

from __future__ import annotations


RECENT_EVENTS_FOR_ASSET = """
MATCH (e:Event)-[:AFFECTS]->(asset)
WHERE asset.entity_key = $entity_key
  AND datetime(e.timestamp) >= datetime($since)
RETURN e, asset
ORDER BY e.timestamp DESC
LIMIT $limit
"""

EVENT_CHAIN = """
MATCH path = (start:Event {event_id: $event_id})-[:NEXT_EVENT|TRIGGERS*1..10]->(next:Event)
WHERE length(path) <= $depth
RETURN path
LIMIT $limit
"""

HIGH_SEVERITY_DISRUPTIONS = """
MATCH (e:Event)-[:AFFECTS]->(asset)
WHERE e.severity >= $min_severity
RETURN e.event_id AS event_id,
       e.event_type AS event_type,
       e.timestamp AS timestamp,
       e.severity AS severity,
       labels(asset) AS asset_labels,
       asset.name AS asset_name
ORDER BY e.severity DESC, e.timestamp DESC
LIMIT $limit
"""

PROVENANCE_FOR_EVENT = """
MATCH (e:Event {event_id: $event_id})-[:EVIDENCED_BY]->(r:Record)
RETURN r
ORDER BY r.timestamp DESC
"""
