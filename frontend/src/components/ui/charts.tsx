/** Light-theme chart primitives shared by Target, Insights and Energy today. */

interface RingProps {
  /** 0..1 filled fraction */
  fraction: number;
  color: string;
  icon: React.ReactNode;
  value: string;
  caption: string;
}

export function Ring({ fraction, color, icon, value, caption }: RingProps) {
  const r = 34;
  const c = 2 * Math.PI * r;
  const f = Math.max(0, Math.min(1, fraction));
  return (
    <div className="ring">
      <svg viewBox="0 0 84 84" className="ring__svg" aria-hidden="true">
        <circle cx="42" cy="42" r={r} fill="none" stroke="#E6ECF7" strokeWidth="7" />
        <circle
          cx="42"
          cy="42"
          r={r}
          fill="none"
          stroke={color}
          strokeWidth="7"
          strokeLinecap="round"
          strokeDasharray={c}
          strokeDashoffset={c * (1 - f)}
          transform="rotate(-90 42 42)"
        />
      </svg>
      <div className="ring__body" style={{ color }}>
        <span className="ring__icon">{icon}</span>
        <b className="ring__value">{value}</b>
        <span className="ring__caption">{caption}</span>
      </div>
    </div>
  );
}

export interface BarDatum {
  label: string;
  value: number;
  /** Optional second series stacked on top of `value` (e.g. simulated on top of metered). */
  stack?: number;
  /** Draw this bar in the strong colour (e.g. peak or current period). */
  strong?: boolean;
  /** Highlight the bar's column (e.g. the selected day). */
  selected?: boolean;
  /** Tooltip label (defaults to `label`). */
  title?: string;
}

interface BarChartProps {
  data: BarDatum[];
  target?: number | null;
  color?: string;
  stackColor?: string;
  height?: number;
  unit?: string;
  /** Show a label above every n-th bar only (keeps dense charts readable). */
  labelEvery?: number;
  /** Makes bars clickable (index of the clicked bar). */
  onSelect?: (index: number) => void;
}

export function BarChart({ data, target = null, color = '#3B6FE0', stackColor = '#7A5AF8', height = 150, unit = '', labelEvery = 1, onSelect }: BarChartProps) {
  const max = Math.max(1e-9, ...data.map((d) => d.value + (d.stack ?? 0)), target ?? 0) * 1.15;
  const yOf = (v: number) => height - (v / max) * height;
  const ticks = [0, 0.5, 1].map((t) => ({ t, v: max * t }));

  return (
    <div className="bars" role="img" aria-label="Bar chart">
      <div className="bars__plot" style={{ height }}>
        {ticks.map(({ t, v }) => (
          <div key={t} className="bars__grid" style={{ bottom: `${t * 100}%` }}>
            <span>{v >= 10 ? Math.round(v) : v.toFixed(1)}</span>
          </div>
        ))}
        {target != null && target > 0 && (
          <div className="bars__target" style={{ top: yOf(target) }} />
        )}
        <div className="bars__cols">
          {data.map((d, i) => {
            const total = d.value + (d.stack ?? 0);
            const tip = `${d.title ?? d.label}: ${total.toFixed(2)} ${unit}${d.stack ? ` (${d.value.toFixed(2)} metered + ${d.stack.toFixed(2)} simulated)` : ''}`;
            const bar = d.stack ? (
              <span className="bars__stack" style={{ height: `${Math.max(2, (total / max) * 100)}%`, opacity: d.strong ? 1 : 0.7 }}>
                <span style={{ flex: d.stack, background: stackColor }} />
                {d.value > 0 && <span style={{ flex: d.value, background: color }} />}
              </span>
            ) : (
              <span className="bars__bar" style={{ height: `${Math.max(2, (d.value / max) * 100)}%`, background: color, opacity: d.strong ? 1 : 0.62 }} />
            );
            return onSelect ? (
              <button key={i} type="button" className={`bars__col bars__col--btn ${d.selected ? 'is-selected' : ''}`} title={tip} aria-label={tip} aria-pressed={!!d.selected} onClick={() => onSelect(i)}>
                {bar}
              </button>
            ) : (
              <div key={i} className={`bars__col ${d.selected ? 'is-selected' : ''}`} title={tip}>{bar}</div>
            );
          })}
        </div>
      </div>
      <div className="bars__axis">
        {data.map((d, i) => (
          <span key={i} className={d.selected ? 'is-selected' : ''}>{i % labelEvery === 0 ? d.label : ''}</span>
        ))}
      </div>
    </div>
  );
}

export function ChartLegend({ items }: { items: { label: string; color: string; dashed?: boolean }[] }) {
  return (
    <div className="legend">
      {items.map((i) => (
        <span key={i.label}>
          <i style={i.dashed ? { borderTop: `2px dashed ${i.color}`, background: 'none', height: 0, borderRadius: 0, width: 16 } : { background: i.color }} />
          {i.label}
        </span>
      ))}
    </div>
  );
}
