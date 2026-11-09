import { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTarget } from '../hooks/useTarget';
import { useBill } from '../hooks/useBill';
import { useInventory } from '../hooks/useInventory';
import { useHomeConfig } from '../hooks/useHomeConfig';
import { useApiQuery } from '../hooks/useApiQuery';
import { fetchBillProjection } from '../api/billingApi';
import { BudgetSaverCard } from '../components/target/BudgetSaverCard';
import { TARGET_CONSTRAINTS } from '../context/targetContextDef';
import { evaluateTarget } from '../utils/targetEvaluation';
import { PageHero } from '../components/art/PageHero';
import { BarChart, ChartLegend, Ring } from '../components/ui/charts';
import { ArrowIcon, BoltIcon, CalendarIcon, ChevronRight, EditIcon, FileIcon, UploadIcon, WalletIcon } from '../components/ui/icons';
import { RouteToast } from '../components/ui/RouteToast';
import './TargetPage.css';

const TONE_COLOR = { green: '#1FA971', amber: '#E9A33A', red: '#E5484D', blue: '#3B6FE0', gray: '#3B6FE0' } as const;

function cyclePeriodLabel(start: string, endExclusive: string): string {
  const s = new Date(`${start}T12:00:00`);
  const e = new Date(`${endExclusive}T12:00:00`);
  e.setDate(e.getDate() - 1);
  const f = (d: Date) => d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
  return `${f(s)} – ${f(e)}`;
}

