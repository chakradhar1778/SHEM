/**
 * SHEM — Phase 2E-A: Bill & Tariff Calculation Utilities
 *
 * Provides pure, safe calculations for electricity billing:
 * - Effective blended tariff rates derived from actual bills.
 * - Period-adjusted household energy estimates.
 * - Energy consumption variance and cost comparisons.
 *
 * NOTE: The effective average rate calculated here is a blended consumer unit rate
 * (total bill amount / units consumed) derived from user-entered billing data.
 * It is NOT an official utility tariff schedule or slab model, and must not be
 * represented as such.
 */

/**
 * Calculates the blended effective average rate per kWh from bill totals.
 * Formula: billAmount (INR) / unitsConsumed (kWh)
 *
 * Handles zero units, negative values, and non-finite inputs safely.
 *
 * @param billAmount Total electricity bill amount in INR (>= 0)
 * @param unitsConsumed Total billed energy consumption in kWh (> 0)
 * @returns Blended rate in INR/kWh, or 0 if inputs are invalid or zero units.
 *
 * Example: calculateEffectiveRate(2100, 280) => 7.50
 */
export function calculateEffectiveRate(billAmount: number, unitsConsumed: number): number {
  const amount = Number(billAmount);
  const units = Number(unitsConsumed);

  if (!Number.isFinite(amount) || !Number.isFinite(units)) {
    return 0;
  }

  if (amount <= 0 || units <= 0) {
    return 0;
  }

  const rate = amount / units;
  return Number.isFinite(rate) ? Number(rate.toFixed(4)) : 0;
}

/**
 * Calculates estimated household energy for a specific billing period duration.
 * Formula: dailyEstimatedKWh * periodDays
 *
 * @param dailyEstimatedKWh Daily household consumption estimate (from appliance ratings & hours)
 * @param periodDays Billing period duration in days (default: 30)
 * @returns Estimated kWh for the period, or 0 if inputs are invalid.
 */
export function calculatePeriodEstimatedEnergy(
  dailyEstimatedKWh: number,
  periodDays = 30
): number {
  const daily = Number(dailyEstimatedKWh);
  const days = Number(periodDays);

  if (!Number.isFinite(daily) || !Number.isFinite(days) || daily <= 0 || days <= 0) {
    return 0;
  }

  const periodKWh = daily * days;
  return Number.isFinite(periodKWh) ? Number(periodKWh.toFixed(3)) : 0;
}

/**
 * Calculates the difference between actual billed consumption and estimated consumption.
 * Formula: billedKWh - estimatedKWh
 * Positive difference means actual billed consumption was higher than configured estimate.
 *
 * @param billedKWh Actual energy consumption from utility bill
 * @param estimatedKWh Estimated household energy consumption
 * @returns Difference in kWh (can be positive, zero, or negative).
 */
export function calculateEnergyDifference(
  billedKWh: number,
  estimatedKWh: number
): number {
  const billed = Number(billedKWh);
  const estimated = Number(estimatedKWh);

  if (!Number.isFinite(billed) || !Number.isFinite(estimated)) {
    return 0;
  }

  const diff = billed - Math.max(0, estimated);
  return Number(diff.toFixed(3));
}

/**
 * Calculates the percentage variance of actual billed consumption vs. estimated consumption.
 * Formula: ((billedKWh - estimatedKWh) / billedKWh) * 100
 *
 * Returns null if billedKWh is zero or invalid, avoiding division by zero or Infinity.
 *
 * @param billedKWh Actual energy consumption from utility bill (> 0)
 * @param estimatedKWh Estimated household energy consumption (>= 0)
 * @returns Percentage variance (rounded to 1 decimal place), or null if denominator invalid.
 */
export function calculateEnergyVariancePercent(
  billedKWh: number,
  estimatedKWh: number
): number | null {
  const billed = Number(billedKWh);
  const estimated = Number(estimatedKWh);

  if (!Number.isFinite(billed) || !Number.isFinite(estimated) || billed <= 0) {
    return null;
  }

  const variance = ((billed - Math.max(0, estimated)) / billed) * 100;
  return Number.isFinite(variance) ? Number(variance.toFixed(1)) : null;
}

/**
 * Calculates estimated household electricity cost using an effective average rate.
 * Formula: estimatedKWh * effectiveRatePerKWh
 *
 * @param estimatedKWh Estimated energy consumption in kWh
 * @param effectiveRatePerKWh Blended tariff rate in INR/kWh
 * @returns Estimated cost in INR (>= 0), or 0 if inputs are invalid.
 *
 * Example: calculateEstimatedCost(150, 7.50) => 1125
 */
