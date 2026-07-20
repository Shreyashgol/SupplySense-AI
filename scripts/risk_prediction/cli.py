"""Command-line interface for Part D: AI-Powered Precursor Detection & Risk Prediction.

Usage
-----
Train a model (extract features from Neo4j, fit XGBoost, persist):

    python -m scripts.risk_prediction.cli --train

Score all assets and write RiskAssessment nodes back to Neo4j:

    python -m scripts.risk_prediction.cli --predict --write-back

Score a single asset (no write-back by default):

    python -m scripts.risk_prediction.cli --predict --asset country_saudi_arabia

Use a custom model path:

    python -m scripts.risk_prediction.cli --train --model-path /tmp/my_model.joblib
    python -m scripts.risk_prediction.cli --predict --model-path /tmp/my_model.joblib

Adjust look-back window:

    python -m scripts.risk_prediction.cli --predict --days 14
"""

from __future__ import annotations

import argparse
import json
import logging
import sys

from .config import RiskPredictionConfig
from .dataset import RiskDatasetBuilder
from .feature_extractor import GraphFeatureExtractor
from .logging_config import configure_logging
from .neo4j_client import RiskPredictionNeo4jClient
from .predictor import RiskPredictor
from .trainer import RiskModelTrainer

LOGGER = logging.getLogger(__name__)


