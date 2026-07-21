"""Command-line interface for Part C temporal knowledge graph loading."""

from __future__ import annotations

import argparse
import logging

from .config import KnowledgeGraphConfig
from .loader import KnowledgeGraphLoader
from .logging_config import configure_logging

LOGGER = logging.getLogger(__name__)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(description="Load Part B processed JSONL into Neo4j.")
    parser.add_argument(
        "--skip-schema",
        action="store_true",
        help="Skip applying Neo4j constraints and indexes before loading.",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        help="Python logging level. Defaults to INFO.",
    )
    return parser.parse_args()


def main() -> None:
    """Run the knowledge graph loader."""
    args = parse_args()
    configure_logging(args.log_level)
    config = KnowledgeGraphConfig.from_env()
    LOGGER.info("Starting Temporal Knowledge Graph load from %s", config.input_dir)
    stats = KnowledgeGraphLoader(config).load(apply_schema=not args.skip_schema)
    print(
        f"Knowledge Graph load complete: {stats['files']} file(s), "
        f"{stats['records_loaded']} records loaded, {stats['records_skipped']} skipped, "
        f"{stats['nodes']} nodes merged, {stats['relationships']} relationships merged, "
        f"elapsed {stats['elapsed_seconds']}s."
    )


if __name__ == "__main__":
    main()
