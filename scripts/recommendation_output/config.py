"""Configuration for Part G: outputs & actionable recommendations.

Environment Variables
---------------------
Inherited from Parts A-F
  NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE

Part G-specific
  GROQ_API_KEY               Groq API key used to generate natural-language
                              justifications for recommendations. When unset,
                              the justifier falls back to a deterministic
                              template (see justification.py) so the pipeline
                              never hard-fails without an LLM key.
  RO_GROQ_MODEL               Groq model id (default: llama-3.1-8b-instant)
  RO_GROQ_TIMEOUT_SECONDS      Groq request timeout (default: 20)
  RO_GROQ_MAX_RETRIES          Groq request retry attempts (default: 2)

  RO_HORIZON_DAYS              Comma-separated alert horizons (default: 7,14,30)
  RO_ALERT_MIN_RISK_SCORE       Minimum latest risk_score to surface an asset
                                as an alert (default: 0.30 - i.e. MEDIUM+)

  RO_LOG_LEVEL                 Python log level (default: inherits DO_LOG_LEVEL)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

from scripts.decision_optimization.config import DecisionOptimizationConfig

BASE_DIR = Path(__file__).resolve().parents[2]


@dataclass(frozen=True)
class RecommendationOutputConfig:
    """Immutable Part G settings sourced from environment variables."""

    decision_config: DecisionOptimizationConfig
    groq_api_key: str | None
    groq_model: str
    groq_timeout_seconds: float
    groq_max_retries: int
    horizon_days: tuple[int, ...]
    alert_min_risk_score: float
    log_level: str

    @classmethod
    def from_env(cls) -> "RecommendationOutputConfig":
        env = _merged_env(BASE_DIR / ".env")
        decision_config = DecisionOptimizationConfig.from_env()
        horizons_raw = env.get("RO_HORIZON_DAYS", "7,14,30")
        horizon_days = tuple(
            sorted({int(part.strip()) for part in horizons_raw.split(",") if part.strip()})
        )
        return cls(
            decision_config=decision_config,
            groq_api_key=env.get("GROQ_API_KEY") or None,
            groq_model=env.get("RO_GROQ_MODEL", "llama-3.1-8b-instant"),
            groq_timeout_seconds=float(env.get("RO_GROQ_TIMEOUT_SECONDS", "20")),
            groq_max_retries=int(env.get("RO_GROQ_MAX_RETRIES", "2")),
            horizon_days=horizon_days or (7, 14, 30),
            alert_min_risk_score=float(env.get("RO_ALERT_MIN_RISK_SCORE", "0.30")),
            log_level=env.get("RO_LOG_LEVEL", decision_config.log_level),
        )

    def validate(self) -> None:
        self.decision_config.validate()
        if not self.horizon_days or any(h <= 0 for h in self.horizon_days):
            raise ValueError("RO_HORIZON_DAYS must contain positive integers.")
        if not 0.0 <= self.alert_min_risk_score <= 1.0:
            raise ValueError("RO_ALERT_MIN_RISK_SCORE must be between 0.0 and 1.0.")
        if self.groq_timeout_seconds <= 0:
            raise ValueError("RO_GROQ_TIMEOUT_SECONDS must be > 0.")
        if self.groq_max_retries < 0:
            raise ValueError("RO_GROQ_MAX_RETRIES must be >= 0.")


def _merged_env(dotenv_path: Path) -> Mapping[str, str]:
    values = _read_dotenv(dotenv_path)
    values.update(os.environ)
    return values


def _read_dotenv(path: Path) -> dict[str, str]:
    if not path.exists():
        return {}
    values: dict[str, str] = {}
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            line = raw_line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            key = key.strip()
            value = value.strip().strip('"').strip("'")
            if key:
                values[key] = value
    return values