# ── Argument parsing ──────────────────────────────────────────────────────────


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.risk_prediction.cli",
        description=(
            "SupplySense-AI Part D — Supply Chain Risk Prediction.\n\n"
            "Reads supply-chain graph features from Neo4j (Part C output) and\n"
            "trains or runs an ML model to produce risk scores (0–1) and risk\n"
            "tiers (LOW / MEDIUM / HIGH / CRITICAL) for each supply-chain asset."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    # ── Mutually exclusive mode flags ──────────────────────────────────────────
    mode_group = parser.add_mutually_exclusive_group(required=True)
    mode_group.add_argument(
        "--train",
        action="store_true",
        help=(
            "Extract features from Neo4j, bootstrap heuristic labels, "
            "train an ML model, and persist it to disk."
        ),
    )
    mode_group.add_argument(
        "--predict",
        action="store_true",
        help=(
            "Load a trained model and score supply-chain assets.  "
            "Use --write-back to persist results to Neo4j."
        ),
    )

    # ── Targeting ──────────────────────────────────────────────────────────────
    parser.add_argument(
        "--asset",
        metavar="ASSET_ID",
        default="",
        help=(
            "Restrict extraction/prediction to a single asset identified by "
            "its entity_key.  Omit to process all assets."
        ),
    )
    parser.add_argument(
        "--days",
        type=int,
        default=None,
        metavar="N",
        help=(
            "Override the long feature window to N days "
            "(sets RP_WINDOW_LONG_DAYS for this run).  "
            "The short window is set to min(7, N)."
        ),
    )

    # ── Persistence ────────────────────────────────────────────────────────────
    parser.add_argument(
        "--model-path",
        metavar="PATH",
        default=None,
        help=(
            "Path to the joblib model file.  "
            "Overrides RP_MODEL_PATH from the environment / .env."
        ),
    )
    parser.add_argument(
        "--write-back",
        action="store_true",
        help=(
            "Write RiskAssessment nodes and HAS_RISK_ASSESSMENT relationships "
            "to Neo4j after prediction.  Ignored when --train is specified."
        ),
    )

    # ── Logging ────────────────────────────────────────────────────────────────
    parser.add_argument(
        "--log-level",
        default=None,
        metavar="LEVEL",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Override the Python log level.  Defaults to RP_LOG_LEVEL (INFO).",
    )

    return parser


# ── Mode handlers ─────────────────────────────────────────────────────────────


def _run_train(
    config: RiskPredictionConfig,
    asset_id: str,
) -> None:
    """Extract features → build training DataFrame → train → save model."""
    LOGGER.info("=== Part D TRAIN mode ===")

    with RiskPredictionNeo4jClient(config) as client:
        client.verify_connectivity()

        extractor = GraphFeatureExtractor(config, client)
        if asset_id:
            LOGGER.info("Extracting features for asset_id=%r …", asset_id)
            features = extractor.extract_asset(asset_id)
        else:
            LOGGER.info("Extracting features for all assets …")
            features = extractor.extract_all()

    LOGGER.info("Feature extraction returned %d asset(s).", len(features))

    builder = RiskDatasetBuilder(config)
    train_df = builder.build(features, mode="training")

    LOGGER.info(
        "Training dataset: %d rows, %d positive labels.",
        len(train_df),
        int(train_df["is_disrupted"].sum()) if "is_disrupted" in train_df.columns else 0,
    )

    trainer = RiskModelTrainer(config)
    result = trainer.train(train_df)

    print("\n" + "=" * 60)
    print("  Part D — Training Complete")
    print("=" * 60)
    print(json.dumps(result.summary(), indent=2))
    print("=" * 60 + "\n")


def _run_predict(
    config: RiskPredictionConfig,
    asset_id: str,
    model_path_override: str | None,
    write_back: bool,
) -> None:
    """Extract features → load model → score → (optionally) write-back."""
    LOGGER.info("=== Part D PREDICT mode ===")

    from pathlib import Path  # noqa: PLC0415

    model_path = Path(model_path_override) if model_path_override else None

    with RiskPredictionNeo4jClient(config) as client:
        client.verify_connectivity()

        extractor = GraphFeatureExtractor(config, client)
        if asset_id:
            LOGGER.info("Extracting features for asset_id=%r …", asset_id)
            features = extractor.extract_asset(asset_id)
        else:
            LOGGER.info("Extracting features for all assets …")
            features = extractor.extract_all()

        LOGGER.info("Feature extraction returned %d asset(s).", len(features))

        predictor = RiskPredictor(config)
        predictor.load_model(model_path)

        result = predictor.predict(
            features,
            client=client if write_back else None,
            write_back=write_back,
        )

    # ── Console output ─────────────────────────────────────────────────────
    print("\n" + "=" * 60)
    print("  Part D — Prediction Complete")
    print("=" * 60)
    print(json.dumps(result.summary(), indent=2))

    if result.assessments:
        print("\nTop 10 highest-risk assets:")
        sorted_assessments = sorted(
            result.assessments, key=lambda a: a.risk_score, reverse=True
        )
        print(f"  {'ASSET ID':<40} {'SCORE':>6}  {'TIER'}")
        print("  " + "-" * 58)
        for ra in sorted_assessments[:10]:
            print(
                f"  {ra.asset_id:<40} {ra.risk_score:>6.4f}  {ra.risk_tier}"
            )

    print("=" * 60 + "\n")


# ── Entry point ───────────────────────────────────────────────────────────────


def main() -> None:
    """CLI entry point for Part D risk prediction."""
    parser = _build_parser()
    args = parser.parse_args()

    # Load configuration (env vars + .env)
    config = RiskPredictionConfig.from_env()

    # Apply --days override before validation
    if args.days is not None:
        import dataclasses  # noqa: PLC0415

        short = min(7, args.days)
        config = dataclasses.replace(
            config,
            window_short_days=short,
            window_long_days=args.days,
        )

    # Apply --model-path override
    if args.model_path:
        import dataclasses  # noqa: PLC0415
        from pathlib import Path  # noqa: PLC0415

        config = dataclasses.replace(config, model_path=Path(args.model_path))

    # Configure logging (--log-level > RP_LOG_LEVEL > INFO)
    log_level = args.log_level or config.log_level
    configure_logging(log_level)

    # Validate config
    try:
        config.validate()
    except ValueError as exc:
        LOGGER.error("Configuration error: %s", exc)
        sys.exit(1)

    LOGGER.info(
        "Part D configuration loaded (uri=%s, database=%s).",
        config.neo4j_uri,
        config.neo4j_database or "default",
    )

    try:
        if args.train:
            _run_train(config, asset_id=args.asset)
        elif args.predict:
            _run_predict(
                config,
                asset_id=args.asset,
                model_path_override=args.model_path,
                write_back=args.write_back,
            )
    except FileNotFoundError as exc:
        LOGGER.error("%s", exc)
        sys.exit(2)
    except ValueError as exc:
        LOGGER.error("Validation error: %s", exc)
        sys.exit(3)
    except RuntimeError as exc:
        LOGGER.error("Runtime error: %s", exc)
        sys.exit(4)
    except KeyboardInterrupt:
        LOGGER.info("Interrupted by user.")
        sys.exit(130)


if __name__ == "__main__":
    main()
