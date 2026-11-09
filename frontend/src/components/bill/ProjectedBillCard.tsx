import { Link } from 'react-router-dom';
import { fetchBillProjection } from '../../api/billingApi';
import type { BillBreakdown, BillProjection } from '../../api/types';
import { useApiQuery } from '../../hooks/useApiQuery';
import { SourceTag } from '../appliances/SourceTag';
import { ArrowIcon } from '../ui/icons';
import './ProjectedBillCard.css';

const inr = (v: number) => `₹${Math.round(v).toLocaleString('en-IN')}`;
const kwhFmt = (v: number) => (v >= 100 ? v.toFixed(0) : v >= 10 ? v.toFixed(1) : v.toFixed(2));

function dateLabel(iso: string, offsetDays = 0): string {
  const d = new Date(`${iso}T12:00:00`);
  d.setDate(d.getDate() + offsetDays);
  return d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}

const STATUS_TEXT = { on_track: 'On track', at_risk: 'At risk', over: 'Over budget' } as const;

/** Projected bill for the current billing cycle. `compact` = dashboard summary that links to the Bill page. */
export function ProjectedBillCard({ compact = false }: { compact?: boolean }) {
  const { data: p, error } = useApiQuery(fetchBillProjection, 'bill-projection', 60_000);

  if (!p) {
    return compact ? null : (
      <section className="card" role={error ? 'alert' : 'status'}>
        <h2 className="card__title">{error ? 'Could not project this bill' : 'Projecting this cycle’s bill…'}</h2>
        {error && <p className="sheet__hint">{error}</p>}
      </section>
    );
  }

  const cycle = `${dateLabel(p.cycleStart)} – ${dateLabel(p.cycleEnd, -1)}`;
  const progress = Math.min(100, (p.elapsedDays / Math.max(1, p.cycleDays)) * 100);
  const b = p.budget;

  if (compact) {
    return (
      <section className="card projbill projbill--compact" aria-label="Projected bill">
        <div className="card__head">
          <h2 className="card__title">This bill cycle</h2>
          <Link to="/bill" className="link-more">Details <ArrowIcon size={14} /></Link>
        </div>
        <div className="projbill__headline">
          <div>
            <span className="projbill__label">Projected bill</span>
            <b className="projbill__amount">{inr(p.projected.totalINR)}</b>
            <span className="projbill__sub">{kwhFmt(p.projectedKWh)} kWh · {cycle}</span>
          </div>
          {b && <span className={`projbill__status is-${b.status}`}>{STATUS_TEXT[b.status]}</span>}
        </div>
        <CycleBar progress={progress} p={p} />
      </section>
    );
  }

  return (
    <section className="card projbill" aria-label="Projected bill">
      <div className="card__head">
        <h2 className="card__title">Projected bill</h2>
        <span className={`projbill__conf is-${p.confidence}`}>{p.confidence} confidence</span>
      </div>

      <div className="projbill__headline">
        <div>
          <span className="projbill__label">Cycle {cycle}</span>
          <b className="projbill__amount">{inr(p.projected.totalINR)}</b>
          <span className="projbill__sub">
            ≈ {kwhFmt(p.projectedKWh)} kWh at {kwhFmt(p.dailyKWh)} kWh/day{p.paceBasis === 'last24h' ? ' (last 24 h pace)' : ''}
          </span>
        </div>
        {b && <span className={`projbill__status is-${b.status}`}>{STATUS_TEXT[b.status]}</span>}
      </div>

      <CycleBar progress={progress} p={p} />

      <div className="projbill__tiles">
        <div><b>{kwhFmt(p.usedKWh)} kWh</b><span>used so far</span></div>
        <div><b>{inr(p.soFar.totalINR)}</b><span>bill so far</span></div>
        <div><b>{Math.ceil(p.daysLeft)}</b><span>days left</span></div>
      </div>
      {p.simulatedKWh > 0 && (
        <p className="projbill__split">
          <SourceTag source="metered" compact /> {kwhFmt(p.meteredKWh)} kWh · <SourceTag source="simulated" compact /> {kwhFmt(p.simulatedKWh)} kWh
        </p>
      )}

      {p.tariff.mode === 'slab' && <SlabMeter bill={p.soFar} projected={p.projected} />}

      {b && (
        <div className={`projbill__budget is-${b.status}`}>
          <div className="projbill__budget-row">
            <span>Budget {inr(b.budgetINR)}</span>
            <span>{Math.round(b.usedPercent)}% used</span>
          </div>
          <div className="projbill__track"><span style={{ width: `${Math.min(100, b.usedPercent)}%` }} /></div>
          <p>
            {b.status === 'over'
              ? `Already ${inr(b.spentINR - b.budgetINR)} over budget this cycle.`
              : b.projectedOverINR > 0
                ? `Heading ${inr(b.projectedOverINR)} over budget.`
                : `Projected ${inr(-b.projectedOverINR)} under budget.`}
            {b.dailyAllowanceKWh != null && b.dailyAllowanceKWh > 0 && b.status !== 'over'
              ? ` Stay under ${kwhFmt(b.dailyAllowanceKWh)} kWh/day to keep within it.`
              : ''}
          </p>
        </div>
      )}

      <details className="projbill__items">
        <summary>Itemised projected bill</summary>
        <BillItems bill={p.projected} />
      </details>

      <p className="source-note">
        {p.disclaimer} <Link to="/settings" className="inline-link">Tariff settings</Link>
      </p>
    </section>
  );
}

