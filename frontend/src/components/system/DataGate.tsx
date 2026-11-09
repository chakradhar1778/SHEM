import type { ReactNode } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { useBill } from '../../hooks/useBill';
import { useHomeConfig } from '../../hooks/useHomeConfig';
import { useInventory } from '../../hooks/useInventory';
import { useTarget } from '../../hooks/useTarget';
import './ConnectionBanner.css';

/** Routes that must stay usable even when the backend can't be reached. */
const UNGATED_PATHS = new Set(['/settings']);

/**
 * Pages initialise their form state from context data when they mount, so
 * they must not mount before the backend data has arrived (otherwise e.g. the
 * Target page opens in "set target" mode and Home Setup pre-fills defaults
 * over saved values). Shows a loading / connection-error card until every data
 * context has loaded once.
 */
export function DataGate({ children }: { children: ReactNode }) {
  const location = useLocation();
  const sources = [useHomeConfig(), useInventory(), useBill(), useTarget()];

  if (UNGATED_PATHS.has(location.pathname) || sources.every((s) => s.loaded)) {
    return <>{children}</>;
  }

  const failed = sources.find((s) => !s.loaded && s.error && !s.loading);
  if (!failed) {
    return (
      <div className="app-state-card" role="status">
        <div className="app-spinner" aria-hidden="true" />
        <p>Connecting to your SHEM backend…</p>
      </div>
    );
  }

  return (
    <div className="app-state-card" role="alert">
      <h2>Can’t load your data</h2>
      <p>{failed.error}</p>
      <div className="app-state-card__actions">
        <button
          type="button"
          className="app-state-card__btn"
          onClick={() => sources.filter((s) => !s.loaded).forEach((s) => void s.refresh())}
        >
          Try again
        </button>
        <NavLink to="/settings" className="app-state-card__btn app-state-card__btn--ghost">
          Backend connection
        </NavLink>
      </div>
    </div>
  );
}
