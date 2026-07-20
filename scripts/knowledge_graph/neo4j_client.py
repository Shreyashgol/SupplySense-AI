"""Neo4j driver wrapper with batch transactions and retry logic."""

from __future__ import annotations

import logging
import time
from pathlib import Path
from typing import Any, Callable

try:
    from neo4j import GraphDatabase, Query
    from neo4j.exceptions import Neo4jError, ServiceUnavailable, TransientError
except ModuleNotFoundError as exc:  # pragma: no cover - depends on local environment
    GraphDatabase = None
    Query = str
    Neo4jError = RuntimeError
    ServiceUnavailable = RuntimeError
    TransientError = RuntimeError
    NEO4J_IMPORT_ERROR = exc
else:
    NEO4J_IMPORT_ERROR = None

from .config import KnowledgeGraphConfig
from .graph_schema import NODE_KEY_PROPERTY, RELATIONSHIP_TYPES, SUPPLY_CHAIN_NODE_LABELS
from .models import GraphNode, GraphRelationship
from .utils import chunks

LOGGER = logging.getLogger(__name__)


class Neo4jKnowledgeGraphClient:
    """Manage Neo4j connections and idempotent graph writes."""

    def __init__(self, config: KnowledgeGraphConfig) -> None:
        self.config = config
        if GraphDatabase is None:
            raise RuntimeError(
                "Neo4j Python Driver is not installed. "
                "Install scripts/knowledge_graph/requirements.txt before loading the graph."
            ) from NEO4J_IMPORT_ERROR
        self.driver = GraphDatabase.driver(
            config.neo4j_uri,
            auth=(config.neo4j_user, config.neo4j_password),
            connection_timeout=config.connection_timeout_seconds,
            max_connection_pool_size=config.max_connection_pool_size,
        )

    def close(self) -> None:
        """Close the underlying Neo4j driver."""
        self.driver.close()

    def verify_connectivity(self) -> None:
        """Verify Neo4j connectivity before running graph operations."""
        self.driver.verify_connectivity()

    def apply_schema_file(self, path: Path) -> None:
        """Execute all semicolon-delimited Cypher statements in a schema file."""
        statements = [statement.strip() for statement in path.read_text(encoding="utf-8").split(";")]
        for statement in statements:
            if statement:
                LOGGER.info("Applying schema statement from %s", path.name)
                self.execute_write(lambda tx, cypher: tx.run(cypher).consume(), statement)

    def write_nodes(self, nodes: list[GraphNode]) -> int:
        """Batch upsert graph nodes."""
        written = 0
        for batch in chunks(nodes, self.config.batch_size):
            grouped: dict[str, list[dict[str, Any]]] = {}
            for node in batch:
                self._validate_label(node.label)
                grouped.setdefault(node.label, []).append(
                    {"key": node.key_value, "properties": node.properties}
                )
            for label, rows in grouped.items():
                key_property = NODE_KEY_PROPERTY[label]
                cypher = (
                    f"""
                    UNWIND $rows AS row
                    MERGE (n:`{label}` {{`{key_property}`: row.key}})
                    WITH n, row, coalesce(n.record_ids, []) + coalesce(row.properties.record_ids, []) AS evidence_ids
                    UNWIND CASE WHEN size(evidence_ids) = 0 THEN [NULL] ELSE evidence_ids END AS evidence_id
                    WITH n, row, [item IN collect(DISTINCT evidence_id) WHERE item IS NOT NULL] AS record_ids
                    SET n += row.properties
                    SET n.record_ids = CASE WHEN size(record_ids) > 0 THEN record_ids ELSE n.record_ids END
                    """
                )
                self.execute_write(lambda tx, query, params: tx.run(query, **params).consume(), cypher, {"rows": rows})
                written += len(rows)
        return written

    def write_relationships(self, relationships: list[GraphRelationship]) -> int:
        """Batch upsert graph relationships."""
        written = 0
        for batch in chunks(relationships, self.config.batch_size):
            grouped: dict[tuple[str, str, str], list[dict[str, Any]]] = {}
            for rel in batch:
                self._validate_label(rel.start_label)
                self._validate_label(rel.end_label)
                self._validate_relationship(rel.relationship_type)
                grouped.setdefault((rel.start_label, rel.relationship_type, rel.end_label), []).append(
                    {
                        "start_key": rel.start_key_value,
                        "end_key": rel.end_key_value,
                        "properties": rel.properties,
                    }
                )
            for (start_label, rel_type, end_label), rows in grouped.items():
                start_key = NODE_KEY_PROPERTY[start_label]
                end_key = NODE_KEY_PROPERTY[end_label]
                cypher = (
                    f"""
                    UNWIND $rows AS row
                    MATCH (a:`{start_label}` {{`{start_key}`: row.start_key}})
                    MATCH (b:`{end_label}` {{`{end_key}`: row.end_key}})
                    MERGE (a)-[r:`{rel_type}`]->(b)
                    WITH r, row, coalesce(r.record_ids, []) + coalesce(row.properties.record_ids, []) AS evidence_ids
                    UNWIND CASE WHEN size(evidence_ids) = 0 THEN [NULL] ELSE evidence_ids END AS evidence_id
                    WITH r, row, [item IN collect(DISTINCT evidence_id) WHERE item IS NOT NULL] AS record_ids
                    SET r += row.properties
                    SET r.record_ids = CASE WHEN size(record_ids) > 0 THEN record_ids ELSE r.record_ids END,
                        r.evidence_count = CASE WHEN size(record_ids) > 0 THEN size(record_ids) ELSE r.evidence_count END
                    """
                )
                self.execute_write(lambda tx, query, params: tx.run(query, **params).consume(), cypher, {"rows": rows})
                written += len(rows)
        return written

    def execute_write(self, work: Callable[..., Any], *args: Any) -> Any:
        """Execute a write transaction with retry handling."""
        last_error: Exception | None = None
        for attempt in range(1, self.config.max_retries + 1):
            try:
                with self.driver.session(database=self.config.neo4j_database) as session:
                    return session.execute_write(work, *args)
            except (ServiceUnavailable, TransientError, Neo4jError) as exc:
                last_error = exc
                if attempt >= self.config.max_retries:
                    break
                sleep_seconds = self.config.retry_backoff_seconds * attempt
                LOGGER.warning(
                    "Neo4j write failed on attempt %s/%s: %s. Retrying in %.1fs",
                    attempt,
                    self.config.max_retries,
                    exc,
                    sleep_seconds,
                )
                time.sleep(sleep_seconds)
        raise RuntimeError("Neo4j write failed after retries.") from last_error

    def _validate_label(self, label: str) -> None:
        if label not in SUPPLY_CHAIN_NODE_LABELS:
            raise ValueError(f"Unsupported Neo4j label: {label}")

    def _validate_relationship(self, relationship_type: str) -> None:
        if relationship_type not in RELATIONSHIP_TYPES:
            raise ValueError(f"Unsupported Neo4j relationship type: {relationship_type}")
