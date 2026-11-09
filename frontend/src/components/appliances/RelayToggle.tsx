import { useLiveData } from '../../hooks/useLiveData';
import { TERMINAL_RELAY_STATUSES } from '../../context/liveDataContextDef';
import { describeRelayStatus } from '../../utils/liveFormat';
import './RelayToggle.css';

/**
 * Compact on/off switch for an appliance wired to a relay channel (channel 1 only today).
 * Shows the relay's reported state; a command only counts once the device acknowledges it.
 */
export function RelayToggle({ applianceName, channel }: { applianceName: string; channel: number }) {
  const { streamStatus, mqttConnected, device, relay, command, sendRelayCommand } = useLiveData();
  if (channel !== 1) return null;

  const state = relay?.commandedState ?? null;
  const pending = command != null && !TERMINAL_RELAY_STATUSES.has(command.status);
  const blockedReason =
    streamStatus !== 'open'
      ? 'Backend connection is down'
      : mqttConnected === false
        ? 'Backend is not connected to the broker'
        : !device?.deviceOnline
          ? 'The meter is offline'
          : null;
  const disabled = pending || blockedReason != null;
  const info = command ? describeRelayStatus(command.status, command.requestedState) : null;
  const next = state === 'ON' ? 'OFF' : 'ON';

  const message =
    info && info.tone !== 'ok' && command ? { tone: info.tone, text: info.text } : !info && blockedReason ? { tone: 'idle', text: blockedReason } : null;

  return (
    <>
    <div className="relay-toggle">
      <span className="relay-toggle__ctl">
      <button
        type="button"
        role="switch"
        aria-checked={state === 'ON'}
        aria-label={`${applianceName}: turn ${next === 'ON' ? 'on' : 'off'}`}
        className={`switch ${state === 'ON' ? 'is-on' : ''} ${pending ? 'is-busy' : ''}`}
        disabled={disabled}
        title={blockedReason ?? (pending ? 'Waiting for the device…' : `Turn ${next === 'ON' ? 'on' : 'off'}`)}
        onClick={() => void sendRelayCommand(next)}
      >
        <span className="switch__knob" />
      </button>
      <span className="relay-toggle__state">{pending ? '…' : state === 'ON' ? 'On' : state === 'OFF' ? 'Off' : '—'}</span>
      </span>
    </div>
    {message && <span className={`relay-toggle__msg relay-toggle__msg--${message.tone}`} role="status">{message.text}</span>}
    </>
  );
}
