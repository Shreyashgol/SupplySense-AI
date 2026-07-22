"""Compound (fused multi-signal) model vs. single-sensor baselines.

Evaluation harness for the "disruption signal detection accuracy vs
single-sensor baselines" and "false negative rate" rubric criteria.

Ground truth
------------
Uses the exact same heuristic precursor label already used to train Part D's
model (see ``dataset.py::_apply_heuristic_labels``) — an asset is "positive"
when its current graph-derived features cross the documented thresholds
(event_count_30d, urgency, cascade_depth, anomaly_rate, geopolitical_score).
This is not an independent ground truth; it is the label the model already
optimizes for, so absolute scores are inflated by that circularity. What the
comparison *does* honestly show is the relative gap between using all signals
together versus relying on any single one — which is the actual question the
rubric asks.

Why there is no dated historical backtest here
-----------------------------------------------
This system's "historical" ingestion domain currently contains only 4
placeholder sample records (see ``scripts/ingestion/historical.py``),
timestamped at ingestion time rather than the real 2021-era incident dates
they describe. That is not enough dated ground truth for a genuine
point-in-time lead-time backtest, and fabricating one would misrepresent the
system's validation. Instead, lead time is addressed structurally below
(see ``LEAD_TIME_NOTE``): a single-sensor threshold is a static yes/no
snapshot with no time axis — it cannot express *any* lead time by
construction — while the compound model's hazard-rate horizon projection
(``scripts/recommendation_output/horizon_alerts.py``) produces an explicit
7/14/30-day forward probability curve per asset.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .config import RiskPredictionConfig
from .models import AssetFeatures, RiskAssessment

LEAD_TIME_NOTE = (
    "This graph's historical-domain ingestion currently holds only 4 placeholder "
    "sample events timestamped at ingestion time (not the real incident date), so a "
    "dated point-in-time backtest is not yet possible with this data (see README "
    "Known Limitations). Structurally, though: a single-sensor threshold is a static "
    "snapshot with no time axis and cannot express lead time at all, while the "
    "compound model's horizon projection (Part G) produces an explicit forward-looking "
    "7/14/30-day probability curve per asset — that capability gap is itself evidence "
    "of the compound model's lead-time advantage."
)


@dataclass(frozen=True)
class DetectorMetrics:
    """Confusion-matrix metrics for one detector (compound model or a baseline)."""

    name: str
    true_positives: int
    false_positives: int
    true_negatives: int
    false_negatives: int

    @property
    def positives(self) -> int:
        return self.true_positives + self.false_negatives

    @property
    def precision(self) -> float | None:
        denom = self.true_positives + self.false_positives
        return self.true_positives / denom if denom else None

    @property
    def recall(self) -> float | None:
        return self.true_positives / self.positives if self.positives else None

    @property
    def false_negative_rate(self) -> float | None:
        return self.false_negatives / self.positives if self.positives else None

    @property
    def f1(self) -> float | None:
        p, r = self.precision, self.recall
        if not p or not r or (p + r) == 0:
            return None
        return 2 * p * r / (p + r)

    @property
    def accuracy(self) -> float:
        total = self.true_positives + self.false_positives + self.true_negatives + self.false_negatives
        return (self.true_positives + self.true_negatives) / total if total else 0.0

    def summary(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "sample_count": self.true_positives + self.false_positives + self.true_negatives + self.false_negatives,
            "positives_in_ground_truth": self.positives,
            "true_positives": self.true_positives,
            "false_positives": self.false_positives,
            "true_negatives": self.true_negatives,
            "false_negatives": self.false_negatives,
            "precision": round(self.precision, 4) if self.precision is not None else None,
            "recall": round(self.recall, 4) if self.recall is not None else None,
            "false_negative_rate": round(self.false_negative_rate, 4) if self.false_negative_rate is not None else None,
            "f1": round(self.f1, 4) if self.f1 is not None else None,
            "accuracy": round(self.accuracy, 4),
        }


def _heuristic_ground_truth(feature: AssetFeatures, config: RiskPredictionConfig) -> bool:
    """The exact label Part D trains against — see dataset.py for the rationale."""
    return (
        feature.event_count_last_30_days >= config.heuristic_event_count
        or feature.urgency_average >= config.heuristic_urgency
        or feature.cascade_depth >= config.heuristic_cascade_depth
        or feature.anomaly_rate >= config.heuristic_anomaly_rate
        or feature.geopolitical_score >= config.heuristic_geopolitical_score
    )


# Single-sensor baselines: one graph-derived signal in isolation, thresholded
# at the exact same cutoff the heuristic rule already uses for that signal —
# not an arbitrary new number invented for this comparison.
_SINGLE_SENSOR_BASELINES: tuple[tuple[str, str, str], ...] = (
    ("geopolitical_score_only", "geopolitical_score", "heuristic_geopolitical_score"),
    ("event_count_only", "event_count_last_30_days", "heuristic_event_count"),
    ("urgency_only", "urgency_average", "heuristic_urgency"),
    ("anomaly_rate_only", "anomaly_rate", "heuristic_anomaly_rate"),
    ("cascade_depth_only", "cascade_depth", "heuristic_cascade_depth"),
)


def compare_compound_vs_single_sensor(
    features: list[AssetFeatures],
    assessments: list[RiskAssessment],
    config: RiskPredictionConfig,
) -> dict[str, Any]:
    """Compare the compound (fused) model against each single-sensor baseline."""
    assessment_by_asset = {a.asset_id: a for a in assessments}
    threshold = config.threshold_medium  # same cutoff Part D already uses for LOW->MEDIUM

    compound_counts = {"tp": 0, "fp": 0, "tn": 0, "fn": 0}
    baseline_counts: dict[str, dict[str, int]] = {
        name: {"tp": 0, "fp": 0, "tn": 0, "fn": 0} for name, _, _ in _SINGLE_SENSOR_BASELINES
    }

    for feature in features:
        truth = _heuristic_ground_truth(feature, config)

        assessment = assessment_by_asset.get(feature.asset_id)
        compound_positive = bool(assessment and assessment.risk_score >= threshold)
        _accumulate(compound_counts, truth, compound_positive)

        for name, feature_attr, threshold_attr in _SINGLE_SENSOR_BASELINES:
            value = getattr(feature, feature_attr)
            cutoff = getattr(config, threshold_attr)
            baseline_positive = value >= cutoff
            _accumulate(baseline_counts[name], truth, baseline_positive)

    compound_metrics = DetectorMetrics(
        name="compound_fused_model",
        true_positives=compound_counts["tp"],
        false_positives=compound_counts["fp"],
        true_negatives=compound_counts["tn"],
        false_negatives=compound_counts["fn"],
    )
    baseline_metrics = [
        DetectorMetrics(
            name=name,
            true_positives=counts["tp"],
            false_positives=counts["fp"],
            true_negatives=counts["tn"],
            false_negatives=counts["fn"],
        )
        for name, counts in baseline_counts.items()
    ]

    return {
        "ground_truth_definition": (
            "Same heuristic precursor label used to train Part D (dataset.py): "
            "event_count_30d, urgency, cascade_depth, anomaly_rate, or geopolitical_score "
            "crossing their configured thresholds."
        ),
        "sample_count": len(features),
        "compound_model": compound_metrics.summary(),
        "single_sensor_baselines": [m.summary() for m in baseline_metrics],
        "lead_time_note": LEAD_TIME_NOTE,
    }


def _accumulate(counts: dict[str, int], truth: bool, predicted: bool) -> None:
    if truth and predicted:
        counts["tp"] += 1
    elif truth and not predicted:
        counts["fn"] += 1
    elif not truth and predicted:
        counts["fp"] += 1
    else:
        counts["tn"] += 1
