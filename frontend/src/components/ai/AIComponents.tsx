import { useEffect, useId, useState } from 'react';
import { DATA_CHANGED_EVENT, errorMessage } from '../../api/backendApi';
import { fetchAppliances } from '../../api/inventoryApi';
import { fetchBills } from '../../api/billsApi';
import type { ActionResult, AIComponent, ChartSeries, MetricItem, Tone } from '../../api/aiTypes';
import type { ApplianceDTO, BillDTO } from '../../api/types';
import { useAI } from '../../hooks/useAI';
import { RelayToggle } from '../appliances/RelayToggle';
import { SimToggle } from '../appliances/SimToggle';
import { SimTag } from '../appliances/SourceTag';
import { ApplianceIcon } from '../appliances/ApplianceIcons';

const PALETTE = ['#3B6FE0', '#1FA971', '#E9A33A', '#E5484D', '#8B5CF6', '#22B8CF', '#F472B6', '#64748B'];
const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

function fmt(v: number | string | null | undefined, digits = 2): string {
  if (v == null) return '—';
  if (typeof v === 'string') return v;
  if (!Number.isFinite(v)) return '—';
  const abs = Math.abs(v);
  const d = abs >= 1000 ? 0 : abs >= 100 ? 1 : digits;
  return v.toLocaleString('en-IN', { maximumFractionDigits: d });
}

function withUnit(value: string, unit?: string): string {
  if (!unit) return value;
  return unit === '₹' || unit === 'INR' ? `₹${value}` : `${value} ${unit}`;
}

const toneClass = (t?: Tone | null) => (t ? `ai-tone--${t}` : '');

// ── Shared cached loaders (several cards in one reply share a request) ───────
function cachedLoader<T>(fetcher: () => Promise<T>, ttlMs = 4000) {
  let cache: { at: number; p: Promise<T> } | null = null;
  const load = () => {
    if (!cache || Date.now() - cache.at > ttlMs) {
      const p = fetcher();
      cache = { at: Date.now(), p };
      p.catch(() => {
        cache = null;
      });
    }
    return cache.p;
  };
  const invalidate = () => {
    cache = null;
  };
  return { load, invalidate };
}

const appliancesLoader = cachedLoader<ApplianceDTO[]>(fetchAppliances);
const billsLoader = cachedLoader<BillDTO[]>(fetchBills);

function useCached<T extends { id: string }>(loader: { load: () => Promise<T[]>; invalidate: () => void }, id: string) {
  const [state, setState] = useState<{ item: T | null; error: string | null; loading: boolean }>({ item: null, error: null, loading: true });
  const [nonce, setNonce] = useState(0);
  useEffect(() => {
    let cancelled = false;
    loader
      .load()
      .then((all) => !cancelled && setState({ item: all.find((x) => x.id === id) ?? null, error: null, loading: false }))
      .catch((err) => !cancelled && setState((s) => ({ ...s, error: errorMessage(err), loading: false })));
    return () => {
      cancelled = true;
    };
  }, [nonce, loader, id]);
  useEffect(() => {
    const bump = () => {
      loader.invalidate();
      setNonce((n) => n + 1);
    };
    window.addEventListener(DATA_CHANGED_EVENT, bump);
    return () => window.removeEventListener(DATA_CHANGED_EVENT, bump);
  }, [loader]);
  return state;
}

