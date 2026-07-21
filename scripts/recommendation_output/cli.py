"""Command-line interface for Part G: outputs & actionable recommendations.

Usage
-----
Early risk alerts across every scored asset (7/14/30 day horizons):

    python -m scripts.recommendation_output.cli risk-alerts

Executive action plan for an existing Part F decision run:

    python -m scripts.recommendation_output.cli action-plan --decision-run-id <ID>

Policy-compliant recommendations with Groq-generated justifications
(persists rationale_text back onto each RecommendedAction node):

    python -m scripts.recommendation_output.cli justify --decision-run-id <ID> --write-back

Scenario comparison / what-if analysis across two or more scenarios:

    python -m scripts.recommendation_output.cli compare --scenario-ids a b c
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
import uuid
from datetime import datetime, timezone

from scripts.risk_prediction.neo4j_client import RiskPredictionNeo4jClient

from .action_plan import ExecutiveActionPlanBuilder
from .comparison import ScenarioComparator
from .config import RecommendationOutputConfig
from .horizon_alerts import HorizonRiskEngine
from .justification import RecommendationJustifier
from .logging_config import configure_logging
from .models import AuditLogEntry
from .repository import RecommendationOutputRepository

LOGGER = logging.getLogger(__name__)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="python -m scripts.recommendation_output.cli",
        description=(
            "SupplySense-AI Part G - Outputs & Actionable Recommendations. "
            "Reads Part D/E/F Neo4j outputs and produces early risk alerts, "
            "executive action plans, justified recommendations, and "
            "scenario comparisons."
        ),
    )
    parser.add_argument(
        "--log-level",
        default=None,
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Override RO_LOG_LEVEL for this run.",
    )
    subparsers = parser.add_subparsers(dest="command", required=True)

    alerts = subparsers.add_parser("risk-alerts", help="Early risk alerts (7/14/30d).")
    alerts.add_argument("--role", default="cli", help="Actor role recorded in the audit log.")

    plan = subparsers.add_parser("action-plan", help="Executive action plan for a decision run.")
    plan.add_argument("--decision-run-id", required=True, metavar="ID")
    plan.add_argument("--role", default="cli", help="Actor role recorded in the audit log.")

    justify = subparsers.add_parser(
        "justify", help="Groq-justified, policy-compliant recommendations."
    )
    justify.add_argument("--decision-run-id", required=True, metavar="ID")
    justify.add_argument(
        "--write-back",
        action="store_true",
        help="Persist rationale_text onto each RecommendedAction node.",
    )
    justify.add_argument("--role", default="cli", help="Actor role recorded in the audit log.")

    compare = subparsers.add_parser("compare", help="Scenario comparison / what-if analysis.")
    compare.add_argument("--scenario-ids", required=True, nargs="+", metavar="ID")
    compare.add_argument("--role", default="cli", help="Actor role recorded in the audit log.")

    return parser


def _audit(
    repository: RecommendationOutputRepository,
    role: str,
    action: str,
    resource_id: str | None,
    outcome: str,
    detail: str,
) -> None:
    entry = AuditLogEntry(
        audit_id=f"audit_{uuid.uuid4().hex[:24]}",
        actor_role=role,
        action=action,
        resource_id=resource_id,
        outcome=outcome,
        detail=detail,
        occurred_at=datetime.now(timezone.utc).isoformat(),
    )
    repository.write_audit_log(entry)


def _run_risk_alerts(args: argparse.Namespace, config: RecommendationOutputConfig) -> None:
    with RiskPredictionNeo4jClient(config.decision_config.scenario_config.risk_config) as client:
        client.verify_connectivity()
        repository = RecommendationOutputRepository(config, client)
        risk_rows = repository.fetch_latest_risk_rows()
        features = repository.fetch_all_features()

        engine = HorizonRiskEngine(config)
        report = engine.build_report(risk_rows, features)

        _audit(repository, args.role, "view_risk_alerts", None, "success", f"{len(report.alerts)} alerts")
        print(json.dumps(report.summary(), indent=2))


def _run_action_plan(args: argparse.Namespace, config: RecommendationOutputConfig) -> None:
    with RiskPredictionNeo4jClient(config.decision_config.scenario_config.risk_config) as client:
        client.verify_connectivity()
        repository = RecommendationOutputRepository(config, client)
        result = repository.fetch_decision_run(args.decision_run_id)
        if result is None:
            _audit(repository, args.role, "view_action_plan", args.decision_run_id, "not_found", "")
            raise ValueError(f"Decision run not found: {args.decision_run_id}")

        plan = ExecutiveActionPlanBuilder().build(result)
        _audit(repository, args.role, "view_action_plan", args.decision_run_id, "success", "")
        print(json.dumps(plan.summary(), indent=2))


def _run_justify(args: argparse.Namespace, config: RecommendationOutputConfig) -> None:
    with RiskPredictionNeo4jClient(config.decision_config.scenario_config.risk_config) as client:
        client.verify_connectivity()
        repository = RecommendationOutputRepository(config, client)
        result = repository.fetch_decision_run(args.decision_run_id)
        if result is None:
            _audit(repository, args.role, "generate_justification", args.decision_run_id, "not_found", "")
            raise ValueError(f"Decision run not found: {args.decision_run_id}")

        justifier = RecommendationJustifier(config)
        justified = justifier.justify_result(result)

        if args.write_back:
            for item in justified.justifications:
                repository.write_justification(
                    recommendation_id=item.recommendation.recommendation_id,
                    rationale_text=item.rationale_text,
                    is_ambiguous=item.is_ambiguous,
                    generated_by=item.generated_by,
                    generated_at=item.generated_at,
                )

        _audit(
            repository,
            args.role,
            "generate_justification",
            args.decision_run_id,
            "success",
            f"{len(justified.justifications)} recommendation(s)",
        )
        print(json.dumps(justified.summary(), indent=2))


def _run_compare(args: argparse.Namespace, config: RecommendationOutputConfig) -> None:
    with RiskPredictionNeo4jClient(config.decision_config.scenario_config.risk_config) as client:
        client.verify_connectivity()
        repository = RecommendationOutputRepository(config, client)
        rows = repository.fetch_scenario_rows(args.scenario_ids)

        comparator = ScenarioComparator()
        result = comparator.compare(rows)

        _audit(
            repository,
            args.role,
            "view_scenario_comparison",
            ",".join(args.scenario_ids),
            "success",
            f"{len(result.rows)} scenario(s)",
        )
        print(json.dumps(result.summary(), indent=2))


def _run(args: argparse.Namespace) -> None:
    config = RecommendationOutputConfig.from_env()
    configure_logging(args.log_level or config.log_level)
    config.validate()

    dispatch = {
        "risk-alerts": _run_risk_alerts,
        "action-plan": _run_action_plan,
        "justify": _run_justify,
        "compare": _run_compare,
    }
    dispatch[args.command](args, config)


def main() -> None:
    parser = _build_parser()
    args = parser.parse_args()
    try:
        _run(args)
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
