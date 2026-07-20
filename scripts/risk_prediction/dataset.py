"""Dataset builder: converts AssetFeatures into a pandas DataFrame.

Supports two modes
------------------
training
    Includes a bootstrapped binary label column ``is_disrupted`` generated
    by a heuristic rule set (documented below).  No explicit labels exist in
    the Part C graph, so labels are inferred from graph-derived signals.

prediction
    Returns a feature-only DataFrame with no label column.

Heuristic Labelling (training mode only)
-----------------------------------------
An asset is labelled ``is_disrupted = 1`` when **any** of the following
threshold conditions are met.  All thresholds are configurable via environment
variables (see config.py); defaults are shown in parentheses.

Condition                              Env var                   Default
----------------------------------------------------------------------
event_count_last_30_days >= N          RP_HEURISTIC_EVENT_COUNT    5
urgency_average >= N                   RP_HEURISTIC_URGENCY        0.65
cascade_depth >= N                     RP_HEURISTIC_CASCADE_DEPTH  3
anomaly_rate >= N                      RP_HEURISTIC_ANOMALY_RATE   0.20
geopolitical_score >= N                RP_HEURISTIC_GEOPOLITICAL   0.60

Rationale: assets with high recent event frequency, elevated urgency,
deep trigger cascades, high anomaly rates, or strong geopolitical signals
are strong precursors of supply-chain disruption in the historical record.

The heuristic is OR-combined (any condition triggers a positive label) so
that a wide variety of disruption precursor patterns is captured.  Class
imbalance is handled in the trainer via sample weighting.
"""

from __future__ import annotations

import logging

import pandas as pd

from .config import RiskPredictionConfig
from .models import AssetFeatures

LOGGER = logging.getLogger(__name__)

# Feature columns in the order the model expects them
FEATURE_COLUMNS = AssetFeatures.feature_columns()
LABEL_COLUMN = "is_disrupted"


class RiskDatasetBuilder:
    """Build a pandas DataFrame from a list of AssetFeatures objects.

    Example::

        builder = RiskDatasetBuilder(config)
        train_df = builder.build(features, mode="training")
        pred_df  = builder.build(features, mode="prediction")
    """

    def __init__(self, config: RiskPredictionConfig) -> None:
        self.config = config

    # ── Public API ────────────────────────────────────────────────────────────

    def build(
        self,
        features: list[AssetFeatures],
        mode: str = "prediction",
    ) -> pd.DataFrame:
        """Convert *features* to a DataFrame.

        Parameters
        ----------
        features:
            List of AssetFeatures from GraphFeatureExtractor.
        mode:
            ``"training"`` — append heuristic ``is_disrupted`` label column.
            ``"prediction"`` — feature columns only (no label).
        """
        if not features:
            LOGGER.warning("No features provided to RiskDatasetBuilder.")
            cols = FEATURE_COLUMNS + ["asset_id", "asset_label", "asset_name"]
            if mode == "training":
                cols.append(LABEL_COLUMN)
            return pd.DataFrame(columns=cols)

        rows = [
            {
                "asset_id": af.asset_id,
                "asset_label": af.asset_label,
                "asset_name": af.asset_name,
                **af.to_feature_dict(),
            }
            for af in features
        ]

        df = pd.DataFrame(rows)

        # Fill missing values with column medians (computed in-sample)
        df = self._impute_missing(df)

        if mode == "training":
            df = self._apply_heuristic_labels(df)
            pos = int(df[LABEL_COLUMN].sum())
            neg = len(df) - pos
            LOGGER.info(
                "Heuristic labelling complete: %d positive, %d negative (total=%d).",
                pos,
                neg,
                len(df),
            )

        LOGGER.info(
            "Dataset built: %d rows, %d feature columns (mode=%s).",
            len(df),
            len(FEATURE_COLUMNS),
            mode,
        )
        return df

    # ── Heuristic labelling ───────────────────────────────────────────────────

    def _apply_heuristic_labels(self, df: pd.DataFrame) -> pd.DataFrame:
        """Bootstrap binary disruption labels from graph-derived features.

        Documented in the module docstring above.
        All thresholds come from RiskPredictionConfig (env-variable driven).
        """
        cfg = self.config

        condition = (
            (df["event_count_last_30_days"] >= cfg.heuristic_event_count)
            | (df["urgency_average"] >= cfg.heuristic_urgency)
            | (df["cascade_depth"] >= cfg.heuristic_cascade_depth)
            | (df["anomaly_rate"] >= cfg.heuristic_anomaly_rate)
            | (df["geopolitical_score"] >= cfg.heuristic_geopolitical_score)
        )

        df = df.copy()
        df[LABEL_COLUMN] = condition.astype(int)
        return df

    # ── Imputation ────────────────────────────────────────────────────────────

    @staticmethod
    def _impute_missing(df: pd.DataFrame) -> pd.DataFrame:
        """Fill NaN / None in feature columns with the column median.

        Uses 0.0 as the fallback when a column is entirely NaN (no median
        available), which is the correct behaviour for sparse graph data.
        """
        df = df.copy()
        for col in FEATURE_COLUMNS:
            if col not in df.columns:
                df[col] = 0.0
                continue
            if df[col].isna().any():
                median = df[col].median()
                fill = float(median) if not pd.isna(median) else 0.0
                df[col] = df[col].fillna(fill)
        return df
