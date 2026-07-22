import axios from "axios";
import type {
  AssetOption,
  AuditLogEntry,
  DecisionRunSummary,
  DetectionAccuracyReport,
  ExecutiveActionPlan,
  LatencyStats,
  RefreshStatus,
  RiskAlertReport,
  RoleInfo,
  ScenarioAssumptions,
  ScenarioComparisonResult,
} from "../types";

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "http://localhost:8000";

export const apiClient = axios.create({ baseURL: API_BASE_URL });

let currentRole: string | null = null;
export function setActiveRole(roleKey: string | null) {
  currentRole = roleKey;
}

// Endpoints that intentionally don't require a resolved role (used to bootstrap
// the role switcher itself before any role is known).
const PUBLIC_PATHS = ["/health", "/api/v1/roles"];

apiClient.interceptors.request.use((config) => {
  const isPublic = PUBLIC_PATHS.some((path) => config.url?.startsWith(path));
  if (currentRole) {
    config.headers.set("X-Stakeholder-Role", currentRole);
  } else if (!isPublic) {
    // Fail fast on the client with a clear message instead of silently
    // sending the request without the header and surfacing a confusing
    // "Field required" 422 from the server. This should only trip if a
    // component fetches before RoleContext has resolved a role — every
    // component's initial fetch is expected to guard on that (see
    // useRole().activeRole being non-null) before calling into this client.
    return Promise.reject(
      new Error(`Blocked ${config.url}: no stakeholder role resolved yet.`)
    );
  }
  return config;
});

export async function fetchRoles(): Promise<RoleInfo[]> {
  const res = await apiClient.get<RoleInfo[]>("/api/v1/roles");
  return res.data;
}

export async function fetchRiskAlerts(): Promise<RiskAlertReport> {
  const res = await apiClient.get<RiskAlertReport>("/api/v1/risk-alerts");
  return res.data;
}

export async function fetchDecisionRuns(limit = 20): Promise<{ decision_runs: DecisionRunSummary[]; count: number }> {
  const res = await apiClient.get("/api/v1/decisions", { params: { limit } });
  return res.data;
}

export async function fetchActionPlan(decisionRunId: string): Promise<ExecutiveActionPlan> {
  const res = await apiClient.get<ExecutiveActionPlan>(
    `/api/v1/decisions/${decisionRunId}/action-plan`
  );
  return res.data;
}

export async function fetchScenarioAssumptions(decisionRunId: string): Promise<ScenarioAssumptions> {
  const res = await apiClient.get<ScenarioAssumptions>(
    `/api/v1/decisions/${decisionRunId}/assumptions`
  );
  return res.data;
}

export async function fetchRecommendations(decisionRunId: string) {
  const res = await apiClient.get(`/api/v1/decisions/${decisionRunId}/recommendations`);
  return res.data;
}

export async function generateRecommendations(decisionRunId: string) {
  const res = await apiClient.post(
    `/api/v1/decisions/${decisionRunId}/recommendations/generate`,
    { write_back: true }
  );
  return res.data;
}

export async function compareScenarios(scenarioIds: string[]): Promise<ScenarioComparisonResult> {
  const res = await apiClient.post<ScenarioComparisonResult>("/api/v1/scenarios/compare", {
    scenario_ids: scenarioIds,
  });
  return res.data;
}

export interface ScenarioPayload {
  scenario_id: string;
  name: string;
  disruption_type: string;
  duration_days: number;
  affected_assets: string[];
}

export async function optimizeDecision(scenario: ScenarioPayload, topK?: number) {
  const res = await apiClient.post("/api/v1/decisions/optimize", {
    scenario,
    top_k: topK,
    write_back: true,
  });
  return res.data;
}

export async function searchAssets(q: string, limit = 15): Promise<AssetOption[]> {
  const res = await apiClient.get<{ assets: AssetOption[] }>("/api/v1/assets", {
    params: { q, limit },
  });
  return res.data.assets;
}

export async function quickActionPlan(
  assetId: string,
  assetLabel: string,
  assetName: string,
  horizonDays: number
) {
  const res = await apiClient.post("/api/v1/risk-alerts/quick-plan", {
    asset_id: assetId,
    asset_label: assetLabel,
    asset_name: assetName,
    horizon_days: horizonDays,
  });
  return res.data;
}

export async function fetchPerformance(): Promise<LatencyStats> {
  const res = await apiClient.get<LatencyStats>("/api/v1/system/performance");
  return res.data;
}

export async function fetchRefreshStatus(): Promise<RefreshStatus> {
  const res = await apiClient.get<RefreshStatus>("/api/v1/system/refresh");
  return res.data;
}

export async function triggerRefresh(): Promise<RefreshStatus> {
  const res = await apiClient.post<RefreshStatus>("/api/v1/system/refresh");
  return res.data;
}

export async function fetchDetectionAccuracy(): Promise<DetectionAccuracyReport> {
  const res = await apiClient.get<DetectionAccuracyReport>("/api/v1/system/detection-accuracy");
  return res.data;
}

export async function fetchAuditLog(limit = 50): Promise<{ entries: AuditLogEntry[]; count: number }> {
  const res = await apiClient.get("/api/v1/audit-log", { params: { limit } });
  return res.data;
}
