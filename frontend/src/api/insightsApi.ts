import { apiRequest } from './backendApi';
import type {
  DailyTotalsResponse,
  EnergyRecommendation,
  InsightsPeriod,
  InsightsResponse,
  TodayInsightsResponse,
} from './types';

export const fetchInsights = (period: InsightsPeriod) =>
  apiRequest<InsightsResponse>(`/api/insights?period=${period}`);

/** One local day's breakdown; `date` is YYYY-MM-DD (omit for today). */
export const fetchTodayInsights = (date?: string) =>
  apiRequest<TodayInsightsResponse>(`/api/insights/today${date ? `?date=${date}` : ''}`);

/** Per-day totals ending at `end` (YYYY-MM-DD, default today). */
export const fetchDailyTotals = (days = 14, end?: string) =>
  apiRequest<DailyTotalsResponse>(`/api/insights/days?days=${days}${end ? `&end=${end}` : ''}`);

export const fetchRecommendations = () => apiRequest<EnergyRecommendation[]>('/api/insights/recommendations');
