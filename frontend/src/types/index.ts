export interface RoleInfo {
  role_key: string;
  display_name: string;
  organizations: string[];
  allowed_views: string[];
  can_view_compliance_details: boolean;
  can_view_financial_details: boolean;
  can_generate_justifications: boolean;
  can_view_audit_log: boolean;
  can_trigger_data_refresh: boolean;
}

export interface LatencyStats {
  sample_count: number;
  mean_seconds: number | null;
  median_seconds: number | null;
  p95_seconds: number | null;
  min_seconds: number | null;
  max_seconds: number | null;
}

export interface RefreshStatus {
  state: "idle" | "running" | "completed" | "failed";
  current_stage: string | null;
  stage_index: number;
  stage_count: number;
  started_at: string | null;
  finished_at: string | null;
  error: string | null;
  log_file: string | null;
  triggered_by: string | null;
}

export interface HorizonProbability {
  horizon_days: number;
  probability: number;
  risk_tier: string;
}

export interface AssetRiskAlert {
  asset_id: string;
  asset_label: string;
  asset_name: string;
  base_risk_score: number;
  base_risk_tier: string;
  predicted_at: string;
  model_version: string;
  hazard_rate: number;
  momentum_factor: number;
  recency_factor: number;
  persistence_factor: number;
  horizons: HorizonProbability[];
  drivers: Record<string, number>;
  lat: number | null;
  lon: number | null;
  geo_evidence: "resolved" | "unresolved";
}

export interface RiskAlertReport {
  generated_at: string;
  horizon_days: number[];
  alert_count: number;
  tier_counts_by_horizon: Record<string, Record<string, number>>;
  alerts: AssetRiskAlert[];
}

export interface PolicyValidation {
  status: string;
  checks?: string[];
  warnings?: string[];
  blockers?: string[];
}

export interface ConcreteAlternative {
  asset_id: string;
  name: string;
  label: string;
  distance_km: number | null;
  graph_connectivity: number;
}

export interface Recommendation {
  recommendation_id: string;
  action_type: string;
  title: string;
  target_asset_id: string;
  target_asset_label: string;
  target_asset_name: string;
  expected_impact_reduction_pct: number;
  cost_index?: number;
  implementation_days: number;
  feasibility_score: number;
  urgency_score: number;
  rank_score: number;
  confidence: number;
  policy_validation: PolicyValidation;
  rationale_text?: string | null;
  is_ambiguous?: boolean | null;
  generated_by?: string | null;
  generated_at?: string | null;
  concrete_alternatives?: ConcreteAlternative[];
}

export interface ActionPlanCategory {
  category: string;
  recommendation_count: number;
  total_expected_impact_reduction_pct?: number;
  average_confidence: number;
  average_urgency_score: number;
  top_recommendation_id: string | null;
  recommendations: Recommendation[];
}

export interface ExecutiveActionPlan {
  decision_run_id: string;
  scenario_id: string;
  scenario_name: string;
  generated_at: string;
  total_recommendations: number;
  categories: ActionPlanCategory[];
}

export interface DecisionRunSummary {
  decision_run_id: string;
  simulation_id: string;
  scenario_id: string;
  scenario_name: string;
  generated_at: string;
  recommendation_count: number;
}

export interface ScenarioComparisonRow {
  scenario_id: string;
  scenario_name: string;
  simulation_id: string;
  decision_run_id: string | null;
  generated_at: string;
  max_impact_score: number;
  average_supply_shortfall_pct: number;
  earliest_inventory_depletion_days: number;
  max_delay_days: number;
  total_economic_impact_index?: number;
  confidence: number;
  recommendation_count: number;
  top_recommendation_title: string | null;
  top_recommendation_rank_score: number | null;
  top_recommendation_cost_index?: number | null;
  compliant_recommendation_pct?: number | null;
}

export interface ScenarioComparisonResult {
  generated_at: string;
  scenario_count: number;
  most_severe_scenario_id: string | null;
  least_costly_response_scenario_id: string | null;
  scenarios: ScenarioComparisonRow[];
}

export interface AssetOption {
  asset_id: string;
  asset_label: string;
  asset_name: string;
}

export interface AssumptionField {
  value: number;
  source: string;
}

export interface ScenarioAssumptions {
  scenario_id: string;
  scenario_name: string;
  disruption_type: string;
  duration_days: number;
  affected_assets: string[];
  generated_at: string;
  assumptions: {
    supply_shock_magnitude: AssumptionField;
    alternative_availability: AssumptionField;
    behavioral_response_factor: AssumptionField;
  };
  drivers: Record<string, number>;
  aggregate_impact: {
    max_impact_score: number;
    average_supply_shortfall_pct: number;
    earliest_inventory_depletion_days: number;
    max_delay_days: number;
    total_economic_impact_index: number;
    confidence: number;
  };
}

export interface DetectorMetrics {
  name: string;
  sample_count: number;
  positives_in_ground_truth: number;
  true_positives: number;
  false_positives: number;
  true_negatives: number;
  false_negatives: number;
  precision: number | null;
  recall: number | null;
  false_negative_rate: number | null;
  f1: number | null;
  accuracy: number;
}

export interface DetectionAccuracyReport {
  ground_truth_definition: string;
  sample_count: number;
  compound_model: DetectorMetrics;
  single_sensor_baselines: DetectorMetrics[];
  lead_time_note: string;
}

export interface AuditLogEntry {
  audit_id: string;
  actor_role: string;
  action: string;
  resource_id: string | null;
  outcome: string;
  detail: string;
  occurred_at: string;
}
