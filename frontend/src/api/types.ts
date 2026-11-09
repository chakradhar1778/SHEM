/**
 * SHEM — Backend response/request shapes (mirror backend/app/models/schemas.py).
 * Datetimes are UTC ISO 8601 strings.
 */

import type { AIActionEvent, Conflict, DailyInsight } from './aiTypes';

export type RelayState = 'ON' | 'OFF';

export interface HealthResponse {
  status: 'ok' | 'degraded';
  version: string;
  dbOk: boolean;
  mqttConnected: boolean;
  timestamp: string;
}

export interface DeviceStatus {
  deviceId: string;
  mqttConnected: boolean;
  deviceOnline: boolean;
  connectionStatus: 'online' | 'offline' | 'unknown' | string;
  lastSeenAt: string | null;
  pzemReadingsValid: boolean;
  relay1State: RelayState | null;
  staleSince: string | null;
}

/** One physical AC reading from the PZEM-004T. */
export interface TelemetryReading {
  id?: number | null;
  deviceId: string;
  voltageV: number | null;
  currentA: number | null;
  activePowerW: number | null;
  energyKWh: number | null;
  frequencyHz: number | null;
  powerFactor: number | null;
  relay1State: string | null;
  /** Measured load activity (power above threshold) — NOT the relay state */
  loadActive: boolean | null;
  supplyType: string;
  source: string;
  validity: string;
  validityReason?: string | null;
  measuredAt: string | null;
  receivedAt: string | null;
}

export interface LatestTelemetryResponse {
  available: boolean;
  stale: boolean;
  ageSeconds: number | null;
  reading: TelemetryReading | null;
  message: string | null;
}

export interface TelemetryHistoryPoint {
  timestamp: string;
  samples: number;
  voltageV: number | null;
  currentA: number | null;
  activePowerW: number | null;
  maxPowerW: number | null;
  energyKWh: number | null;
  energyUsedKWh: number | null;
  frequencyHz: number | null;
  powerFactor: number | null;
}

export interface TelemetryHistoryResponse {
  deviceId: string;
  fromTime: string;
  toTime: string;
  resolution: string;
  count: number;
  truncated: boolean;
  dataNote: string | null;
  readings: TelemetryHistoryPoint[];
}

export interface RelayStatus {
  deviceId: string;
  channel: number;
  commandedState: RelayState | null;
  lastReportedAt: string | null;
}

export type RelayCommandStatus =
  | 'pending'
  | 'published'
  | 'applied'
  | 'rejected_expired'
  | 'rejected_invalid_channel'
  | 'rejected_invalid_state'
  | 'rejected_time_unsynchronized'
  | 'timeout'
  | 'publish_failed';

export interface RelayCommandResponse {
  commandId: string;
  channel: number;
  requestedState: RelayState;
  status: RelayCommandStatus;
  message: string;
  createdAt: string;
  expiresAt: string;
}

export interface RelayCommandDetail {
  commandId: string;
  deviceId: string;
  channel: number;
  requestedState: RelayState;
  status: RelayCommandStatus;
  createdAt: string;
  publishedAt: string | null;
  acknowledgedAt: string | null;
  expiresAt: string | null;
  errorMessage: string | null;
  /** present on relay_update stream events */
  commandedState?: RelayState;
}

export interface HouseholdConfigDTO {
  homeName: string;
  location: string | null;
  homeType: string;
  occupants: number;
  floorAreaSqm: number | null;
  utilityProvider: string | null;
  tariffRateINRPerKWh: number;
  isConfigured: boolean;
  updatedAt: string | null;
}

export interface RoomDTO {
  id: string;
  name: string;
  roomType: string | null;
  floor: number | null;
  createdAt: string | null;
}

