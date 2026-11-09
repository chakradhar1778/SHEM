import { useState } from 'react';
import type { TargetTrendPoint } from '../../utils/targetEvaluation';

interface TargetTrendChartProps {
  trendPoints: TargetTrendPoint[];
  targetINR: number;
  statusColor: 'green' | 'amber' | 'red' | 'blue' | 'gray';
}

export function TargetTrendChart({ trendPoints, targetINR, statusColor }: TargetTrendChartProps) {
  const [selectedFilter, setSelectedFilter] = useState<'month' | 'quarter'>('month');

  // Primary accent bar color
  let barFill = '#16A34A';
  if (statusColor === 'amber') barFill = '#D97706';
  if (statusColor === 'red') barFill = '#DC2626';
  if (statusColor === 'blue') barFill = '#3B82F6';

  const hasData = trendPoints.length > 0;

  // Find max value to scale chart height safely
  const maxAmount = hasData
    ? Math.max(targetINR * 1.2, ...trendPoints.map((p) => p.amountINR))
    : targetINR > 0
    ? targetINR * 1.2
    : 3000;

  const chartHeight = 140;
  const targetY = Math.round(chartHeight - (targetINR / maxAmount) * chartHeight);

  return (
    <div className="target-trend-card">
      <div className="target-trend-card__header">
        <div className="target-trend-card__title-wrap">
          <span className="target-trend-card__icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
              <rect x="3" y="12" width="4.5" height="9" rx="1.5" />
              <rect x="9.75" y="7" width="4.5" height="14" rx="1.5" />
              <rect x="16.5" y="3" width="4.5" height="18" rx="1.5" />
            </svg>
          </span>
          <h2 className="target-trend-card__title">Energy trend</h2>
        </div>

        <div className="target-trend-card__selector">
          <select
            value={selectedFilter}
            onChange={(e) => setSelectedFilter(e.target.value as 'month' | 'quarter')}
            className="target-trend-card__select"
            aria-label="Filter trend period"
          >
            <option value="month">This month</option>
            <option value="quarter">Last 3 months</option>
          </select>
        </div>
      </div>

      {hasData ? (
        <div className="target-trend-card__chart-area">
          <div className="target-trend-card__svg-wrap">
            <svg
              viewBox={`0 0 ${Math.max(260, trendPoints.length * 70)} ${chartHeight + 30}`}
              className="target-trend-card__svg"
              preserveAspectRatio="none"
              aria-label="Target vs Billed Spend Trend Chart"
            >
              {/* Target Dashed Horizontal Line */}
              <line
                x1="0"
                y1={targetY}
                x2="100%"
                y2={targetY}
                stroke="#64748B"
                strokeWidth="1.5"
                strokeDasharray="4 4"
                opacity="0.8"
              />

              {/* Data Bars */}
              {trendPoints.map((pt, idx) => {
                const totalPoints = trendPoints.length;
                const slotWidth = 100 / totalPoints;
                const barWidth = 32;
                const xCenter = (idx + 0.5) * slotWidth;
                const barHeight = Math.max(8, (pt.amountINR / maxAmount) * chartHeight);
                const y = chartHeight - barHeight;

                return (
                  <g key={pt.label + idx}>
                    {/* Bar rectangle */}
                    <rect
                      x={`calc(${xCenter}% - ${barWidth / 2}px)`}
                      y={y}
                      width={barWidth}
                      height={barHeight}
                      rx="6"
                      fill={pt.amountINR > targetINR ? '#DC2626' : barFill}
                      opacity={pt.isCurrent ? '1' : '0.75'}
                    />
                    {/* Amount label above bar */}
                    <text
                      x={`${xCenter}%`}
                      y={Math.max(14, y - 6)}
                      textAnchor="middle"
                      fill="#1E293B"
                      fontSize="10"
                      fontWeight="600"
                    >
                      ₹{pt.amountINR}
                    </text>
                    {/* Period label below chart */}
                    <text
                      x={`${xCenter}%`}
                      y={chartHeight + 20}
                      textAnchor="middle"
                      fill="#64748B"
                      fontSize="11"
                    >
                      {pt.label}
                    </text>
                  </g>
                );
              })}
            </svg>
          </div>

          {/* Chart Legend */}
          <div className="target-trend-card__legend">
            <div className="target-trend-card__legend-item">
              <span className="target-trend-card__dot" style={{ backgroundColor: barFill }} />
              <span>Billed spend</span>
            </div>
            <div className="target-trend-card__legend-item">
              <span className="target-trend-card__dash" />
              <span>Your target (₹{targetINR.toLocaleString('en-IN')})</span>
            </div>
          </div>
        </div>
      ) : (
        /* Empty State when no historical utility records exist */
        <div className="target-trend-card__empty">
          <div className="target-trend-card__empty-icon" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="32" height="32" fill="none" stroke="#94A3B8" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 20V10 M18 20V4 M6 20v-4" />
            </svg>
          </div>
          <p className="target-trend-card__empty-title">Trend comparison activates with logged bills</p>
          <p className="target-trend-card__empty-desc">
            SHEM does not fabricate synthetic daily usage curves. As you log monthly utility bills, this chart will plot your billed spend against your ₹{targetINR > 0 ? targetINR.toLocaleString('en-IN') : '1,800'} budget goal.
          </p>
        </div>
      )}
    </div>
  );
}
