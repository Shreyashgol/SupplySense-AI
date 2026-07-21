import React, { useState } from 'react';
import { RiskAlertsPanel } from '../components/RiskAlertsPanel';
import { ScenarioBuilder } from '../components/ScenarioBuilder';
import { DecisionOptimizationView } from '../components/DecisionOptimizationView';
import { Shield, Zap } from 'lucide-react';

export const Dashboard = () => {
  const [decisionResult, setDecisionResult] = useState<any>(null);

  return (
    <div className="min-h-screen bg-background text-foreground p-6 font-sans">
      <header className="mb-8">
        <div className="flex items-center gap-3">
          <div className="p-2.5 bg-primary/20 rounded-xl">
            <Zap className="text-primary" size={28} />
          </div>
          <div>
            <h1 className="text-3xl font-bold tracking-tight bg-clip-text text-transparent bg-gradient-to-r from-white to-gray-400">
              SupplySense-AI
            </h1>
            <p className="text-sm text-gray-400 mt-1 flex items-center gap-1.5">
              <Shield size={14} className="text-primary" />
              Energy Supply Chain Resilience & Optimization
            </p>
          </div>
        </div>
      </header>

      <main className="grid grid-cols-1 lg:grid-cols-12 gap-6">
        <div className="lg:col-span-4 space-y-6 flex flex-col">
          <div className="h-[45%]">
            <RiskAlertsPanel />
          </div>
          <div className="h-[55%]">
            <ScenarioBuilder onScenarioComplete={setDecisionResult} />
          </div>
        </div>
        
        <div className="lg:col-span-8">
          <DecisionOptimizationView decisionResult={decisionResult} />
        </div>
      </main>
    </div>
  );
};