export interface ApplianceDTO {
  id: string;
  roomId: string | null;
  catalogueId: string | null;
  name: string;
  category: string | null;
  iconType: string | null;
  ratedWatts: number | null;
  quantity: number;
  dailyHours: number;
  status: string;
  isEssential: 'yes' | 'no' | 'unsure' | null;
  brand: string | null;
  model: string | null;
  purchaseYear: number | null;
  notes: string | null;
  /** Relay channel that switches this appliance (null = not relay-controlled) */
  relayChannel: number | null;
  /** True when not on a relay → runs as a realistic simulated device */
  isSimulated: boolean;
  /** Simulated only: follow the daily routine built from dailyHours */
  simAuto: boolean;
  simManualState: 'ON' | 'OFF' | null;
  simOverrideUntil: string | null;
  createdAt: string | null;
  updatedAt: string | null;
}

export interface BillDTO {
  id: string;
  utilityProvider: string | null;
  accountId: string | null;
  billingMonth: number | null;
  billingYear: number | null;
  billingPeriod: string | null;
  billingPeriodStart: string | null;
  billingPeriodEnd: string | null;
  billingPeriodDays: number | null;
  dueDate: string | null;
  documentFilename: string | null;
  unitsConsumedKWh: number;
  billAmountINR: number;
  locationTag: string | null;
  /** A bill document (image/PDF) is stored and can be viewed */
  hasDocument: boolean;
  documentContentType: string | null;
  documentSize: number | null;
  documentUploadedAt: string | null;
  createdAt: string | null;
}

export interface TargetDTO {
  monthlyBudgetINR: number;
  targetType: 'budget' | 'reduction';
  isConfigured: boolean;
  monthlyTargetKWh: number | null;
  updatedAt: string | null;
}

// ── Insights ──────────────────────────────────────────────────────────────────

export type InsightsPeriod = 'week' | 'month' | 'year';

export interface InsightsTrendPoint {
  label: string;
  start: string;
  usageKWh: number;
  targetKWh: number | null;
  isPeak: boolean;
  /** false → no telemetry in this bucket (shown as 0, not estimated) */
  measured: boolean;
}

/** Household rated-load ESTIMATE per category (not a meter reading). */
export interface CategoryShare {
  categoryId: string;
  categoryLabel: string;
  iconType: string;
  kwh: number;
  percentage: number;
  percentChange: number | null;
  direction: 'up' | 'down' | 'neutral';
}

export interface InsightsResponse {
  period: InsightsPeriod;
  periodLabel: string;
  periodStart: string;
  periodEnd: string;
  totalKWh: number;
  totalCostINR: number;
  effectiveRateINR: number;
  isCostEstimated: boolean;
  rateDisclosure: string;
  hasData: boolean;
  isModelledEstimate: boolean;
  coverageHours: number;
  expectedHours: number;
  dataNote: string | null;
  methodologyNote: string;
  keyInsight: { title: string; description: string; peakPeriod: string | null };
  trendPoints: InsightsTrendPoint[];
  shifts: CategoryShare[];
  shiftsAreEstimates: boolean;
  comparison: { previousKWh: number; previousCoverageHours: number; percentChange: number | null } | null;
  billComparison: {
    billingLabel: string;
    billDailyKWh: number;
    billRateINR: number;
    measuredDailyKWh: number | null;
  } | null;
  meteredKWh: number;
  simulatedKWh: number;
  applianceUsage: ApplianceUsage[];
}

export type UsageSource = 'metered' | 'simulated';

/** Energy of one appliance in a period: metered (relay circuit, PZEM) or simulated. */
export interface ApplianceUsage {
  applianceId: string;
  name: string;
  iconType: string | null;
  category: string | null;
  roomName: string | null;
  source: UsageSource;
  kwh: number;
  percentage: number;
  costINR: number;
  onHours: number | null;
  peakHour: number | null;
  peakHourLabel: string | null;
}

export interface HourlyPoint {
  hour: number;
  timeLabel: string;
  usageKWh: number;
  meteredKWh: number;
  simulatedKWh: number;
  targetKWh: number | null;
  isPeak: boolean;
  measured: boolean;
}

