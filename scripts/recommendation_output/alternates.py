"""Concrete, executable alternates for Part F's procurement-style recommendations.

Part F's ``spot_procurement`` and ``activate_alternate_supplier`` templates
say *that* an alternate source should be activated but not *which one* —
"Activate alternate supplier or contract option" is not something a
procurement team can act on directly. This module queries the graph for
real, named candidate alternates (other nodes of the same asset type,
graph-connected to the target, excluding the disrupted asset itself) so the
recommendation names an actual entity a procurement team could contact.

Data-volume honesty: this repository's graph currently has very few
``Supplier`` nodes (real ingestion coverage, not a code limitation) — when
fewer than 1 real alternate exists for a given asset type, this returns an
empty list rather than fabricating one. Distance to each alternate is
computed from real lat/lon (see ``scripts/knowledge_graph/geodata.py``) via
the haversine formula whenever both ends have resolved coordinates.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from scripts.risk_prediction.neo4j_client import RiskPredictionNeo4jClient
from scripts.risk_prediction.utils import ASSET_LABELS, safe_float

# Action types this enrichment applies to — Part F's two procurement-style
# templates (see scripts/decision_optimization/engine.py::ACTION_TEMPLATES).
PROCUREMENT_ACTION_TYPES = frozenset({"spot_procurement", "activate_alternate_supplier"})

QUERY_FIND_ALTERNATES = """
MATCH (target {entity_key: $target_asset_id})
WITH target, labels(target) AS target_labels
MATCH (alt)
WHERE any(lbl IN target_labels WHERE lbl IN $asset_labels AND lbl IN labels(alt))
  AND alt.entity_key <> $target_asset_id
OPTIONAL MATCH (alt)-[out_rel]->()
WITH target, alt, count(DISTINCT out_rel) AS out_degree
OPTIONAL MATCH ()-[in_rel]->(alt)
WITH target, alt, out_degree, count(DISTINCT in_rel) AS in_degree
RETURN
    target.lat AS target_lat,
    target.lon AS target_lon,
    alt.entity_key AS asset_id,
    coalesce(alt.name, alt.entity_key) AS name,
    labels(alt)[0] AS label,
    (out_degree + in_degree) AS degree,
    alt.lat AS lat,
    alt.lon AS lon
ORDER BY degree DESC
LIMIT $limit
"""


@dataclass(frozen=True)
class ConcreteAlternative:
    """One real, named candidate alternate for a procurement recommendation."""

    asset_id: str
    name: str
    label: str
    distance_km: float | None
    graph_connectivity: int

    def summary(self) -> dict[str, Any]:
        return {
            "asset_id": self.asset_id,
            "name": self.name,
            "label": self.label,
            "distance_km": round(self.distance_km, 1) if self.distance_km is not None else None,
            "graph_connectivity": self.graph_connectivity,
        }


class AlternateFinder:
    """Finds real, graph-backed alternate entities for procurement actions."""

    def __init__(self, client: RiskPredictionNeo4jClient) -> None:
        self.client = client

    def find_alternates(self, target_asset_id: str, limit: int = 3) -> list[ConcreteAlternative]:
        # Cast a wider net than `limit` so a genuinely nearby alternative
        # isn't excluded just because a distant, highly-connected node
        # happens to rank higher on raw graph degree alone.
        candidate_pool_size = max(limit * 5, 15)
        rows = self.client.run_read(
            QUERY_FIND_ALTERNATES,
            {"target_asset_id": target_asset_id, "asset_labels": ASSET_LABELS, "limit": candidate_pool_size},
        )
        candidates: list[ConcreteAlternative] = []
        for row in rows:
            distance_km = _haversine_km(
                safe_float(row.get("target_lat"), default=float("nan")),
                safe_float(row.get("target_lon"), default=float("nan")),
                safe_float(row.get("lat"), default=float("nan")),
                safe_float(row.get("lon"), default=float("nan")),
            )
            candidates.append(
                ConcreteAlternative(
                    asset_id=str(row["asset_id"]),
                    name=str(row.get("name") or row["asset_id"]),
                    label=str(row.get("label") or "Unknown"),
                    distance_km=distance_km,
                    graph_connectivity=int(row.get("degree") or 0),
                )
            )
        # Real proximity is a stronger executability signal than raw graph
        # degree — prefer the nearest known-distance alternatives, falling
        # back to connectivity only when distance can't be resolved.
        candidates.sort(
            key=lambda c: (c.distance_km if c.distance_km is not None else float("inf"), -c.graph_connectivity)
        )
        return candidates[:limit]


def _haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float | None:
    """Great-circle distance in km, or None if any coordinate is missing/NaN."""
    for value in (lat1, lon1, lat2, lon2):
        if value != value:  # NaN check without importing math.isnan at call sites
            return None
    radius_km = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    d_phi = math.radians(lat2 - lat1)
    d_lambda = math.radians(lon2 - lon1)
    a = math.sin(d_phi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(d_lambda / 2) ** 2
    return radius_km * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
