"""Logging configuration for Part D: Risk Prediction."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

# Resolved once at import time — same anchor as config.py
_BASE_DIR = Path(__file__).resolve().parents[2]


def configure_logging(level: str = "INFO") -> None:
    """Configure file and console logging for Part D.

    Writes to:
    - stdout (console) with millisecond-precision structured format
    - <project_root>/logs/risk_prediction.log (file, same format)

    Matches Part C's logging conventions.
    """
    numeric_level = getattr(logging, level.upper(), logging.INFO)

    formatter = logging.Formatter(
        fmt="%(asctime)s.%(msecs)03d [%(levelname)-8s] %(name)s — %(message)s",
        datefmt="%Y-%m-%dT%H:%M:%S",
    )

    # Console handler
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(numeric_level)
    console_handler.setFormatter(formatter)

    # File handler
    log_dir = _BASE_DIR / "logs"
    log_dir.mkdir(exist_ok=True)
    file_handler = logging.FileHandler(
        log_dir / "risk_prediction.log", encoding="utf-8"
    )
    file_handler.setLevel(numeric_level)
    file_handler.setFormatter(formatter)

    root = logging.getLogger()
    # Remove any pre-existing handlers to avoid duplicate output
    root.handlers.clear()
    root.setLevel(numeric_level)
    root.addHandler(console_handler)
    root.addHandler(file_handler)

    # Suppress verbose third-party loggers
    for noisy in ("neo4j", "urllib3", "httpx", "lightgbm", "xgboost"):
        logging.getLogger(noisy).setLevel(logging.WARNING)
