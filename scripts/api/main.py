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
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from scripts.decision_optimization.config import DecisionOptimizationConfig
from scripts.decision_optimization.engine import DecisionOptimizer
from scripts.decision_optimization.repository import DecisionOptimizationRepository
from scripts.risk_prediction.neo4j_client import RiskPredictionNeo4jClient
from scripts.scenario_simulation.models import ScenarioInput
from scripts.scenario_simulation.repository import ScenarioSimulationRepository

from scripts.recommendation_output.action_plan import ExecutiveActionPlanBuilder
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
    RoleInfo,
    ScenarioCompareRequest,
    ScenarioSimulateRequest,
)
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

            _audit(req, role, "run_decision_optimization", decision_result.decision_run_id, "success", "")
            return {"decision": decision_result.summary()}
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

        _audit(req, role, "view_action_plan", decision_run_id, "success", "")
        return payload

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
        recommendations = []
        for rec in result.recommendations:
            payload = auth.redact_recommendation(rec.summary(), role)
            justification = cached.get(rec.recommendation_id)
            if justification:
                payload["rationale_text"] = justification.get("rationale_text")
                payload["is_ambiguous"] = justification.get("is_ambiguous")
                payload["generated_by"] = justification.get("generated_by")
                payload["generated_at"] = justification.get("generated_at")
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

    return app


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


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
