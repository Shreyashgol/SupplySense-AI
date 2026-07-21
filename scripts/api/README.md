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
| GET | `/api/v1/audit-log` | H | Requires `can_view_audit_log` |

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
