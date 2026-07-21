import React, { useState } from 'react';
import { Activity, Play } from 'lucide-react';
import { simulateScenario, optimizeDecision, generateRecommendations } from '../services/api';

export const ScenarioBuilder = ({ onScenarioComplete }: { onScenarioComplete: (data: any) => void }) => {
  const [loading, setLoading] = useState(false);
  const [disruptionType, setDisruptionType] = useState('partial_closure');
  const [assetId, setAssetId] = useState('shippingroute_3bd6d0002385eb0842fd5039');
  const [magnitude, setMagnitude] = useState(30);

  const handleSimulate = async () => {
    setLoading(true);
    try {
      const scenario = {
        scenario_id: `sim_${Date.now()}`,
        scenario_name: `Simulation - ${assetId}`,
        name: `Simulation - ${assetId}`,
        disruption_type: disruptionType,
        affected_assets: [assetId],
        supply_shock_magnitude: magnitude / 100,
        duration_days: 14,
      };
      
      // We run the full pipeline: optimize -> generate recommendations
      const optResult = await optimizeDecision(scenario, 5);
      const finalResult = await generateRecommendations(optResult.decision.decision_run_id);
      
      onScenarioComplete(finalResult.decision);
    } catch (e) {
      console.error('Simulation failed', e);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="premium-card p-6">
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 bg-blue-500/20 rounded-lg text-blue-400">
          <Activity size={24} />
        </div>
        <h2 className="text-xl font-semibold tracking-tight">Scenario Simulator</h2>
      </div>

      <div className="space-y-4">
        <div>
          <label className="block text-sm font-medium text-gray-400 mb-1">Disruption Target</label>
          <select 
            className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2.5 text-white focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all"
            value={assetId}
            onChange={(e) => setAssetId(e.target.value)}
          >
            <option value="shippingroute_3bd6d0002385eb0842fd5039">Strait of Hormuz</option>
            <option value="port_9bb8d58c01a14a651d62c105">Red Sea Port (Djibouti)</option>
            <option value="refinery_f34035b6c455bbeac3690b01">Abadan Refinery</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-400 mb-1">Disruption Type</label>
          <select 
            className="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2.5 text-white focus:ring-2 focus:ring-primary focus:border-transparent outline-none transition-all"
            value={disruptionType}
            onChange={(e) => setDisruptionType(e.target.value)}
          >
            <option value="partial_closure">Partial Closure (Capacity Drop)</option>
            <option value="full_closure">Full Closure (0 Capacity)</option>
            <option value="price_spike">Price Spike</option>
          </select>
        </div>

        <div>
          <label className="block text-sm font-medium text-gray-400 mb-1">Severity Magnitude ({magnitude}%)</label>
          <input 
            type="range" 
            min="10" 
            max="100" 
            step="10"
            value={magnitude}
            onChange={(e) => setMagnitude(Number(e.target.value))}
            className="w-full h-2 bg-white/10 rounded-lg appearance-none cursor-pointer accent-primary"
          />
        </div>

        <button 
          onClick={handleSimulate}
          disabled={loading}
          className="w-full mt-4 bg-primary hover:bg-primary/90 text-primary-foreground font-semibold py-3 rounded-lg flex items-center justify-center gap-2 transition-colors disabled:opacity-50"
        >
          {loading ? (
            <div className="animate-spin rounded-full h-5 w-5 border-b-2 border-white"></div>
          ) : (
            <>
              <Play size={18} />
              Run Simulation & Optimize
            </>
          )}
        </button>
      </div>
    </div>
  );
};
