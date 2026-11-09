import { useLiveData } from '../../hooks/useLiveData';
import { formatClock, formatKWh, formatWatts } from '../../utils/simFormat';
import { SimTag } from './SourceTag';
import './ApplianceRelayControl.css';
import './Simulation.css';

/** Full ON/OFF control for a simulated appliance (edit form, Live page) — mirrors ApplianceRelayControl. */
export function SimControlCard({ applianceId, applianceName }: { applianceId: string; applianceName: string }) {
  const { simById, sendSimCommand, resumeSimRoutine, simPending, simError, streamStatus } = useLiveData();
  const live = simById[applianceId];
  const pending = simPending.has(applianceId);
  const canCommand = streamStatus === 'open' && !!live && !pending;
  const error = simError?.applianceId === applianceId ? simError.message : null;
  const on = live?.state === 'ON';

  const modeText = !live
    ? 'Waiting for the simulator…'
    : live.mode === 'manual'
      ? `Switched from the app${live.overrideUntil ? ` · routine resumes ${formatClock(live.overrideUntil)}` : ''}`
      : live.mode === 'auto'
        ? `Following daily routine${live.nextChangeAt ? ` · turns ${on ? 'off' : 'on'} ${formatClock(live.nextChangeAt)}` : ''}`
        : 'Daily routine is off — switch it manually';

  return (
    <div className="relay-control sim-control" onClick={(e) => e.stopPropagation()}>
      <div className="relay-row">
        <div className="relay-row__info">
          <span className="relay-row__name">
            <span className={`sim-dot ${on ? 'is-on' : ''}`} /> {live ? formatWatts(live.powerW) : '--'} <SimTag compact />
          </span>
          <span className="relay-row__sub">
            {applianceName} is <strong>{live ? live.state : 'unknown'}</strong>
            {live ? ` · ${formatKWh(live.todayKWh)} kWh today` : ''}
          </span>
        </div>
        <div className="relay-row__actions">
          <button type="button" className="relay-btn relay-btn--on" disabled={!canCommand || on} onClick={() => void sendSimCommand(applianceId, 'ON')} aria-label={`Turn ${applianceName} ON`}>
            Turn ON
          </button>
          <button type="button" className="relay-btn relay-btn--off" disabled={!canCommand || !on} onClick={() => void sendSimCommand(applianceId, 'OFF')} aria-label={`Turn ${applianceName} OFF`}>
            Turn OFF
          </button>
        </div>
      </div>
      <div className="sim-control__meta">
        <span>{modeText}</span>
        {live?.mode === 'manual' && live.simAuto && live.routine && (
          <button type="button" className="sim-control__resume" disabled={pending} onClick={() => void resumeSimRoutine(applianceId)}>
            Resume routine
          </button>
        )}
      </div>
      {live?.routine && <p className="relay-card__hint">Routine: {live.routine}</p>}
      {error && <p className="relay-card__hint sim-control__error" role="alert">{error}</p>}
    </div>
  );
}
