import React from 'react';
import { render, screen, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { RiskAlertsPanel } from '../RiskAlertsPanel';
import * as api from '../../services/api';

vi.mock('../../services/api', () => ({
  fetchRiskAssessments: vi.fn(),
}));

describe('RiskAlertsPanel', () => {
  it('displays loading state initially', () => {
    (api.fetchRiskAssessments as any).mockResolvedValue({ assessments: [] });
    render(<RiskAlertsPanel />);
    // There isn't text for loading, just pulse divs, but we can verify it doesn't show "No active risks" immediately
    expect(screen.queryByText('No active risks detected.')).not.toBeInTheDocument();
  });

  it('displays no active risks when data is empty', async () => {
    (api.fetchRiskAssessments as any).mockResolvedValue({ assessments: [] });
    render(<RiskAlertsPanel />);
    await waitFor(() => {
      expect(screen.getByText('No active risks detected.')).toBeInTheDocument();
    });
  });

  it('displays risk alerts correctly', async () => {
    const mockData = {
      assessments: [
        {
          asset_id: 'route_hormuz',
          asset_name: 'Strait of Hormuz',
          risk_tier: 'CRITICAL',
          predicted_at: '2023-10-27T10:00:00Z',
          risk_score: 0.85
        }
      ]
    };
    (api.fetchRiskAssessments as any).mockResolvedValue(mockData);
    
    render(<RiskAlertsPanel />);
    
    await waitFor(() => {
      expect(screen.getByText('Strait of Hormuz')).toBeInTheDocument();
      expect(screen.getByText('CRITICAL')).toBeInTheDocument();
      expect(screen.getByText('85.0%')).toBeInTheDocument();
    });
  });
});
