"""Early Risk Alerts engine for Part G (7 / 14 / 30 day horizon).

Why this exists
----------------
Part D's model (see ``scripts/risk_prediction``) outputs a single point-in-time
``risk_score`` per asset. Its heuristic training labels (``dataset.py``) are
dominated by the *long* event window (``RP_WINDOW_LONG_DAYS``, default 30
days), so ``risk_score`` is best read as an implied probability of disruption
occurring within that long window, not a probability tied to a single fixed
day-count.

The architecture requires alerts broken out over multiple explicit horizons
(7 / 14 / 30 days). Rather than fabricate separate numbers, this module
extrapolates ``risk_score`` onto each horizon using a standard survival-
analysis technique (constant hazard-rate assumption), then adjusts the
implied hazard rate per asset using *real* graph-derived signals that Part D
already computes:

  momentum_factor     event acceleration: actual last-7-day event count vs.
                       the count expected if the 30-day rate were uniform.
                       > 1 means events are recently accelerating.
  recency_factor       exp(-days_since_last_event / window_short_days) —
                       close to 1 right after an event, decays as the trail
                       goes cold.
  persistence_factor    structural embeddedness: cascade_depth and
                       upstream_trigger_count — deep, well-triggered chains
                       keep exerting pressure over longer horizons even if
                       the most recent event is not brand new.

Derivation
----------
1. Treat ``risk_score`` as the implied probability at ``T = window_long_days``
   and invert the constant-hazard CDF to obtain a base hazard rate::

       lambda_base = -ln(1 - risk_score) / T

2. Build a horizon-specific multiplier from momentum/recency/persistence:
   short horizons weight momentum + recency more heavily; the long horizon
   weights structural persistence more heavily (a transient spike should not
   inflate the 30-day figure; a deeply cascading one should not deflate it).

3. Recompute probability for each horizon ``h`` with the adjusted hazard rate
   and enforce monotonicity (P(7d) <= P(14d) <= P(30d)) — an ever-widening
   window cannot be less likely to contain a disruption than a narrower one.

This is a documented, deterministic transformation of a real model output —
not a fabricated number — analogous in spirit to the heuristic labelling and
urgency/rank-score formulas already used throughout Parts D-F.
"""

from __future__ import annotations

import logging
import math
from datetime import datetime, timezone

from scripts.risk_prediction.config import RiskPredictionConfig
from scripts.risk_prediction.models import AssetFeatures
from scripts.risk_prediction.utils import clip

from .config import RecommendationOutputConfig
from .models import AssetRiskAlert, HorizonProbability, RiskAlertReport

LOGGER = logging.getLogger(__name__)

_EPSILON = 1e-6


