import { useEffect, useMemo, useState } from "react";
import { AlertTriangle, RefreshCw, ShieldAlert } from "lucide-react";
import { fetchRiskAlerts } from "../api/client";
import { useRole } from "../context/RoleContext";
import type { RiskAlertReport } from "../types";

const HORIZONS = [7, 14, 30];

function tierClass(tier: string) {
  return `badge badge-${tier.toLowerCase()}`;
}

export function RiskAlertsPanel() {
  const { activeRole } = useRole();
  const [report, setReport] = useState<RiskAlertReport | null>(null);
  const [horizon, setHorizon] = useState(7);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = () => {
    if (!activeRole) return;
    setLoading(true);
    setError(null);
    fetchRiskAlerts()
      .then(setReport)
      .catch((e) => setError(e?.response?.data?.detail ?? "Failed to load risk alerts."))
      .finally(() => setLoading(false));
  };

  useEffect(load, [activeRole?.role_key]);

  const sorted = useMemo(() => {
    if (!report) return [];
    return [...report.alerts].sort((a, b) => {
      const pa = a.horizons.find((h) => h.horizon_days === horizon)?.probability ?? 0;
      const pb = b.horizons.find((h) => h.horizon_days === horizon)?.probability ?? 0;
      return pb - pa;
    });
  }, [report, horizon]);

  if (!activeRole?.allowed_views.includes("risk_alerts")) {
    return (
      <div className="panel p-6 h-full flex items-center justify-center text-sm text-gray-500">
        {activeRole?.display_name} does not have access to Early Risk Alerts.
      </div>
    );
  }

  return (
    <div className="panel p-5 flex flex-col h-full">
      <div className="flex items-center justify-between mb-4">
        <div className="flex items-center gap-2">
          <ShieldAlert size={20} className="text-red-400" />
          <h2 className="text-lg font-semibold">Early Risk Alerts</h2>
        </div>
        <button onClick={load} className="text-gray-400 hover:text-white transition-colors">
          <RefreshCw size={16} className={loading ? "animate-spin" : ""} />
        </button>
      </div>

      <div className="flex gap-2 mb-4">
        {HORIZONS.map((h) => (
          <button
            key={h}
            onClick={() => setHorizon(h)}
            className={`px-3 py-1 rounded-full text-xs font-medium border transition-colors ${
              horizon === h
                ? "bg-purple-500/20 border-purple-400/50 text-purple-300"
                : "border-white/10 text-gray-400 hover:text-white"
            }`}
          >
            {h}d horizon
          </button>
        ))}
      </div>

      {error && <div className="text-sm text-red-400">{error}</div>}

      <div className="flex-1 overflow-y-auto space-y-3 pr-1">
        {loading && <div className="text-sm text-gray-500">Loading…</div>}
        {!loading && sorted.length === 0 && (
          <div className="text-sm text-gray-500 text-center py-8">No active risk alerts in scope.</div>
        )}
        {sorted.map((alert) => {
          const hp = alert.horizons.find((h) => h.horizon_days === horizon);
          return (
            <div key={alert.asset_id} className="bg-white/5 border border-white/10 rounded-lg p-3">
              <div className="flex justify-between items-start gap-2">
                <div className="min-w-0">
                  <div className="flex items-center gap-1.5 font-medium text-sm truncate">
                    <AlertTriangle size={14} className="text-orange-400 shrink-0" />
                    <span className="truncate">{alert.asset_name}</span>
                  </div>
                  <div className="text-xs text-gray-500 mt-0.5">{alert.asset_label}</div>
                </div>
                {hp && <span className={tierClass(hp.risk_tier)}>{hp.risk_tier}</span>}
              </div>
              <div className="flex items-center justify-between mt-2 text-xs text-gray-400">
                <span>P({horizon}d) = {hp ? (hp.probability * 100).toFixed(1) : "-"}%</span>
                <span>base risk {alert.base_risk_tier} ({(alert.base_risk_score * 100).toFixed(0)}%)</span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
