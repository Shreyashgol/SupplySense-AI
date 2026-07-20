"""Parameterised Cypher query constants for Part D risk prediction.

Design principles
-----------------
* All Cypher is kept here — no query strings in other modules.
* Every query uses ``$`` parameters; nothing is string-interpolated at
  runtime except ``{max_depth}`` in QUERY_CASCADE_DEPTH, which must be
  an integer literal (Neo4j does not support parameterised path lengths).
* Asset label filtering uses the Cypher ``any()`` predicate over ``$asset_labels``
  (a list parameter) so the query remains label-agnostic.
* ``$asset_id = ''`` acts as a "no filter" sentinel: when passed as an empty
  string the ``OR`` short-circuits and all assets are returned; when a real
  ID is supplied only that asset is returned.

Query inventory
---------------
QUERY_EVENT_FEATURES     — event counts, domain severity, NLP scores, recency
QUERY_ANOMALY_FEATURES   — per-asset anomaly rate from linked Record nodes
QUERY_TOPOLOGY_FEATURES  — degree centrality, upstream triggers, downstream
                           assets, cluster size
QUERY_CASCADE_DEPTH      — max TRIGGERS chain depth reaching each asset
                           (use str.format(max_depth=N) before executing)
QUERY_UPSERT_RISK_ASSESSMENT  — batch MERGE RiskAssessment nodes + link
"""

from __future__ import annotations

# ── Event-level features ──────────────────────────────────────────────────────
# Returns one row per asset with aggregated event counts and NLP scores.
# Parameters:
#   $asset_labels  list[str]  — e.g. ["Country","Port","Refinery", ...]
#   $asset_id      str        — specific asset_id or '' for all assets
#   $cutoff_short  str        — ISO-8601 UTC cutoff for short window
#   $cutoff_long   str        — ISO-8601 UTC cutoff for long window
QUERY_EVENT_FEATURES = """
MATCH (asset)
WHERE any(lbl IN labels(asset) WHERE lbl IN $asset_labels)
  AND ($asset_id = '' OR asset.entity_key = $asset_id)
OPTIONAL MATCH (ev:Event)-[:AFFECTS]->(asset)
RETURN
    asset.entity_key AS asset_id,
    [lbl IN labels(asset) WHERE lbl IN $asset_labels][0] AS asset_label,
    coalesce(asset.name, asset.entity_key) AS asset_name,
    count(CASE WHEN ev IS NOT NULL
                AND ev.valid_from IS NOT NULL
                AND ev.valid_from >= $cutoff_short THEN 1 END)
        AS event_count_last_7_days,
    count(CASE WHEN ev IS NOT NULL
                AND ev.valid_from IS NOT NULL
                AND ev.valid_from >= $cutoff_long  THEN 1 END)
        AS event_count_last_30_days,
    avg(CASE WHEN ev.domain = 'geopolitical'
              AND ev.severity IS NOT NULL
             THEN toFloat(ev.severity) END)
        AS geopolitical_score,
    avg(CASE WHEN ev.domain = 'weather_climate'
              AND ev.severity IS NOT NULL
             THEN toFloat(ev.severity) END)
        AS weather_score,
    avg(CASE WHEN ev.domain = 'market'
              AND ev.severity IS NOT NULL
             THEN toFloat(ev.severity) END)
        AS market_score,
    avg(CASE WHEN ev.domain = 'policy'
              AND ev.severity IS NOT NULL
             THEN toFloat(ev.severity) END)
        AS policy_score,
    avg(CASE WHEN ev.urgency_score IS NOT NULL
             THEN toFloat(ev.urgency_score) END)
        AS urgency_average,
    avg(CASE WHEN ev.sentiment_score IS NOT NULL
             THEN toFloat(ev.sentiment_score) END)
        AS sentiment_average,
    coalesce(
        sum(CASE WHEN ev.confidence IS NOT NULL
                 THEN toFloat(ev.confidence) ELSE 0.0 END),
        0.0)
        AS evidence_count,
    max(CASE WHEN ev.valid_from IS NOT NULL THEN ev.valid_from END)
        AS last_event_at
ORDER BY asset_id
"""

# ── Anomaly rate from Record nodes ────────────────────────────────────────────
# Traverses Event -[:EVIDENCED_BY]-> Record to measure anomaly prevalence.
# Parameters: $asset_labels, $asset_id (same semantics as above)
QUERY_ANOMALY_FEATURES = """
MATCH (asset)
WHERE any(lbl IN labels(asset) WHERE lbl IN $asset_labels)
  AND ($asset_id = '' OR asset.entity_key = $asset_id)
OPTIONAL MATCH (ev:Event)-[:AFFECTS]->(asset)
OPTIONAL MATCH (ev)-[:EVIDENCED_BY]->(r:Record)
WITH
    asset.entity_key AS asset_id,
    count(r)                                                   AS total_records,
    count(CASE WHEN r.anomaly_flag = true THEN 1 END)          AS anomaly_count
RETURN
    asset_id,
    CASE WHEN total_records > 0
         THEN toFloat(anomaly_count) / toFloat(total_records)
         ELSE 0.0
    END AS anomaly_rate
ORDER BY asset_id
"""

