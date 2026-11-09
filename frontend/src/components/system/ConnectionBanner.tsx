import { NavLink } from 'react-router-dom';
import { useLiveData } from '../../hooks/useLiveData';
import { useHomeConfig } from '../../hooks/useHomeConfig';
import { useInventory } from '../../hooks/useInventory';
import { useBill } from '../../hooks/useBill';
import { useTarget } from '../../hooks/useTarget';
import './ConnectionBanner.css';

/**
 * One-line status strip shown only when something is wrong: backend
 * unreachable / unauthorised, MQTT broker down, meter offline, or a save failed.
 */
export function ConnectionBanner() {
  const { streamStatus, mqttConnected, device, reconnect } = useLiveData();
  const home = useHomeConfig();
  const inventory = useInventory();
  const bills = useBill();
  const target = useTarget();

  const saveError = home.error || inventory.error || bills.error || target.error;

  let tone: 'error' | 'warn' | null = null;
  let text = '';
  let action: React.ReactNode = null;

  if (streamStatus === 'unauthorized') {
    tone = 'error';
    text = 'Backend rejected the API key.';
    action = <NavLink to="/settings" className="conn-banner__action">Fix in Settings</NavLink>;
  } else if (streamStatus === 'unreachable') {
    tone = 'error';
    text = 'Cannot reach the SHEM backend.';
    action = <button type="button" className="conn-banner__action" onClick={reconnect}>Retry</button>;
  } else if (saveError) {
    tone = 'error';
    text = saveError;
    action = (
      <button
        type="button"
        className="conn-banner__action"
        onClick={() => {
          void home.refresh();
          void inventory.refresh();
          void bills.refresh();
          void target.refresh();
        }}
      >
        Reload
      </button>
    );
  } else if (streamStatus === 'reconnecting') {
    tone = 'warn';
    text = 'Live connection lost — reconnecting…';
  } else if (streamStatus === 'open' && mqttConnected === false) {
    tone = 'warn';
    text = 'Backend is not connected to the MQTT broker — live data paused.';
  } else if (streamStatus === 'open' && device && !device.deviceOnline) {
    tone = 'warn';
    text = device.lastSeenAt ? 'Energy meter (ESP32) is offline.' : 'Energy meter (ESP32) has not reported yet.';
  }

  if (!tone) return null;
  return (
    <div className={`conn-banner conn-banner--${tone}`} role="status">
      <span className="conn-banner__dot" aria-hidden="true" />
      <span className="conn-banner__text">{text}</span>
      {action}
    </div>
  );
}
