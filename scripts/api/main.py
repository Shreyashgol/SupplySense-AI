"""FastAPI service layer for Part G (outputs) and Part H (stakeholder access).

Wires together:
  Part E/F passthrough    -> run a scenario simulation + decision optimization
  Part G risk alerts       -> GET  /api/v1/risk-alerts
  Part G action plan       -> GET  /api/v1/decisions/{id}/action-plan
  Part G recommendations   -> GET  /api/v1/decisions/{id}/recommendations
                               POST /api/v1/decisions/{id}/recommendations/generate
  Part G scenario compare  -> POST /api/v1/scenarios/compare
  Part H audit log          -> GET  /api/v1/audit-log

Every data-bearing endpoint requires an ``X-Stakeholder-Role`` header
(Part H) and both gates access (401/403) and filters/redacts the response
payload according to ``config/stakeholder_roles.yaml`` — see auth.py.
"""

from __future__ import annotations

import logging
import re
import statistics
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from scripts.decision_optimization.config import DecisionOptimizationConfig
from scripts.decision_optimization.engine import DecisionOptimizer
from scripts.decision_optimization.repository import DecisionOptimizationRepository
from scripts.risk_prediction.baseline_comparison import compare_compound_vs_single_sensor
from scripts.risk_prediction.config import RiskPredictionConfig
from scripts.risk_prediction.dataset import RiskDatasetBuilder
from scripts.risk_prediction.feature_extractor import GraphFeatureExtractor
from scripts.risk_prediction.models import AssetFeatures
from scripts.risk_prediction.neo4j_client import RiskPredictionNeo4jClient
from scripts.risk_prediction.predictor import RiskPredictor
from scripts.risk_prediction.trainer import RiskModelTrainer
from scripts.scenario_simulation.models import ScenarioInput
from scripts.scenario_simulation.repository import ScenarioSimulationRepository

from scripts.recommendation_output.action_plan import ExecutiveActionPlanBuilder
from scripts.recommendation_output.alternates import AlternateFinder, PROCUREMENT_ACTION_TYPES
from scripts.recommendation_output.comparison import ScenarioComparator
from scripts.recommendation_output.config import RecommendationOutputConfig
from scripts.recommendation_output.horizon_alerts import HorizonRiskEngine
from scripts.recommendation_output.justification import RecommendationJustifier
from scripts.recommendation_output.models import AuditLogEntry
from scripts.recommendation_output.repository import RecommendationOutputRepository

from . import auth
from .config import ApiConfig
from .models import (
    DecisionOptimizeRequest,
    HealthResponse,
    JustifyRequest,
    QuickActionPlanRequest,
    RoleInfo,
    ScenarioCompareRequest,
    ScenarioSimulateRequest,
)
from .pipeline_runner import refresh_manager
from .roles import StakeholderRole

LOGGER = logging.getLogger(__name__)