export function calculateEstimatedCost(
  estimatedKWh: number,
  effectiveRatePerKWh: number
): number {
  const kwh = Number(estimatedKWh);
  const rate = Number(effectiveRatePerKWh);

  if (!Number.isFinite(kwh) || !Number.isFinite(rate) || kwh <= 0 || rate <= 0) {
    return 0;
  }

  const cost = kwh * rate;
  return Number.isFinite(cost) ? Number(cost.toFixed(2)) : 0;
}

/**
 * Formats a currency amount in Indian Rupees (INR) with the standard symbol.
 *
 * @param amount Numeric amount in INR
 * @param includeDecimals Whether to format decimal paise
 * @returns Formatted currency string, e.g. "₹2,100" or "₹1,125.00"
 */
export function formatCurrencyINR(amount: number, includeDecimals = false): string {
  const num = Number(amount);
  if (!Number.isFinite(num) || num < 0) {
    return '₹0';
  }

  if (includeDecimals) {
    return `₹${num.toLocaleString('en-IN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}`;
  }
  return `₹${Math.round(num).toLocaleString('en-IN')}`;
}

/**
 * Formats a unit tariff rate with standard precision.
 *
 * @param rate INR per kWh
 * @returns Formatted string, e.g. "₹7.50/kWh"
 */
export function formatUnitRate(rate: number): string {
  const num = Number(rate);
  if (!Number.isFinite(num) || num <= 0) {
    return '₹0.00/kWh';
  }
  return `₹${num.toFixed(2)}/kWh`;
}

/**
 * Validates bill input data before creation or update.
 *
 * @param input Partial bill data to validate
 * @returns Validation result with boolean flag and descriptive error messages
 */
export function validateBillData(input: {
  unitsConsumed?: unknown;
  billAmount?: unknown;
  utilityProvider?: unknown;
  billingMonth?: unknown;
  billingYear?: unknown;
  billingPeriodStart?: unknown;
  billingPeriodEnd?: unknown;
}): { isValid: boolean; errors: string[] } {
  const errors: string[] = [];

  // Units consumed validation
  if (input.unitsConsumed === undefined || input.unitsConsumed === null || input.unitsConsumed === '') {
    errors.push('Units consumed (kWh) is required.');
  } else {
    const units = Number(input.unitsConsumed);
    if (!Number.isFinite(units)) {
      errors.push('Units consumed must be a valid number.');
    } else if (units <= 0) {
      errors.push('Units consumed must be greater than 0 kWh.');
    } else if (units > 1_000_000) {
      errors.push('Units consumed looks too large (max 1,000,000 kWh).');
    }
  }

  // Bill amount validation
  if (input.billAmount === undefined || input.billAmount === null || input.billAmount === '') {
    errors.push('Bill amount is required.');
  } else {
    const amount = Number(input.billAmount);
    if (!Number.isFinite(amount)) {
      errors.push('Bill amount must be a valid number.');
    } else if (amount <= 0) {
      errors.push('Bill amount must be greater than ₹0.');
    } else if (amount > 10_000_000) {
      errors.push('Bill amount looks too large (max ₹1,00,00,000).');
    }
  }

  // Provider validation
  if (input.utilityProvider !== undefined && typeof input.utilityProvider === 'string') {
    if (input.utilityProvider.trim().length === 0) {
      errors.push('Utility provider cannot be empty.');
    }
  }

  // Month validation
  if (input.billingMonth !== undefined && input.billingMonth !== null) {
    const month = Number(input.billingMonth);
    if (!Number.isInteger(month) || month < 1 || month > 12) {
      errors.push('Billing month must be an integer between 1 and 12.');
    }
  }

  // Year validation
  if (input.billingYear !== undefined && input.billingYear !== null) {
    const year = Number(input.billingYear);
    if (!Number.isInteger(year) || year < 2000 || year > 2100) {
      errors.push('Billing year must be a valid four-digit year (2000-2100).');
    }
  }

  // Period dates validation
  if (
    typeof input.billingPeriodStart === 'string' &&
    typeof input.billingPeriodEnd === 'string' &&
    input.billingPeriodStart.trim() &&
    input.billingPeriodEnd.trim()
  ) {
    const start = new Date(input.billingPeriodStart).getTime();
    const end = new Date(input.billingPeriodEnd).getTime();
    if (!isNaN(start) && !isNaN(end) && end < start) {
      errors.push('Billing period end date cannot be earlier than start date.');
    }
  }

  return {
    isValid: errors.length === 0,
    errors,
  };
}

