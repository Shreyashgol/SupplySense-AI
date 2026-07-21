"""Dataclasses used by the Part D risk prediction pipeline."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AssetFeatures:
    """All graph-derived features for a single supply-chain asset node.

    Every numeric field defaults to 0.0 / 0 so the downstream DataFrame
    builder always has a fully populated row — no KeyError-free NaN handling
    required at the feature extraction layer.
    """

    # Identity
    asset_id: str
    asset_label: str
    asset_name: str

    # Temporal event counts
    event_count_last_7_days: int = 0
    event_count_last_30_days: int = 0

    # Domain-specific severity scores (avg over window)
    geopolitical_score: float = 0.0
    weather_score: float = 0.0
    market_score: float = 0.0
    policy_score: float = 0.0

    # NLP/signal averages
    urgency_average: float = 0.0
    sentiment_average: float = 0.0

    # Record-level anomaly rate
    anomaly_rate: float = 0.0

    # Graph topology
    cascade_depth: int = 0
    upstream_trigger_count: int = 0
    downstream_affected_assets: int = 0
    cluster_size: int = 0
    evidence_count: float = 0.0
    degree_centrality: int = 0

    # Recency
    days_since_last_event: float = 0.0

    # Encoded label (integer)
    asset_type_code: int = 0

    def to_feature_dict(self) -> dict[str, float]:
        """Return only the numeric feature columns as a flat dict."""
        return {
            "event_count_last_7_days": float(self.event_count_last_7_days),
            "event_count_last_30_days": float(self.event_count_last_30_days),
            "geopolitical_score": self.geopolitical_score,
            "weather_score": self.weather_score,
            "market_score": self.market_score,
            "policy_score": self.policy_score,
            "urgency_average": self.urgency_average,
            "sentiment_average": self.sentiment_average,
            "anomaly_rate": self.anomaly_rate,
            "cascade_depth": float(self.cascade_depth),
            "upstream_trigger_count": float(self.upstream_trigger_count),
            "downstream_affected_assets": float(self.downstream_affected_assets),
            "cluster_size": float(self.cluster_size),
            "evidence_count": self.evidence_count,
            "degree_centrality": float(self.degree_centrality),
            "days_since_last_event": self.days_since_last_event,
            "asset_type_code": float(self.asset_type_code),
        }

    @classmethod
    def feature_columns(cls) -> list[str]:
        """Return the ordered list of numeric feature column names."""
        return [
            "event_count_last_7_days",
            "event_count_last_30_days",
            "geopolitical_score",
            "weather_score",
            "market_score",
            "policy_score",
            "urgency_average",
            "sentiment_average",
            "anomaly_rate",
            "cascade_depth",
            "upstream_trigger_count",
            "downstream_affected_assets",
            "cluster_size",
            "evidence_count",
            "degree_centrality",
            "days_since_last_event",
            "asset_type_code",
        ]


@dataclass
class RiskAssessment:
    """Risk prediction result for a single supply-chain asset."""

    assessment_id: str
    asset_id: str
    asset_label: str
    asset_name: str
    risk_score: float           # 0.0 – 1.0
    risk_tier: str              # LOW | MEDIUM | HIGH | CRITICAL
    predicted_at: str           # ISO-8601 UTC
    model_version: str          # backend name + timestamp
    feature_importance: dict[str, float]
    features: AssetFeatures

    def summary(self) -> dict[str, Any]:
        """Return a concise summary dict for logging / CLI output."""
        return {
            "asset_id": self.asset_id,
            "asset_label": self.asset_label,
            "asset_name": self.asset_name,
            "risk_score": round(self.risk_score, 4),
            "risk_tier": self.risk_tier,
            "predicted_at": self.predicted_at,
            "model_version": self.model_version,
        }


@dataclass
class TrainingResult:
    """Metrics and metadata from a completed model training run."""

    model_path: str
    model_backend: str          # "xgboost" | "lightgbm" | "random_forest"
    n_training_samples: int
    n_test_samples: int
    n_positive_labels: int
    accuracy: float
    roc_auc: float
    feature_importance: dict[str, float]
    training_time_seconds: float

    def summary(self) -> dict[str, Any]:
        return {
            "model_backend": self.model_backend,
            "model_path": self.model_path,
            "n_training_samples": self.n_training_samples,
            "n_positive_labels": self.n_positive_labels,
            "accuracy": round(self.accuracy, 4),
            "roc_auc": round(self.roc_auc, 4),
            "training_time_seconds": round(self.training_time_seconds, 2),
        }


@dataclass
class PredictionResult:
    """Aggregated results from a batch prediction run."""

    assessments: list[RiskAssessment] = field(default_factory=list)
    n_assets: int = 0
    n_critical: int = 0
    n_high: int = 0
    n_medium: int = 0
    n_low: int = 0
    elapsed_seconds: float = 0.0
    model_backend: str = "unknown"

    def summary(self) -> dict[str, Any]:
        return {
            "n_assets": self.n_assets,
            "n_critical": self.n_critical,
            "n_high": self.n_high,
            "n_medium": self.n_medium,
            "n_low": self.n_low,
            "elapsed_seconds": round(self.elapsed_seconds, 2),
            "model_backend": self.model_backend,
        }
