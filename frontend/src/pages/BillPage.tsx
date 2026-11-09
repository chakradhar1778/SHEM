import { useMemo, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { useBill } from '../hooks/useBill';
import { PageHero } from '../components/art/PageHero';
import { ArrowIcon, CalendarIcon, ChevronDown, CloseIcon, FileIcon, PlusIcon, SearchIcon, TrashIcon, UploadIcon, UserIcon } from '../components/ui/icons';
import { RouteToast } from '../components/ui/RouteToast';
import { ProjectedBillCard } from '../components/bill/ProjectedBillCard';
import { BillCostSplit } from '../components/bill/BillCostSplit';
import { BillVsUsageCard } from '../components/bill/BillVsUsageCard';
import { BillDocumentViewer } from '../components/bill/BillDocumentViewer';
import { isHomeBill } from '../context/billContextDef';
import { BILL_DOCUMENT_MAX_MB, BILL_DOCUMENT_TYPES } from '../api/billsApi';
import { formatCurrencyINR } from '../utils/billMath';
import { fetchTariff } from '../api/billingApi';
import { useApiQuery } from '../hooks/useApiQuery';
import './BillPage.css';

const PROVIDERS = ['BESCOM', 'Tata Power', 'Adani', 'MSEDCL', 'Other'];
const LOCATIONS = [
  { id: 'my_home', label: 'My home' },
  { id: 'parents_home', label: 'Parents’ home' },
  { id: 'office', label: 'Office' },
];
const MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July', 'August', 'September', 'October', 'November', 'December'];

const pad = (n: number) => String(n).padStart(2, '0');
const isoDate = (d: Date) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;

/** The billing cycle that starts in month/year on the meter-reading day: [start, end] (end inclusive). */
function cycleFor(month: number, year: number, cycleDay: number): { start: string; end: string } {
  const start = new Date(year, month - 1, cycleDay);
  const end = new Date(year, month, cycleDay - 1);
  return { start: isoDate(start), end: isoDate(end) };
}

function ordinal(n: number): string {
  const s = n % 100 >= 11 && n % 100 <= 13 ? 'th' : ({ 1: 'st', 2: 'nd', 3: 'rd' } as Record<number, string>)[n % 10] ?? 'th';
  return `${n}${s}`;
}

function daysInclusive(start: string, end: string): number {
  return Math.round((new Date(`${end}T12:00:00`).getTime() - new Date(`${start}T12:00:00`).getTime()) / 86_400_000) + 1;
}

function formatDue(value: string): string {
  const d = /^\d{4}-\d{2}-\d{2}$/.test(value) ? new Date(`${value}T00:00:00`) : null;
  return d && !Number.isNaN(d.getTime()) ? d.toLocaleDateString('en-IN', { day: 'numeric', month: 'short' }) : value;
}

/** Electricity bill: latest bill, optional document, manual entry, history. */
export function BillPage() {
  const navigate = useNavigate();
  const { bills, latestBill, addBill, deleteBill, attachDocument, removeDocument, selectedLocation, setSelectedLocation } = useBill();
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
  const { data: tariff } = useApiQuery(fetchTariff, 'bill-form-tariff');
  const cycleDay = tariff?.billingCycleDay ?? 1;
  // Period dates follow the meter-reading day until the user edits them.
  const [periodOverride, setPeriodOverride] = useState<{ start: string; end: string } | null>(null);
  const period = periodOverride ?? cycleFor(month, year, cycleDay);
  const setPeriod = (key: 'start' | 'end', value: string) => setPeriodOverride({ ...period, [key]: value });
  const [file, setFile] = useState<File | null>(null);
  const [fileError, setFileError] = useState<string | null>(null);
  const fileName = file?.name ?? null;
  const [viewing, setViewing] = useState<string | null>(null);
  const [rowError, setRowError] = useState<{ id: string; message: string } | null>(null);
  const attachRef = useRef<HTMLInputElement>(null);
  const [attachFor, setAttachFor] = useState<string | null>(null);

  /** Client-side check (the server verifies the bytes again). */
  const checkFile = (f: File | undefined | null): string | null => {
    if (!f) return null;
    if (!BILL_DOCUMENT_TYPES.includes(f.type)) return 'Choose a JPG, PNG, WebP or PDF file.';
    if (f.size > BILL_DOCUMENT_MAX_MB * 1024 * 1024) return `That file is over ${BILL_DOCUMENT_MAX_MB} MB.`;
    return null;
  };

  const pickFile = (f: File | undefined) => {
    const err = checkFile(f);
    setFileError(err);
    setFile(err ? null : f ?? null);
    if (err && fileRef.current) fileRef.current.value = '';
  };

  const attachToExisting = async (f: File | undefined) => {
    const id = attachFor;
    if (attachRef.current) attachRef.current.value = '';
    setAttachFor(null);
    if (!id || !f) return;
    const err = checkFile(f) ?? (await attachDocument(id, f));
    setRowError(err ? { id, message: err } : null);
  };
  const [openBill, setOpenBill] = useState<string | null>(null);
  const [historyLoc, setHistoryLoc] = useState<string>('all');
  const locationsInUse = Array.from(new Set(bills.map((b) => b.locationTag || 'my_home')));
  const shownBills = historyLoc === 'all' ? bills : bills.filter((b) => (b.locationTag || 'my_home') === historyLoc);
  const locLabel = (id: string) => LOCATIONS.find((l) => l.id === id)?.label ?? id;
  const summary = (() => {
    if (historyLoc === 'all' || shownBills.length === 0) return null;
    const avg = shownBills.reduce((t, b) => t + b.billAmount, 0) / shownBills.length;
    const avgKWh = shownBills.reduce((t, b) => t + b.unitsConsumed, 0) / shownBills.length;
    return { count: shownBills.length, avg, avgKWh, latest: shownBills[0] };
  })();
  const [errors, setErrors] = useState<{ units?: string; amount?: string; general?: string }>({});

  const years = Array.from({ length: 5 }, (_, i) => now.getFullYear() - i);

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
    } else if (!period.start || !period.end || period.end < period.start) {
      next.general = 'The period end date must be on or after the start date.';
    } else if (daysInclusive(period.start, period.end) > 70) {
      next.general = 'A billing period longer than 70 days looks wrong. Check the dates.';
    }
    if (Object.keys(next).length) return setErrors(next);
    setErrors({});

    const periodLabel = `${MONTHS[month - 1]} ${year}`;
    const saved = addBill({
      utilityProvider: provider,
      accountId: accountId.trim() || undefined,
      billingMonth: month,
      billingYear: year,
      billingPeriod: periodLabel,
      billingPeriodStart: period.start,
      billingPeriodEnd: period.end,
      billingPeriodDays: daysInclusive(period.start, period.end),
      unitsConsumed: u,
      billAmount: a,
      dueDate: dueDate || undefined,
      locationTag: location,
      documentFilename: fileName || undefined,
    }, file);
    if (!saved) return setErrors({ general: 'Could not save the bill. Check the values.' });
    navigate('/target', { state: { toast: `Bill for ${periodLabel} saved` } });
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
            <span>{fileName ?? `PDF, JPG, PNG or WebP · up to ${BILL_DOCUMENT_MAX_MB} MB`}</span>
          </span>
          {fileName ? (
            <button type="button" className="icon-btn" aria-label="Remove document" onClick={() => { setFile(null); if (fileRef.current) fileRef.current.value = ''; }}>
              <CloseIcon size={18} />
            </button>
          ) : (
            <button type="button" className="btn btn--primary btn--small" onClick={() => fileRef.current?.click()}>
              <UploadIcon size={16} /> Upload
            </button>
          )}
          <input ref={fileRef} type="file" accept=".pdf,.jpg,.jpeg,.png,.webp,application/pdf,image/jpeg,image/png,image/webp" hidden onChange={(e) => pickFile(e.target.files?.[0])} />
        </div>
        {fileError && <p className="form__error" role="alert">{fileError}</p>}
        {fileName && <p className="bill__note">Saved with the bill so you can view it later from Bill history. SHEM doesn’t read its contents.</p>}

        <div className="bill__divider"><span>or enter details manually</span></div>

        <div className="bill__grid">
          <div className="bill__field bill__field--wide">
            <span className="form__label">Billing period</span>
            <div className="bill__period">
              <span className="form__select-wrap">
                <select className="form__input" value={month} onChange={(e) => { setMonth(Number(e.target.value)); setPeriodOverride(null); }} aria-label="Billing month">
                  {MONTHS.map((m, i) => <option key={m} value={i + 1}>{m}</option>)}
                </select>
                <ChevronDown className="form__chev" />
              </span>
              <span className="form__select-wrap">
                <select className="form__input" value={year} onChange={(e) => { setYear(Number(e.target.value)); setPeriodOverride(null); }} aria-label="Billing year">
                  {years.map((y) => <option key={y}>{y}</option>)}
                </select>
                <ChevronDown className="form__chev" />
              </span>
            </div>
          </div>
          <label className="bill__field">
            <span className="form__label">Period start</span>
            <input className="form__input" type="date" value={period.start} onChange={(e) => setPeriod('start', e.target.value)} />
          </label>
          <label className="bill__field">
            <span className="form__label">Period end</span>
            <input className="form__input" type="date" value={period.end} onChange={(e) => setPeriod('end', e.target.value)} />
          </label>
          <p className="bill__note bill__field--wide">
            {periodOverride
              ? <>Custom dates. <button type="button" className="btn-link" onClick={() => setPeriodOverride(null)}>Use my billing cycle</button></>
              : `From your meter reading day (${cycleDay === 1 ? 'calendar month' : `the ${ordinal(cycleDay)}`}) — change if your bill shows different dates.`}
            {period.start && period.end && period.end >= period.start ? ` ${daysInclusive(period.start, period.end)} days.` : ''}
          </p>
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

      {latestBill && <BillVsUsageCard key={latestBill.id} bill={latestBill} />}

      <input ref={attachRef} type="file" accept=".pdf,.jpg,.jpeg,.png,.webp,application/pdf,image/jpeg,image/png,image/webp" hidden onChange={(e) => void attachToExisting(e.target.files?.[0])} />
      {viewing && bills.find((x) => x.id === viewing) && (
        <BillDocumentViewer
          bill={bills.find((x) => x.id === viewing)!}
          onClose={() => setViewing(null)}
          onRemove={() => {
            const id = viewing;
            setViewing(null);
            void removeDocument(id).then((err) => setRowError(err ? { id, message: err } : null));
          }}
        />
      )}

      {bills.length > 0 && (
        <section className="card" aria-label="Bill history">
          <div className="card__head"><h2 className="card__title">Bill history</h2></div>
          {locationsInUse.length > 1 && (
            <div className="bill__chips bill-hist__filter" role="tablist" aria-label="Location">
              {['all', ...locationsInUse].map((id) => (
                <button key={id} type="button" role="tab" aria-selected={historyLoc === id} className={`chip ${historyLoc === id ? 'chip--on' : ''}`} onClick={() => setHistoryLoc(id)}>
                  {id === 'all' ? 'All' : locLabel(id)}
                </button>
              ))}
            </div>
          )}
          {summary && (
            <p className="bill__note bill-hist__summary">
              {summary.count} {summary.count === 1 ? 'bill' : 'bills'} · average {formatCurrencyINR(summary.avg)} ({Math.round(summary.avgKWh)} kWh) · latest {summary.latest.billingPeriod}
              {historyLoc !== 'my_home' && ' · not compared with this home’s usage'}
            </p>
          )}
          <div className="list">
            {shownBills.map((b) => (
              <div key={b.id} className="bill-hist-item">
                <div className="row row--plain bill-hist">
                  <span className="row__body">
                    <span className="row__title">{b.billingPeriod}</span>
                    <span className="row__sub">
                      {b.utilityProvider} · {b.unitsConsumed} kWh{(b.locationTag || 'my_home') !== 'my_home' ? ` · ${locLabel(b.locationTag!)}` : ''}
                    </span>
                  </span>
                  <b className="bill-hist__amt">{formatCurrencyINR(b.billAmount)}</b>
                  <button type="button" className="icon-btn" aria-label={`Delete bill for ${b.billingPeriod}`} onClick={() => deleteBill(b.id)}>
                    <TrashIcon />
                  </button>
                </div>
                <div className="bill-hist__actions">
                  {isHomeBill(b) && (
                    <button
                      type="button"
                      className="btn-link bill-hist__toggle"
                      aria-expanded={openBill === b.id}
                      onClick={() => setOpenBill(openBill === b.id ? null : b.id)}
                    >
                      {openBill === b.id ? 'Hide breakdown' : 'Where the money went'}
                    </button>
                  )}
                  {b.documentStatus === 'uploading' ? (
                    <span className="bill-hist__doc-status">Uploading document…</span>
                  ) : b.hasDocument ? (
                    <button type="button" className="btn-link bill-hist__toggle" onClick={() => setViewing(b.id)}>
                      <FileIcon size={14} /> View bill
                    </button>
                  ) : (
                    <button type="button" className="btn-link bill-hist__toggle" onClick={() => { setAttachFor(b.id); attachRef.current?.click(); }}>
                      <UploadIcon size={14} /> {b.documentStatus === 'failed' ? 'Retry document' : 'Attach bill'}
                    </button>
                  )}
                </div>
                {rowError?.id === b.id && <p className="form__error" role="alert">{rowError.message}</p>}
                {openBill === b.id && isHomeBill(b) && <BillCostSplit billId={b.id} />}
              </div>
            ))}
          </div>
        </section>
      )}
    </div>
  );
}
