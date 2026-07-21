import axios from 'axios';

const API_BASE_URL = 'http://localhost:8000/api/v1';

export const apiClient = axios.create({
  baseURL: API_BASE_URL,
  headers: {
    'Content-Type': 'application/json',
  },
});

export const fetchRiskAssessments = async (limit = 10) => {
  const response = await apiClient.post('/risk/assessments', { limit });
  return response.data;
};

export const simulateScenario = async (scenario: any) => {
  const response = await apiClient.post('/scenarios/simulate', { scenario, write_back: true });
  return response.data;
};

export const optimizeDecision = async (scenario: any, top_k = 5) => {
  const response = await apiClient.post('/decisions/optimize', { scenario, top_k, write_back: true });
  return response.data;
};

export const generateRecommendations = async (decision_run_id: string) => {
  const response = await apiClient.post(`/decisions/${decision_run_id}/recommendations/generate`);
  return response.data;
};
