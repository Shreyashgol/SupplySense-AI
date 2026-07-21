import { useState } from "react";
import { PlayCircle } from "lucide-react";
import { optimizeDecision } from "../api/client";
import { AssetPicker } from "./AssetPicker";
import type { AssetOption } from "../types";

interface Props {
  onCompleted: (decisionRunId: string) => void;
}

export function ScenarioRunner({ onCompleted }: Props) {
  const [name, setName] = useState("");
  const [disruptionType, setDisruptionType] = useState("strait_closure");
  const [durationDays, setDurationDays] = useState(7);
  const [assets, setAssets] = useState<AssetOption[]>([]);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const submit = async () => {
    setSubmitting(true);
    setError(null);
    try {
      const scenarioId = `scenario_${Date.now()}`;
      const data = await optimizeDecision({
        scenario_id: scenarioId,
        name: name || assets.map((a) => a.asset_name).join(", ") || scenarioId,
        disruption_type: disruptionType,
        duration_days: durationDays,
        affected_assets: assets.map((a) => a.asset_id),
      });
      onCompleted(data.decision.decision_run_id);
      setName("");
      setAssets([]);
    } catch (e: any) {
      setError(e?.response?.data?.detail ?? "Scenario run failed.");
    } finally {
      setSubmitting(false);
    }
  };

  return (
    <div className="panel p-4 space-y-3">
      <div className="flex items-center gap-2 text-sm font-semibold">
        <PlayCircle size={16} className="text-emerald-300" />
        Run New What-If Scenario
      </div>

      <AssetPicker selected={assets} onChange={setAssets} />

      <input
        className="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs"
        placeholder="Display name (optional — defaults to asset names)"
        value={name}
        onChange={(e) => setName(e.target.value)}
      />
      <div className="flex gap-2">
        <select
          className="flex-1 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs"
          value={disruptionType}
          onChange={(e) => setDisruptionType(e.target.value)}
        >
          <option value="strait_closure">Strait / chokepoint closure</option>
          <option value="port_congestion">Port congestion</option>
          <option value="refinery_outage">Refinery outage</option>
          <option value="sanctions">Sanctions / supplier loss</option>
          <option value="weather_disruption">Weather disruption</option>
          <option value="generic">Generic disruption</option>
        </select>
        <input
          type="number"
          min={1}
          title="Duration (days)"
          className="w-20 bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-xs"
          value={durationDays}
          onChange={(e) => setDurationDays(Number(e.target.value))}
        />
      </div>
      {error && <div className="text-xs text-red-400">{error}</div>}
      <button
        onClick={submit}
        disabled={submitting || assets.length === 0}
        className="w-full bg-emerald-500/20 border border-emerald-400/40 text-emerald-300 rounded-lg py-2 text-xs font-medium disabled:opacity-40 hover:bg-emerald-500/30 transition-colors"
      >
        {submitting ? "Running Part E + F…" : "Simulate + Optimize"}
      </button>
    </div>
  );
}
