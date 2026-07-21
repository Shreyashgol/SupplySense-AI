
## Part G & H — Outputs, Recommendations & Stakeholder Access

Parts A-F ingest data, build the temporal knowledge graph, predict risk, and
generate policy-checked recommendations. Parts G and H (`scripts/recommendation_output/`,
`scripts/api/`, `frontend/`) turn those into what a stakeholder actually
sees and acts on:

- **Early Risk Alerts** (7/14/30 day horizon) — derived from Part D's
  `risk_score` via a documented hazard-rate extrapolation, not a second model.
- **Executive Action Plan** — Part F recommendations grouped into
  Procurement / Inventory / Logistics / Policy.
- **Policy-Compliant Recommendations (with justification)** — Part F's
  deterministic scores and policy checks, rendered into a grounded rationale
  sentence by Groq (`GROQ_API_KEY`), with a template fallback so the system
  never depends on the LLM being reachable.
- **Scenario Comparison (what-if)** — side-by-side Part E/F runs.
- **Stakeholder access (Part H)** — `config/stakeholder_roles.yaml` defines
  8 roles (Policymaker, PSU, Private Refiner, Strategic Planner, Crisis
  Management, Regulator, Ports & Logistics Operator, Financial Institution).
  The API (`scripts/api/`) enforces each role's view/data scope server-side;
  the React dashboard (`frontend/`) is a thin client over that API.

Run the full stack:

```bash
python3 -m uvicorn scripts.api.main:app --reload --port 8000   # backend
cd frontend && npm install && npm run dev                       # frontend (port 5173)
```

See `scripts/recommendation_output/README.md` and `scripts/api/README.md`
for details.

## Known Limitations
- **SWIFT/LC Proxy Data**: Due to the lack of free public APIs for SWIFT banking channels and Letter of Credit (LC) data, this pipeline utilizes proxy financial indicators (like FX rates) as a substitute for direct trade finance intelligence.
- **Low-Volume Domains**: Certain domains like `policy` (e.g., DGFT, MoPNG notifications) and `procurement` (e.g., GeM Tenders) update infrequently. Zero-row runs for these domains are expected during short intervals and accurately reflect the lack of new published data on their respective official portals.
