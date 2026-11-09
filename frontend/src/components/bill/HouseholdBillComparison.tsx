import { useState, useMemo } from 'react';
import { NavLink } from 'react-router-dom';
import type { BillRecord } from '../../context/billContextDef';
import { useInventory } from '../../hooks/useInventory';
import {
  calculateHouseholdDailyKWh,
  compareBillWithHousehold,
  formatCurrencyINR,
  formatUnitRate,
} from '../../utils/billMath';
import './HouseholdBillComparison.css';

interface HouseholdBillComparisonProps {
  bills: BillRecord[];
}

export function HouseholdBillComparison({ bills }: HouseholdBillComparisonProps) {
  const { inventory, totalQuantity } = useInventory();

  // Selected bill ID for comparison (defaults to newest bill)
  const [selectedBillId, setSelectedBillId] = useState<string | null>(null);

  // Active bill to compare (fall back to the first/latest bill if selected one is removed)
  const activeBill = useMemo<BillRecord | null>(() => {
    if (bills.length === 0) return null;
    if (selectedBillId) {
      const found = bills.find((b) => b.id === selectedBillId);
      if (found) return found;
    }
    return bills[0];
  }, [bills, selectedBillId]);

  // Total daily estimated household energy (kWh/day) from active inventory
  const householdDailyKWh = useMemo(() => {
    return calculateHouseholdDailyKWh(inventory);
  }, [inventory]);

  // Compute comparison result using pure math
  const comparison = useMemo(() => {
    if (!activeBill) return null;
    return compareBillWithHousehold(activeBill, householdDailyKWh, inventory.length);
  }, [activeBill, householdDailyKWh, inventory.length]);

  // Empty state: no bills exist
  if (bills.length === 0) {
    return (
      <section className="bill-comparison-section" aria-labelledby="bill-comparison-title">
        <div className="bill-comparison-header">
          <h2 id="bill-comparison-title" className="bill-comparison-title font-serif">
            Household energy comparison
          </h2>
          <span className="bill-comparison-badge bill-comparison-badge--empty">
            Awaiting bill
          </span>
        </div>

        <div className="bill-comp-card bill-comp-card--empty">
          <div className="bill-comp-empty-icon" aria-hidden="true">
            <svg viewBox="0 0 56 56" width="44" height="44" fill="none">
              <rect x="8" y="10" width="40" height="36" rx="8" fill="#EFF6FF" stroke="#93C5FD" strokeWidth="1.5" strokeDasharray="3 3" />
              <path d="M20 28 L28 20 L36 28 M28 22 L28 36" stroke="#3B82F6" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" />
            </svg>
          </div>
          <div className="bill-comp-empty-content">
            <h3 className="bill-comp-empty-heading">No bill recorded yet</h3>
            <p className="bill-comp-empty-desc">
              Enter your utility bill above to compare actual billed units against estimated consumption from your household appliance inventory.
            </p>
          </div>
        </div>
      </section>
    );
  }

  // Active bill exists, display comparison
  return (
    <section className="bill-comparison-section" aria-labelledby="bill-comparison-title" id="household-energy-comparison">
      {/* Section Header */}
      <div className="bill-comparison-header">
        <div>
          <h2 id="bill-comparison-title" className="bill-comparison-title font-serif">
            Household energy comparison
          </h2>
          <p className="bill-comparison-subtitle">
            Actual utility bill vs. appliance inventory estimate
          </p>
        </div>
        {comparison && (
          <span className={`bill-comparison-badge bill-comparison-badge--${comparison.status}`}>
            {comparison.statusHeadline}
          </span>
        )}
      </div>

      {/* Multi-Bill Selector (when 2 or more bills exist) */}
      {bills.length > 1 && (
        <div className="bill-comp-selector" role="tablist" aria-label="Select billing period for comparison">
          <span className="bill-comp-selector-label">Billing period:</span>
          <div className="bill-comp-chips">
            {bills.map((b) => {
              const isSelected = activeBill?.id === b.id;
              const label = b.billingPeriod || `Month ${b.billingMonth}/${b.billingYear}`;
              return (
                <button
                  key={b.id}
                  type="button"
                  role="tab"
                  aria-selected={isSelected}
                  className={`bill-comp-chip ${isSelected ? 'active' : ''}`}
                  onClick={() => setSelectedBillId(b.id)}
                >
                  {label}
                </button>
              );
            })}
          </div>
        </div>
      )}

      {/* Main Comparison Card */}
      <div className="bill-comp-card">
        {/* Period Meta Banner */}
        <div className="bill-comp-banner">
          <div className="bill-comp-banner__period">
            <span className="bill-comp-banner__cal-icon" aria-hidden="true">📅</span>
            <span className="bill-comp-banner__label">{comparison?.periodLabel}</span>
          </div>
          <div className="bill-comp-banner__duration">
            {comparison?.periodDays !== null ? (
              <span className="bill-comp-banner__days-pill">
                {comparison?.periodDays} days duration
              </span>
            ) : (
              <span className="bill-comp-banner__days-pill bill-comp-banner__days-pill--warn">
                Period unavailable
              </span>
            )}
          </div>
        </div>

        {/* Comparison Metrics Grid: Actual vs Estimated */}
        <div className="bill-comp-grid">
          {/* Column A: Actual Utility Bill */}
          <div className="bill-comp-col bill-comp-col--actual">
            <div className="bill-comp-col__header">
              <span className="bill-comp-col__tag">Actual Billed</span>
              <span className="bill-comp-col__source">Utility Bill</span>
            </div>
            <div className="bill-comp-col__main-metric">
              <span className="bill-comp-val font-serif">{comparison?.actualKWh ?? 0}</span>
              <span className="bill-comp-unit">kWh</span>
            </div>
            <div className="bill-comp-col__submetrics">
              <div className="bill-comp-subrow">
                <span className="bill-comp-subrow__lbl">Total Billed:</span>
                <span className="bill-comp-subrow__val font-serif">
                  {formatCurrencyINR(comparison?.actualAmount ?? 0)}
                </span>
              </div>
              <div className="bill-comp-subrow">
                <span className="bill-comp-subrow__lbl">Blended Rate:</span>
                <span className="bill-comp-subrow__val">
                  {comparison?.effectiveRate !== null
                    ? formatUnitRate(comparison?.effectiveRate ?? 0)
                    : 'Rate unavailable'}
                </span>
              </div>
            </div>
          </div>

          {/* Versus Connector */}
          <div className="bill-comp-vs" aria-hidden="true">
            <span className="bill-comp-vs__circle">vs</span>
          </div>

          {/* Column B: Estimated Household Energy */}
          <div className="bill-comp-col bill-comp-col--estimate">
            <div className="bill-comp-col__header">
              <span className="bill-comp-col__tag bill-comp-col__tag--est">Estimated Baseline</span>
              <span className="bill-comp-col__source">Appliance Inventory</span>
            </div>
            <div className="bill-comp-col__main-metric">
              <span className="bill-comp-val font-serif">
                {comparison?.estimatedKWh !== null ? comparison?.estimatedKWh : '--'}
              </span>
              <span className="bill-comp-unit">kWh</span>
            </div>
            <div className="bill-comp-col__submetrics">
              <div className="bill-comp-subrow">
                <span className="bill-comp-subrow__lbl">Estimated Cost:</span>
                <span className="bill-comp-subrow__val font-serif">
                  {comparison?.estimatedCost !== null
                    ? formatCurrencyINR(comparison?.estimatedCost ?? 0)
                    : 'Unavailable'}
                </span>
              </div>
              <div className="bill-comp-subrow">
                <span className="bill-comp-subrow__lbl">Inventory:</span>
                <NavLink to="/devices" className="bill-comp-subrow__val bill-comp-link" title="Manage appliances in Devices">
                  {totalQuantity} items · {householdDailyKWh.toFixed(2)} kWh/d →
                </NavLink>
              </div>
            </div>
          </div>
        </div>

        {/* Difference & Variance Strip */}
        {comparison && comparison.isComparisonValid && comparison.differenceKWh !== null && (
          <div className={`bill-comp-diff-strip bill-comp-diff-strip--${comparison.status}`}>
            <div className="bill-comp-diff-left">
              <span className="bill-comp-diff-label">Variance:</span>
              <span className="bill-comp-diff-value font-serif">
                {comparison.differenceKWh > 0 ? `+${comparison.differenceKWh}` : comparison.differenceKWh} kWh
              </span>
              {comparison.variancePercent !== null && (
                <span className="bill-comp-diff-pct">
                  ({comparison.variancePercent > 0 ? `+${comparison.variancePercent}%` : `${comparison.variancePercent}%`})
                </span>
              )}
            </div>

            <div className="bill-comp-diff-right">
              {comparison.status === 'higher' && (
                <span className="bill-comp-diff-badge bill-comp-diff-badge--amber">
                  Billed exceeds estimate
                </span>
              )}
              {comparison.status === 'lower' && (
                <span className="bill-comp-diff-badge bill-comp-diff-badge--blue">
                  Billed below estimate
                </span>
              )}
              {comparison.status === 'matched' && (
                <span className="bill-comp-diff-badge bill-comp-diff-badge--green">
                  Close match
                </span>
              )}
              {comparison.status === 'zero_units' && (
                <span className="bill-comp-diff-badge bill-comp-diff-badge--neutral">
                  0 billed units
                </span>
              )}
            </div>
          </div>
        )}

        {/* Explanatory Narrative Note */}
        {comparison && (
          <div className="bill-comp-explanation">
            <p className="bill-comp-explanation__text">
              {comparison.statusExplanation}
            </p>

            {/* If cost estimate exists, explicitly label as estimate */}
            {comparison.estimatedCost !== null && comparison.effectiveRate !== null && (
              <p className="bill-comp-cost-note">
                <strong>Cost estimate note:</strong> Estimated cost of {formatCurrencyINR(comparison.estimatedCost)} applies the blended rate of {formatUnitRate(comparison.effectiveRate)} to your household appliance estimate. This is an informative estimate, not an official utility tariff calculation or slab schedule.
              </p>
            )}

            {/* Zero units disclaimer */}
            {comparison.status === 'zero_units' && (
              <p className="bill-comp-cost-note">
                <strong>Rate note:</strong> Zero units consumed means the effective unit rate is mathematically undefined. SHEM does not represent this as ₹0.00/kWh.
              </p>
            )}

            {/* Missing inventory warning */}
            {comparison.status === 'no_appliances' && (
              <div className="bill-comp-action-box">
                <p>No appliances found in your household inventory.</p>
                <NavLink to="/devices" className="bill-comp-action-link">
                  Go to Devices to add appliances →
                </NavLink>
              </div>
            )}

            {/* Missing metadata warning */}
            {comparison.status === 'unavailable' && (
              <p className="bill-comp-cost-note bill-comp-cost-note--warn">
                <strong>Metadata note:</strong> This bill record does not specify a duration or valid calendar month. Edit the billing period to enable comparison.
              </p>
            )}

            <div className="bill-comp-disclaimer" aria-hidden="true">
              ℹ Comparison reflects configured appliance wattage ratings and daily operating hours. It does not represent verified utility meter telemetry, confirmed appliance faults, or guaranteed savings.
            </div>
          </div>
        )}
      </div>
    </section>
  );
}
