"""High-level orchestration for loading Part B JSONL into Neo4j."""

from __future__ import annotations

import logging
import time
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

    def load(self, apply_schema: bool = True) -> dict[str, int | float]:
        """Load all JSONL files from the configured input directory."""
        start_time = time.perf_counter()
        self.config.validate()
        files = list_jsonl_files(self.config.input_dir)
        if not files:
            raise FileNotFoundError(f"No JSONL files found in {self.config.input_dir}")

        records, skipped = self._read_records(files)
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

        elapsed_seconds = round(time.perf_counter() - start_time, 2)
        LOGGER.info(
            "Load complete — files: %d, records loaded: %d, records skipped: %d, "
            "nodes merged: %d, relationships merged: %d, elapsed: %.2fs",
            len(files),
            len(records),
            skipped,
            node_count,
            relationship_count,
            elapsed_seconds,
        )
        return {
            "files": len(files),
            "records_loaded": len(records),
            "records_skipped": skipped,
            "nodes": node_count,
            "relationships": relationship_count,
            "elapsed_seconds": elapsed_seconds,
        }

    def _read_records(self, files: list[Path]) -> tuple[list[ProcessedRecord], int]:
        records: list[ProcessedRecord] = []
        total_skipped = 0
        for path in files:
            LOGGER.info("Reading processed records from %s", path)
            file_loaded = 0
            file_skipped = 0
            for line_number, (row, ok) in enumerate(read_jsonl(path), start=1):
                if not ok:
                    LOGGER.warning("Skipping malformed JSON in %s at line %s", path, line_number)
                    file_skipped += 1
                    total_skipped += 1
                    continue
                try:
                    records.append(validate_raw_record(row, str(path), line_number))
                    file_loaded += 1
                except RecordValidationError as exc:
                    LOGGER.warning("Skipping invalid record at %s:%d — %s", path.name, line_number, exc)
                    file_skipped += 1
                    total_skipped += 1
            LOGGER.info(
                "Finished %s — loaded %d record(s), skipped %d record(s).",
                path.name,
                file_loaded,
                file_skipped,
            )
        if not records:
            raise ValueError("No valid processed records found for graph loading.")
        return records, total_skipped
