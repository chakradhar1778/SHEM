import { useLiveData } from '../../hooks/useLiveData';
import { formatClock, formatWatts } from '../../utils/simFormat';
import './RelayToggle.css';
import './Simulation.css';

/**
 * Compact on/off switch for a SIMULATED appliance (no relay). Behaves like the relay switch,
 * but applies immediately and the device follows its daily routine between manual switches.
 */
export function SimToggle({ applianceId, applianceName, showPower = true }: { applianceId: string; applianceName: string; showPower?: boolean }) {
  const { simById, sendSimCommand, simPending, simError, streamStatus } = useLiveData();
  const live = simById[applianceId];
  const pending = simPending.has(applianceId);
  const on = live?.state === 'ON';
  const blocked = streamStatus !== 'open' ? 'Backend connection is down' : !live ? 'Starting simulation…' : null;
  const error = simError?.applianceId === applianceId ? simError.message : null;
  const next = on ? 'OFF' : 'ON';

  const sub = live
    ? live.mode === 'manual'
      ? live.overrideUntil ? `Manual · until ${formatClock(live.overrideUntil)}` : 'Manual'
      : live.mode === 'auto'
        ? live.nextChangeAt ? `Auto · ${on ? 'off' : 'on'} at ${formatClock(live.nextChangeAt)}` : 'Auto'
        : 'Routine off'
    : null;

  return (
    <>
      <div className="relay-toggle sim-toggle">
        <span className="relay-toggle__ctl">
          {showPower && live && <span className={`sim-toggle__w ${on ? 'is-on' : ''}`}>{formatWatts(live.powerW)}</span>}
          <button
            type="button"
            role="switch"
            aria-checked={on}
            aria-label={`${applianceName} (simulated): turn ${next === 'ON' ? 'on' : 'off'}`}
            className={`switch ${on ? 'is-on' : ''} ${pending ? 'is-busy' : ''}`}
            disabled={pending || blocked != null}
            title={blocked ?? `Turn ${next === 'ON' ? 'on' : 'off'} (simulated)`}
            onClick={() => void sendSimCommand(applianceId, next)}
          >
            <span className="switch__knob" />
          </button>
        </span>
        {sub && <span className="sim-toggle__mode">{sub}</span>}
      </div>
      {error && <span className="relay-toggle__msg relay-toggle__msg--error" role="alert">{error}</span>}
    </>
  );
}
