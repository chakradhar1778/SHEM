import { useMemo, useState } from 'react';
import { useSearchParams } from 'react-router-dom';
import { fetchDailyTotals, fetchTodayInsights } from '../api/insightsApi';
import type { DayPeriodBreakdown, TodayInsightsResponse } from '../api/types';
import { useApiQuery } from '../hooks/useApiQuery';
import { ApplianceIcon } from '../components/appliances/ApplianceIcons';
import { ApplianceUsageList } from '../components/appliances/ApplianceUsageList';
import { SourceTag } from '../components/appliances/SourceTag';
import { BarChart, ChartLegend } from '../components/ui/charts';
import { BoltIcon, CalendarIcon, ChevronLeft, ChevronRight } from '../components/ui/icons';
import { formatKWh as kwh, formatWatts } from '../utils/simFormat';
import './EnergyTodayPage.css';

const PERIOD_ICON: Record<string, string> = { night: '🌙', morning: '🌅', afternoon: '☀️', evening: '🌆' };
const METERED = '#3B6FE0';
const SIMULATED = '#7A5AF8';
const STRIP_DAYS = 14;

/** Local YYYY-MM-DD for a Date. */
function isoDay(d: Date): string {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
}
function shiftDay(day: string, delta: number): string {
  const d = new Date(`${day}T12:00:00`);
  d.setDate(d.getDate() + delta);
  return isoDay(d);
}
function daysBetween(a: string, b: string): number {
  return Math.round((new Date(`${b}T12:00:00`).getTime() - new Date(`${a}T12:00:00`).getTime()) / 86_400_000);
}

/** Energy for any day: totals, hourly profile (metered vs simulated), peak periods and per-appliance split. */
export function EnergyTodayPage() {
  const [params, setParams] = useSearchParams();
  const [today] = useState(() => isoDay(new Date()));
  const requested = params.get('date');
  const date = requested && /^\d{4}-\d{2}-\d{2}$/.test(requested) && requested <= today ? requested : today;
  const isToday = date === today;
  const setDate = (d: string) => setParams(d >= today ? {} : { date: d }, { replace: true });

  // Strip ends today while the chosen day is within it, otherwise at the chosen day.
  const stripEnd = daysBetween(date, today) < STRIP_DAYS ? today : date;
  const { data, error, refresh } = useApiQuery(() => fetchTodayInsights(isToday ? undefined : date), `day:${date}`, isToday ? 60_000 : undefined);
  const { data: strip } = useApiQuery(() => fetchDailyTotals(STRIP_DAYS, stripEnd === today ? undefined : stripEnd), `strip:${stripEnd}`, 120_000);
  const day = data && data.date === date ? data : null;

  const dateLabel = new Date(`${date}T12:00:00`).toLocaleDateString('en-IN', { weekday: 'short', day: 'numeric', month: 'short', year: 'numeric' });

  return (
    <div className="page today">
      <header className="today__head">
        <div>
          <h1 className="hero__title">{isToday ? 'Energy today' : 'Energy by day'}</h1>
          <p className="hero__subtitle">Daily breakdown</p>
        </div>
        <div className="day-nav" role="group" aria-label="Choose day">
          <button type="button" className="day-nav__btn" onClick={() => setDate(shiftDay(date, -1))} aria-label="Previous day">
            <ChevronLeft size={16} />
          </button>
          <label className="date-pill day-nav__pill">
            <CalendarIcon size={16} />
            <span>{dateLabel}</span>
            <input
              type="date"
              className="day-nav__input"
              value={date}
              max={today}
              onChange={(e) => e.target.value && setDate(e.target.value)}
              aria-label="Pick a date"
            />
          </label>
          <button type="button" className="day-nav__btn" onClick={() => setDate(shiftDay(date, 1))} disabled={isToday} aria-label="Next day">
            <ChevronRight size={16} />
          </button>
        </div>
      </header>
      {!isToday && (
        <button type="button" className="btn-link day-nav__today" onClick={() => setDate(today)}>Back to today</button>
      )}

      {strip && (
        <section className="card" aria-label="Day-wise breakdown">
          <div className="card__head">
            <h2 className="card__title">Day-wise breakdown</h2>
            <span className="source-note" style={{ margin: 0 }}>
              {strip.averageKWh != null ? `Avg ${kwh(strip.averageKWh)} kWh/day` : `Last ${STRIP_DAYS} days`}
            </span>
          </div>
          <BarChart
            data={strip.days.map((d) => ({
              label: d.isToday ? 'Today' : d.weekday.slice(0, 2),
              title: `${d.weekday} ${d.dayLabel}`,
              value: d.meteredKWh,
              stack: d.simulatedKWh,
              selected: d.date === date,
              strong: d.date === date,
            }))}
            target={strip.dailyTargetKWh}
            unit="kWh"
            height={110}
            labelEvery={2}
            onSelect={(i) => setDate(strip.days[i].date)}
          />
          <ChartLegend items={[
            { label: 'Metered', color: METERED },
            { label: 'Simulated', color: SIMULATED },
            ...(strip.dailyTargetKWh != null ? [{ label: 'Daily target', color: '#E5484D', dashed: true }] : []),
          ]} />
          <p className="source-note">Tap a day to see its breakdown.</p>
        </section>
      )}

      {!day ? (
        <section className="card" role={error ? 'alert' : 'status'}>
          <h2 className="card__title">{error ? 'Could not load this day' : 'Loading…'}</h2>
          {error && (<><p className="sheet__hint">{error}</p><button type="button" className="btn btn--soft btn--small" onClick={refresh}>Try again</button></>)}
        </section>
      ) : !day.hasData ? (
        <section className="card">
          <div className="empty">
            <BoltIcon size={26} />
            <span>
              <strong>{day.insightCard.title}</strong>
              {day.insightCard.description}{isToday ? ' The breakdown appears as soon as the meter reports or a simulated appliance runs.' : ''}
            </span>
          </div>
        </section>
      ) : (
        <DayBreakdown day={day} />
      )}
    </div>
  );
}

