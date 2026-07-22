import { useState } from "react";
import { PlayCircle, Shield, Zap } from "lucide-react";
import { RoleSelector } from "../components/RoleSelector";
import { RiskAlertsPanel } from "../components/RiskAlertsPanel";
import { DecisionRunPicker } from "../components/DecisionRunPicker";
import { ScenarioRunner } from "../components/ScenarioRunner";
import { ExecutiveActionPlanBoard } from "../components/ExecutiveActionPlanBoard";
import { RecommendationsList } from "../components/RecommendationsList";
import { ScenarioComparisonView } from "../components/ScenarioComparisonView";
import { AuditLogPanel } from "../components/AuditLogPanel";
import { SystemRefreshPanel } from "../components/SystemRefreshPanel";
import { useRole } from "../context/RoleContext";

type Tab = "action-plan" | "recommendations" | "comparison" | "new-scenario";

export function Dashboard() {
  const { activeRole, loading, error } = useRole();
  const [decisionRunId, setDecisionRunId] = useState<string | null>(null);
  const [refreshKey, setRefreshKey] = useState(0);
  const [tab, setTab] = useState<Tab>("action-plan");

  if (loading) {
    return <div className="min-h-screen flex items-center justify-center text-gray-500">Loading…</div>;
  }
  if (error) {
    return (
      <div className="min-h-screen flex items-center justify-center text-red-400 text-sm px-6 text-center">
        {error}
      </div>
    );
  }

  return (
    <div className="min-h-screen p-6">
      <header className="mb-6 flex items-center justify-between flex-wrap gap-3">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-purple-500/20 rounded-xl">
            <Zap className="text-purple-300" size={26} />
          </div>
          <div>
            <h1 className="text-2xl font-bold tracking-tight">SupplySense-AI</h1>
            <p className="text-xs text-gray-500 flex items-center gap-1.5">
              <Shield size={12} className="text-purple-300" />
              Outputs &amp; Actionable Recommendations — {activeRole?.display_name}
            </p>
          </div>
        </div>
        <RoleSelector />
      </header>

      <main className="grid grid-cols-1 lg:grid-cols-12 gap-5">
        <div className="lg:col-span-3 space-y-5">
          <SystemRefreshPanel />
          <div className="h-[420px]">
            <RiskAlertsPanel
              onPlanGenerated={(id) => {
                setDecisionRunId(id);
                setRefreshKey((k) => k + 1);
                setTab("action-plan");
              }}
            />
          </div>
          <DecisionRunPicker selected={decisionRunId} onSelect={setDecisionRunId} refreshKey={refreshKey} />
          <AuditLogPanel />
        </div>

        <div className="lg:col-span-9">
          <div className="flex items-center justify-between gap-2 mb-4">
            <div className="flex gap-2">
              {(
                [
                  ["action-plan", "Executive Action Plan"],
                  ["recommendations", "Recommendations"],
                  ["comparison", "Scenario Comparison"],
                ] as [Tab, string][]
              ).map(([key, label]) => (
                <button
                  key={key}
                  onClick={() => setTab(key)}
                  className={`px-4 py-2 rounded-lg text-sm font-medium transition-colors ${
                    tab === key ? "bg-white/10 text-white" : "text-gray-500 hover:text-white"
                  }`}
                >
                  {label}
                </button>
              ))}
            </div>

            <button
              onClick={() => setTab("new-scenario")}
              className={`flex items-center gap-1.5 px-4 py-2 rounded-lg text-sm font-semibold border transition-colors ${
                tab === "new-scenario"
                  ? "bg-emerald-500/25 border-emerald-400/60 text-emerald-200"
                  : "bg-emerald-500/10 border-emerald-400/30 text-emerald-300 hover:bg-emerald-500/20"
              }`}
            >
              <PlayCircle size={15} />
              Run New What-If Scenario
            </button>
          </div>

          {tab === "action-plan" && <ExecutiveActionPlanBoard decisionRunId={decisionRunId} />}
          {tab === "recommendations" && <RecommendationsList decisionRunId={decisionRunId} />}
          {tab === "comparison" && <ScenarioComparisonView />}
          {tab === "new-scenario" && (
            <div className="max-w-xl">
              <ScenarioRunner
                onCompleted={(id) => {
                  setDecisionRunId(id);
                  setRefreshKey((k) => k + 1);
                  setTab("action-plan");
                }}
              />
            </div>
          )}
        </div>
      </main>
    </div>
  );
}
