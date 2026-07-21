import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ScenarioBuilder } from '../ScenarioBuilder';
import * as api from '../../services/api';

vi.mock('../../services/api', () => ({
  optimizeDecision: vi.fn(),
  generateRecommendations: vi.fn(),
}));

describe('ScenarioBuilder', () => {
  it('renders correctly and has default values', () => {
    render(<ScenarioBuilder onScenarioComplete={vi.fn()} />);
    expect(screen.getByText('Scenario Simulator')).toBeInTheDocument();
    expect(screen.getByText('Run Simulation & Optimize')).toBeInTheDocument();
  });

  it('calls optimize and generate endpoints when simulate is clicked', async () => {
    const mockOnComplete = vi.fn();
    (api.optimizeDecision as any).mockResolvedValue({ decision: { decision_run_id: 'dr_123' } });
    (api.generateRecommendations as any).mockResolvedValue({ decision: { success: true } });

    render(<ScenarioBuilder onScenarioComplete={mockOnComplete} />);
    
    const runBtn = screen.getByText('Run Simulation & Optimize');
    fireEvent.click(runBtn);
    
    await waitFor(() => {
      expect(api.optimizeDecision).toHaveBeenCalled();
      expect(api.generateRecommendations).toHaveBeenCalledWith('dr_123');
      expect(mockOnComplete).toHaveBeenCalledWith({ success: true });
    });
  });
});