def configure_logging(level: str) -> None:
    logging.basicConfig(
        level=getattr(logging, level.upper(), logging.INFO),
        format="%(asctime)s %(levelname)s %(name)s - %(message)s",
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    config = ApiConfig.from_env()
    config.validate()
    configure_logging(config.log_level)
    auth.reload_roles(config.roles_file)

    ro_config = RecommendationOutputConfig.from_env()
    ro_config.validate()
    client = RiskPredictionNeo4jClient(ro_config.decision_config.scenario_config.risk_config)
    client.verify_connectivity()

    app.state.ro_config = ro_config
    app.state.client = client
    app.state.repository = RecommendationOutputRepository(ro_config, client)
    LOGGER.info("SupplySense-AI Part G/H API server starting up.")
    yield
    client.close()
    LOGGER.info("SupplySense-AI Part G/H API server shut down.")


def create_app() -> FastAPI:
    config = ApiConfig.from_env()
    app = FastAPI(
        title="SupplySense-AI API",
        description=(
            "Part G outputs (risk alerts, executive action plan, justified "
            "recommendations, scenario comparison) with Part H stakeholder "
            "role-based access."
        ),
        version="1.0.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        LOGGER.exception("Unhandled exception: %s", exc)
        return JSONResponse(status_code=500, content={"detail": "Internal server error", "error": str(exc)})

    @app.get("/health", response_model=HealthResponse)
    async def health_check():
        return HealthResponse(status="healthy", version="1.0.0", timestamp=_now())

    @app.head("/health", include_in_schema=False)
    async def health_check_head():
        return Response(status_code=200)

    @app.get("/api/v1/roles", response_model=list[RoleInfo])
    async def list_roles():
        """Public metadata used by the frontend's Part H role switcher."""
        roles = auth.get_roles()
        return [
            RoleInfo(
                role_key=r.role_key,
                display_name=r.display_name,
                organizations=list(r.organizations),
                allowed_views=sorted(r.allowed_views),
                can_view_compliance_details=r.can_view_compliance_details,
                can_view_financial_details=r.can_view_financial_details,
                can_generate_justifications=r.can_generate_justifications,
                can_view_audit_log=r.can_view_audit_log,
                can_trigger_data_refresh=r.can_trigger_data_refresh,
            )
            for r in roles.values()
        ]

    @app.get("/api/v1/assets")
    async def search_assets(
        req: Request,
        role: StakeholderRole = Depends(auth.resolve_role),
        q: str = "",
        limit: int = 20,
    ):
        """Asset search for the scenario-builder picker (any authenticated role)."""
        repository: RecommendationOutputRepository = req.app.state.repository
        results = repository.search_assets(q, limit)
        return {"assets": results, "count": len(results)}

    # ── Part E/F passthrough (run a what-if / decision) ─────────────────────

    @app.post("/api/v1/scenarios/simulate")
    async def simulate_scenario(
        request: ScenarioSimulateRequest,
        req: Request,
        role: StakeholderRole = Depends(auth.resolve_role),
    ):
        try:
            scenario = ScenarioInput.from_dict(request.scenario)
            do_config = req.app.state.ro_config.decision_config
            client: RiskPredictionNeo4jClient = req.app.state.client
            repo = ScenarioSimulationRepository(do_config.scenario_config, client)
            simulation = _simulate_scenario(do_config, scenario, repo)
            if request.write_back:
                repo.write_result(simulation)
            _audit(req, role, "run_scenario_simulation", scenario.scenario_id, "success", "")
            return {"simulation": simulation.summary()}
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.post("/api/v1/decisions/optimize")
    async def optimize_decision(
        request: DecisionOptimizeRequest,
        req: Request,
        role: StakeholderRole = Depends(auth.resolve_role),
    ):
        started_at = time.perf_counter()
        try:
            scenario = ScenarioInput.from_dict(request.scenario)
            do_config = req.app.state.ro_config.decision_config
            if request.top_k is not None:
                do_config = _with_top_k(do_config, request.top_k)
            client: RiskPredictionNeo4jClient = req.app.state.client
            scenario_repo = ScenarioSimulationRepository(do_config.scenario_config, client)
            simulation = _simulate_scenario(do_config, scenario, scenario_repo)

            optimizer = DecisionOptimizer(do_config)
            decision_result = optimizer.optimize(simulation, top_k=request.top_k)

            if request.write_back:
                scenario_repo.write_result(simulation)
                DecisionOptimizationRepository(client).write_result(decision_result)

            response_time_seconds = round(time.perf_counter() - started_at, 3)
            _audit(
                req, role, "run_decision_optimization", decision_result.decision_run_id,
                "success", f"response_time_seconds={response_time_seconds}",
            )
            return {
                "decision": decision_result.summary(),
                "response_time_seconds": response_time_seconds,
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/v1/decisions")
    async def list_decisions(
        req: Request,
        role: StakeholderRole = Depends(auth.resolve_role),
        limit: int = 20,
    ):
        repository: RecommendationOutputRepository = req.app.state.repository
        runs = repository.fetch_latest_decision_runs(limit)
        return {"decision_runs": runs, "count": len(runs)}

    # ── Part G: Early Risk Alerts ────────────────────────────────────────────

    @app.get("/api/v1/risk-alerts")
    async def get_risk_alerts(
        req: Request,
        role: StakeholderRole = Depends(auth.resolve_role),
    ):
        auth.check_view(role, "risk_alerts")
        repository: RecommendationOutputRepository = req.app.state.repository
        risk_rows = repository.fetch_latest_risk_rows()
        features = repository.fetch_all_features()
        engine = HorizonRiskEngine(req.app.state.ro_config)
        report = engine.build_report(risk_rows, features)

        payload = report.summary()
        payload["alerts"] = auth.filter_alerts_by_scope(payload["alerts"], role)
        payload["alert_count"] = len(payload["alerts"])

        _audit(req, role, "view_risk_alerts", None, "success", f"{payload['alert_count']} alerts")
        return payload

    @app.post("/api/v1/risk-alerts/quick-plan")
    async def quick_action_plan_from_alert(
        request: QuickActionPlanRequest,
        req: Request,
        role: StakeholderRole = Depends(auth.resolve_role),
    ):
        """Bridge a real-time risk alert straight into a Part E+F decision run.

        Early Risk Alerts read Part D directly and need no scenario. Part F's
        optimizer requires a ScenarioSimulationResult, which needs a
        disruption_type/duration that a bare risk_score does not carry — so
        this endpoint derives a reasonable default scenario for the one
        flagged asset and runs the normal Part E+F pipeline against it,
        closing the gap between "this asset is CRITICAL" and "here is an
        action plan for it" without requiring a hand-built what-if scenario.
        """
        auth.check_view(role, "action_plan")
        started_at = time.perf_counter()
        try:
            scenario = ScenarioInput.from_dict(
                {
                    "scenario_id": f"autogen_{uuid.uuid4().hex[:12]}",
                    "name": f"Auto plan: {request.asset_name} ({request.horizon_days}d)",
                    "disruption_type": _infer_disruption_type(request.asset_label),
                    "duration_days": request.horizon_days,
                    "affected_assets": [request.asset_id],
                }
            )
            do_config = req.app.state.ro_config.decision_config
            client: RiskPredictionNeo4jClient = req.app.state.client
            scenario_repo = ScenarioSimulationRepository(do_config.scenario_config, client)
            simulation = _simulate_scenario(do_config, scenario, scenario_repo)

            optimizer = DecisionOptimizer(do_config)
            decision_result = optimizer.optimize(simulation)

            scenario_repo.write_result(simulation)
            DecisionOptimizationRepository(client).write_result(decision_result)

            # This is the literal "signal to recommendation" metric: wall-clock
            # time from a stakeholder clicking a risk alert to a ranked,
            # policy-checked recommendation being written and returned.
            response_time_seconds = round(time.perf_counter() - started_at, 3)
            _audit(
                req, role, "quick_action_plan_from_alert", request.asset_id,
                "success",
                f"decision_run_id={decision_result.decision_run_id} "
                f"response_time_seconds={response_time_seconds}",
            )
            return {
                "decision": decision_result.summary(),
                "response_time_seconds": response_time_seconds,
            }
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    # ── Part G: Executive Action Plan ────────────────────────────────────────

    @app.get("/api/v1/decisions/{decision_run_id}/action-plan")
    async def get_action_plan(
        decision_run_id: str,
        req: Request,
        role: StakeholderRole = Depends(auth.resolve_role),
    ):
        auth.check_view(role, "action_plan")
        repository: RecommendationOutputRepository = req.app.state.repository
        result = repository.fetch_decision_run(decision_run_id)
        if result is None:
            _audit(req, role, "view_action_plan", decision_run_id, "not_found", "")
            raise HTTPException(status_code=404, detail=f"Decision run not found: {decision_run_id}")

        plan = ExecutiveActionPlanBuilder().build(result)
        payload = plan.summary()
        payload["categories"] = auth.filter_categories_by_scope(payload["categories"], role)

        finder = AlternateFinder(req.app.state.client)
        for category in payload["categories"]:
            category["recommendations"] = [
                _attach_alternates(rec, finder) for rec in category["recommendations"]
            ]

        _audit(req, role, "view_action_plan", decision_run_id, "success", "")
        return payload

    @app.get("/api/v1/decisions/{decision_run_id}/assumptions")
    async def get_scenario_assumptions(
        decision_run_id: str,
        req: Request,
        role: StakeholderRole = Depends(auth.resolve_role),
    ):
        """Scenario model fidelity: every Part E assumption, tagged with
        whether it was analyst-provided or graph-estimated, plus the exact
        driver values used to estimate it — so the model's reasoning is
        inspectable and testable, not just its output."""
        auth.check_view(role, "action_plan")
        repository: RecommendationOutputRepository = req.app.state.repository
        assumptions = repository.fetch_scenario_assumptions(decision_run_id)
        if assumptions is None:
            _audit(req, role, "view_assumptions", decision_run_id, "not_found", "")
            raise HTTPException(
                status_code=404,
                detail=f"No scenario simulation found for decision run: {decision_run_id}",
            )
        _audit(req, role, "view_assumptions", decision_run_id, "success", "")
        return assumptions

    # ── Part G: Policy-Compliant Recommendations (with justification) ───────

    @app.get("/api/v1/decisions/{decision_run_id}/recommendations")
    async def get_recommendations(
        decision_run_id: str,
        req: Request,
        role: StakeholderRole = Depends(auth.resolve_role),
    ):
        auth.check_view(role, "justified_recommendations")
        repository: RecommendationOutputRepository = req.app.state.repository
        result = repository.fetch_decision_run(decision_run_id)
        if result is None:
            _audit(req, role, "view_recommendations", decision_run_id, "not_found", "")
            raise HTTPException(status_code=404, detail=f"Decision run not found: {decision_run_id}")

        cached = repository.fetch_cached_justifications(
            [rec.recommendation_id for rec in result.recommendations]
        )
        finder = AlternateFinder(req.app.state.client)
        recommendations = []
        for rec in result.recommendations:
            payload = auth.redact_recommendation(rec.summary(), role)
            justification = cached.get(rec.recommendation_id)
            if justification:
                payload["rationale_text"] = justification.get("rationale_text")
                payload["is_ambiguous"] = justification.get("is_ambiguous")
                payload["generated_by"] = justification.get("generated_by")
                payload["generated_at"] = justification.get("generated_at")
            payload = _attach_alternates(payload, finder)
            recommendations.append(payload)

        _audit(req, role, "view_recommendations", decision_run_id, "success", "")
        return {
            "decision_run_id": result.decision_run_id,
            "scenario_id": result.scenario_id,
            "scenario_name": result.scenario_name,
            "recommendation_count": len(recommendations),
            "recommendations": recommendations,
        }

    @app.post("/api/v1/decisions/{decision_run_id}/recommendations/generate")
    async def generate_recommendations(
        decision_run_id: str,
        request: JustifyRequest,
        req: Request,
        role: StakeholderRole = Depends(auth.resolve_role),
    ):
        auth.check_view(role, "justified_recommendations")
        if not role.can_generate_justifications:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{role.role_key}' may not generate new justifications.",
            )
        repository: RecommendationOutputRepository = req.app.state.repository
        result = repository.fetch_decision_run(decision_run_id)
        if result is None:
            _audit(req, role, "generate_justification", decision_run_id, "not_found", "")
            raise HTTPException(status_code=404, detail=f"Decision run not found: {decision_run_id}")

        justifier = RecommendationJustifier(req.app.state.ro_config)
        justified = justifier.justify_result(result)

        if request.write_back:
            for item in justified.justifications:
                repository.write_justification(
                    recommendation_id=item.recommendation.recommendation_id,
                    rationale_text=item.rationale_text,
                    is_ambiguous=item.is_ambiguous,
                    generated_by=item.generated_by,
                    generated_at=item.generated_at,
                )

        payload = justified.summary()
        payload["recommendations"] = [
            auth.redact_recommendation(rec, role) for rec in payload["recommendations"]
        ]
        _audit(
            req, role, "generate_justification", decision_run_id, "success",
            f"{len(justified.justifications)} recommendation(s)",
        )
        return payload

    # ── Part G: Scenario Comparison (what-if) ────────────────────────────────

    @app.post("/api/v1/scenarios/compare")
    async def compare_scenarios(
        request: ScenarioCompareRequest,
        req: Request,
        role: StakeholderRole = Depends(auth.resolve_role),
    ):
        auth.check_view(role, "scenario_comparison")
        repository: RecommendationOutputRepository = req.app.state.repository
        rows = repository.fetch_scenario_rows(request.scenario_ids)
        result = ScenarioComparator().compare(rows)

        payload = result.summary()
        payload["scenarios"] = [
            auth.redact_comparison_row(row, role) for row in payload["scenarios"]
        ]
        _audit(
            req, role, "view_scenario_comparison", ",".join(request.scenario_ids),
            "success", f"{len(result.rows)} scenario(s)",
        )
        return payload

    # ── System refresh (Parts A->B->C->D data refresh chain) ─────────────────

    @app.get("/api/v1/system/refresh")
    async def get_refresh_status(role: StakeholderRole = Depends(auth.resolve_role)):
        """Any authenticated role may check refresh status (read-only)."""
        return refresh_manager.status()

    @app.post("/api/v1/system/refresh")
    async def start_refresh(
        req: Request,
        role: StakeholderRole = Depends(auth.resolve_role),
    ):
        if not role.can_trigger_data_refresh:
            raise HTTPException(
                status_code=403,
                detail=f"Role '{role.role_key}' may not trigger a data refresh.",
            )
        started = refresh_manager.start(triggered_by=role.role_key)
        if not started:
            _audit(req, role, "trigger_data_refresh", None, "already_running", "")
            raise HTTPException(status_code=409, detail="A data refresh is already running.")
        _audit(req, role, "trigger_data_refresh", None, "started", "")
        return refresh_manager.status()

    # ── Part H: Audit & Explainability ───────────────────────────────────────

    @app.get("/api/v1/audit-log")
    async def get_audit_log(
        req: Request,
        role: StakeholderRole = Depends(auth.resolve_role),
        limit: int = 100,
    ):
        auth.check_view(role, "audit_log")
        client: RiskPredictionNeo4jClient = req.app.state.client
        rows = client.run_read(
            "MATCH (a:AuditLogEntry) RETURN a ORDER BY a.occurred_at DESC LIMIT $limit",
            {"limit": limit},
        )
        return {"entries": [dict(row["a"]) for row in rows], "count": len(rows)}

    @app.get("/api/v1/system/performance")
    async def get_performance(
        req: Request,
        role: StakeholderRole = Depends(auth.resolve_role),  # noqa: ARG001 — auth required, no role-specific data
        limit: int = 200,
    ):
        """Aggregate end-to-end signal-to-recommendation latency (evaluation metric).

        Reads response_time_seconds recorded by run_decision_optimization and
        quick_action_plan_from_alert audit entries — real measured wall-clock
        time from each request, not a synthetic figure.
        """
        client: RiskPredictionNeo4jClient = req.app.state.client
        rows = client.run_read(
            """
            MATCH (a:AuditLogEntry)
            WHERE a.action IN ['run_decision_optimization', 'quick_action_plan_from_alert']
              AND a.detail CONTAINS 'response_time_seconds='
            RETURN a.detail AS detail, a.action AS action
            ORDER BY a.occurred_at DESC
            LIMIT $limit
            """,
            {"limit": limit},
        )
        samples = _extract_response_times([row["detail"] for row in rows])
        return {"sample_count": len(samples), **_latency_stats(samples)}

    @app.get("/api/v1/system/detection-accuracy")
    async def get_detection_accuracy(
        req: Request,
        role: StakeholderRole = Depends(auth.resolve_role),  # noqa: ARG001 — auth required, no role-specific data
    ):
        """Compound (fused multi-signal) model vs. single-sensor baselines.

        See scripts/risk_prediction/baseline_comparison.py for the full
        methodology and honesty caveats (ground truth is the same heuristic
        label the model trains on; there is no dated historical backtest
        because this graph's historical domain has too few dated samples).
        """
        client: RiskPredictionNeo4jClient = req.app.state.client
        ro_config = req.app.state.ro_config
        risk_config = ro_config.decision_config.scenario_config.risk_config
        extractor = GraphFeatureExtractor(risk_config, client)
        features = extractor.extract_all()
        predictor = RiskPredictor(risk_config)
        try:
            result = predictor.predict(features, client, write_back=False)
        except FileNotFoundError:
            # Self-heal: `models/` is gitignored, so a fresh deployment has no
            # artifact yet. Training this dataset takes well under a second
            # (see scripts/risk_prediction/trainer.py), so it's cheap to do
            # inline here rather than fail the request and require an operator
            # to shell into the container and run --train manually.
            LOGGER.info("No trained risk model found; training one now (first request after deploy).")
            _train_model_inline(risk_config, features)
            predictor = RiskPredictor(risk_config)
            result = predictor.predict(features, client, write_back=False)
        return compare_compound_vs_single_sensor(features, result.assessments, risk_config)

    return app


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


_RESPONSE_TIME_PATTERN = re.compile(r"response_time_seconds=([0-9.]+)")


def _extract_response_times(details: list[str]) -> list[float]:
    samples: list[float] = []
    for detail in details:
        match = _RESPONSE_TIME_PATTERN.search(detail or "")
        if match:
            samples.append(float(match.group(1)))
    return samples


def _latency_stats(samples: list[float]) -> dict[str, float | None]:
    if not samples:
        return {"mean_seconds": None, "median_seconds": None, "p95_seconds": None, "min_seconds": None, "max_seconds": None}
    ordered = sorted(samples)
    p95_index = min(int(len(ordered) * 0.95), len(ordered) - 1)
    return {
        "mean_seconds": round(statistics.mean(ordered), 3),
        "median_seconds": round(statistics.median(ordered), 3),
        "p95_seconds": round(ordered[p95_index], 3),
        "min_seconds": round(ordered[0], 3),
        "max_seconds": round(ordered[-1], 3),
    }


def _audit(
    req: Request,
    role: StakeholderRole,
    action: str,
    resource_id: str | None,
    outcome: str,
    detail: str,
) -> None:
    repository: RecommendationOutputRepository = req.app.state.repository
    entry = AuditLogEntry(
        audit_id=f"audit_{uuid.uuid4().hex[:24]}",
        actor_role=role.role_key,
        action=action,
        resource_id=resource_id,
        outcome=outcome,
        detail=detail,
        occurred_at=_now(),
    )
    try:
        repository.write_audit_log(entry)
    except Exception as exc:  # noqa: BLE001
        LOGGER.warning("Failed to write audit log entry: %s", exc)


_DISRUPTION_TYPE_BY_ASSET_LABEL: dict[str, str] = {
    "ShippingRoute": "strait_closure",
    "Port": "port_congestion",
    "Terminal": "port_congestion",
    "Refinery": "refinery_outage",
    "Pipeline": "refinery_outage",
    "Supplier": "sanctions",
}


def _attach_alternates(rec: dict, finder: AlternateFinder) -> dict:
    """Enrich spot_procurement/activate_alternate_supplier recs with real,
    named, graph-backed alternate entities (see recommendation_output/alternates.py).
    No-op for every other action type."""
    if rec.get("action_type") not in PROCUREMENT_ACTION_TYPES:
        return rec
    rec = dict(rec)
    alternatives = finder.find_alternates(rec["target_asset_id"], limit=3)
    rec["concrete_alternatives"] = [alt.summary() for alt in alternatives]
    return rec


def _train_model_inline(risk_config: RiskPredictionConfig, features: list[AssetFeatures]) -> None:
    """Train and persist a Part D model synchronously (see docstring at call site)."""
    builder = RiskDatasetBuilder(risk_config)
    train_df = builder.build(features, mode="training")
    trainer = RiskModelTrainer(risk_config)
    trainer.train(train_df)


def _infer_disruption_type(asset_label: str) -> str:
    """Best-guess disruption_type for a quick action plan, from asset type alone."""
    return _DISRUPTION_TYPE_BY_ASSET_LABEL.get(asset_label, "generic")


def _simulate_scenario(do_config: DecisionOptimizationConfig, scenario: ScenarioInput, repo: ScenarioSimulationRepository):
    from scripts.decision_optimization.cli import _simulate  # local import: avoid module import cycle at startup

    return _simulate(do_config, scenario, repo)


def _with_top_k(do_config: DecisionOptimizationConfig, top_k: int) -> DecisionOptimizationConfig:
    return DecisionOptimizationConfig(
        scenario_config=do_config.scenario_config,
        top_k=top_k,
        minimum_rank_score=do_config.minimum_rank_score,
        benefit_weight=do_config.benefit_weight,
        feasibility_weight=do_config.feasibility_weight,
        urgency_weight=do_config.urgency_weight,
        confidence_weight=do_config.confidence_weight,
        cost_penalty_weight=do_config.cost_penalty_weight,
        time_penalty_weight=do_config.time_penalty_weight,
        compliance_penalty_weight=do_config.compliance_penalty_weight,
        log_level=do_config.log_level,
    )


app = create_app()


if __name__ == "__main__":
    import uvicorn

    config = ApiConfig.from_env()
    config.validate()
    uvicorn.run(
        "scripts.api.main:app",
        host=config.host,
        port=config.port,
        workers=config.workers,
        log_level=config.log_level.lower(),
    )
