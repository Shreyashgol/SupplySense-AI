"""Logging setup for knowledge graph commands."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

from .config import BASE_DIR


def configure_logging(level: str = "INFO") -> None:
    """Configure file and console logging for the module."""
    log_dir = BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    logging.basicConfig(
        filename=str(log_dir / "knowledge_graph.log"),
        level=numeric_level,
        format="%(asctime)s - %(levelname)s - %(name)s - %(message)s",
    )

    root = logging.getLogger()
    if not any(isinstance(handler, logging.StreamHandler) for handler in root.handlers):
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(
            logging.Formatter("%(asctime)s - %(levelname)s - %(name)s - %(message)s")
        )
        root.addHandler(console_handler)

