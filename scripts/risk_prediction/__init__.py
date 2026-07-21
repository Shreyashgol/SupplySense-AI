"""Part D – AI-Powered Precursor Detection & Risk Prediction.

Public API
----------
    from scripts.risk_prediction import (
        RiskPredictionConfig,
        RiskPredictionNeo4jClient,
        GraphFeatureExtractor,
        RiskDatasetBuilder,
        RiskModelTrainer,
        RiskPredictor,
    )
"""

from __future__ import annotations

from .config import RiskPredictionConfig
from .dataset import RiskDatasetBuilder
from .feature_extractor import GraphFeatureExtractor
from .models import AssetFeatures, PredictionResult, RiskAssessment, TrainingResult
from .neo4j_client import RiskPredictionNeo4jClient
from .predictor import RiskPredictor
from .trainer import RiskModelTrainer

__all__ = [
    "RiskPredictionConfig",
    "RiskPredictionNeo4jClient",
    "GraphFeatureExtractor",
    "RiskDatasetBuilder",
    "RiskModelTrainer",
    "RiskPredictor",
    "AssetFeatures",
    "RiskAssessment",
    "TrainingResult",
    "PredictionResult",
]
