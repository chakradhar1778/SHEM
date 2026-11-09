import type { TargetEvaluationResult } from '../../utils/targetEvaluation';

interface TargetMetricGaugesProps {
  evaluation: TargetEvaluationResult;
}

export function TargetMetricGauges({ evaluation }: TargetMetricGaugesProps) {
  const {
    status,
    budgetLeftINR,
    overBudgetINR,
    usedKWh,
    daysLeft,
    percentUsed,
    targetINR,
  } = evaluation;

  // Determine color theme based on status
  let strokeColor = '#16A34A'; // green
  let trackColor = '#DCFCE7';
  let isOver = false;

  if (status === 'ON_TRACK') {
    strokeColor = '#D97706'; // amber
    trackColor = '#FEF3C7';
  } else if (status === 'EXCEEDED_TARGET') {
    strokeColor = '#DC2626'; // red
    trackColor = '#FEE2E2';
    isOver = true;
  }

  // Radius and circumference for circular arc
  const radius = 34;
  const circumference = 2 * Math.PI * radius; // ~213.63

  // Budget Arc: percent of budget used
  const budgetRatio = Math.min(1, Math.max(0, percentUsed / 100));
  const budgetDashoffset = circumference * (1 - budgetRatio);

  // kWh Arc: ratio of used kWh to target-equivalent kWh at the configured tariff
  const targetKWhEquivalent = targetINR > 0 ? targetINR / evaluation.tariffRateINR : 200;
  const kwhRatio = Math.min(1, Math.max(0, usedKWh / targetKWhEquivalent));
  const kwhDashoffset = circumference * (1 - kwhRatio);

  // Days Arc: days remaining out of 30 days
  const daysRatio = Math.min(1, Math.max(0, daysLeft / 30));
  const daysDashoffset = circumference * (1 - daysRatio);

  const isEstimated = evaluation.dataSource === 'ESTIMATED_INVENTORY';
  const isMetered = evaluation.dataSource === 'MEASURED_METER';
  const isCompleted = evaluation.isCycleCompleted;

  let budgetLabel = isOver ? 'over target' : 'budget left';
  if (isEstimated || isMetered) {
    budgetLabel = isOver ? 'over target (est.)' : 'budget left (est.)';
  }

  const kwhLabel = isEstimated ? 'estimated' : isMetered ? 'metered' : 'used';
  const daysLabel = isCompleted ? 'cycle closed' : 'days left';

  return (
    <div className="target-gauges" role="region" aria-label="Energy Target Key Metrics">
      {/* Gauge 1: Budget Left / Over Target */}
      <div className={`target-gauge-card target-gauge-card--${status.toLowerCase()}`}>
        <div className="target-gauge-card__circle-wrap">
          <svg className="target-gauge-card__svg" viewBox="0 0 88 88" aria-hidden="true">
            <circle
              className="target-gauge-card__track"
              cx="44"
              cy="44"
              r={radius}
              stroke={trackColor}
              strokeWidth="6"
              fill="none"
            />
            <circle
              className="target-gauge-card__indicator"
              cx="44"
              cy="44"
              r={radius}
              stroke={strokeColor}
              strokeWidth="6"
              strokeLinecap="round"
              fill="none"
              strokeDasharray={circumference}
              strokeDashoffset={budgetDashoffset}
              transform="rotate(-90 44 44)"
            />
          </svg>
          <div className="target-gauge-card__center-icon">
            {/* Wallet Icon */}
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke={strokeColor} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M20 7H4a2 2 0 0 0-2 2v10a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V9a2 2 0 0 0-2-2z" />
              <path d="M16 3H4a2 2 0 0 0-2 2v2" />
              <circle cx="16" cy="14" r="1.5" fill={strokeColor} />
            </svg>
          </div>
        </div>
        <div className="target-gauge-card__data">
          <span className="target-gauge-card__val font-serif">
            {isOver ? `₹${overBudgetINR.toLocaleString('en-IN')}` : `₹${budgetLeftINR.toLocaleString('en-IN')}`}
          </span>
          <span className="target-gauge-card__lbl">
            {budgetLabel}
          </span>
        </div>
      </div>

      {/* Gauge 2: Energy Used (kWh) */}
      <div className={`target-gauge-card target-gauge-card--${status.toLowerCase()}`}>
        <div className="target-gauge-card__circle-wrap">
          <svg className="target-gauge-card__svg" viewBox="0 0 88 88" aria-hidden="true">
            <circle
              className="target-gauge-card__track"
              cx="44"
              cy="44"
              r={radius}
              stroke={trackColor}
              strokeWidth="6"
              fill="none"
            />
            <circle
              className="target-gauge-card__indicator"
              cx="44"
              cy="44"
              r={radius}
              stroke={strokeColor}
              strokeWidth="6"
              strokeLinecap="round"
              fill="none"
              strokeDasharray={circumference}
              strokeDashoffset={kwhDashoffset}
              transform="rotate(-90 44 44)"
            />
          </svg>
          <div className="target-gauge-card__center-icon">
            {/* Leaf Icon */}
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke={strokeColor} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <path d="M11 20A7 7 0 0 1 9.8 6.1C15.5 5 17 3.3 17 3.3s-1.5 6.5-4.5 10.3A6.98 6.98 0 0 1 11 20z" />
              <path d="M2 21c0-4 3.5-7 7.5-7" />
            </svg>
          </div>
        </div>
        <div className="target-gauge-card__data">
          <span className="target-gauge-card__val font-serif">
            {usedKWh.toLocaleString('en-IN')} <span className="target-gauge-card__unit">kWh</span>
          </span>
          <span className="target-gauge-card__lbl">{kwhLabel}</span>
        </div>
      </div>

      {/* Gauge 3: Days Remaining */}
      <div className={`target-gauge-card target-gauge-card--${status.toLowerCase()}`}>
        <div className="target-gauge-card__circle-wrap">
          <svg className="target-gauge-card__svg" viewBox="0 0 88 88" aria-hidden="true">
            <circle
              className="target-gauge-card__track"
              cx="44"
              cy="44"
              r={radius}
              stroke={trackColor}
              strokeWidth="6"
              fill="none"
            />
            <circle
              className="target-gauge-card__indicator"
              cx="44"
              cy="44"
              r={radius}
              stroke={strokeColor}
              strokeWidth="6"
              strokeLinecap="round"
              fill="none"
              strokeDasharray={circumference}
              strokeDashoffset={daysDashoffset}
              transform="rotate(-90 44 44)"
            />
          </svg>
          <div className="target-gauge-card__center-icon">
            {/* Calendar Icon */}
            <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke={strokeColor} strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="4" width="18" height="18" rx="3" ry="3" />
              <line x1="16" y1="2" x2="16" y2="6" />
              <line x1="8" y1="2" x2="8" y2="6" />
              <line x1="3" y1="10" x2="21" y2="10" />
            </svg>
          </div>
        </div>
        <div className="target-gauge-card__data">
          <span className="target-gauge-card__val font-serif">
            {isCompleted ? '0' : daysLeft} <span className="target-gauge-card__unit">{isCompleted ? '' : 'days'}</span>
          </span>
          <span className="target-gauge-card__lbl">{daysLabel}</span>
        </div>
      </div>
    </div>
  );

}
