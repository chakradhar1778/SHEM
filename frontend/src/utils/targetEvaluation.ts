import type { BillRecord } from '../context/billContextDef';
import type { InventoryItem } from '../context/inventoryContextDef';
import type { TargetConfig } from '../context/targetContextDef';
import { calculateDailyKWh, calculateMonthlyKWh } from './energyMath';
import { calculateEstimatedCost } from './billMath';

export type TargetStatus =
  | 'NOT_CONFIGURED'
  | 'NO_DATA'
  | 'WITHIN_TARGET'
  | 'ON_TRACK'
  | 'EXCEEDED_TARGET';

export type TargetDataSource = 'ACTUAL_BILL' | 'MEASURED_METER' | 'ESTIMATED_INVENTORY' | 'NONE';

/** Month-to-date energy measured by the SHEM meter (from GET /api/insights?period=month). */
export interface MeasuredMonth {
  kwh: number;
  hasData: boolean;
  dataNote?: string | null;
}

export interface TargetTrendPoint {
  label: string;
  amountINR: number;
  kwh: number;
  isCurrent?: boolean;
}

export interface TargetEvaluationResult {
  status: TargetStatus;
  statusColor: 'green' | 'amber' | 'red' | 'blue' | 'gray';
  headline: string;
  subtitle: string;
  guidanceText: string;
  dataSource: TargetDataSource;
  dataSourceLabel: string;

  /** Identified period label, e.g. "October 2026 (Current)" or "March 2024 (Historical)" */
  periodLabel: string;

  /** True if evaluating a completed historical billing period */
  isHistoricalPeriod: boolean;

  /** True if the period is finished / cycle completed */
  isCycleCompleted: boolean;

  /** Explicit disclosure when estimated tariff rates are used */
  rateDisclosure?: string;

  /** Configured monthly budget target in INR */
  targetINR: number;

  /** Tariff used for cost estimates (₹/kWh) */
  tariffRateINR: number;

  /** Total consumed energy in kWh associated with evaluated period */
  usedKWh: number;

  /** Current spend in INR (actual bill amount or estimated monthly cost) */
  currentCostINR: number;

  /** Remaining budget in INR (>= 0) when within or on track */
  budgetLeftINR: number;

  /** Over-budget amount in INR (> 0) when exceeded */
  overBudgetINR: number;

  /** Percentage of budget consumed (0 to 100+) */
  percentUsed: number;

  /** Days remaining in the active billing / target period */
  daysLeft: number;

  /** Note regarding historical bills on file when evaluating current month */
  historicalNotice?: string;

  /** Real historical bill trend data (empty if no historical bills logged) */
  trendPoints: TargetTrendPoint[];
}

/**
 * Standard progress status thresholds (centralized for easy client tuning).
 * - WITHIN_TARGET: ratio <= 0.80 (used <= 80% of budget)
 * - ON_TRACK: 0.80 < ratio <= 1.00 (used between 80% and 100% of budget)
 * - EXCEEDED_TARGET: ratio > 1.00 (used more than 100% of budget)
 */
export const TARGET_THRESHOLDS = {
  WITHIN_TARGET_MAX_RATIO: 0.8,
  ON_TRACK_MAX_RATIO: 1.0,
  FALLBACK_TARIFF_INR_PER_KWH: 7.5, // Standard residential blended rate (BESCOM / Urban average)
} as const;

const MONTH_NAMES = [
  'January', 'February', 'March', 'April', 'May', 'June',
  'July', 'August', 'September', 'October', 'November', 'December',
];

/**
 * Formats a month and year into a human-readable period string.
 */
export function formatPeriodLabel(month: number, year: number): string {
  const mName = MONTH_NAMES[month - 1] || `Month ${month}`;
  return `${mName} ${year}`;
}

/**
 * Calculates days remaining in the active calendar month.
 */
