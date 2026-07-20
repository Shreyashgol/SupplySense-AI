"""Graph feature extraction pipeline for Part D.

Reads exclusively from the Neo4j graph produced by Part C.
No JSONL files are read here — all data comes from the graph.

Feature extraction runs four parameterised Cypher queries per pass:

  1. QUERY_EVENT_FEATURES      — event counts, domain severity, NLP scores, recency
  2. QUERY_ANOMALY_FEATURES    — anomaly rate via Record nodes
  3. QUERY_TOPOLOGY_FEATURES   — degree, cluster size, upstream/downstream counts
  4. QUERY_CASCADE_DEPTH       — max TRIGGERS chain depth (depth limited by config)

Results are joined in Python on ``asset_id`` and returned as AssetFeatures objects.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta, timezone
from typing import Any

from .config import RiskPredictionConfig
from .models import AssetFeatures
from .neo4j_client import RiskPredictionNeo4jClient
from .queries import (
    QUERY_ANOMALY_FEATURES,
    QUERY_CASCADE_DEPTH,
    QUERY_EVENT_FEATURES,
    QUERY_TOPOLOGY_FEATURES,
)
from .utils import ASSET_LABELS, days_since, encode_asset_type, safe_float, safe_int

LOGGER = logging.getLogger(__name__)


class GraphFeatureExtractor:
    """Extract graph-derived ML features from the Part C Neo4j knowledge graph.

    Example::

        config = RiskPredictionConfig.from_env()
        with RiskPredictionNeo4jClient(config) as client:
            extractor = GraphFeatureExtractor(config, client)
            features = extractor.extract_all()
    """

    def __init__(
        self,
        config: RiskPredictionConfig,
        client: RiskPredictionNeo4jClient,
    ) -> None:
        self.config = config
        self.client = client

    # ── Public API ────────────────────────────────────────────────────────────

    def extract_all(self) -> list[AssetFeatures]:
        """Extract features for every supply-chain asset in the graph."""
        return self._extract(asset_id="")

    def extract_asset(self, asset_id: str) -> list[AssetFeatures]:
        """Extract features for a single asset identified by *asset_id*."""
        if not asset_id:
            raise ValueError("asset_id must be a non-empty string.")
        return self._extract(asset_id=asset_id)

    # ── Core extraction ───────────────────────────────────────────────────────

    def _extract(self, asset_id: str) -> list[AssetFeatures]:
        """Run all four queries and merge results by asset_id."""
        cutoff_short, cutoff_long = self._compute_cutoffs()
        base_params: dict[str, Any] = {
            "asset_labels": ASSET_LABELS,
            "asset_id": asset_id,
        }

        LOGGER.info(
            "Starting feature extraction (asset_id=%r, window_short=%dd, window_long=%dd)",
            asset_id or "<all>",
            self.config.window_short_days,
            self.config.window_long_days,
        )

        # ── Query 1: event features ───────────────────────────────────────────
        LOGGER.debug("Running QUERY_EVENT_FEATURES …")
        event_rows = self.client.run_read(
            QUERY_EVENT_FEATURES,
            {**base_params, "cutoff_short": cutoff_short, "cutoff_long": cutoff_long},
        )
        LOGGER.info("Event features returned %d asset rows.", len(event_rows))

        # ── Query 2: anomaly features ─────────────────────────────────────────
        LOGGER.debug("Running QUERY_ANOMALY_FEATURES …")
        anomaly_rows = self.client.run_read(QUERY_ANOMALY_FEATURES, base_params)
        anomaly_map: dict[str, float] = {
            row["asset_id"]: safe_float(row.get("anomaly_rate"))
            for row in anomaly_rows
            if row.get("asset_id")
        }

        # ── Query 3: topology features ────────────────────────────────────────
        LOGGER.debug("Running QUERY_TOPOLOGY_FEATURES …")
        topology_rows = self.client.run_read(QUERY_TOPOLOGY_FEATURES, base_params)
        topology_map: dict[str, dict[str, Any]] = {
            row["asset_id"]: row
            for row in topology_rows
            if row.get("asset_id")
        }

        # ── Query 4: cascade depth ────────────────────────────────────────────
        cascade_query = QUERY_CASCADE_DEPTH.format(
            max_depth=self.config.cascade_max_depth
        )
        LOGGER.debug(
            "Running QUERY_CASCADE_DEPTH (max_depth=%d) …",
            self.config.cascade_max_depth,
        )
        cascade_rows = self.client.run_read(cascade_query, base_params)
        cascade_map: dict[str, int] = {
            row["asset_id"]: safe_int(row.get("cascade_depth"))
            for row in cascade_rows
            if row.get("asset_id")
        }

        # ── Merge all results ─────────────────────────────────────────────────
        features: list[AssetFeatures] = []
        skipped = 0

        for row in event_rows:
            aid = row.get("asset_id")
            if not aid:
                skipped += 1
                LOGGER.debug("Skipping row with no asset_id: %r", row)
                continue

            label = str(row.get("asset_label") or "Organization")
            topo = topology_map.get(aid, {})

            af = AssetFeatures(
                asset_id=aid,
                asset_label=label,
                asset_name=str(row.get("asset_name") or aid),
                # ── temporal event counts ──
                event_count_last_7_days=safe_int(row.get("event_count_last_7_days")),
                event_count_last_30_days=safe_int(
                    row.get("event_count_last_30_days")
                ),
                # ── domain severity averages ──
                geopolitical_score=safe_float(row.get("geopolitical_score")),
                weather_score=safe_float(row.get("weather_score")),
                market_score=safe_float(row.get("market_score")),
                policy_score=safe_float(row.get("policy_score")),
                # ── NLP signal averages ──
                urgency_average=safe_float(row.get("urgency_average")),
                sentiment_average=safe_float(row.get("sentiment_average")),
                # ── record anomaly rate ──
                anomaly_rate=anomaly_map.get(aid, 0.0),
                # ── graph topology ──
                cascade_depth=cascade_map.get(aid, 0),
                upstream_trigger_count=safe_int(topo.get("upstream_trigger_count")),
                downstream_affected_assets=safe_int(
                    topo.get("downstream_affected_assets")
                ),
                cluster_size=safe_int(topo.get("cluster_size")),
                evidence_count=safe_float(row.get("evidence_count")),
                degree_centrality=safe_int(topo.get("degree_centrality")),
                # ── recency ──
                days_since_last_event=days_since(
                    row.get("last_event_at")  # type: ignore[arg-type]
                ),
                # ── encoded label ──
                asset_type_code=encode_asset_type(label),
            )
            features.append(af)

        LOGGER.info(
            "Feature extraction complete: %d assets extracted, %d skipped.",
            len(features),
            skipped,
        )
        return features

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _compute_cutoffs(self) -> tuple[str, str]:
        """Return ISO-8601 UTC cutoff strings for short and long windows."""
        now = datetime.now(timezone.utc)
        cutoff_short = (
            now - timedelta(days=self.config.window_short_days)
        ).isoformat()
        cutoff_long = (
            now - timedelta(days=self.config.window_long_days)
        ).isoformat()
        return cutoff_short, cutoff_long