class HorizonRiskEngine:
    """Derive 7/14/30-day early-warning probabilities from Part D outputs."""

    def __init__(self, config: RecommendationOutputConfig) -> None:
        self.config = config
        self.risk_config: RiskPredictionConfig = (
            config.decision_config.scenario_config.risk_config
        )

    def build_report(
        self,
        risk_rows: dict[str, dict],
        features: list[AssetFeatures],
    ) -> RiskAlertReport:
        """Combine latest RiskAssessment rows with Part D features into alerts."""
        feature_map = {f.asset_id: f for f in features}
        alerts: list[AssetRiskAlert] = []

        for asset_id, row in risk_rows.items():
            risk_score = float(row.get("risk_score") or 0.0)
            if risk_score < self.config.alert_min_risk_score:
                continue
            feature = feature_map.get(asset_id)
            alert = self._build_alert(asset_id, row, feature)
            alerts.append(alert)

        alerts.sort(
            key=lambda a: a.horizons[-1].probability if a.horizons else 0.0,
            reverse=True,
        )

        tier_counts: dict[int, dict[str, int]] = {
            h: {"LOW": 0, "MEDIUM": 0, "HIGH": 0, "CRITICAL": 0}
            for h in self.config.horizon_days
        }
        for alert in alerts:
            for hp in alert.horizons:
                tier_counts[hp.horizon_days][hp.risk_tier] += 1

        return RiskAlertReport(
            generated_at=datetime.now(timezone.utc).isoformat(),
            horizon_days=self.config.horizon_days,
            alerts=alerts,
            tier_counts_by_horizon=tier_counts,
        )

    # ── Per-asset derivation ──────────────────────────────────────────────────

    def _build_alert(
        self,
        asset_id: str,
        row: dict,
        feature: AssetFeatures | None,
    ) -> AssetRiskAlert:
        risk_score = clip(float(row.get("risk_score") or 0.0))
        base_tier = str(row.get("risk_tier") or "LOW")
        predicted_at = str(row.get("predicted_at") or "")
        model_version = str(row.get("model_version") or "unknown")

        momentum = self._momentum_factor(feature)
        recency = self._recency_factor(feature)
        persistence = self._persistence_factor(feature)

        base_window = float(self.risk_config.window_long_days)
        lambda_base = _implied_hazard_rate(risk_score, base_window)

        horizons: list[HorizonProbability] = []
        running_max = 0.0
        for horizon_days in self.config.horizon_days:
            multiplier = self._horizon_multiplier(
                horizon_days, momentum, recency, persistence
            )
            lambda_h = lambda_base * multiplier
            probability = 1.0 - math.exp(-lambda_h * horizon_days)
            probability = clip(max(probability, running_max))
            running_max = probability
            horizons.append(
                HorizonProbability(
                    horizon_days=horizon_days,
                    probability=probability,
                    risk_tier=self._tier_for_score(probability),
                )
            )

        drivers = {
            "risk_score": risk_score,
            "event_count_last_7_days": float(feature.event_count_last_7_days) if feature else 0.0,
            "event_count_last_30_days": float(feature.event_count_last_30_days) if feature else 0.0,
            "days_since_last_event": feature.days_since_last_event if feature else 0.0,
            "cascade_depth": float(feature.cascade_depth) if feature else 0.0,
            "upstream_trigger_count": float(feature.upstream_trigger_count) if feature else 0.0,
        }

        return AssetRiskAlert(
            asset_id=asset_id,
            asset_label=str(row.get("asset_label") or (feature.asset_label if feature else "Unknown")),
            asset_name=str(row.get("asset_name") or (feature.asset_name if feature else asset_id)),
            base_risk_score=risk_score,
            base_risk_tier=base_tier,
            predicted_at=predicted_at,
            model_version=model_version,
            hazard_rate=lambda_base,
            momentum_factor=momentum,
            recency_factor=recency,
            persistence_factor=persistence,
            horizons=horizons,
            drivers=drivers,
        )

    def _momentum_factor(self, feature: AssetFeatures | None) -> float:
        """Ratio of actual recent event rate to the rate implied by the long window."""
        if feature is None:
            return 1.0
        window_short = self.risk_config.window_short_days
        window_long = self.risk_config.window_long_days
        expected_short_count = feature.event_count_last_30_days * (
            window_short / window_long
        )
        ratio = (feature.event_count_last_7_days + 1.0) / (
            expected_short_count + 1.0
        )
        return clip(ratio, lo=0.2, hi=3.0)

    def _recency_factor(self, feature: AssetFeatures | None) -> float:
        if feature is None:
            return 0.5
        window_short = max(self.risk_config.window_short_days, 1)
        return clip(math.exp(-feature.days_since_last_event / window_short))

    def _persistence_factor(self, feature: AssetFeatures | None) -> float:
        if feature is None:
            return 0.0
        max_depth = max(self.risk_config.cascade_max_depth, 1)
        cascade_component = clip(feature.cascade_depth / max_depth)
        upstream_component = clip(feature.upstream_trigger_count / 5.0)
        return clip(cascade_component * 0.5 + upstream_component * 0.5)

    @staticmethod
    def _horizon_multiplier(
        horizon_days: int,
        momentum: float,
        recency: float,
        persistence: float,
    ) -> float:
        """Blend momentum/recency (near-term) and persistence (structural) signals.

        Short horizons are dominated by whether something is happening *right
        now*; the long horizon is dominated by whether the risk is
        structurally embedded enough to still matter weeks out.
        """
        if horizon_days <= 7:
            return clip(
                (0.55 + 0.45 * momentum) * (0.6 + 0.4 * recency),
                lo=0.2,
                hi=3.0,
            )
        if horizon_days <= 14:
            return clip(
                (0.7 + 0.3 * momentum)
                * (0.75 + 0.25 * recency)
                * (0.85 + 0.15 * persistence),
                lo=0.2,
                hi=3.0,
            )
        return clip(0.55 + 0.25 * persistence + 0.20 * momentum, lo=0.2, hi=3.0)

    def _tier_for_score(self, score: float) -> str:
        cfg = self.risk_config
        if score >= cfg.threshold_critical:
            return "CRITICAL"
        if score >= cfg.threshold_high:
            return "HIGH"
        if score >= cfg.threshold_medium:
            return "MEDIUM"
        return "LOW"


def _implied_hazard_rate(risk_score: float, window_days: float) -> float:
    """Invert the constant-hazard CDF P = 1 - exp(-lambda*T) for lambda."""
    bounded_score = min(max(risk_score, _EPSILON), 1.0 - _EPSILON)
    return -math.log(1.0 - bounded_score) / max(window_days, _EPSILON)
