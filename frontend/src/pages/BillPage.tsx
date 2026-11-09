import { useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useBill } from '../hooks/useBill';
import { useInventory } from '../hooks/useInventory';
import { PageHero } from '../components/art/PageHero';
import { ArrowIcon, CalendarIcon, ChevronDown, CloseIcon, PlusIcon, SearchIcon, TrashIcon, UploadIcon, UserIcon } from '../components/ui/icons';
import { RouteToast } from '../components/ui/RouteToast';
import { ProjectedBillCard } from '../components/bill/ProjectedBillCard';
import { calculateHouseholdDailyKWh, compareBillWithHousehold, formatCurrencyINR } from '../utils/billMath';
import './BillPage.css';

const PROVIDERS = ['BESCOM', 'Tata Power', 'Adani', 'MSEDCL', 'Other'];
const LOCATIONS = [
  { id: 'my_home', label: 'My home' },
  { id: 'parents_home', label: 'Parents’ home' },
  { id: 'office', label: 'Office' },
];
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

function formatDue(value: string): string {
  const d = /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T00:00:00`) : null;
  return d && !Number.isNaN(d.getTime()) ? d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }) : value;
}

/** Electricity bill: latest bill, optional document, manual entry, history. */
export function BillPage() {
  const navigate = useNavigate();
  const { bills, latestBill, addBill, deleteBill, selectedLocation, setSelectedLocation } = useBill();
  const { inventory } = useInventory();
  const fileRef = useRef<HTMLInputElement>(null);

  const now = useMemo(() => new Date(), []);
  const lastMonth = new Date(now.getFullYear(), now.getMonth() - 1, 1);

  const [provider, setProvider] = useState('BESCOM');
  const [accountId, setAccountId] = useState('');
  const [location, setLocation] = useState(selectedLocation || 'my_home');
  const [customLocation, setCustomLocation] = useState<string | null>(null);
  const [month, setMonth] = useState(lastMonth.getMonth() + 1);
  const [year, setYear] = useState(lastMonth.getFullYear());
  const [units, setUnits] = useState('');
  const [amount, setAmount] = useState('');
  const [dueDate, setDueDate] = useState('');
  const [fileName, setFileName] = useState<string | null>(null);
  const [errors, setErrors] = useState<{ units?: string; amount?: string; general?: string }>({});

  const years = Array.from({ length: 5 }, (_, i) => now.getFullYear() - i);

  const comparison = useMemo(
    () =>
      latestBill && inventory.length > 0
        ? compareBillWithHousehold(latestBill, calculateHouseholdDailyKWh(inventory), inventory.length)
        : null,
    [latestBill, inventory]
  );

  const pickLocation = (id: string) => {
    setLocation(id);
    setSelectedLocation(id);
    setCustomLocation(null);
  };

  const submit = (e: React.FormEvent) => {
    e.preventDefault();

    // Nothing entered: treat as "continue" through the setup flow.
    if (!units.trim() && !amount.trim()) {
      navigate('/target');
      return;
    }

    const next: typeof errors = {};
    const u = Number(units);
    const a = Number(amount);
    if (!units.trim() || !Number.isFinite(u)) next.units = 'Enter the units in kWh.';
    else if (u <= 0) next.units = 'Must be more than 0 kWh.';
    else if (u > 1_000_000) next.units = 'That looks too large.';
    if (!amount.trim() || !Number.isFinite(a)) next.amount = 'Enter the bill amount in ₹.';
    else if (a <= 0) next.amount = 'Must be more than ₹0.';
    else if (a > 10_000_000) next.amount = 'That looks too large.';
    if (year > now.getFullYear() || (year === now.getFullYear() && month > now.getMonth() + 1)) {
      next.general = 'The billing period cannot be in the future.';
    }
    if (Object.keys(next).length) return setErrors(next);
    setErrors({});

    const period = `${MONTHS[month - 1]} ${year}`;
    const saved = addBill({
      utilityProvider: provider,
      accountId: accountId.trim() || undefined,
      billingMonth: month,
      billingYear: year,
      billingPeriod: period,
      unitsConsumed: u,
      billAmount: a,
      dueDate: dueDate || undefined,
      locationTag: location,
      documentFilename: fileName || undefined,
    });
    if (!saved) return setErrors({ general: 'Could not save the bill. Check the values.' });
    navigate('/target', { state: { toast: `Bill for ${period} saved` } });
  };

  return (
    <div className="page">
      <RouteToast />
      <PageHero art="bill" title={<>Your electricity<br />bill</>} subtitle="Bring your bill into SHEM to track usage and costs." />

      <ProjectedBillCard />

      <form className="sheet bill" onSubmit={submit} noValidate>
        <label className="bill__field">
          <span className="form__label">Utility provider</span>
          <span className="form__select-wrap">
            <select className="form__input" value={provider} onChange={(e) => setProvider(e.target.value)}>
              {PROVIDERS.map((p) => <option key={p}>{p}</option>)}
            </select>
            <ChevronDown className="form__chev" />
          </span>
        </label>

        <label className="bill__field">
          <span className="form__label">Account ID <i>(optional)</i></span>
          <span className="bill__search">
            <UserIcon size={18} />
            <input value={accountId} onChange={(e) => setAccountId(e.target.value)} placeholder="Enter account ID (optional)" maxLength={40} />
            <SearchIcon size={18} />
          </span>
        </label>

        <div className="bill__field">
          <span className="form__label">Save bill as</span>
          <div className="bill__chips">
            {LOCATIONS.map((l) => (
              <button key={l.id} type="button" className={`chip ${location === l.id ? 'chip--on' : ''}`} onClick={() => pickLocation(l.id)}>
                {l.label}
              </button>
            ))}
            {location && !LOCATIONS.some((l) => l.id === location) && (
              <button type="button" className="chip chip--on">{location}</button>
            )}
            {customLocation === null ? (
              <button type="button" className="chip" onClick={() => setCustomLocation('')}><PlusIcon size={14} /> Add</button>
            ) : (
              <input
                className="form__input bill__custom"
                autoFocus
                value={customLocation}
                placeholder="Name"
                onChange={(e) => setCustomLocation(e.target.value)}
                onBlur={() => (customLocation.trim() ? pickLocation(customLocation.trim()) : setCustomLocation(null))}
                onKeyDown={(e) => { if (e.key === 'Enter') { e.preventDefault(); e.currentTarget.blur(); } }}
              />
            )}
          </div>
        </div>

        {latestBill && (
          <div className="latest-bill" aria-label="Latest bill">
            <div className="latest-bill__main">
              <span className="latest-bill__label">Latest bill</span>
              <b className="latest-bill__amount">{formatCurrencyINR(latestBill.billAmount)}</b>
              <span className="latest-bill__period">{latestBill.billingPeriod}</span>
            </div>
            <div className="latest-bill__side">
              {latestBill.dueDate && <span className="latest-bill__pill"><CalendarIcon size={16} /> Due {formatDue(latestBill.dueDate)}</span>}
              <span className="latest-bill__pill latest-bill__pill--kwh">{latestBill.unitsConsumed} kWh</span>
            </div>
          </div>
        )}

        <div className="bill__upload">
          <span className="bill__upload-icon"><UploadIcon size={26} /></span>
          <span className="bill__upload-text">
            <b>Add bill document <i>(optional)</i></b>
            <span>{fileName ?? 'PDF, JPG or PNG'}</span>
          </span>
          {fileName ? (
            <button type="button" className="icon-btn" aria-label="Remove document" onClick={() => { setFileName(null); if (fileRef.current) fileRef.current.value = ''; }}>
              <CloseIcon size={18} />
            </button>
          ) : (
            <button type="button" className="btn btn--primary btn--small" onClick={() => fileRef.current?.click()}>
              <UploadIcon size={16} /> Upload
            </button>
          )}
          <input ref={fileRef} type="file" accept=".pdf,.jpg,.jpeg,.png" hidden onChange={(e) => setFileName(e.target.files?.[0]?.name ?? null)} />
        </div>
        {fileName && <p className="bill__note">Only the file name is saved. SHEM doesn’t upload or read the document.</p>}

        <div className="bill__divider"><span>or enter details manually</span></div>

        <div className="bill__grid">
          <div className="bill__field bill__field--wide">
            <span className="form__label">Billing period</span>
            <div className="bill__period">
              <span className="form__select-wrap">
                <select className="form__input" value={month} onChange={(e) => setMonth(Number(e.target.value))} aria-label="Billing month">
                  {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
                </select>
                <ChevronDown className="form__chev" />
              </span>
              <span className="form__select-wrap">
                <select className="form__input" value={year} onChange={(e) => setYear(Number(e.target.value))} aria-label="Billing year">
                  {years.map((y) => <option key={y}>{y}</option>)}
                </select>
                <ChevronDown className="form__chev" />
              </span>
            </div>
          </div>
          <label className="bill__field">
            <span className="form__label">Units consumed (kWh)</span>
            <input className={`form__input ${errors.units ? 'is-bad' : ''}`} inputMode="decimal" value={units} onChange={(e) => setUnits(e.target.value)} placeholder="e.g. 280" />
            {errors.units && <span className="form__error">{errors.units}</span>}
          </label>
          <label className="bill__field">
            <span className="form__label">Bill amount (₹)</span>
            <input className={`form__input ${errors.amount ? 'is-bad' : ''}`} inputMode="decimal" value={amount} onChange={(e) => setAmount(e.target.value)} placeholder="e.g. 2,100" />
            {errors.amount && <span className="form__error">{errors.amount}</span>}
          </label>
          <label className="bill__field bill__field--wide">
            <span className="form__label">Due date <i>(optional)</i></span>
            <input className="form__input" type="date" value={dueDate} onChange={(e) => setDueDate(e.target.value)} />
          </label>
        </div>
        {errors.general && <p className="form__error" role="alert">{errors.general}</p>}

        <div className="btn-row">
          <button type="button" className="btn btn--soft" onClick={() => navigate('/target')}>Skip for now</button>
          <button type="submit" className="btn btn--primary" id="btn-save-bill">
            {units.trim() || amount.trim() ? 'Save bill' : 'Continue'}
            <span className="btn__arrow"><ArrowIcon /></span>
          </button>
        </div>
      </form>

      {comparison?.isComparisonValid && comparison.estimatedKWh !== null && latestBill && (
        <section className="card" aria-label="Compared with your appliances">
          <div className="card__head"><h2 className="card__title">Bill vs your appliances</h2></div>
          <div className="compare">
            <div><b>{latestBill.unitsConsumed} kWh</b><span>On your bill</span></div>
            <div><b>{comparison.estimatedKWh} kWh</b><span>Estimated from appliances</span></div>
            {comparison.variancePercent !== null && (
              <div><b className={comparison.variancePercent > 0 ? 'is-up' : 'is-down'}>{comparison.variancePercent > 0 ? '+' : ''}{comparison.variancePercent}%</b><span>Difference</span></div>
            )}
          </div>
          <p className="bill__note">{comparison.statusExplanation}</p>
        </section>
      )}

      {bills.length > 0 && (
        <section className="card" aria-label="Bill history">
          <div className="card__head"><h2 className="card__title">Bill history</h2></div>
          <div className="list">
            {bills.map((b) => (
              <div key={b.id} className="row row--plain bill-hist">
                <span className="row__body">
                  <span className="row__title">{b.billingPeriod}</span>
                  <span className="row__sub">{b.utilityProvider} · {b.unitsConsumed} kWh</span>
                </span>
                <b className="bill-hist__amt">{formatCurrencyINR(b.billAmount)}</b>
                <button type="button" className="icon-btn" aria-label={`Delete bill for ${b.billingPeriod}`} onClick={() => deleteBill(b.id)}>
                  <TrashIcon />
                </button>
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