// ── metric_cards ─────────────────────────────────────────────────────────────
function MetricCards({ title, items }: { title?: string; items: MetricItem[] }) {
  return (
    <div className="ai-card">
      {title && <div className="ai-card__title">{title}</div>}
      <div className={`ai-metrics ai-metrics--${Math.min(items.length, 3)}`}>
        {items.map((m, i) => (
          <div key={i} className={`ai-metric ${toneClass(m.tone)}`}>
            <span className="ai-metric__label">{m.label}</span>
            <span className="ai-metric__value">
              {m.unit === '₹' || m.unit === 'INR' ? `₹${fmt(m.value)}` : fmt(m.value)}
              {m.unit && m.unit !== '₹' && m.unit !== 'INR' && <small> {m.unit}</small>}
            </span>
            {(m.delta || m.trend) && (
              <span className={`ai-metric__delta ai-trend--${m.trend ?? 'flat'}`}>
                {m.trend === 'up' ? '▲ ' : m.trend === 'down' ? '▼ ' : ''}
                {m.delta}
              </span>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

// ── chart (line / area / bar) ───────────────────────────────────────────────
const W = 320;
const H = 170;
const PAD = { l: 36, r: 8, t: 10, b: 26 };

function niceMax(v: number): number {
  if (v <= 0) return 1;
  const p = 10 ** Math.floor(Math.log10(v));
  const n = v / p;
  return (n <= 1 ? 1 : n <= 2 ? 2 : n <= 2.5 ? 2.5 : n <= 5 ? 5 : 10) * p;
}

function Chart({ chartType, title, unit, xLabel, yLabel, series }: { chartType: 'line' | 'bar' | 'area'; title?: string; unit?: string; xLabel?: string; yLabel?: string; series: ChartSeries[] }) {
  const gid = `g${useId().replace(/[^a-zA-Z0-9]/g, '')}`;
  const labels: (string | number)[] = [];
  const seen = new Set<string>();
  for (const s of series) for (const p of s.points) if (!seen.has(String(p.x))) { seen.add(String(p.x)); labels.push(p.x); }
  const n = labels.length;
  const values = series.flatMap((s) => s.points.map((p) => p.y).filter((y): y is number => y != null && Number.isFinite(y)));
  if (!n || !values.length) return null;
  const minV = Math.min(0, ...values);
  const maxV = niceMax(Math.max(...values, 0));
  const range = maxV - minV || 1;
  const iw = W - PAD.l - PAD.r;
  const ih = H - PAD.t - PAD.b;
  const y = (v: number) => PAD.t + ih - ((v - minV) / range) * ih;
  const slot = iw / n;
  const xc = (i: number) => (chartType === 'bar' ? PAD.l + slot * i + slot / 2 : PAD.l + (n === 1 ? iw / 2 : (iw * i) / (n - 1)));
  const idx = new Map(labels.map((l, i) => [String(l), i]));
  const labelStep = Math.max(1, Math.ceil(n / 6));
  const ticks = [0, 0.5, 1].map((f) => minV + range * f);

  return (
    <div className="ai-card">
      {title && <div className="ai-card__title">{title}{unit ? <span className="ai-card__unit"> · {unit}</span> : null}</div>}
      <svg viewBox={`0 0 ${W} ${H}`} className="ai-chart" role="img" aria-label={title ?? 'Chart'}>
        <defs>
          {series.map((_, si) => (
            <linearGradient key={si} id={`${gid}-${si}`} x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stopColor={PALETTE[si % PALETTE.length]} stopOpacity="0.28" />
              <stop offset="100%" stopColor={PALETTE[si % PALETTE.length]} stopOpacity="0" />
            </linearGradient>
          ))}
        </defs>
        {ticks.map((t, i) => (
          <g key={i}>
            <line x1={PAD.l} x2={W - PAD.r} y1={y(t)} y2={y(t)} className="ai-chart__grid" />
            <text x={PAD.l - 5} y={y(t) + 3} textAnchor="end" className="ai-chart__axis">{fmt(t, 2)}</text>
          </g>
        ))}
        {labels.map((l, i) =>
          i % labelStep === 0 || i === n - 1 ? (
            <text key={i} x={xc(i)} y={H - 8} textAnchor="middle" className="ai-chart__axis">{String(l).slice(0, 8)}</text>
          ) : null
        )}
        {chartType === 'bar'
          ? series.map((s, si) => {
              const bw = Math.max(2, (slot * 0.72) / series.length);
              return s.points.map((p, pi) => {
                if (p.y == null) return null;
                const i = idx.get(String(p.x)) ?? 0;
                const x0 = xc(i) - (bw * series.length) / 2 + bw * si;
                const top = y(Math.max(p.y, 0));
                const h = Math.abs(y(p.y) - y(0));
                return (
                  <rect key={`${si}-${pi}`} x={x0} y={top} width={bw - 1} height={Math.max(h, 0.5)} rx={Math.min(3, bw / 3)} fill={PALETTE[si % PALETTE.length]}>
                    <title>{`${s.name} · ${p.x}: ${withUnit(fmt(p.y), unit)}`}</title>
                  </rect>
                );
              });
            })
          : series.map((s, si) => {
              const color = PALETTE[si % PALETTE.length];
              const runs: { x: number; y: number }[][] = [];
              let run: { x: number; y: number }[] = [];
              for (const p of s.points) {
                if (p.y == null) {
                  if (run.length) runs.push(run);
                  run = [];
                } else run.push({ x: xc(idx.get(String(p.x)) ?? 0), y: y(p.y) });
              }
              if (run.length) runs.push(run);
              return (
                <g key={si}>
                  {runs.map((r, ri) => {
                    const d = r.map((pt, k) => `${k ? 'L' : 'M'}${pt.x.toFixed(1)},${pt.y.toFixed(1)}`).join(' ');
                    return (
                      <g key={ri}>
                        {chartType === 'area' && r.length > 1 && (
                          <path d={`${d} L${r[r.length - 1].x.toFixed(1)},${y(Math.max(minV, 0))} L${r[0].x.toFixed(1)},${y(Math.max(minV, 0))} Z`} fill={`url(#${gid}-${si})`} />
                        )}
                        <path d={d} fill="none" stroke={color} strokeWidth="2.2" strokeLinejoin="round" strokeLinecap="round" />
                        {r.length === 1 && <circle cx={r[0].x} cy={r[0].y} r="3" fill={color} />}
                      </g>
                    );
                  })}
                </g>
              );
            })}
      </svg>
      {(series.length > 1 || xLabel || yLabel) && (
        <div className="ai-legend">
          {series.length > 1 && series.map((s, si) => (
            <span key={si}><i style={{ background: PALETTE[si % PALETTE.length] }} />{s.name}</span>
          ))}
          {(xLabel || yLabel) && <span className="ai-legend__axes">{[yLabel, xLabel].filter(Boolean).join(' vs ')}</span>}
        </div>
      )}
    </div>
  );
}

// ── breakdown (donut) ────────────────────────────────────────────────────────
function Breakdown({ title, unit, items }: { title?: string; unit?: string; items: { label: string; value: number; unit?: string }[] }) {
  const total = items.reduce((a, b) => a + Math.max(0, b.value), 0);
  const R = 42;
  const C = 2 * Math.PI * R;
  let acc = 0;
  return (
    <div className="ai-card">
      {title && <div className="ai-card__title">{title}</div>}
      <div className="ai-donut">
        <svg viewBox="0 0 110 110" className="ai-donut__svg" aria-hidden="true">
          <circle cx="55" cy="55" r={R} fill="none" stroke="#EEF2FA" strokeWidth="14" />
          {total > 0 && items.map((it, i) => {
            const len = (Math.max(0, it.value) / total) * C;
            const el = (
              <circle key={i} cx="55" cy="55" r={R} fill="none" stroke={PALETTE[i % PALETTE.length]} strokeWidth="14"
                strokeDasharray={`${Math.max(0, len - 1.2)} ${C}`} strokeDashoffset={-acc} transform="rotate(-90 55 55)" />
            );
            acc += len;
            return el;
          })}
          <text x="55" y="53" textAnchor="middle" className="ai-donut__total">{fmt(total)}</text>
          <text x="55" y="67" textAnchor="middle" className="ai-donut__unit">{unit ?? 'total'}</text>
        </svg>
        <ul className="ai-donut__legend">
          {items.map((it, i) => (
            <li key={i}>
              <i style={{ background: PALETTE[i % PALETTE.length] }} />
              <span className="ai-donut__label">{it.label}</span>
              <b>{total > 0 ? `${Math.round((Math.max(0, it.value) / total) * 100)}%` : '—'}</b>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

// ── progress ─────────────────────────────────────────────────────────────────
function ProgressCard({ label, current, target, unit, caption, tone }: { label: string; current: number; target: number; unit?: string; caption?: string; tone?: Tone }) {
  const pct = target > 0 ? (current / target) * 100 : 0;
  const auto: Tone = pct > 100 ? 'bad' : pct > 85 ? 'warn' : 'good';
  return (
    <div className={`ai-card ai-progress ${toneClass(tone ?? auto)}`}>
      <div className="ai-progress__head">
        <span>{label}</span>
        <b>{Math.round(pct)}%</b>
      </div>
      <div className="ai-progress__bar"><span style={{ width: `${Math.min(100, Math.max(0, pct))}%` }} /></div>
      <div className="ai-progress__foot">
        <span>{withUnit(fmt(current), unit)} of {withUnit(fmt(target), unit)}</span>
        {caption && <span>{caption}</span>}
      </div>
    </div>
  );
}

// ── table ────────────────────────────────────────────────────────────────────
function TableCard({ title, columns, rows }: { title?: string; columns: string[]; rows: (string | number | null)[][] }) {
  return (
    <div className="ai-card">
      {title && <div className="ai-card__title">{title}</div>}
      <div className="ai-table-wrap">
        <table className="ai-table">
          <thead><tr>{columns.map((c, i) => <th key={i}>{c}</th>)}</tr></thead>
          <tbody>
            {rows.map((r, ri) => (
              <tr key={ri}>{columns.map((_, ci) => <td key={ci} className={typeof r[ci] === 'number' ? 'is-num' : ''}>{fmt(r[ci] ?? null)}</td>)}</tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}

// ── appliance_card ───────────────────────────────────────────────────────────
function ApplianceCard({ applianceId, name }: { applianceId: string; name?: string }) {
  const { item, error, loading } = useCached(appliancesLoader, applianceId);

  if (loading && !item) return <div className="ai-card ai-skeleton" aria-busy="true">Loading {name ?? 'appliance'}…</div>;
  if (!item) return <div className="ai-card ai-muted">{error ?? `${name ?? 'This appliance'} is no longer in your inventory.`}</div>;

  const watts = item.ratedWatts != null ? `${fmt(item.ratedWatts * item.quantity, 0)} W` : 'Rating unknown';

  return (
    <div className="ai-card ai-appliance">
      <div className="ai-appliance__icon"><ApplianceIcon type={item.iconType ?? 'bulb'} size={26} /></div>
      <div className="ai-appliance__body">
        <b>{item.name}</b>
        <span>
          {watts}
          {item.quantity > 1 ? ` · ×${item.quantity}` : ''}
          {item.dailyHours ? ` · ${fmt(item.dailyHours, 1)} h/day` : ''}
          {item.relayChannel ? ` · Relay ${item.relayChannel}` : ''}
          {!item.relayChannel && <> <SimTag compact /></>}
        </span>
      </div>
      {item.relayChannel ? (
        <RelayToggle applianceName={item.name} channel={item.relayChannel} />
      ) : (
        <SimToggle applianceId={item.id} applianceName={item.name} showPower={false} />
      )}
    </div>
  );
}

// ── relay_control ────────────────────────────────────────────────────────────
function RelayControlCard({ channel, label }: { channel: number; label?: string }) {
  return (
    <div className="ai-card ai-appliance">
      <div className="ai-appliance__icon ai-appliance__icon--relay">⚡</div>
      <div className="ai-appliance__body">
        <b>{label ?? `Relay ${channel}`}</b>
        <span>Switches only after the device confirms</span>
      </div>
      <RelayToggle applianceName={label ?? `Relay ${channel}`} channel={channel} />
    </div>
  );
}

// ── alert ────────────────────────────────────────────────────────────────────
function AlertCard({ severity, title, message, conflictId }: { severity: 'info' | 'warning' | 'critical' | 'success'; title: string; message: string; conflictId?: string }) {
  const { dismissConflict } = useAI();
  const [dismissed, setDismissed] = useState(false);
  if (dismissed) return null;
  const icon = severity === 'critical' ? '⛔' : severity === 'warning' ? '⚠️' : severity === 'success' ? '✅' : 'ℹ️';
  return (
    <div className={`ai-alert ai-alert--${severity}`} role={severity === 'critical' ? 'alert' : 'status'}>
      <span className="ai-alert__icon" aria-hidden="true">{icon}</span>
      <div className="ai-alert__body">
        <b>{title}</b>
        <p>{message}</p>
        {conflictId && (
          <button type="button" className="link-more" onClick={() => { setDismissed(true); void dismissConflict(conflictId); }}>
            Dismiss
          </button>
        )}
      </div>
    </div>
  );
}

// ── recommendations ──────────────────────────────────────────────────────────
function RecommendationsCard({ title, items }: { title?: string; items: { title: string; description: string; impact?: string; priority?: 'high' | 'medium' | 'low' }[] }) {
  return (
    <div className="ai-card">
      {title && <div className="ai-card__title">{title}</div>}
      <ol className="ai-recs">
        {items.map((r, i) => (
          <li key={i} className={`ai-rec ai-rec--${r.priority ?? 'low'}`}>
            <span className="ai-rec__num">{i + 1}</span>
            <div>
              <b>{r.title}</b>
              <p>{r.description}</p>
              {r.impact && <span className="ai-rec__impact">{r.impact}</span>}
            </div>
          </li>
        ))}
      </ol>
    </div>
  );
}

// ── action_buttons ───────────────────────────────────────────────────────────
function ActionButtons({ buttons }: { buttons: { label: string; prompt: string }[] }) {
  const { send, streaming } = useAI();
  return (
    <div className="ai-buttons">
      {buttons.map((b, i) => (
        <button key={i} type="button" className="ai-btn" disabled={streaming} onClick={() => send(b.prompt)}>
          {b.label}
        </button>
      ))}
    </div>
  );
}

// ── bill_card ────────────────────────────────────────────────────────────────
function BillCard({ billId }: { billId: string }) {
  const { item, error, loading } = useCached(billsLoader, billId);
  if (loading && !item) return <div className="ai-card ai-skeleton" aria-busy="true">Loading bill…</div>;
  if (!item) return <div className="ai-card ai-muted">{error ?? 'This bill no longer exists.'}</div>;
  const period =
    item.billingPeriod ||
    (item.billingMonth && item.billingYear ? `${MONTHS[item.billingMonth - 1]} ${item.billingYear}` : null) ||
    [item.billingPeriodStart, item.billingPeriodEnd].filter(Boolean).join(' → ') ||
    'Bill';
  const rate = item.unitsConsumedKWh > 0 ? item.billAmountINR / item.unitsConsumedKWh : null;
  return (
    <div className="ai-card ai-bill">
      <div className="ai-bill__head">
        <span className="ai-bill__icon" aria-hidden="true">🧾</span>
        <div>
          <b>{period}</b>
          <span>{item.utilityProvider ?? 'Electricity bill'}{item.dueDate ? ` · due ${item.dueDate}` : ''}</span>
        </div>
      </div>
      <div className="ai-metrics ai-metrics--3">
        <div className="ai-metric"><span className="ai-metric__label">Amount</span><span className="ai-metric__value">₹{fmt(item.billAmountINR)}</span></div>
        <div className="ai-metric"><span className="ai-metric__label">Units</span><span className="ai-metric__value">{fmt(item.unitsConsumedKWh)}<small> kWh</small></span></div>
        <div className="ai-metric"><span className="ai-metric__label">Rate</span><span className="ai-metric__value">{rate ? `₹${fmt(rate)}` : '—'}<small>/kWh</small></span></div>
      </div>
    </div>
  );
}

// ── timeline ─────────────────────────────────────────────────────────────────
function TimelineCard({ title, items }: { title?: string; items: { time: string; title: string; description?: string }[] }) {
  return (
    <div className="ai-card">
      {title && <div className="ai-card__title">{title}</div>}
      <ul className="ai-timeline">
        {items.map((it, i) => (
          <li key={i}>
            <span className="ai-timeline__time">{it.time}</span>
            <div><b>{it.title}</b>{it.description && <p>{it.description}</p>}</div>
          </li>
        ))}
      </ul>
    </div>
  );
}

// ── action_result ────────────────────────────────────────────────────────────
const RELAY_ERROR = /^(rejected_|timeout|publish_failed)/;

export function ActionResultCard({ action }: { action: ActionResult }) {
  const { commandStatus } = useAI();
  const live = action.commandId ? commandStatus[action.commandId] : undefined;
  const status: ActionResult['status'] = live ? (live === 'applied' ? 'success' : RELAY_ERROR.test(live) ? 'error' : 'pending') : action.status;
  const liveDetail = live
    ? live === 'applied'
      ? 'Confirmed by the device.'
      : RELAY_ERROR.test(live)
        ? `Device did not apply it (${live.replace(/_/g, ' ')}).`
        : null
    : null;
  return (
    <div className={`ai-action ai-action--${status}`} role="status">
      <span className="ai-action__icon" aria-hidden="true">
        {status === 'success' ? '✓' : status === 'error' ? '!' : <span className="ai-spinner" />}
      </span>
      <div className="ai-action__body">
        <b>{action.title}</b>
        {(liveDetail ?? action.detail) && <span>{liveDetail ?? action.detail}</span>}
      </div>
    </div>
  );
}

/** Render one AI component; unknown types render nothing. */
export function AIComponentView({ component }: { component: AIComponent }) {
  switch (component.type) {
    case 'metric_cards':
      return component.items?.length ? <MetricCards title={component.title} items={component.items} /> : null;
    case 'chart':
      return component.series?.length ? <Chart {...component} chartType={component.chartType ?? 'line'} /> : null;
    case 'breakdown':
      return component.items?.length ? <Breakdown {...component} /> : null;
    case 'progress':
      return <ProgressCard {...component} />;
    case 'table':
      return component.columns?.length ? <TableCard title={component.title} columns={component.columns} rows={component.rows ?? []} /> : null;
    case 'appliance_card':
      return <ApplianceCard applianceId={component.applianceId} name={component.name} />;
    case 'relay_control':
      return <RelayControlCard channel={component.channel ?? 1} label={component.label} />;
    case 'alert':
      return <AlertCard {...component} />;
    case 'recommendations':
      return component.items?.length ? <RecommendationsCard title={component.title} items={component.items} /> : null;
    case 'action_buttons':
      return component.buttons?.length ? <ActionButtons buttons={component.buttons} /> : null;
    case 'bill_card':
      return <BillCard billId={component.billId} />;
    case 'timeline':
      return component.items?.length ? <TimelineCard title={component.title} items={component.items} /> : null;
    case 'action_result':
      return <ActionResultCard action={component} />;
    default:
      return null;
  }
}
