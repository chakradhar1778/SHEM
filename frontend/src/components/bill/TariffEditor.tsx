import { useCallback, useEffect, useState } from 'react';
import { DATA_CHANGED_EVENT, emitWindowEvent, errorMessage } from '../../api/backendApi';
import { estimateBill, fetchTariff, updateTariff } from '../../api/billingApi';
import type { BillBreakdown, Tariff } from '../../api/types';
import { useHomeConfig } from '../../hooks/useHomeConfig';
import { PlusIcon, TrashIcon } from '../ui/icons';
import './TariffEditor.css';

interface SlabRow { upto: string; rate: string }

const DEFAULT_SLABS: SlabRow[] = [
  { upto: '100', rate: '' },
  { upto: '200', rate: '' },
  { upto: '', rate: '' },
];

const num = (v: string) => (v.trim() === '' ? NaN : Number(v));

/** Tariff settings copied from the user's own bill: flat or slabs, fixed charge, fuel adjustment, duty, cycle day. */
export function TariffEditor() {
  const { refresh: refreshHome } = useHomeConfig();
  const [saved, setSaved] = useState<Tariff | null>(null);
  const [mode, setMode] = useState<'flat' | 'slab'>('flat');
  const [flat, setFlat] = useState('7.5');
  const [slabs, setSlabs] = useState<SlabRow[]>(DEFAULT_SLABS);
  const [fixed, setFixed] = useState('0');
  const [fuel, setFuel] = useState('0');
  const [duty, setDuty] = useState('0');
  const [cycleDay, setCycleDay] = useState('1');
  const [error, setError] = useState<string | null>(null);
  const [status, setStatus] = useState<'idle' | 'saving' | 'saved'>('idle');
  const [sampleKWh, setSampleKWh] = useState('150');
  const [sample, setSample] = useState<BillBreakdown | null>(null);

  const load = useCallback((t: Tariff) => {
    setSaved(t);
    setMode(t.mode);
    setFlat(String(t.flatRateINR));
    setSlabs(t.slabs.length ? t.slabs.map((s) => ({ upto: s.uptoKWh == null ? '' : String(s.uptoKWh), rate: String(s.rateINR) })) : DEFAULT_SLABS);
    setFixed(String(t.fixedChargeINR));
    setFuel(String(t.fuelAdjustmentINRPerKWh));
    setDuty(String(t.electricityDutyPercent));
    setCycleDay(String(t.billingCycleDay));
  }, []);

  useEffect(() => {
    fetchTariff().then(load).catch((e) => setError(errorMessage(e)));
  }, [load]);

  // Preview uses the SAVED tariff, so it always matches what every screen shows.
  useEffect(() => {
    const k = Number(sampleKWh);
    if (!saved || !Number.isFinite(k) || k < 0) return;
    const timer = window.setTimeout(() => {
      estimateBill(k).then(setSample).catch(() => setSample(null));
    }, 300);
    return () => window.clearTimeout(timer);
  }, [sampleKWh, saved]);

  const validate = (): string | null => {
    const f = num(flat);
    if (mode === 'flat' && !(f > 0 && f <= 100)) return 'Enter a rate between ₹0.1 and ₹100 per kWh.';
    if (mode === 'slab') {
      let prev = 0;
      for (let i = 0; i < slabs.length; i += 1) {
        const last = i === slabs.length - 1;
        const r = num(slabs[i].rate);
        if (!(r >= 0 && r <= 100)) return `Slab ${i + 1}: enter a rate in ₹ per kWh.`;
        if (!last) {
          const u = num(slabs[i].upto);
          if (!(u > prev)) return `Slab ${i + 1}: the upper limit must be more than ${prev} kWh.`;
          prev = u;
        }
      }
    }
    if (!(num(fixed) >= 0)) return 'Fixed charge must be ₹0 or more.';
    if (!(num(fuel) >= 0 && num(fuel) <= 20)) return 'Fuel adjustment must be between ₹0 and ₹20 per kWh.';
    if (!(num(duty) >= 0 && num(duty) <= 50)) return 'Duty must be between 0% and 50%.';
    const d = num(cycleDay);
    if (!(Number.isInteger(d) && d >= 1 && d <= 28)) return 'Billing cycle day must be 1–28.';
    return null;
  };

  const save = async () => {
    const err = validate();
    if (err) return setError(err);
    setError(null);
    setStatus('saving');
    try {
      const body = {
        flatRateINR: num(flat) > 0 ? num(flat) : undefined,
        fixedChargeINR: num(fixed),
        fuelAdjustmentINRPerKWh: num(fuel),
        electricityDutyPercent: num(duty),
        billingCycleDay: num(cycleDay),
        ...(mode === 'slab'
          ? { slabs: slabs.map((s, i) => ({ uptoKWh: i === slabs.length - 1 ? null : num(s.upto), rateINR: num(s.rate) })) }
          : {}),
        mode,
      };
      load(await updateTariff(body));
      void refreshHome();
      emitWindowEvent(DATA_CHANGED_EVENT, { tool: 'ui', summary: 'Tariff updated', entityType: 'household', entityId: '1' });
      setStatus('saved');
      window.setTimeout(() => setStatus('idle'), 2000);
    } catch (e) {
      setError(errorMessage(e));
      setStatus('idle');
    }
  };

  const setSlab = (i: number, key: keyof SlabRow, value: string) =>
    setSlabs((rows) => rows.map((r, j) => (j === i ? { ...r, [key]: value } : r)));
  const addSlab = () =>
    setSlabs((rows) => {
      const prevLimit = rows.length > 1 ? num(rows[rows.length - 2].upto) : 0;
      const next = [...rows];
      next.splice(rows.length - 1, 0, { upto: String((Number.isFinite(prevLimit) ? prevLimit : 0) + 100), rate: '' });
      return next;
    });
  const removeSlab = (i: number) => setSlabs((rows) => (rows.length <= 2 ? rows : rows.filter((_, j) => j !== i)));

  const lowerOf = (i: number) => (i === 0 ? 0 : num(slabs[i - 1].upto));

  return (
    <section className="settings__block tariff">
      <h2 className="card__title">Electricity tariff</h2>
      <p className="sheet__hint">Copy these from your bill. They price every cost in SHEM and the projected bill.</p>

      <div className="seg seg--full" role="tablist" aria-label="Tariff type">
        {(['flat', 'slab'] as const).map((m) => (
          <button key={m} type="button" role="tab" aria-selected={mode === m} className={`seg__btn ${mode === m ? 'seg__btn--on' : ''}`} onClick={() => setMode(m)}>
            {m === 'flat' ? 'Flat rate' : 'Slab rates'}
          </button>
        ))}
      </div>

      {mode === 'flat' ? (
        <label className="form__field">
          <span className="form__label">Rate (₹ per kWh)</span>
          <input className="form__input" type="number" inputMode="decimal" min="0.1" max="100" step="0.05" value={flat} onChange={(e) => setFlat(e.target.value)} />
        </label>
      ) : (
        <div className="tariff__slabs">
          <div className="tariff__slab tariff__slab--head"><span>Units in cycle</span><span>₹ / kWh</span><span /></div>
          {slabs.map((s, i) => {
            const last = i === slabs.length - 1;
            const lo = lowerOf(i);
            return (
              <div key={i} className="tariff__slab">
                <span className="tariff__range">
                  {Number.isFinite(lo) ? lo : '?'} –{' '}
                  {last ? (
                    <em>above</em>
                  ) : (
                    <input className="form__input tariff__num" type="number" inputMode="decimal" min="1" value={s.upto} onChange={(e) => setSlab(i, 'upto', e.target.value)} aria-label={`Slab ${i + 1} upper limit (kWh)`} />
                  )}
                </span>
                <input className="form__input tariff__num" type="number" inputMode="decimal" min="0" step="0.05" value={s.rate} onChange={(e) => setSlab(i, 'rate', e.target.value)} placeholder="₹" aria-label={`Slab ${i + 1} rate`} />
                {!last && slabs.length > 2 ? (
                  <button type="button" className="icon-btn" aria-label={`Remove slab ${i + 1}`} onClick={() => removeSlab(i)}><TrashIcon size={16} /></button>
                ) : <span />}
              </div>
            );
          })}
          <button type="button" className="btn-link tariff__add" onClick={addSlab}><PlusIcon size={14} /> Add slab</button>
        </div>
      )}

      <div className="tariff__grid">
        <label className="form__field">
          <span className="form__label">Fixed charge (₹ / bill)</span>
          <input className="form__input" type="number" inputMode="decimal" min="0" value={fixed} onChange={(e) => setFixed(e.target.value)} />
        </label>
        <label className="form__field">
          <span className="form__label">Fuel adj. (₹ / kWh)</span>
          <input className="form__input" type="number" inputMode="decimal" min="0" step="0.01" value={fuel} onChange={(e) => setFuel(e.target.value)} />
        </label>
        <label className="form__field">
          <span className="form__label">Electricity duty (%)</span>
          <input className="form__input" type="number" inputMode="decimal" min="0" max="50" step="0.5" value={duty} onChange={(e) => setDuty(e.target.value)} />
        </label>
        <label className="form__field">
          <span className="form__label">Meter reading day</span>
          <input className="form__input" type="number" inputMode="numeric" min="1" max="28" value={cycleDay} onChange={(e) => setCycleDay(e.target.value)} />
        </label>
      </div>
      <p className="sheet__hint">
        Meter reading day starts each billing cycle (e.g. 14 → the 14th to the 13th). Use 1 for calendar months. Duty applies to energy + fuel charges.
      </p>

      {error && <p className="form__error" role="alert">{error}</p>}
      <button type="button" className="btn btn--primary btn--small settings__btn" onClick={() => void save()} disabled={status === 'saving'}>
        {status === 'saved' ? '✓ Saved' : status === 'saving' ? 'Saving…' : 'Save tariff'}
      </button>

      {saved && (
        <div className="tariff__preview">
          <label className="tariff__preview-in">
            Bill for
            <input className="form__input tariff__num" type="number" inputMode="numeric" min="0" value={sampleKWh} onChange={(e) => setSampleKWh(e.target.value)} />
            kWh
          </label>
          {sample && (
            <div className="tariff__preview-out">
              <b>₹{sample.totalINR.toLocaleString('en-IN', { maximumFractionDigits: 0 })}</b>
              <span>
                energy ₹{Math.round(sample.energyChargeINR)} · fuel ₹{Math.round(sample.fuelChargeINR)} · duty ₹{Math.round(sample.dutyINR)} · fixed ₹{Math.round(sample.fixedChargeINR)}
                {sample.effectiveRateINR != null ? ` · ₹${sample.effectiveRateINR.toFixed(2)}/kWh overall` : ''}
              </span>
            </div>
          )}
          <span className="tariff__preview-note">Uses the saved tariff.</span>
        </div>
      )}
    </section>
  );
}