/** Energy target: set a monthly goal, then see how the current billing cycle is going against it. */
export function TargetPage() {
  const navigate = useNavigate();
  const { target, saveTarget, validateAmount } = useTarget();
  const { homeBills: bills, latestBill } = useBill();
  const { inventory } = useInventory();
  const { config } = useHomeConfig();
  const { data: cycle } = useApiQuery(fetchBillProjection, 'target-cycle', 120_000);

  const [periodId, setPeriodId] = useState('current');
  // Progress is measured over the current BILLING CYCLE (meter-reading day), priced with the tariff model.
  const measured = cycle
    ? {
        kwh: cycle.usedKWh,
        hasData: cycle.usedKWh > 0,
        dataNote: cycle.confidence === 'low' ? 'Early in the cycle, so the projection is rough.' : null,
        costINR: cycle.soFar.totalINR,
        projectedINR: cycle.projected.totalINR,
        daysLeft: Math.max(0, Math.ceil(cycle.daysLeft)),
        periodLabel: cyclePeriodLabel(cycle.cycleStart, cycle.cycleEnd),
        includesSimulated: cycle.simulatedKWh > 0,
      }
    : null;
  const ev = evaluateTarget(target, bills, latestBill, inventory, periodId, measured, config.tariffRateINR);

  const [editing, setEditing] = useState(!target.isConfigured);
  const showForm = !target.isConfigured || editing;

  const startAmount = target.isConfigured && target.monthlyBudgetINR > 0 ? target.monthlyBudgetINR : TARGET_CONSTRAINTS.DEFAULT_SUGGESTED_INR;
  const [amount, setAmount] = useState(String(startAmount));
  const [kind, setKind] = useState<'budget' | 'reduction'>(target.targetType || 'budget');
  const [typing, setTyping] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);

  const numeric = Number(amount) || 0;
  const slider = Math.min(TARGET_CONSTRAINTS.SLIDER_MAX_INR, Math.max(TARGET_CONSTRAINTS.SLIDER_MIN_INR, numeric));

  const suggest = () => {
    let s: number = TARGET_CONSTRAINTS.DEFAULT_SUGGESTED_INR;
    if (ev.dataSource === 'ESTIMATED_INVENTORY' && ev.currentCostINR > 0) s = Math.round((ev.currentCostINR * 1.15) / 50) * 50;
    s = Math.max(TARGET_CONSTRAINTS.MIN_AMOUNT_INR, Math.min(TARGET_CONSTRAINTS.MAX_AMOUNT_INR, s));
    setAmount(String(s));
    setError(null);
    setHint(`Suggested ₹${s.toLocaleString('en-IN')} a month based on your home.`);
  };

  const save = () => {
    const v = validateAmount(numeric);
    if (!v.valid) return setError(v.error || 'Enter a valid target amount.');
    if (!saveTarget(numeric, kind)) return setError('Could not save the target.');
    setError(null);
    setHint(null);
    setEditing(false);
    navigate('/target', { replace: true, state: { toast: `Target of ₹${numeric.toLocaleString('en-IN')} saved` } });
  };

  /* ---------------- Set target ---------------- */
  if (showForm) {
    return (
      <div className="page">
        <RouteToast />
        <PageHero art="story" title={<>Set your<br />energy target</>} subtitle="Choose a goal that feels right for your home." />

        <div className="sheet target-form">
          <div className="seg seg--full" role="tablist" aria-label="Target type">
            <button type="button" role="tab" aria-selected={kind === 'budget'} className={`seg__btn ${kind === 'budget' ? 'seg__btn--on' : ''}`} onClick={() => setKind('budget')}>
              <WalletIcon size={16} /> Monthly bill
            </button>
            <button type="button" role="tab" aria-selected={kind === 'reduction'} className={`seg__btn ${kind === 'reduction' ? 'seg__btn--on' : ''}`} onClick={() => setKind('reduction')}>
              Reduce usage
            </button>
          </div>

          <div>
            <h2 className="card__title">Your monthly bill target</h2>
            <p className="sheet__hint">Set a target amount for your monthly electricity bill.</p>
          </div>

          <div className="amount-box">
            <span className="amount-box__cur">₹</span>
            {typing ? (
              <input
                className="amount-box__input"
                type="number"
                inputMode="numeric"
                autoFocus
                value={amount}
                min={TARGET_CONSTRAINTS.MIN_AMOUNT_INR}
                max={TARGET_CONSTRAINTS.MAX_AMOUNT_INR}
                onChange={(e) => { setAmount(e.target.value); setError(null); }}
                onBlur={() => setTyping(false)}
                aria-label="Monthly target in rupees"
              />
            ) : (
              <button type="button" className="amount-box__value" onClick={() => setTyping(true)}>{numeric.toLocaleString('en-IN')}</button>
            )}
            <button type="button" className="icon-btn" aria-label="Edit amount" onClick={() => setTyping((t) => !t)}><EditIcon size={18} /></button>
          </div>

          <div className="slider">
            <input
              type="range"
              min={TARGET_CONSTRAINTS.SLIDER_MIN_INR}
              max={TARGET_CONSTRAINTS.SLIDER_MAX_INR}
              step={TARGET_CONSTRAINTS.SLIDER_STEP_INR}
              value={slider}
              onChange={(e) => { setAmount(e.target.value); setError(null); }}
              aria-label="Adjust monthly target"
              style={{ ['--fill' as string]: `${((slider - TARGET_CONSTRAINTS.SLIDER_MIN_INR) / (TARGET_CONSTRAINTS.SLIDER_MAX_INR - TARGET_CONSTRAINTS.SLIDER_MIN_INR)) * 100}%` }}
            />
            <div className="slider__ticks" aria-hidden="true">
              {['₹1,000', '₹1,500', '₹2,000', '₹2,500', '₹3,000'].map((t) => <span key={t}>{t}</span>)}
            </div>
          </div>
          {error && <p className="form__error" role="alert">{error}</p>}
          {hint && <p className="sheet__hint">{hint}</p>}
        </div>

        <button type="button" className="row row--card" onClick={() => navigate('/bill')}>
          <span className="row__icon"><FileIcon size={28} /></span>
          <span className="row__body">
            <span className="row__title">Add a recent bill (optional)</span>
            <span className="row__sub">Upload a bill to personalise our suggestions.</span>
          </span>
          <span className="btn btn--soft btn--small"><UploadIcon size={16} /> Upload</span>
        </button>

        <button type="button" className="row row--card" onClick={suggest}>
          <span className="row__icon"><BoltIcon size={26} /></span>
          <span className="row__body">
            <span className="row__title">Not sure what to set?</span>
            <span className="row__sub">We can suggest a target based on your home.</span>
          </span>
          <span className="row__end"><ChevronRight /></span>
        </button>

        <button type="button" className="btn btn--primary" id="btn-save-target" onClick={save}>
          Save my target <span className="btn__arrow"><ArrowIcon /></span>
        </button>
        {target.isConfigured && <button type="button" className="btn-link" onClick={() => setEditing(false)}>Cancel</button>}
      </div>
    );
  }

  /* ---------------- Status ---------------- */
  const tone = ev.statusColor;
  const color = TONE_COLOR[tone];
  const over = ev.status === 'EXCEEDED_TARGET';
  const targetKWh = ev.targetINR > 0 ? ev.targetINR / ev.tariffRateINR : 0;
  const trend = ev.trendPoints.map((p) => ({ label: p.label, value: p.amountINR, strong: p.isCurrent }));

  const insightTitle =
    ev.status === 'WITHIN_TARGET' ? 'Nice work — keep your current habits.'
    : ev.status === 'ON_TRACK' ? 'A few small changes can help you save more.'
    : over ? 'Let’s bring it back on track.'
    : 'Start tracking your electricity spend.';

  return (
    <div className={`page tone--${tone}`}>
      <RouteToast />
      <PageHero art="cottage" layout="split" title={ev.headline} subtitle={ev.subtitle} />

      {bills.length > 0 && (
        <label className="period-pick">
          <span>Period</span>
          <select value={periodId} onChange={(e) => setPeriodId(e.target.value)}>
            <option value="current">This month</option>
            {bills.map((b) => <option key={b.id} value={b.id}>{b.billingPeriod}</option>)}
          </select>
        </label>
      )}

      <section className="card ring-card" aria-label="Target progress">
        <div className="ring-row">
          <Ring
            fraction={ev.percentUsed / 100}
            color={color}
            icon={<WalletIcon size={18} />}
            value={`₹${Math.round(over ? ev.overBudgetINR : ev.budgetLeftINR).toLocaleString('en-IN')}`}
            caption={over ? 'over target' : 'budget left'}
          />
          <Ring
            fraction={targetKWh > 0 ? ev.usedKWh / targetKWh : 0}
            color={color}
            icon={<BoltIcon size={18} />}
            value={`${ev.usedKWh.toFixed(ev.usedKWh < 10 ? 1 : 0)} kWh`}
            caption="used"
          />
          <Ring
            fraction={ev.daysLeft / 30}
            color={color}
            icon={<CalendarIcon size={18} />}
            value={`${ev.daysLeft}`}
            caption={ev.isCycleCompleted ? 'cycle closed' : 'days left'}
          />
        </div>
        <p className="source-note">{ev.dataSourceLabel}{ev.rateDisclosure ? ` · ${ev.rateDisclosure}` : ''}</p>
      </section>

      <section className="card" aria-label="Energy trend">
        <div className="card__head"><h2 className="card__title">Spend trend</h2></div>
        {trend.length > 0 ? (
          <>
            <BarChart data={trend} target={ev.targetINR} color={color} unit="₹" />
            <ChartLegend items={[{ label: 'Your spend', color }, { label: 'Your target', color, dashed: true }]} />
          </>
        ) : (
          <div className="empty"><span><strong>No history yet.</strong>Add a bill to see how your spending compares with your target.</span></div>
        )}
      </section>

      <BudgetSaverCard />

      <button type="button" className="note-card" onClick={() => navigate(ev.dataSource === 'NONE' ? '/devices' : '/bill')}>
        <span className="note-card__icon"><BoltIcon size={26} /></span>
        <span className="note-card__text"><b>{insightTitle}</b><span>{ev.guidanceText}</span></span>
        <ChevronRight />
      </button>

      <button type="button" className="btn btn--primary" onClick={() => navigate('/insights')}>
        View insights <span className="btn__arrow"><ArrowIcon /></span>
      </button>
      <button type="button" className="btn-link" onClick={() => setEditing(true)} id="btn-edit-target">
        <EditIcon /> Change target (₹{ev.targetINR.toLocaleString('en-IN')})
      </button>
    </div>
  );
}