function DayBreakdown({ day }: { day: TodayInsightsResponse }) {
  const points = day.hourlyPoints;
  const hourlyTarget = points[0]?.targetKWh ?? null;
  const hasSim = day.simulatedKWh > 0;
  // Today: show 12am up to the latest hour with data (the data refreshes every minute).
  const lastHour = points.reduce((last, p) => (p.measured ? p.hour : last), -1);
  const chartPoints = day.isToday && lastHour >= 0 ? points.filter((p) => p.hour <= lastHour) : points;
  const peakPeriod = useMemo(() => day.dayPeriods.find((p) => p.isPeak) ?? null, [day.dayPeriods]);

  return (
    <>
      <div className="today__tiles">
        <div className="tile">
          <span className="tile__icon"><BoltIcon /></span>
          <span className="tile__body"><b className="tile__value">{kwh(day.energyTodayKWh)} <small>kWh</small></b><span className="tile__label">{day.isToday ? 'Energy used today' : 'Energy used'}</span></span>
        </div>
        <div className="tile tile--green">
          <span className="tile__icon"><BoltIcon /></span>
          <span className="tile__body"><b className="tile__value">{day.dailyTargetKWh != null ? `${kwh(day.dailyTargetKWh)} kWh` : '--'}</b><span className="tile__label">{day.isTargetConfigured ? 'Daily target' : 'No target set'}</span></span>
        </div>
        <div className="tile tile--amber">
          <span className="tile__icon">₹</span>
          <span className="tile__body"><b className="tile__value">₹{day.costTodayINR.toFixed(day.costTodayINR < 10 ? 2 : 0)}</b><span className="tile__label">Estimated cost</span></span>
        </div>
      </div>

      {hasSim && (
        <div className="split-bar" aria-label="Metered versus simulated energy">
          <div className="split-bar__track">
            <span style={{ flex: day.meteredKWh, background: METERED }} />
            <span style={{ flex: day.simulatedKWh, background: SIMULATED }} />
          </div>
          <div className="split-bar__legend">
            <span><SourceTag source="metered" compact /> {kwh(day.meteredKWh)} kWh</span>
            <span><SourceTag source="simulated" compact /> {kwh(day.simulatedKWh)} kWh</span>
          </div>
        </div>
      )}

      <section className="card" aria-label="Hourly usage">
        <div className="card__head"><h2 className="card__title">Hourly usage</h2><span className="source-note" style={{ margin: 0 }}>{day.isToday ? '12am – now' : '12am – 12am'}</span></div>
        <BarChart
          data={chartPoints.map((p) => ({
            label: p.hour % 4 === 0 ? p.timeLabel : '',
            title: p.timeLabel,
            value: hasSim ? p.meteredKWh : p.usageKWh,
            stack: hasSim ? p.simulatedKWh : undefined,
            strong: p.isPeak,
          }))}
          target={hourlyTarget}
          unit="kWh"
        />
        <ChartLegend items={[
          ...(hasSim ? [{ label: 'Metered', color: METERED }, { label: 'Simulated', color: SIMULATED }] : [{ label: 'Your usage', color: METERED }]),
          ...(hourlyTarget != null ? [{ label: 'Target', color: '#E5484D', dashed: true }] : []),
        ]} />
      </section>

      <section className="card" aria-label="Peak usage">
        <div className="card__head"><h2 className="card__title">Peak usage</h2></div>
        {day.peak && peakPeriod && (
          <div className="peak-hero">
            <span className="peak-hero__icon">{PERIOD_ICON[peakPeriod.period] ?? '⚡'}</span>
            <span className="peak-hero__body">
              <span className="peak-hero__tag">Peak period</span>
              <b>{peakPeriod.label} <small>{peakPeriod.timeRange}</small></b>
              <span>
                {kwh(peakPeriod.kwh)} kWh · {Math.round(peakPeriod.percentage)}% of the day · peak hour {day.peak.hourLabel}
                {day.peak.avgPowerW != null ? ` (avg ${formatWatts(day.peak.avgPowerW)})` : ''}
                {day.peak.topAppliance ? ` · mostly ${day.peak.topAppliance}` : ''}
              </span>
            </span>
          </div>
        )}
        <div className="list">
          {day.dayPeriods.map((p) => <PeriodRow key={p.period} p={p} />)}
        </div>
      </section>

      {day.applianceUsage.length > 0 && (
        <section className="card" aria-label="Usage by appliance">
          <div className="card__head"><h2 className="card__title">Usage by appliance</h2></div>
          <ApplianceUsageList items={day.applianceUsage} showLive={day.isToday} />
          <p className="source-note">
            Metered = relay circuit measured by the SHEM meter. Simulated = appliances without a relay, run by SHEM’s realistic power model.
          </p>
        </section>
      )}

      <div className="note-card tone--amber">
        <span className="note-card__icon"><BoltIcon size={24} /></span>
        <span className="note-card__text"><b>{day.insightCard.title}</b><span>{day.insightCard.description}</span></span>
      </div>
      {day.dataNote && <p className="source-note">{day.dataNote}</p>}
      <p className="source-note">{day.rateDisclosure}</p>
    </>
  );
}