export interface PeriodTopAppliance {
  applianceId: string;
  name: string;
  iconType: string | null;
  source: UsageSource;
  kwh: number;
}

export type DayPeriodKey = 'night' | 'morning' | 'afternoon' | 'evening';

export interface DayPeriodBreakdown {
  period: DayPeriodKey;
  label: string;
  timeRange: string;
  kwh: number;
  percentage: number;
  meteredKWh: number;
  simulatedKWh: number;
  costINR: number;
  avgPowerW: number;
  isPeak: boolean;
  peakHour: number | null;
  peakHourLabel: string | null;
  peakHourKWh: number | null;
  topAppliances: PeriodTopAppliance[];
}

export interface PeakSummary {
  period: DayPeriodKey | null;
  periodLabel: string | null;
  hour: number | null;
  hourLabel: string | null;
  hourKWh: number | null;
  avgPowerW: number | null;
  topAppliance: string | null;
}

export interface TodayInsightsResponse {
  date: string;
  isToday: boolean;
  hasData: boolean;
  energyTodayKWh: number;
  dailyTargetKWh: number | null;
  isTargetConfigured: boolean;
  costTodayINR: number;
  effectiveRateINR: number;
  rateDisclosure: string;
  hourlyPoints: HourlyPoint[];
  dayPeriods: DayPeriodBreakdown[];
  applianceBreakdown: CategoryShare[];
  insightCard: { title: string; description: string; badgeText: string };
  dataNote: string | null;
  methodologyNote: string;
  meteredKWh: number;
  simulatedKWh: number;
  applianceUsage: ApplianceUsage[];
  peak: PeakSummary | null;
}

export interface DailyTotal {
  date: string;
  weekday: string;
  dayLabel: string;
  kwh: number;
  meteredKWh: number;
  simulatedKWh: number;
  costINR: number;
  hasData: boolean;
  isToday: boolean;
  peakPeriod: DayPeriodKey | null;
}

export interface DailyTotalsResponse {
  days: DailyTotal[];
  averageKWh: number | null;
  dailyTargetKWh: number | null;
}

// ── Simulated appliances ──────────────────────────────────────────────────────

export interface SimApplianceLive {
  applianceId: string;
  name: string;
  iconType: string | null;
  roomId: string | null;
  state: RelayState;
  powerW: number;
  /** auto = following the daily routine, manual = switched from the app, off = routine disabled */
  mode: 'auto' | 'manual' | 'off';
  simAuto: boolean;
  overrideUntil: string | null;
  nextChangeAt: string | null;
  routine: string | null;
  todayKWh: number;
  ratedWatts: number | null;
  quantity: number;
}

export interface SimStatus {
  appliances: SimApplianceLive[];
  totalPowerW: number;
  voltageV: number | null;
  serverTime: string | null;
}

export interface EnergyRecommendation {
  id: string;
  title: string;
  description: string;
  category: string;
  priority: 'high' | 'medium' | 'low';
  evidence: string;
}

// ── WebSocket stream events ───────────────────────────────────────────────────

export interface InitSnapshot {
  serverTime: string;
  deviceStatus: DeviceStatus;
  latestTelemetry: LatestTelemetryResponse;
  relayStatus: RelayStatus;
  simStatus?: SimStatus;
}

export type StreamEvent =
  | { type: 'init_snapshot'; data: InitSnapshot; sentAt: string }
  | { type: 'telemetry'; data: TelemetryReading; sentAt: string }
  | { type: 'sim_update'; data: SimStatus; sentAt: string }
  | { type: 'device_status'; data: DeviceStatus; sentAt: string }
  | { type: 'relay_state'; data: RelayStatus; sentAt: string }
  | { type: 'relay_update'; data: RelayCommandDetail; sentAt: string }
  | { type: 'heartbeat'; data: { serverTime: string; mqttConnected: boolean }; sentAt: string }
  | { type: 'pong'; data: { serverTime: string }; sentAt: string }
  | { type: 'ai_action'; data: AIActionEvent; sentAt: string }
  | { type: 'ai_conflict'; data: { conflicts: Conflict[] }; sentAt: string }
  | { type: 'ai_daily_insight'; data: DailyInsight; sentAt: string };

