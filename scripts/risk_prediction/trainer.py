"""Model training for Part D: AI-Powered Precursor Detection & Risk Prediction.

Backend selection (attempted in order)
---------------------------------------
1. XGBoost  (``xgboost`` package) — preferred
2. LightGBM (``lightgbm`` package) — first fallback
3. RandomForestClassifier (``scikit-learn``) — guaranteed fallback

All three expose a scikit-learn-compatible API, so the training logic is
backend-agnostic.  The selected backend is logged and embedded in the saved
model artefact name for traceability.

Labelling & class imbalance
-----------------------------
Labels are bootstrapped heuristically by dataset.py (no ground-truth labels
exist in the graph).  Class imbalance (typically many more 0s than 1s) is
handled via ``scale_pos_weight`` (XGBoost/LightGBM) or ``class_weight``
(RandomForest), ensuring the minority class (disrupted assets) receives
appropriate gradient signal.

Model persistence
-----------------
Models are saved with ``joblib`` to the path specified in
``RiskPredictionConfig.model_path`` (default:
``<project_root>/models/risk_prediction/risk_model.joblib``).
A companion metadata JSON is written alongside the model file.
"""

from __future__ import annotations

import json
import logging
import time
from pathlib import Path
from typing import Any

import joblib
import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, classification_report, roc_auc_score
from sklearn.model_selection import StratifiedShuffleSplit

from .config import RiskPredictionConfig
from .dataset import FEATURE_COLUMNS, LABEL_COLUMN
from .models import TrainingResult
from .utils import utc_now_iso

LOGGER = logging.getLogger(__name__)

# Minimum training samples required before attempting ML training
MIN_TRAINING_SAMPLES = 10
# Minimum positive samples for meaningful binary classification
MIN_POSITIVE_SAMPLES = 2


