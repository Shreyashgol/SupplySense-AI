"""High-level orchestration for loading Part B JSONL into Neo4j."""

from __future__ import annotations

import logging
from pathlib import Path

from .config import KnowledgeGraphConfig
from .models import ProcessedRecord
from .neo4j_client import Neo4jKnowledgeGraphClient
from .transformer import GraphTransformer
from .utils import list_jsonl_files, read_jsonl
from .validators import RecordValidationError, validate_raw_record

LOGGER = logging.getLogger(__name__)


class KnowledgeGraphLoader:
    """Load processed Part B outputs into the temporal knowledge graph."""

    def __init__(self, config: KnowledgeGraphConfig) -> None:
        self.config = config
        self.transformer = GraphTransformer(config.energy_entities_path)

    def load(self, apply_schema: bool = True) -> dict[str, int]:
        """Load all JSONL files from the configured input directory."""
        self.config.validate()
        files = list_jsonl_files(self.config.input_dir)
        if not files:
            raise FileNotFoundError(f"No JSONL files found in {self.config.input_dir}")

        records = self._read_records(files)
        graph_batch = self.transformer.transform_records(records)

        client = Neo4jKnowledgeGraphClient(self.config)
        try:
            client.verify_connectivity()
            if apply_schema:
                for filename in ("constraints.cypher", "indexes.cypher", "graph_schema.cypher"):
                    client.apply_schema_file(self.config.cypher_dir / filename)
            node_count = client.write_nodes(graph_batch.nodes)
            relationship_count = client.write_relationships(graph_batch.relationships)
        finally:
            client.close()

        return {
            "files": len(files),
            "records": len(records),
            "nodes": node_count,
            "relationships": relationship_count,
        }

    def _read_records(self, files: list[Path]) -> list[ProcessedRecord]:
        records: list[ProcessedRecord] = []
        for path in files:
            LOGGER.info("Reading processed records from %s", path)
            for line_number, row in enumerate(read_jsonl(path), start=1):
                try:
                    records.append(validate_raw_record(row, str(path), line_number))
                except RecordValidationError as exc:
                    LOGGER.warning("Skipping invalid record: %s", exc)
        if not records:
            raise ValueError("No valid processed records found for graph loading.")
        return records

