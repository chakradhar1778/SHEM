import { useState } from 'react';
import { Link } from 'react-router-dom';
import { errorMessage } from '../../api/backendApi';
import { fetchBudgetSaver, updateBudgetSaver } from '../../api/alertsApi';
import type { BudgetSaverSettings } from '../../api/types';
import { useApiQuery } from '../../hooks/useApiQuery';
import { ApplianceIcon } from '../appliances/ApplianceIcons';
import { SourceTag } from '../appliances/SourceTag';
import './BudgetSaverCard.css';

const MODES: { id: BudgetSaverSettings['mode']; label: string; hint: string }[] = [
  { id: 'off', label: 'Off', hint: 'SHEM never switches anything for your budget.' },
  { id: 'suggest', label: 'Suggest', hint: 'You get a notification listing non-essential appliances that are on.' },
  { id: 'auto', label: 'Automatic', hint: 'SHEM switches non-essential appliances off, at most once a day each, and tells you.' },
];

const ACTION_TEXT = { switched_off: 'Switched off', suggested: 'Suggested', skipped: 'Skipped', failed: 'Failed' } as const;

/** Opt-in budget saver: suggest or switch off appliances marked non-essential when the budget is at risk. */
export function BudgetSaverCard() {
  const { data, refresh } = useApiQuery(fetchBudgetSaver, 'budget-saver', 60_000);
  const [local, setLocal] = useState<BudgetSaverSettings | null>(null);
  const [error, setError] = useState<string | null>(null);
  const s = local ?? data;
  if (!s) return null;

  const save = async (patch: Partial<Pick<BudgetSaverSettings, 'mode' | 'trigger'>>) => {
    setError(null);
    setLocal({ ...s, ...patch });
    try {
      setLocal(await updateBudgetSaver(patch));
      refresh();
    } catch (e) {
      setLocal(null);
      setError(errorMessage(e));
    }
  };

  const hint = MODES.find((m) => m.id === s.mode)?.hint;

  return (
    <section className="card saver" aria-label="Budget saver">
      <div className="card__head">
        <h2 className="card__title">Budget saver</h2>
        <span className={`saver__state is-${s.mode}`}>{s.mode === 'off' ? 'Off' : s.mode === 'suggest' ? 'Suggesting' : 'Automatic'}</span>
      </div>
      <p className="sheet__hint">When this cycle’s bill heads over your budget, act on appliances you marked <b>Essential: No</b>.</p>

      <div className="seg seg--full" role="radiogroup" aria-label="Budget saver mode">
        {MODES.map((m) => (
          <button key={m.id} type="button" role="radio" aria-checked={s.mode === m.id} className={`seg__btn ${s.mode === m.id ? 'seg__btn--on' : ''}`} onClick={() => void save({ mode: m.id })}>
            {m.label}
          </button>
        ))}
      </div>
      <p className="saver__hint">{hint}</p>

      {s.mode !== 'off' && (
        <label className="saver__trigger">
          Act when
          <select className="form__input" value={s.trigger} onChange={(e) => void save({ trigger: e.target.value as BudgetSaverSettings['trigger'] })}>
            <option value="at_risk">the projected bill is above budget</option>
            <option value="over">the bill so far is above budget</option>
          </select>
        </label>
      )}
      {!s.budgetConfigured && s.mode !== 'off' && <p className="form__error">Set a monthly budget above for the saver to work.</p>}
      {error && <p className="form__error" role="alert">{error}</p>}

      <div className="saver__apps">
        <span className="saver__label">Non-essential appliances</span>
        {s.candidates.length === 0 ? (
          <p className="sheet__hint">
            None yet. Mark appliances as <b>Essential: No</b> in <Link to="/devices" className="inline-link">Devices</Link> to let the saver use them.
          </p>
        ) : (
          <ul>
            {s.candidates.map((c) => (
              <li key={c.applianceId}>
                <ApplianceIcon type={c.iconType ?? 'bulb'} size={22} />
                <span>{c.name}</span>
                <SourceTag source={c.simulated ? 'simulated' : 'metered'} compact />
                <i className={c.isOn ? 'is-on' : ''}>{c.isOn ? 'On' : 'Off'}</i>
              </li>
            ))}
          </ul>
        )}
      </div>

      {s.log.length > 0 && (
        <details className="saver__log">
          <summary>Recent actions ({s.log.length})</summary>
          <ul>
            {s.log.map((e) => (
              <li key={e.id}>
                <b className={`is-${e.action}`}>{ACTION_TEXT[e.action]}</b>
                <span>{e.reason}</span>
                <i>{new Date(e.createdAt).toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: 'numeric', minute: '2-digit' })}</i>
              </li>
            ))}
          </ul>
        </details>
      )}
    </section>
  );
}
