import { api } from './client';
import type { FarmDetail, HealthSummary } from '../types';

export const fetchFarms = (): Promise<{ farms: FarmDetail[] }> => {
  return api.get<{ farms: FarmDetail[] }>('/farms');
};

export const fetchFarm = (farmId: string): Promise<FarmDetail> => {
  return api.get<FarmDetail>(`/farms/${farmId}`);
};

export const fetchFarmHealth = (farmId: string): Promise<HealthSummary> => {
  return api.get<HealthSummary>(`/farms/${farmId}/health`);
};

export const runFarmAnalysis = (farmId: string): Promise<any> => {
  return api.post<any>(`/farms/${farmId}/analyze`, {});
};

export const uploadObservation = (farmId: string, payload: any): Promise<any> => {
  return api.post<any>(`/farms/${farmId}/observations`, payload);
};

export const runImageAnalysis = (farmId: string, payload: any): Promise<any> => {
  return api.post<any>(`/farms/${farmId}/image-analysis`, payload);
};
