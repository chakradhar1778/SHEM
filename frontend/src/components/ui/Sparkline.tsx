interface SparklineProps {
  values: number[];
  height?: number;
  /** Optional axis labels shown under the line, evenly spaced. */
  labels?: string[];
}

/** Smooth area line with a marker on the latest point (used for live power). */
export function Sparkline({ values, height = 84, labels }: SparklineProps) {
  const w = 340;
  const pad = 10;
  const n = values.length;

  if (n < 2) {
    return <div className="spark spark--empty" style={{ height }} aria-hidden="true" />;
  }

  const min = Math.min(...values);
  const max = Math.max(...values);
  const range = max - min || 1;
  const pts = values.map((v, i) => ({
    x: (i / (n - 1)) * w,
    y: height - pad - ((v - min) / range) * (height - pad * 2),
  }));

  let d = `M ${pts[0].x} ${pts[0].y}`;
  for (let i = 0; i < n - 1; i++) {
    const p0 = pts[Math.max(0, i - 1)];
    const p1 = pts[i];
    const p2 = pts[i + 1];
    const p3 = pts[Math.min(n - 1, i + 2)];
    d += ` C ${p1.x + (p2.x - p0.x) / 6} ${p1.y + (p2.y - p0.y) / 6}, ${p2.x - (p3.x - p1.x) / 6} ${p2.y - (p3.y - p1.y) / 6}, ${p2.x} ${p2.y}`;
  }
  const last = pts[n - 1];
  const area = `${d} L ${last.x} ${height} L 0 ${height} Z`;

  return (
    <div className="spark">
      <svg viewBox={`0 0 ${w} ${height}`} preserveAspectRatio="none" width="100%" height={height} aria-hidden="true">
        <defs>
          <linearGradient id="sparkFill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0" stopColor="#3B6FE0" stopOpacity="0.22" />
            <stop offset="1" stopColor="#3B6FE0" stopOpacity="0" />
          </linearGradient>
        </defs>
        <path d={area} fill="url(#sparkFill)" />
        <path d={d} fill="none" stroke="#3B6FE0" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" vectorEffect="non-scaling-stroke" />
      </svg>
      <span className="spark__dot" style={{ left: `${(last.x / w) * 100}%`, top: last.y }} />
      {labels && (
        <div className="spark__labels">
          {labels.map((l) => <span key={l}>{l}</span>)}
        </div>
      )}
    </div>
  );
}
