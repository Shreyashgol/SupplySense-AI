import React, { useEffect, useState } from 'react';
import { AlertTriangle, Clock, ShieldAlert } from 'lucide-react';
import { fetchRiskAssessments } from '../services/api';

export const RiskAlertsPanel = () => {
  const [alerts, setAlerts] = useState<any[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const loadAlerts = async () => {
      try {
        const data = await fetchRiskAssessments(5);
        setAlerts(data.assessments || []);
      } catch (e) {
        console.error('Failed to load risk assessments', e);
      } finally {
        setLoading(false);
      }
    };
    loadAlerts();
  }, []);

  return (
    <div className="premium-card p-6 flex flex-col h-full">
      <div className="flex items-center gap-3 mb-6">
        <div className="p-2 bg-red-500/20 rounded-lg text-red-400">
          <ShieldAlert size={24} />
        </div>
        <h2 className="text-xl font-semibold tracking-tight">Active Risk Signals</h2>
      </div>

      <div className="flex-1 overflow-y-auto space-y-4 pr-2">
        {loading ? (
          <div className="animate-pulse space-y-4">
            {[1, 2, 3].map((i) => (
              <div key={i} className="h-24 bg-white/5 rounded-xl"></div>
            ))}
          </div>
        ) : alerts.length === 0 ? (
          <div className="text-center text-gray-400 py-8">
            No active risks detected.
          </div>
        ) : (
          alerts.map((alert, idx) => (
            <div key={idx} className="group relative bg-white/5 border border-white/10 rounded-xl p-4 hover:bg-white/10 transition-colors">
              <div className="flex justify-between items-start mb-2">
                <h3 className="font-medium text-gray-100 flex items-center gap-2">
                  <AlertTriangle size={16} className={alert.risk_tier === 'CRITICAL' ? 'text-red-500' : 'text-orange-400'} />
                  {alert.asset_name || alert.asset_id}
                </h3>
                <span className={`px-2 py-1 rounded text-xs font-bold ${
                  alert.risk_tier === 'CRITICAL' ? 'bg-red-500/20 text-red-400' : 'bg-orange-500/20 text-orange-400'
                }`}>
                  {alert.risk_tier || 'HIGH'}
                </span>
              </div>
              
              <div className="flex justify-between items-end mt-4">
                <div className="text-sm text-gray-400 flex items-center gap-1">
                  <Clock size={14} />
                  <span>{new Date(alert.predicted_at).toLocaleDateString()}</span>
                </div>
                <div className="text-right">
                  <div className="text-xs text-gray-500 uppercase tracking-wider mb-1">Probability</div>
                  <div className="text-lg font-mono text-white">{(alert.risk_score * 100).toFixed(1)}%</div>
                </div>
              </div>
            </div>
          ))
        )}
      </div>
    </div>
  );
};
