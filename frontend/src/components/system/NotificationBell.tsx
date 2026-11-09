import { useCallback, useEffect, useRef, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { fetchNotifications, markAllNotificationsRead, markNotificationRead } from '../../api/alertsApi';
import { CONNECTION_CHANGED_EVENT, NOTIFICATION_EVENT } from '../../api/backendApi';
import type { NotificationItem } from '../../api/types';
import './NotificationBell.css';

function ago(iso: string): string {
  const s = Math.max(0, (Date.now() - Date.parse(iso)) / 1000);
  if (s < 60) return 'just now';
  if (s < 3600) return `${Math.floor(s / 60)} min ago`;
  if (s < 86400) return `${Math.floor(s / 3600)} h ago`;
  return new Date(iso).toLocaleDateString('en-IN', { day: 'numeric', month: 'short' });
}

const ICON: Record<NotificationItem['severity'], string> = { critical: '!', warning: '!', info: 'i', success: '✓' };

/** Top-bar bell: alerts from the backend (bills due, budget, slabs, bill vs usage, budget saver). */
export function NotificationBell() {
  const navigate = useNavigate();
  const [items, setItems] = useState<NotificationItem[]>([]);
  const [unread, setUnread] = useState(0);
  const [open, setOpen] = useState(false);
  const [error, setError] = useState(false);
  const ref = useRef<HTMLDivElement>(null);

  const load = useCallback(() => {
    fetchNotifications(30)
      .then((r) => {
        setItems(r.items);
        setUnread(r.unreadCount);
        setError(false);
      })
      .catch(() => setError(true));
  }, []);

  useEffect(() => {
    load();
    const onNew = (e: Event) => {
      const n = (e as CustomEvent<NotificationItem>).detail;
      if (!n) return;
      setItems((prev) => (prev.some((p) => p.id === n.id) ? prev : [n, ...prev].slice(0, 30)));
      if (!n.readAt) setUnread((u) => u + 1);
    };
    window.addEventListener(NOTIFICATION_EVENT, onNew);
    window.addEventListener(CONNECTION_CHANGED_EVENT, load);
    return () => {
      window.removeEventListener(NOTIFICATION_EVENT, onNew);
      window.removeEventListener(CONNECTION_CHANGED_EVENT, load);
    };
  }, [load]);

  useEffect(() => {
    if (!open) return;
    const close = (e: MouseEvent | KeyboardEvent) => {
      if (e instanceof KeyboardEvent ? e.key === 'Escape' : !ref.current?.contains(e.target as Node)) setOpen(false);
    };
    document.addEventListener('mousedown', close);
    document.addEventListener('keydown', close);
    return () => {
      document.removeEventListener('mousedown', close);
      document.removeEventListener('keydown', close);
    };
  }, [open]);

  const openItem = (n: NotificationItem) => {
    if (!n.readAt) {
      setItems((prev) => prev.map((p) => (p.id === n.id ? { ...p, readAt: new Date().toISOString() } : p)));
      setUnread((u) => Math.max(0, u - 1));
      markNotificationRead(n.id).catch(() => undefined);
    }
    setOpen(false);
    if (n.link) navigate(n.link);
  };

  const readAll = () => {
    markAllNotificationsRead()
      .then((r) => {
        setItems(r.items);
        setUnread(r.unreadCount);
      })
      .catch(() => undefined);
  };

  return (
    <div className="notif" ref={ref}>
      <button
        type="button"
        className="mobile-topbar__btn"
        title="Notifications"
        aria-label={unread ? `Notifications, ${unread} unread` : 'Notifications'}
        aria-haspopup="true"
        aria-expanded={open}
        onClick={() => {
          setOpen((o) => !o);
          if (!open) load();
        }}
      >
        <svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
          <path d="M18 8A6 6 0 0 0 6 8c0 7-3 9-3 9h18s-3-2-3-9" />
          <path d="M13.73 21a2 2 0 0 1-3.46 0" />
        </svg>
        {unread > 0 && <span className="notif__badge" aria-hidden="true">{unread > 9 ? '9+' : unread}</span>}
      </button>

      {open && (
        <div className="notif__panel" role="dialog" aria-label="Notifications">
          <div className="notif__head">
            <b>Notifications</b>
            {unread > 0 && <button type="button" className="btn-link" onClick={readAll}>Mark all read</button>}
          </div>
          {error && items.length === 0 ? (
            <p className="notif__empty">Couldn’t load notifications.</p>
          ) : items.length === 0 ? (
            <p className="notif__empty">You’re all caught up. Alerts for bill due dates, your budget and tariff slabs appear here.</p>
          ) : (
            <ul className="notif__list">
              {items.map((n) => (
                <li key={n.id}>
                  <button type="button" className={`notif__item ${n.readAt ? '' : 'is-unread'}`} onClick={() => openItem(n)}>
                    <span className={`notif__icon is-${n.severity}`} aria-hidden="true">{ICON[n.severity]}</span>
                    <span className="notif__body">
                      <b>{n.title}</b>
                      <span>{n.message}</span>
                      <i>{ago(n.createdAt)}</i>
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>
      )}
    </div>
  );
}
