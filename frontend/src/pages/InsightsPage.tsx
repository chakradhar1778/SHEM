import { useState } from 'react';
import { Link } from 'react-router-dom';
import { fetchInsights } from '../api/insightsApi';
import type { InsightsPeriod } from '../api/types';
import { useApiQuery } from '../hooks/useApiQuery';
import { ApplianceIcon } from '../components/appliances/ApplianceIcons';
import { ApplianceUsageList } from '../components/appliances/ApplianceUsageList';
import { SourceTag } from '../components/appliances/SourceTag';
import { PageHero } from '../components/art/PageHero';
import { BarChart, ChartLegend } from '../components/ui/charts';
import { BoltIcon, ChevronRight, FileIcon } from '../components/ui/icons';
import { iconForCategory } from '../utils/applianceGroups';
import './InsightsPage.css';

/** "Your energy story": measured usage over a week, month or year. */
export function InsightsPage() {
  const [period, setPeriod] = useState<InsightsPeriod>('week');
  const { data, error, refresh } = useApiQuery(() => fetchInsights(period), period, 120_000);
  const insights = data && data.period === period ? data : null;

  const points = insights?.trendPoints ?? [];
  const targetKWh = points[0]?.targetKWh ?? null;
  const change = insights?.comparison?.percentChange ?? null;

  return (
    <div className="page">
      <PageHero art="story" title={<>Your energy<br />story</>} subtitle="Patterns worth noticing.">
        <div className="seg" role="tablist" aria-label="Period">
          {(['week', 'month', 'year'] as InsightsPeriod[]).map((p) => (
            <button key={p} type="button" role="tab" aria-selected={period === p} className={`seg__btn ${period === p ? 'seg__btn--on' : ''}`} onClick={() => setPeriod(p)}>
              {p[0].toUpperCase() + p.slice(1)}
            </button>
          ))}
        </div>
      </PageHero>

      {!insights ? (
        <section className="card" role={error ? 'alert' : 'status'}>
          <h2 className="card__title">{error ? 'Could not load insights' : 'Loading insights…'}</h2>
          {error && (
            <>
              <p className="sheet__hint">{error}</p>
              <button type="button" className="btn btn--soft btn--small" onClick={refresh}>Try again</button>
            </>
          )}
        </section>
      ) : !insights.hasData ? (
        <section className="card">
          <div className="empty">
            <BoltIcon size={26} />
            <span><strong>No readings for this {period} yet.</strong>{insights.dataNote ?? 'Insights appear once the meter has reported.'}</span>
          </div>
        </section>
      ) : (
        <>
          <Link to="/insights/daily" className="note-card tone--amber">
            <span className="note-card__icon"><BoltIcon size={26} /></span>
            <span className="note-card__text">
              <span className="note-card__tag">Key insight</span>
              <b>{insights.keyInsight.title}</b>
              <span>{insights.keyInsight.description}</span>
            </span>
            <ChevronRight />
          </Link>

          <div className="tile-grid">
            <div className="card stat">
              <span className="tile__icon"><BoltIcon /></span>
              <b className="stat__value">{insights.totalKWh.toLocaleString('en-IN')} <small>kWh</small></b>
              <span className="stat__label">{insights.periodLabel.toLowerCase()}</span>
              {insights.simulatedKWh > 0 && (
                <span className="stat__split">
                  <SourceTag source="metered" compact /> {insights.meteredKWh.toFixed(2)} · <SourceTag source="simulated" compact /> {insights.simulatedKWh.toFixed(2)}
                </span>
              )}
              {change != null && (
                <span className={`delta ${change > 0 ? 'is-up' : 'is-down'}`}>
                  {change > 0 ? '↑' : '↓'} {Math.abs(Math.round(change))}% vs last {period}
                </span>
              )}
            </div>
            <div className="card stat">
              <span className="tile__icon tile__icon--amber">₹</span>
              <b className="stat__value">₹{Math.round(insights.totalCostINR).toLocaleString('en-IN')}</b>
              <span className="stat__label">estimated cost</span>
              <span className="delta">at ₹{insights.effectiveRateINR}/kWh</span>
            </div>
          </div>

          <section className="card" aria-label="Usage trend">
            <div className="card__head">
              <h2 className="card__title">Your usage trend</h2>
              <span className="chip chip--static">{insights.periodLabel}</span>
            </div>
            <BarChart
              data={points.map((p) => ({ label: p.label, value: p.usageKWh, strong: p.isPeak }))}
              target={targetKWh}
              unit="kWh"
              labelEvery={points.length > 12 ? 3 : 1}
            />
            <ChartLegend items={[{ label: 'Your usage', color: '#3B6FE0' }, ...(targetKWh ? [{ label: 'Target', color: '#E5484D', dashed: true }] : [])]} />
            {insights.dataNote && <p className="source-note">{insights.dataNote}</p>}
          </section>

          <section className="card" aria-label="Where energy goes">
            <div className="card__head">
              <h2 className="card__title">{insights.shiftsAreEstimates ? 'Biggest shifts' : 'Where energy goes'}</h2>
              <Link to="/insights/daily" className="link-more">View details <ChevronRight size={14} /></Link>
            </div>
            {insights.shifts.length === 0 ? (
              <p className="sheet__hint">Add appliances with wattage and daily hours in Devices to see this breakdown.</p>
            ) : (
              <>
                <div className="list">
                  {insights.shifts.slice(0, 4).map((s) => (
                    <div key={s.categoryId} className="shift">
                      <ApplianceIcon type={iconForCategory(s.categoryId)} size={34} />
                      <span className="shift__body">
                        <span className="shift__top"><b>{s.categoryLabel}</b><span>{insights.shiftsAreEstimates ? '~' : ''}{s.kwh} kWh</span></span>
                        <span className="shift__track"><span style={{ width: `${Math.min(100, Math.max(6, s.percentage))}%` }} /></span>
                      </span>
                      {s.direction !== 'neutral' && s.percentChange != null && (
                        <span className={`delta ${s.direction === 'up' ? 'is-up' : 'is-down'}`}>{s.direction === 'up' ? '↑' : '↓'} {s.percentChange}%</span>
                      )}
                    </div>
                  ))}
                </div>
                <p className="source-note">
                  {insights.shiftsAreEstimates
                    ? 'Estimated from appliance ratings × daily hours, not individually metered.'
                    : 'By category, from metered energy and simulated appliances.'}
                </p>
              </>
            )}
          </section>

          {insights.applianceUsage.length > 0 && (
            <section className="card" aria-label="Usage by appliance">
              <div className="card__head">
                <h2 className="card__title">By appliance</h2>
                <span className="chip chip--static">{insights.periodLabel}</span>
              </div>
              <ApplianceUsageList items={insights.applianceUsage} />
            </section>
          )}
        </>
      )}

      <Link to="/insights/guide" className="note-card tone--amber">
        <span className="note-card__icon"><BoltIcon size={24} /></span>
        <span className="note-card__text"><b>Your energy guide</b><span>Tips based on your measured usage.</span></span>
        <ChevronRight />
      </Link>
      <Link to="/map" className="note-card">
        <span className="note-card__icon"><FileIcon size={24} /></span>
        <span className="note-card__text"><b>Appliance map</b><span>See appliances around your home.</span></span>
        <ChevronRight />
      </Link>
    </div>
  );
}