function PeriodRow({ p }: { p: DayPeriodBreakdown }) {
  return (
    <div className={`period-card ${p.isPeak ? 'is-peak' : ''}`}>
      <div className="period">
        <span className="period__icon">{PERIOD_ICON[p.period] ?? '⚡'}</span>
        <span className="period__body">
          <b>{p.label}{p.isPeak && <span className="peak-badge">Peak</span>}</b>
          <span>{p.timeRange}</span>
        </span>
        <span className="period__track"><span style={{ width: `${Math.max(3, p.percentage)}%` }} /></span>
        <span className="period__val"><b>{kwh(p.kwh)} kWh</b><span>{Math.round(p.percentage)}%</span></span>
      </div>
      {p.kwh > 0 && (
        <div className="period-card__meta">
          <span>avg {formatWatts(p.avgPowerW)}</span>
          {p.peakHourLabel && <span>peak hour {p.peakHourLabel}</span>}
          <span>₹{p.costINR.toFixed(p.costINR < 10 ? 2 : 0)}</span>
        </div>
      )}
      {p.topAppliances.length > 0 && (
        <div className="period-card__apps">
          {p.topAppliances.map((a) => (
            <span key={a.applianceId} className={`app-chip ${a.source === 'simulated' ? 'is-sim' : ''}`} title={a.source === 'simulated' ? 'Simulated' : 'Metered'}>
              <ApplianceIcon type={a.iconType ?? 'bulb'} size={16} /> {a.name} · {kwh(a.kwh)}
            </span>
          ))}
        </div>
      )}
    </div>
  );
}
