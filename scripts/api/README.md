# Part G/H - API Service Layer & Stakeholder Access

> **Module:** `scripts/api/`
> **Depends on:** Part G (`scripts/recommendation_output`), Parts D-F
> **Runtime:** Python 3.11+, FastAPI + Uvicorn

This is the "API / Reports / Dashboard (Stakeholder Access)" box from the
architecture. It exposes every Part G output over HTTP and enforces Part H's
stakeholder role matrix (`config/stakeholder_roles.yaml`) server-side — not
just in the frontend.

## Run

```bash
python3 -m uvicorn scripts.api.main:app --reload --port 8000
```

Every data endpoint requires an `X-Stakeholder-Role` header naming one of the
roles in `config/stakeholder_roles.yaml` (see `GET /api/v1/roles` for the
list). Unknown/missing roles get `401`; known roles without permission for a
given view get `403`.

## Endpoints

| Method | Path | Part | Notes |
|---|---|---|---|
| GET | `/api/v1/roles` | H | Public role metadata for the frontend role switcher |
| POST | `/api/v1/scenarios/simulate` | E | Passthrough scenario simulation |
| POST | `/api/v1/decisions/optimize` | E+F | Passthrough simulation + optimization |
| GET | `/api/v1/decisions` | F | List recent decision runs |
| GET | `/api/v1/risk-alerts` | G | Early Risk Alerts, asset-scope filtered by role |
| GET | `/api/v1/decisions/{id}/action-plan` | G | Executive Action Plan, category-scope filtered |
| GET | `/api/v1/decisions/{id}/recommendations` | G | Recommendations + any cached rationale |
| POST | `/api/v1/decisions/{id}/recommendations/generate` | G | Groq-generates and persists rationale (requires `can_generate_justifications`) |
| POST | `/api/v1/scenarios/compare` | G | Scenario comparison / what-if |
| GET | `/api/v1/assets` | - | Asset name search for the scenario-builder picker |
| GET | `/api/v1/system/refresh` | A-D | Data-refresh chain status (any role) |
| POST | `/api/v1/system/refresh` | A-D | Start the Part A→B→C→D data-refresh chain (requires `can_trigger_data_refresh`) |
| GET | `/api/v1/audit-log` | H | Requires `can_view_audit_log` |

## Data refresh chain (`pipeline_runner.py`)

`POST /api/v1/system/refresh` runs the existing, unmodified Parts A-D CLI
scripts as real OS subprocesses, sequentially, on a background thread:

1. `scripts/ingestion/run_all_sources.py` — pull fresh source data (Part A)
2. `python -m scripts.pipeline.run_pipeline` — normalize/dedup/NLP/store (Part B)
3. `python -m scripts.knowledge_graph.cli` — load into Neo4j (Part C)
4. `python -m scripts.risk_prediction.cli --predict --write-back` — refresh
   `RiskAssessment` scores that Part G's Early Risk Alerts read (Part D)

These scripts call `sys.exit()` and do their own file logging, so they are
launched as subprocesses rather than imported — importing them would kill
the whole API process on completion/failure. Only one refresh can run at a
time (`409` if already running); combined output is written to
`logs/system_refresh_<timestamp>.log` and progress is exposed via `GET
/api/v1/system/refresh` for the frontend to poll every 3s.

## Part H enforcement (`auth.py`)

Two layers, both server-side:

1. **Gate** — `check_view(role, view)` raises `403` before any Part D-G code
   runs if the role's `allowed_views` doesn't include the requested view.
2. **Redact** — `redact_recommendation`, `filter_alerts_by_scope`,
   `filter_categories_by_scope`, `redact_comparison_row` strip
   fields/entries from the *response payload* itself (asset-label scope,
   action-plan category scope, compliance detail, financial detail) so a
   restricted role cannot see data outside its scope even if it knows a
   decision_run_id.

## Configuration

| Env var | Default | Purpose |
|---|---:|---|
| `API_HOST` | `0.0.0.0` | Bind host |
| `API_PORT` | `8000` | Bind port |
| `API_CORS_ORIGINS` | `*` | Comma-separated allowed origins |
| `API_ROLES_FILE` | `config/stakeholder_roles.yaml` | Part H role matrix path |
