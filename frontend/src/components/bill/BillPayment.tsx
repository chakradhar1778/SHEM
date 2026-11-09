import { useState } from 'react';
import { billPaymentStatus, type BillRecord } from '../../context/billContextDef';
import { useBill } from '../../hooks/useBill';
import './BillPayment.css';

const todayIso = () => {
  const d = new Date();
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`;
};

/** Paid / due status pill. */
export function BillStatusPill({ bill }: { bill: Pick<BillRecord, 'paidOn' | 'dueDate'> }) {
  const s = billPaymentStatus(bill);
  return <span className={`pay-pill is-${s.tone}`}>{s.tone === 'paid' ? '✓ ' : ''}{s.label}</span>;
}

/** Mark as paid (with a payment date) / undo. */
export function BillPaymentControl({ bill, compact = false }: { bill: BillRecord; compact?: boolean }) {
  const { setPaid } = useBill();
  const [picking, setPicking] = useState(false);
  const [date, setDate] = useState(todayIso);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async (paid: boolean, on?: string) => {
    setBusy(true);
    setError(null);
    const err = await setPaid(bill.id, paid, on);
    setBusy(false);
    if (err) setError(err);
    else setPicking(false);
  };

  if (bill.paidOn) {
    return (
      <span className="pay-ctl">
        {!compact && <BillStatusPill bill={bill} />}
        <button type="button" className="btn-link pay-ctl__undo" disabled={busy} onClick={() => void run(false)}>Mark unpaid</button>
        {error && <span className="form__error" role="alert">{error}</span>}
      </span>
    );
  }

  return (
    <span className="pay-ctl">
      {!compact && <BillStatusPill bill={bill} />}
      {picking ? (
        <span className="pay-ctl__pick">
          <label>
            Paid on
            <input className="form__input" type="date" value={date} max={todayIso()} onChange={(e) => setDate(e.target.value)} />
          </label>
          <button type="button" className="btn btn--primary btn--small" disabled={busy || !date} onClick={() => void run(true, date)}>
            {busy ? 'Saving…' : 'Confirm'}
          </button>
          <button type="button" className="btn-link" onClick={() => setPicking(false)}>Cancel</button>
        </span>
      ) : (
        <button type="button" className="btn btn--soft btn--small pay-ctl__mark" onClick={() => setPicking(true)}>Mark as paid</button>
      )}
      {error && <span className="form__error" role="alert">{error}</span>}
    </span>
  );
}
