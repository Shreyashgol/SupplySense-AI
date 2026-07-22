"""One-off maintenance: backfill lat/lon onto existing Country/Port nodes.

``transformer.py`` now resolves a real country centroid for every new
Country/Port node it creates (see ``geodata.py``), but that only takes
effect on the next ingestion run. This script patches nodes that already
exist in Neo4j from before that fix, without requiring a full Part A-C
re-run.

Usage::

    python3 -m scripts.knowledge_graph.backfill_geodata
"""

from __future__ import annotations

import logging

from scripts.risk_prediction.config import RiskPredictionConfig
from scripts.risk_prediction.neo4j_client import RiskPredictionNeo4jClient

from .geodata import resolve_country_centroid
from .logging_config import configure_logging

LOGGER = logging.getLogger(__name__)

QUERY_FIND_UNRESOLVED = """
MATCH (a) WHERE (a:Country OR a:Port) AND a.lat IS NULL
RETURN a.entity_key AS entity_key, a.name AS name, labels(a)[0] AS label
"""

QUERY_SET_COORDINATES = """
MATCH (a {entity_key: $entity_key})
SET a.lat = $lat, a.lon = $lon
"""


def run() -> None:
    config = RiskPredictionConfig.from_env()
    config.validate()
    with RiskPredictionNeo4jClient(config) as client:
        client.verify_connectivity()
        rows = client.run_read(QUERY_FIND_UNRESOLVED)
        LOGGER.info("Found %d Country/Port node(s) without coordinates.", len(rows))

        resolved = 0
        unresolved: list[str] = []
        for row in rows:
            centroid = resolve_country_centroid(str(row.get("name") or ""))
            if centroid is None:
                unresolved.append(f"{row.get('label')}:{row.get('name')}")
                continue
            client.run_write(
                QUERY_SET_COORDINATES,
                {"entity_key": row["entity_key"], "lat": centroid[0], "lon": centroid[1]},
            )
            resolved += 1

        LOGGER.info(
            "Geodata backfill complete: %d resolved, %d left without coordinates "
            "(no known country name matched — left as None, not fabricated).",
            resolved,
            len(unresolved),
        )
        if unresolved:
            LOGGER.info("Unresolved sample: %s", unresolved[:20])


if __name__ == "__main__":
    configure_logging("INFO")
    run()
