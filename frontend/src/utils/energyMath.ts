/**
 * SHEM Energy Estimation Utilities (Phase 2D-C)
 */

export const CATEGORY_DEFAULT_HOURS: Record<string, number> = {
  lighting: 4,
  fans: 8,
  cooling: 8,
  refrigerator: 24,
  kitchen: 1,
  entertainment: 4,
  heating: 1,
  'washing machine': 1,
  'water purifier': 3,
};

/**
 * Returns category-aware default daily operating hours (fallback: 4 hrs/day)
 */
export function getDefaultDailyHours(categoryName?: string): number {
  if (!categoryName) return 4;
  const key = categoryName.toLowerCase().trim();
  return CATEGORY_DEFAULT_HOURS[key] ?? 4;
}

/**
 * Total Configured Rated Load (Watts)
 * Formula: ratedWatts * quantity
 */
export function calculateConfiguredRatedWatts(ratedWatts: number, quantity: number): number {
  const watts = Math.max(0, ratedWatts || 0);
  const qty = Math.max(1, quantity || 1);
  return watts * qty;
}

/**
 * Estimated Daily Energy Consumption (kWh/day)
 * Formula: (ratedWatts * quantity * dailyHours) / 1000
 */
export function calculateDailyKWh(ratedWatts: number, quantity: number, dailyHours: number): number {
  const watts = Math.max(0, ratedWatts || 0);
  const qty = Math.max(1, quantity || 1);
  const hours = Math.max(0, Math.min(24, Number(dailyHours) || 0));

  if (watts === 0 || hours === 0) return 0;
  return (watts * qty * hours) / 1000;
}

/**
 * Estimated Monthly Energy Consumption (kWh/month)
 * Formula: estimatedDailyKWh * 30
 */
export function calculateMonthlyKWh(dailyKWh: number): number {
  const daily = Math.max(0, dailyKWh || 0);
  return daily * 30;
}

/**
 * Formats a kWh value for display with appropriate decimal precision
 */
export function formatKWh(kwh: number, maxDecimals = 3): string {
  if (kwh === 0) return '0.000';
  if (kwh < 0.001) return '< 0.001';
  // Use up to maxDecimals without trailing extra zeros when possible, but keep at least 2 or 3 decimals
  return Number(kwh.toFixed(maxDecimals)).toString();
}

/**
 * Formats a rated power in Watts to readable kW or W (e.g. 1200 -> '1.2 kW', 200 -> '0.2 kW', 25 -> '25 W')
 */
export function formatRatedPower(watts: number): string {
  if (watts >= 1000) {
    const kw = watts / 1000;
    return `${kw % 1 === 0 ? kw.toFixed(0) : kw.toFixed(1)} kW`;
  }
  if (watts >= 100) {
    return `${(watts / 1000).toFixed(1)} kW`;
  }
  return `${watts} W`;
}
