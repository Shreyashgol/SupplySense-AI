import React from 'react';
import { render, screen } from '@testing-library/react';
import { describe, it, expect } from 'vitest';
import { DecisionOptimizationView } from '../DecisionOptimizationView';

describe('DecisionOptimizationView', () => {
  it('displays placeholder when no decision result is provided', () => {
    render(<DecisionOptimizationView decisionResult={null} />);
    expect(screen.getByText('Run a scenario simulation to generate actionable recommendations.')).toBeInTheDocument();
  });

  it('displays recommendations and rationale correctly', () => {
    const mockDecisionResult = {
      decision_run_id: 'dr_001',
      scenario_name: 'Test Scenario',
      recommendations: [
        {
          title: 'Reroute to Alternative',
          action_type: 'Reroute',
          target_asset_name: 'Terminal X',
          rationale_text: 'This is the best option because it reduces impact.',
          is_ambiguous: false,
          expected_impact_reduction_pct: 12.5,
          confidence: 0.85,
          implementation_days: 5,
          cost_index: 1.1,
          policy_validation: {
            status: 'PASS',
            blockers: [],
            warnings: []
          }
        }
      ]
    };

    render(<DecisionOptimizationView decisionResult={mockDecisionResult} />);
    
    expect(screen.getByText('Optimized Recommendations')).toBeInTheDocument();
    expect(screen.getByText('Reroute to Alternative')).toBeInTheDocument();
    expect(screen.getByText('This is the best option because it reduces impact.')).toBeInTheDocument();
    expect(screen.getByText('Policy: PASS')).toBeInTheDocument();
    expect(screen.getByText('+12.5%')).toBeInTheDocument();
  });

  it('disables execute button when policy validation fails', () => {
    const mockDecisionResult = {
      decision_run_id: 'dr_001',
      scenario_name: 'Test Scenario',
      recommendations: [
        {
          title: 'Buy from Sanctioned',
          action_type: 'Procurement',
          target_asset_name: 'Sanctioned Corp',
          rationale_text: 'Cheap but risky.',
          is_ambiguous: false,
          expected_impact_reduction_pct: 20.0,
          confidence: 0.9,
          implementation_days: 2,
          cost_index: 0.5,
          policy_validation: {
            status: 'FAIL',
            blockers: ['Sanctioned entity detected'],
            warnings: []
          }
        }
      ]
    };

    render(<DecisionOptimizationView decisionResult={mockDecisionResult} />);
    
    expect(screen.getByText('Policy: FAIL')).toBeInTheDocument();
    expect(screen.getByText('Sanctioned entity detected')).toBeInTheDocument();
    
    const execBtn = screen.getByText('Execute Action');
    expect(execBtn).toBeDisabled();
  });
});