/**
 * Resolves the billing period duration in days for a bill record or input.
 *
 * Prioritizes:
 * 1. Explicit billingPeriodDays if a positive finite number (> 0)
 * 2. Difference between valid billingPeriodStart and billingPeriodEnd dates (inclusive)
 * 3. Exact calendar days in the specified billingMonth and billingYear (respecting leap years)
 *
 * Returns null if duration cannot be determined from available metadata.
 *
 * @param bill Object containing billing period fields
 * @returns Number of days in the period, or null if insufficient/invalid metadata
 */
export function getBillingPeriodDays(bill: {
  billingPeriodDays?: number;
  billingPeriodStart?: string;
  billingPeriodEnd?: string;
  billingMonth?: number;
  billingYear?: number;
}): number | null {
  // 1. Specific start and end dates take precedence
  if (
    typeof bill.billingPeriodStart === 'string' &&
    typeof bill.billingPeriodEnd === 'string' &&
    bill.billingPeriodStart.trim() &&
    bill.billingPeriodEnd.trim()
  ) {
    const start = new Date(bill.billingPeriodStart).getTime();
    const end = new Date(bill.billingPeriodEnd).getTime();
    if (!isNaN(start) && !isNaN(end) && end >= start) {
      const days = Math.round((end - start) / (1000 * 60 * 60 * 24)) + 1;
      if (days > 0) {
        return days;
      }
    }
  }

  // 2. Exact calendar month and year duration (accounting for leap years)
  if (
    typeof bill.billingMonth === 'number' &&
    Number.isInteger(bill.billingMonth) &&
    bill.billingMonth >= 1 &&
    bill.billingMonth <= 12 &&
    typeof bill.billingYear === 'number' &&
    Number.isInteger(bill.billingYear) &&
    bill.billingYear >= 2000 &&
    bill.billingYear <= 2100
  ) {
    return new Date(bill.billingYear, bill.billingMonth, 0).getDate();
  }

  // 3. Explicit period days (if month/year unavailable)
  if (
    typeof bill.billingPeriodDays === 'number' &&
    Number.isFinite(bill.billingPeriodDays) &&
    bill.billingPeriodDays > 0
  ) {
    return Math.round(bill.billingPeriodDays);
  }

  return null;
}

/**
 * Calculates total daily household energy consumption (kWh/day) from an appliance inventory.
 * Formula: sum((ratedWatts * quantity * dailyHours) / 1000)
 *
 * @param inventory Array of items with ratedWatts, quantity, and dailyHours
 * @returns Daily energy in kWh/day (>= 0)
 */
export function calculateHouseholdDailyKWh(inventory: Array<{
  ratedWatts: number;
  quantity: number;
  dailyHours?: number;
}>): number {
  if (!Array.isArray(inventory) || inventory.length === 0) {
    return 0;
  }

  const total = inventory.reduce((sum, item) => {
    const watts = Math.max(0, Number(item.ratedWatts) || 0);
    const qty = Math.max(1, Number(item.quantity) || 1);
    const hours = Math.max(0, Math.min(24, Number(item.dailyHours) || 0));
    return sum + (watts * qty * hours) / 1000;
  }, 0);

  return Number(total.toFixed(4));
}

/**
 * Structured result of comparing an actual utility bill with estimated household energy.
 */
export interface BillComparisonResult {
  periodDays: number | null;
  periodLabel: string;
  actualKWh: number;
  actualAmount: number;
  effectiveRate: number | null;
  estimatedKWh: number | null;
  estimatedCost: number | null;
  differenceKWh: number | null;
  variancePercent: number | null;
  isComparisonValid: boolean;
  status: 'higher' | 'lower' | 'matched' | 'zero_units' | 'unavailable' | 'no_appliances';
  statusHeadline: string;
  statusExplanation: string;
}

/**
 * Compares an actual utility bill with estimated household energy for the corresponding period.
 *
 * @param bill The utility bill record to compare
 * @param householdDailyKWh Total daily household consumption from appliance inventory (kWh/day)
 * @param inventoryCount Total number of configured appliances in inventory
 * @returns Comprehensive comparison result with difference, variance, costs, and explanations
 */