function getDaysRemainingInCurrentMonth(): number {
  const now = new Date();
  const year = now.getFullYear();
  const month = now.getMonth(); // 0-indexed
  const totalDays = new Date(year, month + 1, 0).getDate();
  const currentDay = now.getDate();
  return Math.max(1, totalDays - currentDay);
}

/**
 * Evaluates the user's energy target progress against real utility bills or estimated inventory.
 *
 * Requirements:
 * - Historical bills are NOT treated as current-month spending.
 * - The billing period is identified correctly.
 * - If available data cannot establish current-period spending, the interface clearly says so.
 * - Estimated projections are explicitly labelled as estimates with tariff rate disclosure.
 * - Status thresholds remain centralized in TARGET_THRESHOLDS.
 *
 * @param target User target configuration
 * @param bills All recorded bills in history
 * @param latestBill Most recent recorded bill (if any)
 * @param inventory Current household appliance inventory
 * @param selectedPeriodId 'current' to evaluate active current month, or a specific bill ID
 */
export function evaluateTarget(
  target: TargetConfig,
  bills: BillRecord[],
  latestBill: BillRecord | null,
  inventory: InventoryItem[],
  selectedPeriodId?: string,
  measured?: MeasuredMonth | null,
  tariffRate: number = TARGET_THRESHOLDS.FALLBACK_TARIFF_INR_PER_KWH
): TargetEvaluationResult {
  const targetINR = target.monthlyBudgetINR;
  const now = new Date();
  const currentYear = now.getFullYear();
  const currentMonth = now.getMonth() + 1; // 1-indexed
  const currentMonthLabel = formatPeriodLabel(currentMonth, currentYear);

  // Compile real trend points from historical bills (newest to oldest reversed to chronological order)
  const trendPoints: TargetTrendPoint[] = [...bills]
    .slice(0, 6)
    .reverse()
    .map((b) => ({
      label: b.billingPeriod || formatPeriodLabel(b.billingMonth, b.billingYear),
      amountINR: b.billAmount,
      kwh: b.unitsConsumed,
      isCurrent: latestBill ? b.id === latestBill.id : false,
    }));

  // Case 1: Target is not yet configured by the user
  if (!target.isConfigured || targetINR <= 0) {
    return {
      status: 'NOT_CONFIGURED',
      statusColor: 'blue',
      headline: 'Set your energy target',
      subtitle: 'Choose a monthly electricity budget that feels right for your home.',
      guidanceText: 'Configure a target to unlock real-time tracking, proactive alerts, and personalized saving guidance.',
      dataSource: 'NONE',
      dataSourceLabel: 'No target set',
      periodLabel: currentMonthLabel,
      isHistoricalPeriod: false,
      isCycleCompleted: false,
      targetINR: 0,
      tariffRateINR: tariffRate,
      usedKWh: 0,
      currentCostINR: 0,
      budgetLeftINR: 0,
      overBudgetINR: 0,
      percentUsed: 0,
      daysLeft: getDaysRemainingInCurrentMonth(),
      trendPoints,
    };
  }

  // Check if user explicitly asked to evaluate a specific historical bill
  const explicitHistoricalBill = selectedPeriodId && selectedPeriodId !== 'current'
    ? bills.find((b) => b.id === selectedPeriodId) || null
    : null;

  // Determine if latestBill is an actual bill for the ACTIVE calendar month
  const currentPeriodBill = latestBill &&
    latestBill.billingYear === currentYear &&
    latestBill.billingMonth === currentMonth
      ? latestBill
      : null;

  // Determine evaluation target bill:
  // Either user chose an explicit historical bill, OR an actual bill for the active month exists
  const activeBill = explicitHistoricalBill || currentPeriodBill;

  // ========================================================================
  // Scenario A: Actual Bill Data Available for the evaluated period
  // ========================================================================
  if (activeBill && activeBill.billAmount > 0) {
    const isHistorical = activeBill.billingYear !== currentYear || activeBill.billingMonth !== currentMonth;
    const periodLabel = activeBill.billingPeriod || formatPeriodLabel(activeBill.billingMonth, activeBill.billingYear);
    const currentCost = Math.round(activeBill.billAmount);
    const usedKWh = Number(activeBill.unitsConsumed.toFixed(1));
    const ratio = currentCost / targetINR;
    const percentUsed = Math.round(ratio * 100);

    // Days left: 0 if historical completed cycle, else remaining in active month
    const daysLeft = isHistorical ? 0 : getDaysRemainingInCurrentMonth();

    const periodDesc = isHistorical
      ? `${periodLabel} (Historical Billed Cycle)`
      : `${periodLabel} (Current Billed Period)`;

    const sourceLabel = `Actual utility bill (${activeBill.utilityProvider} · ${periodDesc})`;

    if (ratio <= TARGET_THRESHOLDS.WITHIN_TARGET_MAX_RATIO) {
      return {
        status: 'WITHIN_TARGET',
        statusColor: 'green',
        headline: isHistorical
          ? `Within Target for ${periodLabel}`
          : "Great! You're within your target",
        subtitle: isHistorical
          ? `Billed consumption for ${periodLabel} was comfortably within your ₹${targetINR.toLocaleString('en-IN')} target.`
          : 'Your energy use is comfortably within your goal.',
        guidanceText: isHistorical
          ? `Past performance in ${periodLabel} met your budget goal with ₹${Math.max(0, targetINR - currentCost).toLocaleString('en-IN')} remaining.`
          : 'Nice work — keep your current habits. Your energy use is lower than your target. Keep it up!',
        dataSource: 'ACTUAL_BILL',
        dataSourceLabel: sourceLabel,
        periodLabel,
        isHistoricalPeriod: isHistorical,
        isCycleCompleted: isHistorical,
        targetINR,
        tariffRateINR: tariffRate,
        usedKWh,
        currentCostINR: currentCost,
        budgetLeftINR: Math.max(0, targetINR - currentCost),
        overBudgetINR: 0,
        percentUsed,
        daysLeft,
        trendPoints,
      };
    }

    if (ratio <= TARGET_THRESHOLDS.ON_TRACK_MAX_RATIO) {
      return {
        status: 'ON_TRACK',
        statusColor: 'amber',
        headline: isHistorical
          ? `On Track for ${periodLabel}`
          : "You're on track",
        subtitle: isHistorical
          ? `Billed consumption for ${periodLabel} was close to your target, but within budget.`
          : "Your energy use is close to your target, but you're still on track.",
        guidanceText: isHistorical
          ? `In ${periodLabel}, spending reached ${percentUsed}% of your ₹${targetINR.toLocaleString('en-IN')} goal.`
          : 'A few small changes can help you save more. Try switching off unused lights and appliances.',
        dataSource: 'ACTUAL_BILL',
        dataSourceLabel: sourceLabel,
        periodLabel,
        isHistoricalPeriod: isHistorical,
        isCycleCompleted: isHistorical,
        targetINR,
        tariffRateINR: tariffRate,
        usedKWh,
        currentCostINR: currentCost,
        budgetLeftINR: Math.max(0, targetINR - currentCost),
        overBudgetINR: 0,
        percentUsed,
        daysLeft,
        trendPoints,
      };
    }

    // Ratio > 1.00 => EXCEEDED_TARGET
    return {
      status: 'EXCEEDED_TARGET',
      statusColor: 'red',
      headline: isHistorical
        ? `Exceeded Target in ${periodLabel}`
        : "You've exceeded your target",
      subtitle: isHistorical
        ? `Billed consumption for ${periodLabel} exceeded your monthly target by ₹${(currentCost - targetINR).toLocaleString('en-IN')}.`
        : 'Your energy use is higher than your target this month.',
      guidanceText: isHistorical
        ? `In ${periodLabel}, spending reached ₹${currentCost.toLocaleString('en-IN')} (${percentUsed}% of target). Review high-draw appliances to stay under budget this month.`
        : "Let's bring it back on track. Try reducing usage in high-consumption appliances.",
      dataSource: 'ACTUAL_BILL',
      dataSourceLabel: sourceLabel,
      periodLabel,
      isHistoricalPeriod: isHistorical,
      isCycleCompleted: isHistorical,
      targetINR,
      tariffRateINR: tariffRate,
      usedKWh,
      currentCostINR: currentCost,
      budgetLeftINR: 0,
      overBudgetINR: Math.max(0, currentCost - targetINR),
      percentUsed,
      daysLeft,
      trendPoints,
    };
  }

  // ========================================================================
  // Scenario M: Measured month-to-date energy from the SHEM meter (PZEM-004T)
  // Energy is metered; cost is an estimate at the configured tariff. Status
  // uses the month-end projection at the current pace.
  // ========================================================================
  if (!explicitHistoricalBill && measured && measured.hasData && measured.kwh > 0) {
    const daysInMonth = new Date(currentYear, currentMonth, 0).getDate();
    const elapsedDays = Math.max(
      1 / 24,
      (now.getTime() - new Date(currentYear, currentMonth - 1, 1).getTime()) / 86_400_000
    );
    const mtdCost = measured.kwh * tariffRate;
    const projectedCost = (mtdCost / elapsedDays) * daysInMonth;
    const projectedRatio = projectedCost / targetINR;
    const usedKWh = Number(measured.kwh.toFixed(2));
    const currentCost = Math.round(mtdCost);
    const percentUsed = Math.round((mtdCost / targetINR) * 100);
    const alreadyOver = mtdCost > targetINR;
    const sourceLabel = `Measured by your SHEM meter (${currentMonthLabel}, month to date)`;
    const rateDisclosure = `*Energy is metered by the PZEM-004T; cost is estimated at your tariff of ₹${tariffRate.toFixed(2)}/kWh. Month-end projection ≈ ₹${Math.round(projectedCost).toLocaleString('en-IN')} at the current pace.${measured.dataNote ? ` ${measured.dataNote}` : ''}`;
    const base = {
      dataSource: 'MEASURED_METER' as const,
      dataSourceLabel: sourceLabel,
      periodLabel: `${currentMonthLabel} (Metered)`,
      isHistoricalPeriod: false,
      isCycleCompleted: false,
      rateDisclosure,
      targetINR,
      tariffRateINR: tariffRate,
      usedKWh,
      currentCostINR: currentCost,
      budgetLeftINR: Math.max(0, targetINR - currentCost),
      overBudgetINR: Math.max(0, currentCost - targetINR),
      percentUsed,
      daysLeft: getDaysRemainingInCurrentMonth(),
      historicalNotice: latestBill
        ? `Latest bill on file: ${latestBill.billingPeriod || formatPeriodLabel(latestBill.billingMonth, latestBill.billingYear)} (₹${latestBill.billAmount.toLocaleString('en-IN')}). Current progress uses metered data.`
        : undefined,
      trendPoints,
    };

    if (!alreadyOver && projectedRatio <= TARGET_THRESHOLDS.WITHIN_TARGET_MAX_RATIO) {
      return {
        ...base,
        status: 'WITHIN_TARGET',
        statusColor: 'green',
        headline: "Great! You're within your target",
        subtitle: `You've used ${usedKWh} kWh (≈ ₹${currentCost.toLocaleString('en-IN')}) so far this month.`,
        guidanceText: `At this pace the month ends around ₹${Math.round(projectedCost).toLocaleString('en-IN')} — comfortably under your ₹${targetINR.toLocaleString('en-IN')} target.`,
      };
    }
    if (!alreadyOver && projectedRatio <= TARGET_THRESHOLDS.ON_TRACK_MAX_RATIO) {
      return {
        ...base,
        status: 'ON_TRACK',
        statusColor: 'amber',
        headline: "You're on track",
        subtitle: `You've used ${usedKWh} kWh (≈ ₹${currentCost.toLocaleString('en-IN')}) so far this month.`,
        guidanceText: `At this pace the month ends around ₹${Math.round(projectedCost).toLocaleString('en-IN')}, close to your target. Trimming the largest loads keeps you safe.`,
      };
    }
    return {
      ...base,
      status: 'EXCEEDED_TARGET',
      statusColor: 'red',
      headline: alreadyOver ? "You've exceeded your target" : 'On course to exceed your target',
      subtitle: alreadyOver
        ? `Metered use this month (≈ ₹${currentCost.toLocaleString('en-IN')}) is already above your ₹${targetINR.toLocaleString('en-IN')} target.`
        : `At this pace the month ends around ₹${Math.round(projectedCost).toLocaleString('en-IN')}, above your target.`,
      guidanceText: "Let's bring it back on track. See the Energy Guide for the loads driving your usage.",
    };
  }

  // ========================================================================
  // Scenario B: No Current-Month Bill, but Household Appliance Inventory Exists
  // Any cost calculated from estimated appliance energy is explicitly labelled
  // as an estimate, with the assumed ₹7.50/kWh rate disclosed.
  // Historical bills are NOT treated as current-month spending.
  // ========================================================================
  if (inventory.length > 0) {
    const totalDailyKWh = inventory.reduce((sum, item) => {
      const dailyKWh = calculateDailyKWh(
        item.ratedWatts || 0,
        item.quantity || 1,
        item.dailyHours ?? 4
      );
      return sum + dailyKWh;
    }, 0);

    const estimatedMonthlyKWh = calculateMonthlyKWh(totalDailyKWh);
    const estimatedCost = Math.round(calculateEstimatedCost(estimatedMonthlyKWh, tariffRate));
    const usedKWh = Number(estimatedMonthlyKWh.toFixed(1));
    const ratio = estimatedCost / targetINR;
    const percentUsed = Math.round(ratio * 100);
    const daysLeft = getDaysRemainingInCurrentMonth();

    // Prepare note if a historical bill exists on file
    const historicalNotice = latestBill
      ? `Historical bill on file: ${latestBill.billingPeriod || formatPeriodLabel(latestBill.billingMonth, latestBill.billingYear)} (₹${latestBill.billAmount.toLocaleString('en-IN')}). Current period spending is projected from household inventory.`
      : undefined;

    const rateDisclosure = `*Estimated monthly cost calculated using standard residential tariff of ₹${tariffRate.toFixed(2)}/kWh for ${inventory.length} configured appliance${inventory.length === 1 ? '' : 's'}. Enter an actual utility bill to track confirmed billed spend.`;

    if (ratio <= TARGET_THRESHOLDS.WITHIN_TARGET_MAX_RATIO) {
      return {
        status: 'WITHIN_TARGET',
        statusColor: 'green',
        headline: "Great! You're within your target",
        subtitle: `Projected monthly spend for ${currentMonthLabel} is comfortably within your goal.`,
        guidanceText: `Your ${inventory.length} configured household appliances are estimated at ₹${estimatedCost.toLocaleString('en-IN')}/month (at ₹${tariffRate.toFixed(2)}/kWh), leaving ~₹${Math.max(0, targetINR - estimatedCost).toLocaleString('en-IN')} buffer.`,
        dataSource: 'ESTIMATED_INVENTORY',
        dataSourceLabel: `Estimated projection (${currentMonthLabel} · ${inventory.length} appliances at ₹${tariffRate.toFixed(2)}/kWh)`,
        periodLabel: `${currentMonthLabel} (Estimated)`,
        isHistoricalPeriod: false,
        isCycleCompleted: false,
        rateDisclosure,
        historicalNotice,
        targetINR,
        tariffRateINR: tariffRate,
        usedKWh,
        currentCostINR: estimatedCost,
        budgetLeftINR: Math.max(0, targetINR - estimatedCost),
        overBudgetINR: 0,
        percentUsed,
        daysLeft,
        trendPoints,
      };
    }

    if (ratio <= TARGET_THRESHOLDS.ON_TRACK_MAX_RATIO) {
      return {
        status: 'ON_TRACK',
        statusColor: 'amber',
        headline: "You're on track",
        subtitle: `Projected monthly spend for ${currentMonthLabel} is close to your target.`,
        guidanceText: `Estimated appliance load is ~${percentUsed}% of your budget. Review operating hours on high-consumption cooling or heating units to maintain headroom.`,
        dataSource: 'ESTIMATED_INVENTORY',
        dataSourceLabel: `Estimated projection (${currentMonthLabel} · ${inventory.length} appliances at ₹${tariffRate.toFixed(2)}/kWh)`,
        periodLabel: `${currentMonthLabel} (Estimated)`,
        isHistoricalPeriod: false,
        isCycleCompleted: false,
        rateDisclosure,
        historicalNotice,
        targetINR,
        tariffRateINR: tariffRate,
        usedKWh,
        currentCostINR: estimatedCost,
        budgetLeftINR: Math.max(0, targetINR - estimatedCost),
        overBudgetINR: 0,
        percentUsed,
        daysLeft,
        trendPoints,
      };
    }

    return {
      status: 'EXCEEDED_TARGET',
      statusColor: 'red',
      headline: "You've exceeded your target",
      subtitle: `Projected monthly spend for ${currentMonthLabel} exceeds your target.`,
      guidanceText: `Estimated household consumption (₹${estimatedCost.toLocaleString('en-IN')} at ₹${tariffRate.toFixed(2)}/kWh) is ₹${(estimatedCost - targetINR).toLocaleString('en-IN')} over target. Adjust operating hours or raise your target goal.`,
      dataSource: 'ESTIMATED_INVENTORY',
      dataSourceLabel: `Estimated projection (${currentMonthLabel} · ${inventory.length} appliances at ₹${tariffRate.toFixed(2)}/kWh)`,
      periodLabel: `${currentMonthLabel} (Estimated)`,
      isHistoricalPeriod: false,
      isCycleCompleted: false,
      rateDisclosure,
      historicalNotice,
      targetINR,
      tariffRateINR: tariffRate,
      usedKWh,
      currentCostINR: estimatedCost,
      budgetLeftINR: 0,
      overBudgetINR: Math.max(0, estimatedCost - targetINR),
      percentUsed,
      daysLeft,
      trendPoints,
    };
  }

  // ========================================================================
  // Scenario C: Neither Current Bill Nor Appliance Inventory Exists
  // Display missing-data state explaining what data is needed to establish progress.
  // If a historical bill exists, state so explicitly without using it as current spending.
  // ========================================================================
  const historicalNote = latestBill
    ? `Latest bill on file is for ${latestBill.billingPeriod || formatPeriodLabel(latestBill.billingMonth, latestBill.billingYear)} (₹${latestBill.billAmount.toLocaleString('en-IN')}). Because historical bills cannot establish current-month spending, enter an actual bill for ${currentMonthLabel} or add household appliances to track progress.`
    : `SHEM needs consumption data to calculate whether your home is within budget. Connect your SHEM meter, add your appliances in Devices, or enter a recent bill.`;

  return {
    status: 'NO_DATA',
    statusColor: 'blue',
    headline: `Target Configured: ₹${targetINR.toLocaleString('en-IN')}`,
    subtitle: `No consumption data recorded for ${currentMonthLabel}.`,
    guidanceText: historicalNote,
    dataSource: 'NONE',
    dataSourceLabel: latestBill
      ? `Historical bill on file (${latestBill.billingPeriod}) · Current period awaiting data`
      : 'No consumption data logged',
    periodLabel: currentMonthLabel,
    isHistoricalPeriod: false,
    isCycleCompleted: false,
    targetINR,
    tariffRateINR: tariffRate,
    usedKWh: 0,
    currentCostINR: 0,
    budgetLeftINR: targetINR,
    overBudgetINR: 0,
    percentUsed: 0,
    daysLeft: getDaysRemainingInCurrentMonth(),
    trendPoints,
  };
}
