"""Risk prediction engine for Part D.

Responsibilities
----------------
1. Load a persisted ML model from disk (joblib).
2. Classify supply-chain assets and return:
   - risk_score  (float 0–1, raw positive-class probability)
   - risk_tier   (LOW | MEDIUM | HIGH | CRITICAL)
3. Optionally write RiskAssessment nodes back to the Neo4j graph
   using parameterised MERGE statements (no Part C schema modifications).

The predictor is intentionally stateless with respect to the graph:
it accepts a list of AssetFeatures and a RiskPredictionNeo4jClient,
and delegates all graph writes to queries.py.

Explainability (SHAP)
---------------------
When ``config.use_shap`` is True **and** the ``shap`` package is installed,
SHAP TreeExplainer values are computed for the prediction batch and attached
to each RiskAssessment.feature_importance dict.  If SHAP is unavailable or
fails, the model's built-in feature_importances_ are used instead — the
prediction always succeeds.
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

from .config import RiskPredictionConfig
from .dataset import FEATURE_COLUMNS
from .models import AssetFeatures, PredictionResult, RiskAssessment
from .neo4j_client import RiskPredictionNeo4jClient
from .queries import QUERY_UPSERT_RISK_ASSESSMENT
from .utils import (
    ASSET_LABELS,
    assessment_id_for,
    chunks,
    clip,
    to_json_str,
    utc_now_iso,
)

LOGGER = logging.getLogger(__name__)

RISK_TIERS = ("LOW", "MEDIUM", "HIGH", "CRITICAL")


class RiskPredictor:
    """Load a trained model and generate risk predictions for supply-chain assets.

    Example::

        config = RiskPredictionConfig.from_env()
        predictor = RiskPredictor(config)
        with RiskPredictionNeo4jClient(config) as client:
            result = predictor.predict(features, client, write_back=True)
            for ra in result.assessments:
                print(ra.summary())
    """

    def __init__(self, config: RiskPredictionConfig) -> None:
        self.config = config
        self._model: Any | None = None
        self._model_backend: str = "unknown"
        self._model_version: str = "unknown"

    # ── Public API ────────────────────────────────────────────────────────────

    def load_model(self, model_path: Path | None = None) -> None:
        """Load the ML model from *model_path* (defaults to config.model_path).

        Raises
        ------
        FileNotFoundError
            If the model file does not exist.
        RuntimeError
            If the model file cannot be deserialised.
        """
        path = model_path or self.config.model_path
        if not path.exists():
            raise FileNotFoundError(
                f"Model file not found: {path}\n"
                "Run 'python -m scripts.risk_prediction.cli --train' first."
            )
        LOGGER.info("Loading model from %s …", path)
        try:
            self._model = joblib.load(path)
        except Exception as exc:
            raise RuntimeError(f"Failed to load model from {path}: {exc}") from exc

        # Read companion metadata for backend name + training timestamp
        meta_path = path.with_suffix(".json")
        if meta_path.exists():
            try:
                meta = json.loads(meta_path.read_text(encoding="utf-8"))
                self._model_backend = meta.get("backend", "unknown")
                trained_at = meta.get("trained_at", "unknown")
                self._model_version = f"{self._model_backend}@{trained_at}"
            except (json.JSONDecodeError, OSError) as exc:
                LOGGER.warning("Could not read model metadata: %s", exc)
                self._model_version = "unknown"
        else:
            self._model_version = path.stem

        LOGGER.info(
            "Model loaded: backend=%s  version=%s",
            self._model_backend,
            self._model_version,
        )

    def predict(
        self,
        features: list[AssetFeatures],
        client: RiskPredictionNeo4jClient | None = None,
        write_back: bool = False,
    ) -> PredictionResult:
        """Score *features* and return a PredictionResult.

        Parameters
        ----------
        features:
            AssetFeatures objects from GraphFeatureExtractor.
        client:
            A connected RiskPredictionNeo4jClient.  Required when
            ``write_back=True``.
        write_back:
            When True, MERGE RiskAssessment nodes into Neo4j.

        Returns
        -------
        PredictionResult
            Contains the full list of RiskAssessment objects and tier counts.
        """
        if self._model is None:
            self.load_model()

        if not features:
            LOGGER.warning("No features provided to predict(); returning empty result.")
            return PredictionResult()

        LOGGER.info("Scoring %d assets …", len(features))
        start = time.monotonic()

        # Build feature matrix
        X = self._build_matrix(features)

        # Score
        scores = self._score(X)

        # Build feature importance map (per-batch mean SHAP or global importances)
        importance_map = self._importance_map(X, features)

        # Assemble RiskAssessment objects
        predicted_at = utc_now_iso()
        assessments: list[RiskAssessment] = []
        for af, score in zip(features, scores):
            tier = self._score_to_tier(score)
            ra = RiskAssessment(
                assessment_id=assessment_id_for(af.asset_id),
                asset_id=af.asset_id,
                asset_label=af.asset_label,
                asset_name=af.asset_name,
                risk_score=clip(float(score)),
                risk_tier=tier,
                predicted_at=predicted_at,
                model_version=self._model_version,
                feature_importance=importance_map,
                features=af,
            )
            assessments.append(ra)
            LOGGER.debug(
                "Asset %-40s  score=%.4f  tier=%s",
                af.asset_id,
                score,
                tier,
            )

        elapsed = time.monotonic() - start
        LOGGER.info(
            "Prediction complete: %d assets in %.2fs (avg %.3fs/asset).",
            len(assessments),
            elapsed,
            elapsed / len(assessments) if assessments else 0,
        )

        # Tier counts
        n_critical = sum(1 for a in assessments if a.risk_tier == "CRITICAL")
        n_high = sum(1 for a in assessments if a.risk_tier == "HIGH")
        n_medium = sum(1 for a in assessments if a.risk_tier == "MEDIUM")
        n_low = sum(1 for a in assessments if a.risk_tier == "LOW")

        LOGGER.info(
            "Risk distribution — CRITICAL=%d  HIGH=%d  MEDIUM=%d  LOW=%d",
            n_critical,
            n_high,
            n_medium,
            n_low,
        )

        result = PredictionResult(
            assessments=assessments,
            n_assets=len(assessments),
            n_critical=n_critical,
            n_high=n_high,
            n_medium=n_medium,
            n_low=n_low,
            elapsed_seconds=elapsed,
            model_backend=self._model_backend,
        )

        if write_back:
            if client is None:
                raise ValueError(
                    "A connected RiskPredictionNeo4jClient is required for write_back=True."
                )
            self._write_assessments(assessments, client)

        return result

    # ── Private: scoring ──────────────────────────────────────────────────────

    def _build_matrix(self, features: list[AssetFeatures]) -> np.ndarray:
        """Convert AssetFeatures list to a float32 numpy matrix in column order."""
        rows = [af.to_feature_dict() for af in features]
        df = pd.DataFrame(rows, columns=FEATURE_COLUMNS)
        return df.values.astype(np.float32)

    def _score(self, X: np.ndarray) -> np.ndarray:
        """Return positive-class probabilities for all rows in X."""
        try:
            proba = self._model.predict_proba(X)
            return proba[:, 1]
        except AttributeError:
            LOGGER.warning(
                "Model does not support predict_proba; using predict() as score."
            )
            return self._model.predict(X).astype(float)

    def _score_to_tier(self, score: float) -> str:
        """Map a numeric risk score to a risk tier label."""
        cfg = self.config
        if score >= cfg.threshold_critical:
            return "CRITICAL"
        if score >= cfg.threshold_high:
            return "HIGH"
        if score >= cfg.threshold_medium:
            return "MEDIUM"
        return "LOW"

    # ── Private: explainability ───────────────────────────────────────────────

    def _importance_map(
        self,
        X: np.ndarray,
        features: list[AssetFeatures],  # noqa: ARG002  # kept for API symmetry
    ) -> dict[str, float]:
        """Return a feature→importance dict.

        Attempts SHAP TreeExplainer if config.use_shap is True and the shap
        package is installed.  Falls back to model.feature_importances_.
        """
        if self.config.use_shap:
            shap_map = self._try_shap(X)
            if shap_map is not None:
                return shap_map

        return self._global_importances()

    def _try_shap(self, X: np.ndarray) -> dict[str, float] | None:
        """Attempt SHAP-based feature importance.  Returns None on any failure."""
        try:
            import shap  # noqa: PLC0415

            explainer = shap.TreeExplainer(self._model)
            shap_values = explainer.shap_values(X)
            # For binary classifiers shap_values may be [neg_class, pos_class]
            if isinstance(shap_values, list) and len(shap_values) == 2:
                shap_values = shap_values[1]
            mean_abs = np.abs(shap_values).mean(axis=0)
            importance_map: dict[str, float] = {
                col: float(val)
                for col, val in zip(FEATURE_COLUMNS, mean_abs)
            }
            LOGGER.debug("SHAP importance computed for %d features.", len(importance_map))
            return importance_map
        except ImportError:
            LOGGER.debug("shap not installed; using model feature_importances_.")
        except Exception as exc:  # noqa: BLE001
            LOGGER.warning("SHAP computation failed (%s); falling back.", exc)
        return None

    def _global_importances(self) -> dict[str, float]:
        """Return the model's global feature_importances_ as a dict."""
        try:
            importances = self._model.feature_importances_
            return {
                col: float(imp)
                for col, imp in zip(FEATURE_COLUMNS, importances)
            }
        except AttributeError:
            return {col: 0.0 for col in FEATURE_COLUMNS}

    # ── Private: Neo4j write-back ─────────────────────────────────────────────

    def _write_assessments(
        self,
        assessments: list[RiskAssessment],
        client: RiskPredictionNeo4jClient,
    ) -> None:
        """Batch MERGE RiskAssessment nodes and HAS_RISK_ASSESSMENT relationships."""
        total_written = 0
        total_errors = 0

        for batch in chunks(assessments, self.config.batch_size):
            rows = [
                {
                    "assessment_id": ra.assessment_id,
                    "asset_id": ra.asset_id,
                    "asset_label": ra.asset_label,
                    "asset_name": ra.asset_name,
                    "risk_score": ra.risk_score,
                    "risk_tier": ra.risk_tier,
                    "predicted_at": ra.predicted_at,
                    "model_version": ra.model_version,
                    "feature_importance_json": to_json_str(ra.feature_importance),
                }
                for ra in batch
            ]
            try:
                counters = client.run_write(
                    QUERY_UPSERT_RISK_ASSESSMENT,
                    {"rows": rows, "asset_labels": ASSET_LABELS},
                )
                batch_written = len(batch)
                total_written += batch_written
                LOGGER.debug(
                    "Wrote batch of %d RiskAssessment(s): %s",
                    batch_written,
                    counters,
                )
            except RuntimeError as exc:
                total_errors += len(batch)
                LOGGER.error(
                    "Failed to write batch of %d assessments: %s",
                    len(batch),
                    exc,
                )

        LOGGER.info(
            "Neo4j write-back complete: %d RiskAssessment(s) written, %d errors.",
            total_written,
            total_errors,
        )
        if total_errors > 0:
            raise RuntimeError(
                f"Neo4j write-back completed with {total_errors} error(s). "
                "Check logs for details."
            )
