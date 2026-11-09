import { formatRaw } from '../../utils/liveFormat';
interface LiveSpeedometerGaugeProps {
  /** Measured AC active power; null when no reading is available */
  powerWatts: number | null;
  maxScaleWatts?: number;
  /** True only when the reading is fresh (device online, stream open) */
  isLive: boolean;
}

const ARC = 'M 40.7 157.5 A 95 95 0 1 1 219.3 157.5';
const ARC_LENGTH = Math.PI * 95 * (220 / 180);

/** Semi-circle power gauge with the reading in the middle. */
export function LiveSpeedometerGauge({ powerWatts, maxScaleWatts = 1000, isLive }: LiveSpeedometerGaugeProps) {
  const running = isLive && powerWatts != null;
  const fraction = maxScaleWatts > 0 ? Math.max(0, Math.min(1, (powerWatts ?? 0) / maxScaleWatts)) : 0;
  // Raw meter value in watts — never rounded.
  const value = formatRaw(powerWatts);

  return (
    <div className="gauge" role="img" aria-label={powerWatts == null ? 'Live power: no reading' : `Live power: ${value} watts`}>
      <svg viewBox="0 0 260 200" className="gauge__svg" aria-hidden="true">
        <defs>
          <linearGradient id="gaugeGrad" x1="0" y1="1" x2="1" y2="0">
            <stop offset="0" stopColor="#4FB783" />
            <stop offset="0.55" stopColor="#8CC56A" />
            <stop offset="1" stopColor="#F2B53D" />
          </linearGradient>
        </defs>
        <path d={ARC} fill="none" stroke="#E3EAF5" strokeWidth="16" strokeLinecap="round" />
        {running && (
          <path
            d={ARC}
            fill="none"
            stroke="url(#gaugeGrad)"
            strokeWidth="16"
            strokeLinecap="round"
            strokeDasharray={ARC_LENGTH}
            strokeDashoffset={ARC_LENGTH * (1 - fraction)}
            className="gauge__progress"
          />
        )}
        <text x="36" y="182" className="gauge__tick" textAnchor="middle">0</text>
        <text x="224" y="182" className="gauge__tick" textAnchor="middle">
          {maxScaleWatts >= 1000 ? `${maxScaleWatts / 1000} kW` : `${maxScaleWatts} W`}
        </text>
      </svg>

      <div className="gauge__readout">
        <span className="gauge__label">Current usage</span>
        <span className="gauge__value">
          {value}
          <small>W</small>
        </span>
        <span className={`gauge__pill ${running ? 'is-live' : ''}`}>
          <i />
          {running ? 'LIVE' : powerWatts != null ? 'LAST READING' : 'NO DATA'}
        </span>
      </div>
    </div>
  );
}
