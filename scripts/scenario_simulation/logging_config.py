"""Logging configuration for Part E: scenario simulation."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

_BASE_DIR = Path(__file__).resolve().parents[2]


def configure_logging(level: str = "INFO") -> None:
    """Configure stdout and file logging for Part E."""
    numeric_level = getattr(logging, level.upper(), logging.INFO)
    formatter = logging.Formatter(
        fmt="%(asctime)s.%(msecs)03d [%(levelname)-8s] %(name)s - %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)

    log_dir = _BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(
        log_dir / "scenario_simulation.log", encoding="utf-8"
    )
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    root.handlers.clear()
    root.setLevel(numeric_level)
    root.addHandler(console_handler)
    root.addHandler(file_handler)

    for noisy in ("neo4j", "urllib3", "httpx"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