# ── Graph topology features ───────────────────────────────────────────────────
# Computes degree centrality, upstream trigger count, downstream affected assets,
# and event cluster size.  Each sub-pattern is computed in a separate WITH stage
# to prevent Cartesian product inflation across different relationship types.
# Parameters: $asset_labels, $asset_id
QUERY_TOPOLOGY_FEATURES = """
MATCH (asset)
WHERE any(lbl IN labels(asset) WHERE lbl IN $asset_labels)
  AND ($asset_id = '' OR asset.entity_key = $asset_id)

// Step 1 — degree centrality (computed before event expansion to avoid inflation)
OPTIONAL MATCH (asset)-[out_rel]->()
WITH asset, count(DISTINCT out_rel) AS out_degree
OPTIONAL MATCH ()-[in_rel]->(asset)
WITH asset, out_degree, count(DISTINCT in_rel) AS in_degree

// Step 2 — upstream trigger count:
//   events that TRIGGER other events which AFFECT this asset
OPTIONAL MATCH (upstream_ev:Event)-[:TRIGGERS]->(ev:Event)-[:AFFECTS]->(asset)
WITH asset, out_degree, in_degree, count(DISTINCT upstream_ev) AS upstream_trigger_count

// Step 3 — downstream affected assets:
//   assets affected by events that are triggered BY events affecting this asset
OPTIONAL MATCH (ev2:Event)-[:AFFECTS]->(asset)
OPTIONAL MATCH (ev2)-[:TRIGGERS]->(d_ev:Event)-[:AFFECTS]->(asset2)
WHERE any(lbl2 IN labels(asset2) WHERE lbl2 IN $asset_labels)
  AND asset2.entity_key <> asset.entity_key
WITH asset, out_degree, in_degree, upstream_trigger_count,
     count(DISTINCT asset2) AS downstream_affected_assets

// Step 4 — cluster size: peer events in the same EventCluster
OPTIONAL MATCH (ev3:Event)-[:AFFECTS]->(asset)
OPTIONAL MATCH (ev3)-[:PART_OF_CLUSTER]->(ec:EventCluster)<-[:PART_OF_CLUSTER]-(ev_peer:Event)
WITH asset, out_degree, in_degree, upstream_trigger_count, downstream_affected_assets,
     count(DISTINCT ev_peer) AS cluster_size

RETURN
    asset.entity_key                         AS asset_id,
    (out_degree + in_degree)                 AS degree_centrality,
    upstream_trigger_count,
    downstream_affected_assets,
    coalesce(cluster_size, 0)                AS cluster_size
ORDER BY asset_id
"""

# ── Cascade depth ─────────────────────────────────────────────────────────────
# Finds the maximum TRIGGERS chain depth reaching each asset.
# IMPORTANT: path length is not a Cypher parameter — use str.format(max_depth=N)
#            before executing this query (default N=4, configured via RP_CASCADE_MAX_DEPTH).
#
# length(path) counts total relationships in path; the path structure is:
#   (trigger_chain)-[:TRIGGERS*1..N]->(ev)-[:AFFECTS]->(asset)
# so length(path) − 1 gives the number of pure TRIGGERS hops.
# Parameters: $asset_labels, $asset_id
QUERY_CASCADE_DEPTH = """
MATCH (asset)
WHERE any(lbl IN labels(asset) WHERE lbl IN $asset_labels)
  AND ($asset_id = '' OR asset.entity_key = $asset_id)
OPTIONAL MATCH path =
    (trigger_chain:Event)-[:TRIGGERS*1..{max_depth}]->(ev:Event)-[:AFFECTS]->(asset)
WITH
    asset.entity_key AS asset_id,
    max(CASE WHEN path IS NOT NULL THEN length(path) - 1 ELSE 0 END) AS cascade_depth
RETURN
    asset_id,
    coalesce(cascade_depth, 0) AS cascade_depth
ORDER BY asset_id
"""

# ── RiskAssessment write-back ─────────────────────────────────────────────────
# Batch MERGE RiskAssessment nodes and link them to their source asset.
# Idempotent: repeated runs update existing nodes rather than creating duplicates.
# Parameters:
#   $rows          list[dict]  — one dict per assessment (see predictor.py)
#   $asset_labels  list[str]   — used to match the correct asset node
QUERY_UPSERT_RISK_ASSESSMENT = """
UNWIND $rows AS row
MERGE (ra:RiskAssessment {assessment_id: row.assessment_id})
ON CREATE SET ra.created_at = row.predicted_at
SET
    ra.risk_score              = row.risk_score,
    ra.risk_tier               = row.risk_tier,
    ra.predicted_at            = row.predicted_at,
    ra.model_version           = row.model_version,
    ra.feature_importance_json = row.feature_importance_json,
    ra.asset_id                = row.asset_id,
    ra.asset_label             = row.asset_label,
    ra.asset_name              = row.asset_name,
    ra.updated_at              = row.predicted_at
WITH ra, row
MATCH (asset)
WHERE any(lbl IN labels(asset) WHERE lbl IN $asset_labels)
  AND asset.entity_key = row.asset_id
MERGE (asset)-[:HAS_RISK_ASSESSMENT]->(ra)
"""
