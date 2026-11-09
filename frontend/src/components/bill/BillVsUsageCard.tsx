import { fetchBillAppliances } from '../../api/billingApi';
import type { BillRecord } from '../../context/billContextDef';
import { useApiQuery } from '../../hooks/useApiQuery';
import { useInventory } from '../../hooks/useInventory';
import { calculateHouseholdDailyKWh, compareBillWithHousehold } from '../../utils/billMath';
import { SourceTag } from '../appliances/SourceTag';

const kwh = (v: number) => (v >= 100 ? v.toFixed(0) : v >= 10 ? v.toFixed(1) : v.toFixed(2));

/**
 * A bill vs what SHEM recorded (metered + simulated) in that bill's period, per day over the recorded hours.
 * Falls back to the rated-watt appliance estimate only when SHEM has no usage for the period.
 */
export function BillVsUsageCard({ bill }: { bill: BillRecord }) {
  const { inventory } = useInventory();
  const { data, error } = useApiQuery(() => fetchBillAppliances(bill.id), `bill-vs:${bill.id}`);
  const r = data && data.billId === bill.id ? data : null;

  if (r && r.recordedDailyKWh != null && r.billedDailyKWh != null) {
    const v = r.variancePercent ?? 0;
    const close = Math.abs(v) <= 15;
    const verdict = close
      ? 'SHEM’s recorded usage is in line with this bill.'
      : v > 0
        ? 'SHEM recorded more per day than this bill. Simulated devices aren’t on the real meter, and they may run more than you actually do.'
        : 'This bill is higher per day than SHEM recorded. Part of your home isn’t on the meter or modelled as an appliance (see “Rest of home” in the bill’s breakdown).';
    return (
      <section className="card" aria-label="Bill versus recorded usage">
        <div className="card__head"><h2 className="card__title">Bill vs recorded usage</h2><span className="chip chip--static">{bill.billingPeriod}</span></div>
        <div className="compare">
          <div><b>{kwh(r.billedDailyKWh)} kWh</b><span>Per day on the bill</span></div>
          <div><b>{kwh(r.recordedDailyKWh)} kWh</b><span>Per day recorded by SHEM</span></div>
          <div><b className={close ? '' : v > 0 ? 'is-up' : 'is-down'}>{v > 0 ? '+' : ''}{Math.round(v)}%</b><span>Difference</span></div>
        </div>
        <p className="bill__note">{verdict}</p>
        <p className="bill__note">
          Based on {r.coveredHours} recorded {r.coveredHours === 1 ? 'hour' : 'hours'} ({Math.round(r.coveragePercent)}% of the {Math.round(r.periodDays)}-day period)
          {' · '}<SourceTag source="metered" compact /> {kwh(r.meteredKWh)} kWh · <SourceTag source="simulated" compact /> {kwh(r.simulatedKWh)} kWh
        </p>
      </section>
    );
  }

  // No recorded usage for this period: fall back to the appliance-rating estimate (clearly labelled).
  const est = inventory.length > 0 ? compareBillWithHousehold(bill, calculateHouseholdDailyKWh(inventory), inventory.length) : null;
  if (!r && !error) return null;
  if (!est?.isComparisonValid || est.estimatedKWh === null) return null;
  return (
    <section className="card" aria-label="Bill versus appliance estimate">
      <div className="card__head"><h2 className="card__title">Bill vs your appliances</h2><span className="chip chip--static">estimate</span></div>
      <div className="compare">
        <div><b>{bill.unitsConsumed} kWh</b><span>On your bill</span></div>
        <div><b>{est.estimatedKWh} kWh</b><span>Rated W × hours/day</span></div>
        {est.variancePercent !== null && (
          <div><b className={est.variancePercent > 0 ? 'is-up' : 'is-down'}>{est.variancePercent > 0 ? '+' : ''}{est.variancePercent}%</b><span>Difference</span></div>
        )}
      </div>
      <p className="bill__note">
        SHEM has no recorded usage for this bill’s period, so this uses appliance ratings × daily hours. {est.statusExplanation}
      </p>
    </section>
  );
}