// ── Billing: tariff + projected bill ──────────────────────────────────────────

export interface TariffSlab {
  /** Cumulative upper bound in the cycle; null = no limit (last slab) */
  uptoKWh: number | null;
  rateINR: number;
}

export interface Tariff {
  mode: 'flat' | 'slab';
  flatRateINR: number;
  slabs: TariffSlab[];
  fixedChargeINR: number;
  fuelAdjustmentINRPerKWh: number;
  electricityDutyPercent: number;
  /** Meter-reading day that starts each billing cycle (1 = calendar month) */
  billingCycleDay: number;
  utilityProvider: string | null;
}

export interface BillLine {
  label: string;
  fromKWh: number;
  toKWh: number | null;
  kwh: number;
  rateINR: number;
  amountINR: number;
}

export interface BillBreakdown {
  kwh: number;
  lines: BillLine[];
  energyChargeINR: number;
  fuelChargeINR: number;
  dutyINR: number;
  fixedChargeINR: number;
  totalINR: number;
  effectiveRateINR: number | null;
  variableRateINR: number | null;
  marginalRateINR: number;
  slabIndex: number;
  kwhToNextSlab: number | null;
  nextSlabRateINR: number | null;
}

export interface BudgetStatus {
  budgetINR: number;
  budgetKWh: number;
  spentINR: number;
  projectedINR: number;
  projectedOverINR: number;
  usedPercent: number;
  remainingKWh: number;
  dailyAllowanceKWh: number | null;
  status: 'on_track' | 'at_risk' | 'over';
}

export interface BillProjection {
  cycleStart: string;
  /** Exclusive: the first day of the next cycle */
  cycleEnd: string;
  cycleDays: number;
  elapsedDays: number;
  daysLeft: number;
  usedKWh: number;
  meteredKWh: number;
  simulatedKWh: number;
  dailyKWh: number;
  projectedKWh: number;
  paceBasis: 'cycle' | 'last24h';
  confidence: 'low' | 'medium' | 'high';
  soFar: BillBreakdown;
  projected: BillBreakdown;
  tariff: Tariff;
  budget: BudgetStatus | null;
  /** Projected bill split by appliance (usage charges only; the fixed charge is separate). */
  applianceCosts: ApplianceBillShare[];
  disclaimer: string;
}

export interface ApplianceBillShare {
  applianceId: string;
  name: string;
  iconType: string | null;
  source: UsageSource;
  kwh: number;
  /** Share of the bill's total amount */
  sharePercent: number;
  costINR: number;
}

/** A recorded bill split across appliances, the fixed charge and unmeasured "rest of home". */
export interface BillApplianceBreakdown {
  billId: string;
  billingLabel: string;
  periodStart: string;
  /** Exclusive */
  periodEnd: string;
  periodSource: 'dates' | 'cycle';
  billKWh: number;
  billAmountINR: number;
  measuredKWh: number;
  meteredKWh: number;
  simulatedKWh: number;
  coveragePercent: number;
  fixedChargeINR: number;
  variableRateINR: number;
  appliances: ApplianceBillShare[];
  restKWh: number;
  restINR: number;
  restPercent: number;
  notes: string[];
  periodDays: number;
  coveredHours: number;
  /** Bill kWh ÷ period days */
  billedDailyKWh: number | null;
  /** SHEM metered + simulated kWh per recorded day (needs ≥ 6 recorded hours) */
  recordedDailyKWh: number | null;
  variancePercent: number | null;
}
