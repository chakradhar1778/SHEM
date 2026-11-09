import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { errorMessage } from '../../api/backendApi';
import { fetchBillAppliances } from '../../api/billingApi';
import type { ApplianceBillShare, BillApplianceBreakdown } from '../../api/types';
import { ApplianceIcon } from '../appliances/ApplianceIcons';
import { SourceTag } from '../appliances/SourceTag';
import { BoltIcon, HomeTypeIcon } from '../ui/icons';
import './BillCostSplit.css';

const inr = (v: number) => `₹${v < 10 ? v.toFixed(2) : Math.round(v).toLocaleString('en-IN')}`;
const kwh = (v: number) => (v >= 100 ? v.toFixed(0) : v >= 10 ? v.toFixed(1) : v.toFixed(2));

interface ExtraRow { key: string; label: string; sub: string; cost: number; percent: number; icon: 'fixed' | 'rest' }

/** Rows of "where the money goes": appliances (tagged Metered / Simulated) plus fixed charge and rest of home. */
export function CostSplitList({ items, extras = [], total, limit }: { items: ApplianceBillShare[]; extras?: ExtraRow[]; total: number; limit?: number }) {
  const shown = limit ? items.slice(0, limit) : items;
  const hidden = limit ? items.slice(limit) : [];
  const max = Math.max(1e-9, ...shown.map((a) => a.costINR), ...extras.map((e) => e.cost));
  return (
    <div className="cost-split">
      {shown.map((a) => (
        <Link key={a.applianceId} to={a.applianceId === 'metered-circuit' ? '/live' : `/devices/edit/${a.applianceId}`} className="cost-split__row">
          <span className="cost-split__icon"><ApplianceIcon type={a.iconType ?? 'bulb'} size={26} /></span>
          <span className="cost-split__body">
            <span className="cost-split__top"><b>{a.name}</b><SourceTag source={a.source} compact /></span>
            <span className="cost-split__track"><span className={a.source === 'simulated' ? 'is-sim' : ''} style={{ width: `${Math.max(3, (a.costINR / max) * 100)}%` }} /></span>
            <span className="cost-split__sub">{kwh(a.kwh)} kWh · {Math.round(a.sharePercent)}% of the bill</span>
          </span>
          <b className="cost-split__amt">{inr(a.costINR)}</b>
        </Link>
      ))}
      {hidden.length > 0 && (
        <p className="cost-split__more">
          + {hidden.length} more · {inr(hidden.reduce((s, a) => s + a.costINR, 0))}
        </p>
      )}
      {extras.filter((e) => e.cost > 0).map((e) => (
        <div key={e.key} className="cost-split__row cost-split__row--extra">
          <span className="cost-split__icon">{e.icon === 'fixed' ? <BoltIcon size={20} /> : <HomeTypeIcon size={20} />}</span>
          <span className="cost-split__body">
            <span className="cost-split__top"><b>{e.label}</b></span>
            <span className="cost-split__track"><span className="is-extra" style={{ width: `${Math.max(3, (e.cost / max) * 100)}%` }} /></span>
            <span className="cost-split__sub">{e.sub}{e.percent ? ` · ${Math.round(e.percent)}% of the bill` : ''}</span>
          </span>
          <b className="cost-split__amt">{inr(e.cost)}</b>
        </div>
      ))}
      <div className="cost-split__total"><span>Total</span><b>{inr(total)}</b></div>
    </div>
  );
}

/** Lazy per-appliance split of one recorded bill (fetched when shown). */
export function BillCostSplit({ billId }: { billId: string }) {
  const [data, setData] = useState<BillApplianceBreakdown | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    fetchBillAppliances(billId)
      .then((d) => !cancelled && setData(d))
      .catch((e) => !cancelled && setError(errorMessage(e)));
    return () => {
      cancelled = true;
    };
  }, [billId]);

  if (error) return <p className="form__error" role="alert">{error}</p>;
  if (!data) return <p className="sheet__hint">Splitting the bill…</p>;

  const end = new Date(`${data.periodEnd}T12:00:00`);
  end.setDate(end.getDate() - 1);
  const fmt = (d: Date) => d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short', year: 'numeric' });
  const period = `${fmt(new Date(`${data.periodStart}T12:00:00`))} – ${fmt(end)}`;

  return (
    <div className="bill-split">
      <p className="bill-split__period">
        {period} · {data.periodSource === 'dates' ? 'from the bill dates' : 'billing cycle of this month'} · ₹{data.variableRateINR.toFixed(2)}/kWh usage rate
      </p>
      <CostSplitList
        items={data.appliances}
        total={data.billAmountINR}
        extras={[
          { key: 'fixed', label: 'Fixed charge', sub: 'Every bill, regardless of usage', cost: data.fixedChargeINR, percent: data.billAmountINR ? (data.fixedChargeINR / data.billAmountINR) * 100 : 0, icon: 'fixed' },
          { key: 'rest', label: 'Rest of home', sub: `${kwh(data.restKWh)} kWh billed but not measured by SHEM`, cost: data.restINR, percent: data.restPercent, icon: 'rest' },
        ]}
      />
      {data.notes.map((n) => <p key={n} className="bill-split__note">{n}</p>)}
    </div>
  );
}
