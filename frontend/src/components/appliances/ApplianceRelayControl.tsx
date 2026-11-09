import { useLiveData } from '../../hooks/useLiveData';
import { TERMINAL_RELAY_STATUSES } from '../../context/liveDataContextDef';
import { describeRelayStatus, formatDateTime } from '../../utils/liveFormat';
import './ApplianceRelayControl.css';

interface ApplianceRelayControlProps {
  applianceName: string;
  channel: number;
}

/**
 * ON/OFF control for an appliance that has a relay channel assigned.
 * Only channel 1 exists on the firmware/backend today.
 */
export function ApplianceRelayControl({ applianceName, channel }: ApplianceRelayControlProps) {
  const { streamStatus, mqttConnected, device, relay, command, sendRelayCommand, dismissCommand } = useLiveData();

  if (channel !== 1) return null;

  const commandPending = command != null && !TERMINAL_RELAY_STATUSES.has(command.status);
  const canCommand = streamStatus === 'open' && mqttConnected !== false && !!device?.deviceOnline && !commandPending;
  const cannotCommandReason =
    streamStatus !== 'open'
      ? 'Backend connection is down.'
      : mqttConnected === false
        ? 'Backend is not connected to the MQTT broker.'
        : !device?.deviceOnline
          ? 'The ESP32 is offline — a command would not be delivered.'
          : null;

  const relayState = relay?.commandedState ?? null;
  const commandInfo = command ? describeRelayStatus(command.status, command.requestedState) : null;

  return (
    <div className="relay-control" onClick={(e) => e.stopPropagation()}>
      <div className="relay-row">
        <div className="relay-row__info">
          <span className="relay-row__name">⚡ Relay {channel}</span>
          <span className="relay-row__sub">
            {applianceName} is <strong>{relayState ?? 'unknown'}</strong>
            {relay?.lastReportedAt ? ` · reported ${formatDateTime(relay.lastReportedAt)}` : ''}
          </span>
        </div>
        <div className="relay-row__actions">
          <button
            type="button"
            className="relay-btn relay-btn--on"
            disabled={!canCommand}
            onClick={() => void sendRelayCommand('ON')}
            aria-label={`Turn ${applianceName} ON`}
          >
            Turn ON
          </button>
          <button
            type="button"
            className="relay-btn relay-btn--off"
            disabled={!canCommand}
            onClick={() => void sendRelayCommand('OFF')}
            aria-label={`Turn ${applianceName} OFF`}
          >
            Turn OFF
          </button>
        </div>
      </div>

      {commandInfo && command && (
        <div className={`relay-status relay-status--${commandInfo.tone}`} role="status">
          {commandInfo.tone === 'pending' && <span className="relay-status__spinner" aria-hidden="true" />}
          <span className="relay-status__text">
            {commandInfo.text}
            {command.message && commandInfo.tone === 'error' && command.status === 'failed' ? ` ${command.message}` : ''}
          </span>
          {!commandPending && (
            <button type="button" className="relay-status__dismiss" onClick={dismissCommand} aria-label="Dismiss">
              ×
            </button>
          )}
        </div>
      )}
      {!canCommand && !commandPending && cannotCommandReason && <p className="relay-card__hint">{cannotCommandReason}</p>}
    </div>
  );
}
