"""Standalone Neo4j driver wrapper for Part D.

This module is intentionally independent of Part C's neo4j_client.py.
It uses the same neo4j driver package but has its own session management,
retry logic, and validation so that Parts C and D can evolve separately.
"""

from __future__ import annotations

import logging
import time
from typing import Any

try:
    from neo4j import GraphDatabase
    from neo4j.exceptions import Neo4jError, ServiceUnavailable, TransientError

    _NEO4J_AVAILABLE = True
    _NEO4J_IMPORT_ERROR: Exception | None = None
except ModuleNotFoundError as _exc:
    GraphDatabase = None  # type: ignore[assignment,misc]
    Neo4jError = RuntimeError  # type: ignore[assignment,misc]
    ServiceUnavailable = RuntimeError  # type: ignore[assignment,misc]
    TransientError = RuntimeError  # type: ignore[assignment,misc]
    _NEO4J_AVAILABLE = False
    _NEO4J_IMPORT_ERROR = _exc

from .config import RiskPredictionConfig

LOGGER = logging.getLogger(__name__)


class RiskPredictionNeo4jClient:
    """Manage Neo4j connections and execute read/write transactions for Part D.

    Usage (preferred — context manager ensures the driver is always closed)::

        with RiskPredictionNeo4jClient(config) as client:
            rows = client.run_read(query, params)
    """

    def __init__(self, config: RiskPredictionConfig) -> None:
        if not _NEO4J_AVAILABLE:
            raise RuntimeError(
                "Neo4j Python driver is not installed. "
                "Run: pip install -r scripts/risk_prediction/requirements.txt"
            ) from _NEO4J_IMPORT_ERROR

        self.config = config
        self._driver = GraphDatabase.driver(
            config.neo4j_uri,
            auth=(config.neo4j_user, config.neo4j_password),
            connection_timeout=config.connection_timeout_seconds,
            max_connection_pool_size=config.max_connection_pool_size,
        )
        LOGGER.debug("Neo4j driver initialised for %s", config.neo4j_uri)

    # ── Context manager ───────────────────────────────────────────────────────

    def __enter__(self) -> "RiskPredictionNeo4jClient":
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        """Close the underlying driver and release all pooled connections."""
        try:
            self._driver.close()
            LOGGER.debug("Neo4j driver closed.")
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("Error closing Neo4j driver: %s", exc)

    # ── Connectivity ──────────────────────────────────────────────────────────

    def verify_connectivity(self) -> None:
        """Verify Neo4j connectivity. Exits gracefully on failure with hints."""
        try:
            self._driver.verify_connectivity()
            LOGGER.info(
                "Neo4j connectivity verified: %s (database=%s)",
                self.config.neo4j_uri,
                self.config.neo4j_database or "default",
            )
        except Exception as exc:
            import sys
            LOGGER.error(
                "Failed to connect to Neo4j database or retrieve routing information.\n"
                "Troubleshooting hints:\n"
                "1. Verify that the URI is correct: %s\n"
                "2. Ensure your Aura database is running (not paused).\n"
                "3. Check your credentials (username: '%s').\n"
                "4. Verify your network allows traffic to the database port.\n"
                "Original error: %s",
                self.config.neo4j_uri,
                self.config.neo4j_user,
                exc,
            )
            sys.exit(1)

    # ── Read operations ───────────────────────────────────────────────────────

    def run_read(
        self,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> list[dict[str, Any]]:
        """Execute *query* inside a managed read transaction.

        Returns a list of dicts, one per result row.  Empty list on no results.
        """
        params = params or {}
        last_error: Exception | None = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                with self._driver.session(
                    database=self.config.neo4j_database
                ) as session:
                    result = session.execute_read(
                        lambda tx, q, p: [
                            dict(record) for record in tx.run(q, **p)
                        ],
                        query,
                        params,
                    )
                    return result
            except (ServiceUnavailable, TransientError, Neo4jError) as exc:
                last_error = exc
                if attempt >= self.config.max_retries:
                    break
                sleep_s = self.config.retry_backoff_seconds * attempt
                LOGGER.warning(
                    "Read failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt,
                    self.config.max_retries,
                    exc,
                    sleep_s,
                )
                time.sleep(sleep_s)

        raise RuntimeError(
            f"Neo4j read failed after {self.config.max_retries} attempts."
        ) from last_error

    # ── Write operations ──────────────────────────────────────────────────────

    def run_write(
        self,
        query: str,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Execute *query* inside a managed write transaction.

        Returns the SummaryCounters as a dict (nodes_created, etc.).
        """
        params = params or {}
        last_error: Exception | None = None

        for attempt in range(1, self.config.max_retries + 1):
            try:
                with self._driver.session(
                    database=self.config.neo4j_database
                ) as session:
                    summary = session.execute_write(
                        lambda tx, q, p: tx.run(q, **p).consume(),
                        query,
                        params,
                    )
                    counters = summary.counters
                    return {
                        "nodes_created": counters.nodes_created,
                        "nodes_deleted": counters.nodes_deleted,
                        "relationships_created": counters.relationships_created,
                        "properties_set": counters.properties_set,
                    }
            except (ServiceUnavailable, TransientError, Neo4jError) as exc:
                last_error = exc
                if attempt >= self.config.max_retries:
                    break
                sleep_s = self.config.retry_backoff_seconds * attempt
                LOGGER.warning(
                    "Write failed (attempt %d/%d): %s — retrying in %.1fs",
                    attempt,
                    self.config.max_retries,
                    exc,
                    sleep_s,
                )
                time.sleep(sleep_s)

        raise RuntimeError(
            f"Neo4j write failed after {self.config.max_retries} attempts."
        ) from last_error