export function compareBillWithHousehold(
  bill: {
    unitsConsumed: number;
    billAmount: number;
    billingPeriod?: string;
    billingMonth?: number;
    billingYear?: number;
    billingPeriodDays?: number;
    billingPeriodStart?: string;
    billingPeriodEnd?: string;
  },
  householdDailyKWh: number,
  inventoryCount = 0
): BillComparisonResult {
  const actualKWh = Number(bill.unitsConsumed) || 0;
  const actualAmount = Number(bill.billAmount) || 0;

  // Resolve period label
  const periodLabel = bill.billingPeriod && bill.billingPeriod.trim()
    ? bill.billingPeriod.trim()
    : typeof bill.billingMonth === 'number' && typeof bill.billingYear === 'number'
      ? `${new Date(bill.billingYear, bill.billingMonth - 1).toLocaleString('en-US', { month: 'long' })} ${bill.billingYear}`
      : 'Billing Period';

  // Effective rate is only mathematically valid if actual billed units > 0
  const effectiveRate = actualKWh > 0 ? calculateEffectiveRate(actualAmount, actualKWh) : null;

  // Step 3: Match billing period duration
  const periodDays = getBillingPeriodDays(bill);

  // If period cannot be determined
  if (periodDays === null || periodDays <= 0) {
    return {
      periodDays: null,
      periodLabel,
      actualKWh,
      actualAmount,
      effectiveRate,
      estimatedKWh: null,
      estimatedCost: null,
      differenceKWh: null,
      variancePercent: null,
      isComparisonValid: false,
      status: 'unavailable',
      statusHeadline: 'Billing period unavailable',
      statusExplanation: 'Insufficient billing dates or duration metadata to calculate a defensible household estimate.',
    };
  }

  // If no appliances are configured in inventory
  if (inventoryCount === 0 || householdDailyKWh <= 0) {
    return {
      periodDays,
      periodLabel,
      actualKWh,
      actualAmount,
      effectiveRate,
      estimatedKWh: 0,
      estimatedCost: 0,
      differenceKWh: actualKWh,
      variancePercent: actualKWh > 0 ? 100 : null,
      isComparisonValid: false,
      status: 'no_appliances',
      statusHeadline: 'No appliances configured',
      statusExplanation: 'No household appliances found in your inventory. Add appliances in Devices to estimate household consumption.',
    };
  }

  // Calculate estimated energy for the matched period
  const estimatedKWh = calculatePeriodEstimatedEnergy(householdDailyKWh, periodDays);

  // Difference in kWh: actual billed kWh - estimated household kWh
  const differenceKWh = calculateEnergyDifference(actualKWh, estimatedKWh);

  // Percentage variance: ((actual billed - estimated) / actual billed) * 100
  const variancePercent = calculateEnergyVariancePercent(actualKWh, estimatedKWh);

  // Estimated cost using effective rate
  const estimatedCost = effectiveRate !== null && effectiveRate > 0
    ? calculateEstimatedCost(estimatedKWh, effectiveRate)
    : null;

  // Determine status and descriptive explanation
  if (actualKWh === 0) {
    return {
      periodDays,
      periodLabel,
      actualKWh: 0,
      actualAmount,
      effectiveRate: null,
      estimatedKWh,
      estimatedCost: null,
      differenceKWh,
      variancePercent: null,
      isComparisonValid: true,
      status: 'zero_units',
      statusHeadline: 'Zero billed units',
      statusExplanation: `Bill recorded with 0 units. Effective rate and cost estimates are unavailable for zero consumption. Estimated household baseline is ${estimatedKWh} kWh.`,
    };
  }

  if (differenceKWh > 0.05) {
    return {
      periodDays,
      periodLabel,
      actualKWh,
      actualAmount,
      effectiveRate,
      estimatedKWh,
      estimatedCost,
      differenceKWh,
      variancePercent,
      isComparisonValid: true,
      status: 'higher',
      statusHeadline: `Billed consumption is higher than estimate`,
      statusExplanation: `Billed consumption (${actualKWh} kWh) exceeds the configured appliance estimate (${estimatedKWh} kWh) by ${differenceKWh} kWh${variancePercent !== null ? ` (+${variancePercent}%)` : ''}.`,
    };
  }

  if (differenceKWh < -0.05) {
    return {
      periodDays,
      periodLabel,
      actualKWh,
      actualAmount,
      effectiveRate,
      estimatedKWh,
      estimatedCost,
      differenceKWh,
      variancePercent,
      isComparisonValid: true,
      status: 'lower',
      statusHeadline: `Billed consumption is lower than estimate`,
      statusExplanation: `Billed consumption (${actualKWh} kWh) is below the configured appliance estimate (${estimatedKWh} kWh) by ${Math.abs(differenceKWh)} kWh${variancePercent !== null ? ` (${variancePercent}%)` : ''}.`,
    };
  }

  return {
    periodDays,
    periodLabel,
    actualKWh,
    actualAmount,
    effectiveRate,
    estimatedKWh,
    estimatedCost,
    differenceKWh: 0,
    variancePercent: 0,
    isComparisonValid: true,
    status: 'matched',
    statusHeadline: `Billed consumption matches estimate`,
    statusExplanation: `Billed consumption (${actualKWh} kWh) closely matches the configured household appliance estimate (${estimatedKWh} kWh).`,
  };
}

