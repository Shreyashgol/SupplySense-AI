import React from 'react';
import { CheckCircle2, XCircle, AlertTriangle, Lightbulb, ExternalLink } from 'lucide-react';

export const DecisionOptimizationView = ({ decisionResult }: { decisionResult: any }) => {
  if (!decisionResult) {
    return (
      <div className="premium-card p-6 flex items-center justify-center h-full min-h-[400px]">
        <div className="text-center text-gray-500">
          <Lightbulb size={48} className="mx-auto mb-4 opacity-20" />
          <p>Run a scenario simulation to generate actionable recommendations.</p>
        </div>
      </div>
    );
  }

  return (
    <div className="premium-card p-6">
      <div className="flex items-center justify-between mb-6 border-b border-white/10 pb-4">
        <div>
          <h2 className="text-2xl font-semibold tracking-tight text-white mb-1">Optimized Recommendations</h2>
          <p className="text-sm text-gray-400">Decision Run: {decisionResult.decision_run_id}</p>
        </div>
        <div className="text-right">
          <div className="text-sm text-gray-400 mb-1">Scenario</div>
          <div className="font-medium text-white">{decisionResult.scenario_name}</div>
        </div>
      </div>

      <div className="space-y-6">
        {decisionResult.recommendations.map((rec: any, idx: number) => {
          const pv = rec.policy_validation;
          const statusColors = {
            PASS: 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400',
            WARN: 'bg-orange-500/10 border-orange-500/20 text-orange-400',
            FAIL: 'bg-red-500/10 border-red-500/20 text-red-400',
          };
          const statusIcon = {
            PASS: <CheckCircle2 size={18} />,
            WARN: <AlertTriangle size={18} />,
            FAIL: <XCircle size={18} />,
          };

          return (
            <div key={idx} className="bg-white/5 border border-white/10 rounded-xl p-5 hover:border-primary/30 transition-colors">
              <div className="flex justify-between items-start mb-4">
                <div className="flex items-start gap-4">
                  <div className="h-10 w-10 rounded-full bg-primary/20 flex items-center justify-center text-primary font-bold">
                    #{idx + 1}
                  </div>
                  <div>
                    <h3 className="text-lg font-semibold text-white">{rec.title}</h3>
                    <div className="text-sm text-gray-400 flex items-center gap-2 mt-1">
                      <span className="bg-white/10 px-2 py-0.5 rounded text-xs">{rec.action_type}</span>
                      <span>Target: {rec.target_asset_name}</span>
                    </div>
                  </div>
                </div>
                
                <div className={`flex items-center gap-2 px-3 py-1.5 rounded-lg border ${statusColors[pv.status as keyof typeof statusColors] || statusColors.WARN}`}>
                  {statusIcon[pv.status as keyof typeof statusIcon]}
                  <span className="font-medium text-sm">Policy: {pv.status}</span>
                </div>
              </div>

              {/* Rationale Block (LLM Output) */}
              {rec.rationale_text && (
                <div className="mb-4 bg-primary/5 border border-primary/20 rounded-lg p-4">
                  <div className="flex items-start gap-3">
                    <Lightbulb className="text-primary mt-1 shrink-0" size={18} />
                    <div>
                      <p className="text-gray-200 text-sm leading-relaxed">{rec.rationale_text}</p>
                      {rec.is_ambiguous && (
                        <div className="mt-2 inline-flex items-center gap-1.5 text-xs font-medium text-orange-400 bg-orange-400/10 px-2 py-1 rounded">
                          <AlertTriangle size={12} />
                          Human Review Advised: Ambiguous Signals Detected
                        </div>
                      )}
                    </div>
                  </div>
                </div>
              )}

              <div className="grid grid-cols-4 gap-4 mt-4">
                <div className="bg-black/20 rounded-lg p-3">
                  <div className="text-xs text-gray-500 uppercase">Impact Red.</div>
                  <div className="text-lg font-semibold text-emerald-400">+{rec.expected_impact_reduction_pct}%</div>
                </div>
                <div className="bg-black/20 rounded-lg p-3">
                  <div className="text-xs text-gray-500 uppercase">Confidence</div>
                  <div className="text-lg font-semibold text-blue-400">{(rec.confidence * 100).toFixed(0)}%</div>
                </div>
                <div className="bg-black/20 rounded-lg p-3">
                  <div className="text-xs text-gray-500 uppercase">Time to Impl.</div>
                  <div className="text-lg font-semibold text-white">{rec.implementation_days}d</div>
                </div>
                <div className="bg-black/20 rounded-lg p-3">
                  <div className="text-xs text-gray-500 uppercase">Cost Index</div>
                  <div className="text-lg font-semibold text-white">{rec.cost_index}</div>
                </div>
              </div>

              {(pv.blockers.length > 0 || pv.warnings.length > 0) && (
                <div className="mt-4 pt-4 border-t border-white/5 space-y-2">
                  {pv.blockers.map((b: string, i: number) => (
                    <div key={i} className="text-xs text-red-400 flex items-center gap-2"><XCircle size={12}/> {b}</div>
                  ))}
                  {pv.warnings.map((w: string, i: number) => (
                    <div key={i} className="text-xs text-orange-400 flex items-center gap-2"><AlertTriangle size={12}/> {w}</div>
                  ))}
                </div>
              )}
              
              <div className="mt-4 flex justify-end">
                <button 
                  className={`text-sm font-medium px-4 py-2 rounded-lg flex items-center gap-2 transition-colors ${
                    pv.status === 'FAIL' 
                      ? 'bg-gray-800 text-gray-500 cursor-not-allowed' 
                      : 'bg-white/10 hover:bg-white/20 text-white'
                  }`}
                  disabled={pv.status === 'FAIL'}
                >
                  Execute Action
                  <ExternalLink size={14} />
                </button>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
};
