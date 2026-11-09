import { useEffect, useRef, useState } from 'react';
import { errorMessage } from '../../api/backendApi';
import { fetchBillDocument } from '../../api/billsApi';
import type { BillRecord } from '../../context/billContextDef';
import { CloseIcon, TrashIcon } from '../ui/icons';
import './BillDocumentViewer.css';

/** Full-screen viewer for a stored bill document (image or PDF). The file is fetched with the API key. */
export function BillDocumentViewer({ bill, onClose, onRemove }: { bill: BillRecord; onClose: () => void; onRemove: () => void }) {
  const [url, setUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const closeRef = useRef<HTMLButtonElement>(null);
  const isPdf = bill.documentContentType === 'application/pdf';

  useEffect(() => {
    let objectUrl: string | null = null;
    let cancelled = false;
    fetchBillDocument(bill.id)
      .then((blob) => {
        if (cancelled) return;
        objectUrl = URL.createObjectURL(blob);
        setUrl(objectUrl);
      })
      .catch((e) => !cancelled && setError(errorMessage(e)));
    return () => {
      cancelled = true;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [bill.id]);

  useEffect(() => {
    closeRef.current?.focus();
    const onKey = (e: KeyboardEvent) => e.key === 'Escape' && onClose();
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [onClose]);

  const name = bill.documentFilename || `${bill.billingPeriod ?? 'bill'}${isPdf ? '.pdf' : ''}`;
  const size = bill.documentSize ? `${(bill.documentSize / 1024 / 1024).toFixed(bill.documentSize > 1024 * 1024 ? 1 : 2)} MB` : '';

  return (
    <div className="docview" role="dialog" aria-modal="true" aria-label={`Bill document: ${name}`} onClick={onClose}>
      <div className="docview__panel" onClick={(e) => e.stopPropagation()}>
        <header className="docview__head">
          <span className="docview__title">
            <b>{bill.billingPeriod}</b>
            <span>{name}{size ? ` · ${size}` : ''}</span>
          </span>
          <button ref={closeRef} type="button" className="icon-btn" aria-label="Close" onClick={onClose}><CloseIcon size={20} /></button>
        </header>
        <div className="docview__body">
          {error ? (
            <p className="form__error" role="alert">{error}</p>
          ) : !url ? (
            <p className="sheet__hint">Loading document…</p>
          ) : isPdf ? (
            <iframe className="docview__pdf" src={url} title={name} />
          ) : (
            <img className="docview__img" src={url} alt={`Bill for ${bill.billingPeriod}`} />
          )}
        </div>
        <footer className="docview__foot">
          {url && <a className="btn btn--soft btn--small" href={url} download={name}>Download</a>}
          <button type="button" className="btn-link btn-link--danger" onClick={onRemove}><TrashIcon size={16} /> Remove document</button>
        </footer>
      </div>
    </div>
  );
}
