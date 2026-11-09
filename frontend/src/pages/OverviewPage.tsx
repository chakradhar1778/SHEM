import { useState } from 'react';
import { Link, useNavigate } from 'react-router-dom';
import { fetchInsights, fetchTodayInsights } from '../api/insightsApi';
import { useApiQuery } from '../hooks/useApiQuery';
import { useBill } from '../hooks/useBill';
import { useLiveData } from '../hooks/useLiveData';
import { useTarget } from '../hooks/useTarget';
import { PageHero } from '../components/art/PageHero';
import { ApplianceUsageList } from '../components/appliances/ApplianceUsageList';
import { SourceTag } from '../components/appliances/SourceTag';
import { Sparkline } from '../components/ui/Sparkline';
import { ArrowIcon, BoltIcon, CalendarIcon, ChevronRight, ClockIcon, UploadIcon, WalletIcon } from '../components/ui/icons';
import { formatRaw } from '../utils/liveFormat';
import { formatKWh } from '../utils/simFormat';
import { formatCurrencyINR } from '../utils/billMath';
import './OverviewPage.css';

function daysInfo() {
  const now = new Date();
  return { day: now.getDate(), total: new Date(now.getFullYear(), now.getMonth() + 1, 0).getDate() };
}

/** "My home": live power, this month at a glance, latest bill. */
export function OverviewPage() {
  const navigate = useNavigate();
  const { isLive, streamStatus, device, sim, homePowerW, meteredPowerW, homePoints, homeLive } = useLiveData();
  const { target } = useTarget();
  const { latestBill } = useBill();
  const { data: month } = useApiQuery(() => fetchInsights('month'), 'month', 60_000);
  const { data: today } = useApiQuery(() => fetchTodayInsights(), 'today', 30_000);
  const [range, setRange] = useState<'today' | 'month'>('today');
  const simCount = sim?.appliances.length ?? 0;
  const simOn = sim?.appliances.filter((a) => a.state === 'ON').length ?? 0;
  const breakdown = (range === 'today' ? today?.applianceUsage : month?.applianceUsage) ?? [];
  const breakdownTotal = range === 'today' ? today : month;

  const { day, total } = daysInfo();
  const budget = target.isConfigured ? target.monthlyBudgetINR : null;
  const consumed = month?.totalKWh ?? null;
  const spent = month?.totalCostINR ?? null;
  const remaining = budget != null && spent != null ? budget - spent : null;

  const status = isLive
    ? 'LIVE POWER'
    : streamStatus !== 'open'
      ? 'BACKEND OFFLINE'
      : homeLive
        ? 'LIVE POWER · SIMULATED ONLY'
        : device && !device.deviceOnline
          ? 'METER OFFLINE'
          : 'WAITING FOR METER';

  return (
    <div className="page">
      <PageHero art="villa" title="My home" subtitle="Your energy status at a glance" />

      <section className="card live-card" aria-label="Live power">
        <div className="live-card__top">
          <span className="live-card__status">
            <span className={`live-card__dot ${homeLive ? 'is-live' : ''}`} />
            {status}
          </span>
          <button type="button" className="live-card__pill" onClick={() => navigate('/live')}>
            Live <ChevronRight size={14} />
          </button>
        </div>
        <div className="live-card__reading" onClick={() => navigate('/live')} role="button" tabIndex={0}
          onKeyDown={(e) => { if (e.key === 'Enter') navigate('/live'); }}>
          <span className="live-card__value">{formatRaw(homePowerW)}</span>
          <span className="live-card__unit">W</span>
        </div>
        {simCount > 0 && homeLive && (
          <div className="live-card__split">
            <span><SourceTag source="metered" compact /> {formatRaw(meteredPowerW)} W</span>
            <span><SourceTag source="simulated" compact /> {formatRaw(sim?.totalPowerW ?? 0)} W · {simOn}/{simCount} on</span>
          </div>
        )}
        <Sparkline values={homePoints.slice(-90).map((p) => p.powerW)} labels={['earlier', 'now']} />
      </section>

      <section className="card" aria-label="Appliance breakdown">
        <div className="card__head">
          <h2 className="card__title">Appliance breakdown</h2>
          <div className="seg" role="tablist" aria-label="Range">
            {(['today', 'month'] as const).map((r) => (
              <button key={r} type="button" role="tab" aria-selected={range === r} className={`seg__btn ${range === r ? 'seg__btn--on' : ''}`} onClick={() => setRange(r)}>
                {r === 'today' ? 'Today' : 'Month'}
              </button>
            ))}
          </div>
        </div>
        {breakdown.length === 0 ? (
          <p className="sheet__hint">
            {breakdownTotal ? 'No appliance usage recorded yet. Simulated appliances start counting as soon as they run.' : 'Loading…'}
          </p>
        ) : (
          <>
            {breakdownTotal && (
              <p className="breakdown-total">
                <b>{formatKWh(range === 'today' ? today!.energyTodayKWh : month!.totalKWh)} kWh</b>{' '}
                {range === 'today' ? 'today' : 'this month'} · {breakdown.length} {breakdown.length === 1 ? 'appliance' : 'appliances'}
              </p>
            )}
            <ApplianceUsageList items={breakdown} showLive limit={6} />
            <Link to="/insights/daily" className="link-more breakdown-more">Day-wise breakdown & peak hours <ArrowIcon size={14} /></Link>
          </>
        )}
      </section>

      <section className="card" aria-label="This month">
        <div className="card__head">
          <h2 className="card__title">This month</h2>
          <Link to="/insights" className="link-more">View details <ArrowIcon size={14} /></Link>
        </div>
        <div className="tile-grid">
          <div className="tile">
            <span className="tile__icon"><WalletIcon /></span>
            <span className="tile__body">
              <span className="tile__value">{budget != null ? formatCurrencyINR(budget) : '--'}</span>
              <span className="tile__label">Energy budget</span>
            </span>
          </div>
          <div className="tile tile--green">
            <span className="tile__icon"><BoltIcon /></span>
            <span className="tile__body">
              <span className="tile__value">{consumed != null ? `${consumed.toFixed(consumed < 10 ? 2 : 1)} kWh` : '0.0 kWh'}</span>
              <span className="tile__label">Consumed</span>
            </span>
          </div>
          <div className="tile tile--amber">
            <span className="tile__icon"><ClockIcon /></span>
            <span className="tile__body">
              <span className="tile__value">
                {remaining != null ? `${remaining < 0 ? '−' : ''}${formatCurrencyINR(Math.abs(remaining))}` : '--'}
              </span>
              <span className="tile__label">{remaining != null && remaining < 0 ? 'Over budget' : 'Remaining'}</span>
            </span>
          </div>
          <div className="tile">
            <span className="tile__icon"><CalendarIcon /></span>
            <span className="tile__body">
              <span className="tile__value">{day}/{total}</span>
              <span className="tile__label">Days elapsed</span>
            </span>
          </div>
        </div>
      </section>

      <section className="card" aria-label="Bill history">
        <div className="card__head">
          <h2 className="card__title">Bill history</h2>
          <Link to="/bill" className="link-more">View all <ArrowIcon size={14} /></Link>
        </div>
        {latestBill ? (
          <Link to="/bill" className="row bill-row">
            <span className="bill-row__amount">{formatCurrencyINR(latestBill.billAmount)}</span>
            <span className="row__body">
              <span className="row__title">{latestBill.billingPeriod ?? 'Latest bill'}</span>
              <span className="row__sub">{latestBill.unitsConsumed} kWh · {latestBill.utilityProvider}</span>
            </span>
            <span className="row__end"><ChevronRight /></span>
          </Link>
        ) : (
          <div className="bill-empty">
            <p>No bills yet. Upload one to see your trend.</p>
            <Link to="/bill" className="btn btn--soft btn--small"><UploadIcon size={18} /> Upload bill</Link>
          </div>
        )}
      </section>
    </div>
  );
}
