"""Configuration for Part D: AI-Powered Precursor Detection & Risk Prediction.

All settings are sourced from environment variables.  The project's root .env
file is merged with process-level environment variables; process-level values
take precedence so that CI / container overrides work without touching .env.

Environment Variables
---------------------
Inherited from Parts A–C
  NEO4J_URI, NEO4J_USER, NEO4J_PASSWORD, NEO4J_DATABASE

Part D-specific
  RP_CONNECTION_TIMEOUT_SECONDS  Neo4j driver connection timeout (default: 15)
  RP_MAX_CONNECTION_POOL_SIZE    Neo4j driver pool size       (default: 10)
  RP_MAX_RETRIES                 Retry attempts on transient errors (default: 3)
  RP_RETRY_BACKOFF_SECONDS       Seconds between retries      (default: 1.5)
  RP_BATCH_SIZE                  Write-back batch size        (default: 200)

  RP_WINDOW_SHORT_DAYS           Short event-count window     (default: 7)
  RP_WINDOW_LONG_DAYS            Long event-count window      (default: 30)
  RP_CASCADE_MAX_DEPTH           Max TRIGGERS path depth      (default: 4)

  RP_THRESHOLD_MEDIUM            Score boundary LOW→MEDIUM    (default: 0.30)
  RP_THRESHOLD_HIGH              Score boundary MEDIUM→HIGH   (default: 0.55)
  RP_THRESHOLD_CRITICAL          Score boundary HIGH→CRITICAL (default: 0.75)

  Heuristic labelling (training only — no explicit labels in the graph)
  RP_HEURISTIC_EVENT_COUNT       event_count_last_30_days ≥ N (default: 5)
  RP_HEURISTIC_URGENCY           urgency_average ≥ N          (default: 0.65)
  RP_HEURISTIC_CASCADE_DEPTH     cascade_depth ≥ N            (default: 3)
  RP_HEURISTIC_ANOMALY_RATE      anomaly_rate ≥ N             (default: 0.20)
  RP_HEURISTIC_GEOPOLITICAL      geopolitical_score ≥ N       (default: 0.60)

  ML model hyper-parameters
  RP_MODEL_N_ESTIMATORS          Trees / boosting rounds      (default: 100)
  RP_MODEL_MAX_DEPTH             Tree max depth               (default: 4)
  RP_MODEL_LEARNING_RATE         Boosting learning rate       (default: 0.10)

  RP_MODEL_PATH                  Absolute path to saved model joblib file
                                 (default: <project_root>/models/risk_prediction/risk_model.joblib)
  RP_LOG_LEVEL                   Python log level             (default: INFO)
  RP_USE_SHAP                    Attempt SHAP explainability  (default: true)
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Mapping

BASE_DIR = Path(__file__).resolve().parents[2]
SUPPORTED_NEO4J_URI_SCHEMES = ("neo4j://", "neo4j+s://", "neo4j+ssc://", "bolt://", "bolt+s://", "bolt+ssc://")

# Model artifacts stored outside source code
DEFAULT_MODEL_DIR = BASE_DIR / "models" / "risk_prediction"
DEFAULT_MODEL_PATH = DEFAULT_MODEL_DIR / "risk_model.joblib"


@dataclass(frozen=True)
class RiskPredictionConfig:
    """Immutable runtime configuration sourced entirely from environment variables."""

    # ── Neo4j connection ──────────────────────────────────────────────────────
    neo4j_uri: str
    neo4j_user: str
    neo4j_password: str
    neo4j_database: str | None

    # ── Neo4j driver tuning ───────────────────────────────────────────────────
    connection_timeout_seconds: float
    max_connection_pool_size: int
    max_retries: int
    retry_backoff_seconds: float
    batch_size: int

    # ── Feature windows ───────────────────────────────────────────────────────
    window_short_days: int
    window_long_days: int
    cascade_max_depth: int

    # ── Risk tier thresholds ──────────────────────────────────────────────────
    threshold_medium: float    # score ≥ this → MEDIUM (else LOW)
    threshold_high: float      # score ≥ this → HIGH
    threshold_critical: float  # score ≥ this → CRITICAL

    # ── Heuristic labelling thresholds (training) ─────────────────────────────
    heuristic_event_count: int
    heuristic_urgency: float
    heuristic_cascade_depth: int
    heuristic_anomaly_rate: float
    heuristic_geopolitical_score: float

    # ── ML model hyper-parameters ─────────────────────────────────────────────
    model_n_estimators: int
    model_max_depth: int
    model_learning_rate: float

    # ── Persistence & runtime ─────────────────────────────────────────────────
    model_path: Path
    log_level: str
    use_shap: bool

    # ──────────────────────────────────────────────────────────────────────────
    @classmethod
    def from_env(cls) -> "RiskPredictionConfig":
        """Build configuration by merging .env with process environment."""
        env = _merged_env(BASE_DIR / ".env")
        return cls(
            # Neo4j connection (reused from Parts A–C)
            neo4j_uri=env.get("NEO4J_URI", ""),
            neo4j_user=env.get("NEO4J_USER", ""),
            neo4j_password=env.get("NEO4J_PASSWORD", ""),
            neo4j_database=env.get("NEO4J_DATABASE") or None,
            # Driver tuning
            connection_timeout_seconds=float(
                env.get("RP_CONNECTION_TIMEOUT_SECONDS", "15")
            ),
            max_connection_pool_size=int(
                env.get("RP_MAX_CONNECTION_POOL_SIZE", "10")
            ),
            max_retries=int(env.get("RP_MAX_RETRIES", "3")),
            retry_backoff_seconds=float(env.get("RP_RETRY_BACKOFF_SECONDS", "1.5")),
            batch_size=int(env.get("RP_BATCH_SIZE", "200")),
            # Feature windows
            window_short_days=int(env.get("RP_WINDOW_SHORT_DAYS", "7")),
            window_long_days=int(env.get("RP_WINDOW_LONG_DAYS", "30")),
            cascade_max_depth=int(env.get("RP_CASCADE_MAX_DEPTH", "4")),
            # Risk tier thresholds
            threshold_medium=float(env.get("RP_THRESHOLD_MEDIUM", "0.30")),
            threshold_high=float(env.get("RP_THRESHOLD_HIGH", "0.55")),
            threshold_critical=float(env.get("RP_THRESHOLD_CRITICAL", "0.75")),
            # Heuristic labelling
            heuristic_event_count=int(env.get("RP_HEURISTIC_EVENT_COUNT", "5")),
            heuristic_urgency=float(env.get("RP_HEURISTIC_URGENCY", "0.65")),
            heuristic_cascade_depth=int(
                env.get("RP_HEURISTIC_CASCADE_DEPTH", "3")
            ),
            heuristic_anomaly_rate=float(
                env.get("RP_HEURISTIC_ANOMALY_RATE", "0.20")
            ),
            heuristic_geopolitical_score=float(
                env.get("RP_HEURISTIC_GEOPOLITICAL", "0.60")
            ),
            # ML model hyper-parameters
            model_n_estimators=int(env.get("RP_MODEL_N_ESTIMATORS", "100")),
            model_max_depth=int(env.get("RP_MODEL_MAX_DEPTH", "4")),
            model_learning_rate=float(env.get("RP_MODEL_LEARNING_RATE", "0.10")),
            # Persistence & runtime
            model_path=Path(
                env.get("RP_MODEL_PATH", str(DEFAULT_MODEL_PATH))
            ),
            log_level=env.get("RP_LOG_LEVEL", "INFO"),
            use_shap=env.get("RP_USE_SHAP", "true").lower()
            not in ("false", "0", "no"),
        )

    def validate(self) -> None:
        """Raise ValueError for any invalid configuration combination."""
        if not self.neo4j_uri:
            raise ValueError("NEO4J_URI is required.")
        if not self.neo4j_uri.startswith(SUPPORTED_NEO4J_URI_SCHEMES):
            schemes = ", ".join(SUPPORTED_NEO4J_URI_SCHEMES)
            raise ValueError(f"NEO4J_URI must start with one of: {schemes}")
        if not self.neo4j_user:
            raise ValueError("NEO4J_USER is required.")
        if not self.neo4j_password:
            raise ValueError("NEO4J_PASSWORD is required.")
        if not (
            0.0 < self.threshold_medium
            < self.threshold_high
            < self.threshold_critical
            <= 1.0
        ):
            raise ValueError(
                "Risk thresholds must satisfy: 0 < MEDIUM < HIGH < CRITICAL ≤ 1"
            )
        if self.window_short_days >= self.window_long_days:
            raise ValueError(
                "RP_WINDOW_SHORT_DAYS must be less than RP_WINDOW_LONG_DAYS."
            )


# ── Private helpers ───────────────────────────────────────────────────────────

def _merged_env(dotenv_path: Path) -> Mapping[str, str]:
    """Merge .env values with process env (process env takes precedence)."""
    values = _read_dotenv(dotenv_path)
    values.update(os.environ)
    return values


def _read_dotenv(path: Path) -> dict[str, str]:
    """Parse simple KEY=VALUE pairs from a .env file without logging secrets."""
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