function CycleBar({ progress, p }: { progress: number; p: BillProjection }) {
  return (
    <div className="projbill__cycle" aria-label={`Day ${Math.ceil(p.elapsedDays)} of ${p.cycleDays}`}>
      <div className="projbill__track"><span style={{ width: `${progress}%` }} /></div>
      <span>Day {Math.max(1, Math.ceil(p.elapsedDays))} of {p.cycleDays}</span>
    </div>
  );
}

function SlabMeter({ bill, projected }: { bill: BillBreakdown; projected: BillBreakdown }) {
  const current = bill.lines[bill.slabIndex];
  return (
    <div className="projbill__slab">
      <div className="projbill__slab-bars">
        {bill.lines.map((ln, i) => (
          <span key={ln.label} className={`${i < bill.slabIndex ? 'is-full' : ''} ${i === bill.slabIndex ? 'is-now' : ''} ${i <= projected.slabIndex && i > bill.slabIndex ? 'is-proj' : ''}`} title={`${ln.label} @ ₹${ln.rateINR}`}>
            ₹{ln.rateINR}
          </span>
        ))}
      </div>
      <p>
        Now in the <b>{current?.label ?? 'first'}</b> slab (₹{current?.rateINR}/kWh).
        {bill.kwhToNextSlab != null && bill.nextSlabRateINR != null
          ? ` ${kwhFmt(bill.kwhToNextSlab)} kWh left before ₹${bill.nextSlabRateINR}/kWh.`
          : ''}
        {projected.slabIndex > bill.slabIndex ? ` At this pace you’ll reach the ${projected.lines[projected.slabIndex].label} slab.` : ''}
      </p>
    </div>
  );
}

function BillItems({ bill }: { bill: BillBreakdown }) {
  const rows: [string, string, number][] = [
    ...bill.lines.filter((ln) => ln.kwh > 0).map((ln) => [ln.label, `${kwhFmt(ln.kwh)} kWh × ₹${ln.rateINR}`, ln.amountINR] as [string, string, number]),
    ...(bill.fuelChargeINR ? [['Fuel adjustment', '', bill.fuelChargeINR] as [string, string, number]] : []),
    ...(bill.dutyINR ? [['Electricity duty', '', bill.dutyINR] as [string, string, number]] : []),
    ...(bill.fixedChargeINR ? [['Fixed charge', '', bill.fixedChargeINR] as [string, string, number]] : []),
  ];
  return (
    <table className="projbill__table">
      <tbody>
        {rows.map(([label, detail, amount]) => (
          <tr key={label}><td>{label}{detail && <small>{detail}</small>}</td><td>₹{amount.toFixed(2)}</td></tr>
        ))}
        <tr className="is-total"><td>Total</td><td>₹{bill.totalINR.toFixed(2)}</td></tr>
      </tbody>
    </table>
  );
}