class RiskModelTrainer:
    """Train and persist an ML model for supply-chain risk prediction.

    Example::

        config = RiskPredictionConfig.from_env()
        trainer = RiskModelTrainer(config)
        result = trainer.train(train_df)
        print(result.summary())
    """

    def __init__(self, config: RiskPredictionConfig) -> None:
        self.config = config

    # ── Public API ────────────────────────────────────────────────────────────

    def train(self, df: pd.DataFrame) -> TrainingResult:
        """Train a model on *df* and persist it to disk.

        Parameters
        ----------
        df:
            DataFrame produced by ``RiskDatasetBuilder.build(mode="training")``.
            Must contain FEATURE_COLUMNS and ``is_disrupted`` label column.

        Returns
        -------
        TrainingResult with accuracy, ROC-AUC, feature importance, and timing.
        """
        self._validate_dataframe(df)

        X = df[FEATURE_COLUMNS].values.astype(np.float32)
        y = df[LABEL_COLUMN].values.astype(int)

        LOGGER.info(
            "Training dataset: %d samples, %d features, %d positive labels.",
            len(y),
            X.shape[1],
            int(y.sum()),
        )

        # ── Train/test split ──────────────────────────────────────────────────
        splitter = StratifiedShuffleSplit(n_splits=1, test_size=0.2, random_state=42)
        try:
            train_idx, test_idx = next(splitter.split(X, y))
        except ValueError:
            # Falls back to 90/10 when class is too small for stratified split
            n = len(X)
            test_size = max(1, int(n * 0.1))
            train_idx = np.arange(n - test_size)
            test_idx = np.arange(n - test_size, n)
            LOGGER.warning(
                "Stratified split failed; using sequential 90/10 split instead."
            )

        X_train, X_test = X[train_idx], X[test_idx]
        y_train, y_test = y[train_idx], y[test_idx]

        # ── Model selection + training ────────────────────────────────────────
        model, backend = self._build_model(y_train)

        start = time.monotonic()
        LOGGER.info("Fitting %s model …", backend)
        model.fit(X_train, y_train)
        elapsed = time.monotonic() - start
        LOGGER.info("Training complete in %.2f seconds.", elapsed)

        # ── Evaluation ───────────────────────────────────────────────────────
        y_pred = model.predict(X_test)
        y_proba = self._predict_proba(model, X_test)

        accuracy = float(accuracy_score(y_test, y_pred))
        try:
            roc_auc = float(roc_auc_score(y_test, y_proba))
        except ValueError:
            roc_auc = float("nan")
            LOGGER.warning("ROC-AUC could not be computed (single class in test set).")

        LOGGER.info(
            "Evaluation — accuracy=%.4f  ROC-AUC=%.4f", accuracy, roc_auc
        )
        LOGGER.info(
            "Classification report:\n%s",
            classification_report(y_test, y_pred, zero_division=0),
        )

        # ── Feature importance ────────────────────────────────────────────────
        feature_importance = self._extract_importance(model, FEATURE_COLUMNS)

        top5 = sorted(feature_importance.items(), key=lambda x: x[1], reverse=True)[:5]
        LOGGER.info("Top-5 feature importances: %s", top5)

        # ── Persist model ─────────────────────────────────────────────────────
        model_path = self._save_model(model, backend, feature_importance)

        return TrainingResult(
            model_path=str(model_path),
            model_backend=backend,
            n_training_samples=len(X_train),
            n_test_samples=len(X_test),
            n_positive_labels=int(y_train.sum()),
            accuracy=accuracy,
            roc_auc=roc_auc,
            feature_importance=feature_importance,
            training_time_seconds=elapsed,
        )

    # ── Model construction ────────────────────────────────────────────────────

    def _build_model(self, y_train: np.ndarray) -> tuple[Any, str]:
        """Select and instantiate the best available classifier backend."""
        pos = int(y_train.sum())
        neg = len(y_train) - pos
        scale_pos_weight = (neg / pos) if pos > 0 else 1.0

        # Try XGBoost first
        try:
            import xgboost as xgb  # noqa: PLC0415

            LOGGER.info(
                "Backend: XGBoost %s (scale_pos_weight=%.2f)",
                xgb.__version__,
                scale_pos_weight,
            )
            model = xgb.XGBClassifier(
                n_estimators=self.config.model_n_estimators,
                max_depth=self.config.model_max_depth,
                learning_rate=self.config.model_learning_rate,
                scale_pos_weight=scale_pos_weight,
                eval_metric="logloss",
                random_state=42,
                verbosity=0,
            )
            return model, "xgboost"
        except Exception as e:
            LOGGER.warning("XGBoost not available or failed to load (%s), trying LightGBM …", e)

        # Try LightGBM second
        try:
            import lightgbm as lgb  # noqa: PLC0415

            LOGGER.info(
                "Backend: LightGBM %s (scale_pos_weight=%.2f)",
                lgb.__version__,
                scale_pos_weight,
            )
            model = lgb.LGBMClassifier(
                n_estimators=self.config.model_n_estimators,
                max_depth=self.config.model_max_depth,
                learning_rate=self.config.model_learning_rate,
                scale_pos_weight=scale_pos_weight,
                random_state=42,
                verbose=-1,
            )
            return model, "lightgbm"
        except Exception as e:
            LOGGER.warning("LightGBM not available or failed to load (%s), using fallback to RandomForest …", e)

        # Guaranteed fallback: RandomForestClassifier (scikit-learn)
        from sklearn.ensemble import RandomForestClassifier  # noqa: PLC0415

        import sklearn  # noqa: PLC0415

        LOGGER.warning(
            "Backend: RandomForestClassifier (sklearn %s) — "
            "install xgboost or lightgbm for better performance.",
            sklearn.__version__,
        )
        model = RandomForestClassifier(
            n_estimators=self.config.model_n_estimators,
            max_depth=self.config.model_max_depth,
            class_weight="balanced",
            random_state=42,
            n_jobs=-1,
        )
        return model, "random_forest"

    # ── Persistence ───────────────────────────────────────────────────────────

    def _save_model(
        self,
        model: Any,
        backend: str,
        feature_importance: dict[str, float],
    ) -> Path:
        """Save model artefact and companion metadata JSON."""
        model_path = self.config.model_path
        model_path.parent.mkdir(parents=True, exist_ok=True)

        joblib.dump(model, model_path, compress=3)
        LOGGER.info("Model saved to %s", model_path)

        # Companion metadata file (same stem, .json extension)
        meta_path = model_path.with_suffix(".json")
        metadata = {
            "backend": backend,
            "feature_columns": FEATURE_COLUMNS,
            "feature_importance": feature_importance,
            "trained_at": utc_now_iso(),
            "model_path": str(model_path),
        }
        meta_path.write_text(
            json.dumps(metadata, indent=2, default=str), encoding="utf-8"
        )
        LOGGER.info("Model metadata saved to %s", meta_path)
        return model_path

    # ── Helpers ───────────────────────────────────────────────────────────────

    def _validate_dataframe(self, df: pd.DataFrame) -> None:
        if len(df) < MIN_TRAINING_SAMPLES:
            raise ValueError(
                f"Need at least {MIN_TRAINING_SAMPLES} training samples, "
                f"got {len(df)}.  Ensure the Neo4j graph has sufficient data."
            )
        if LABEL_COLUMN not in df.columns:
            raise ValueError(
                f"DataFrame is missing label column '{LABEL_COLUMN}'. "
                "Use RiskDatasetBuilder.build(mode='training')."
            )
        missing = [c for c in FEATURE_COLUMNS if c not in df.columns]
        if missing:
            raise ValueError(f"Missing feature columns: {missing}")
        pos = int(df[LABEL_COLUMN].sum())
        if pos < MIN_POSITIVE_SAMPLES:
            LOGGER.warning(
                "Only %d positive labels found.  "
                "Consider lowering RP_HEURISTIC_* thresholds.",
                pos,
            )

    @staticmethod
    def _predict_proba(model: Any, X: np.ndarray) -> np.ndarray:
        """Return positive-class probabilities, falling back to predict() if needed."""
        try:
            proba = model.predict_proba(X)
            return proba[:, 1]
        except AttributeError:
            return model.predict(X).astype(float)

    @staticmethod
    def _extract_importance(
        model: Any, feature_cols: list[str]
    ) -> dict[str, float]:
        """Extract feature importance from the trained model."""
        try:
            importances = model.feature_importances_
            return {
                col: float(imp)
                for col, imp in zip(feature_cols, importances)
            }
        except AttributeError:
            LOGGER.warning("Model does not expose feature_importances_.")
            return {col: 0.0 for col in feature_cols}
