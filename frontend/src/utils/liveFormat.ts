import type { RelayUiStatus } from '../context/liveDataContextDef';

export function formatNumber(value: number | null | undefined, digits: number): string {
  return value == null || !Number.isFinite(value) ? '--' : value.toFixed(digits);
}

/**
 * The value exactly as the meter reported it (no rounding to fixed decimals).
 * toPrecision(12) only strips binary float noise such as 98.20000000000001.
 */
export function formatRaw(value: number | null | undefined): string {
  return value == null || !Number.isFinite(value) ? '--' : String(Number(value.toPrecision(12)));
}

export function formatAge(seconds: number | null): string {
  if (seconds == null) return 'no readings yet';
  if (seconds < 5) return 'just now';
  if (seconds < 60) return `${seconds}s ago`;
  if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
  if (seconds < 86400) return `${Math.floor(seconds / 3600)} h ago`;
  return `${Math.floor(seconds / 86400)} d ago`;
}

export function formatDateTime(iso: string | null | undefined): string {
  if (!iso) return '—';
  const d = new Date(iso);
  return Number.isNaN(d.getTime())
    ? '—'
    : d.toLocaleString('en-IN', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' });
}

/** User-facing text for each relay command lifecycle status. */
export function describeRelayStatus(status: RelayUiStatus, requested: 'ON' | 'OFF'): { text: string; tone: 'pending' | 'ok' | 'error' } {
  switch (status) {
    case 'sending':
    case 'pending':
      return { text: `Sending ${requested} command…`, tone: 'pending' };
    case 'published':
      return { text: `${requested} command sent — waiting for the device to confirm…`, tone: 'pending' };
    case 'applied':
      return { text: `Relay switched ${requested} — confirmed by the device.`, tone: 'ok' };
    case 'timeout':
      return { text: 'No confirmation from the device in time. The relay may not have switched.', tone: 'error' };
    case 'rejected_expired':
      return { text: 'The command expired before the device received it.', tone: 'error' };
    case 'rejected_time_unsynchronized':
      return { text: 'The device clock is not synchronised, so it rejected the command for safety.', tone: 'error' };
    case 'rejected_invalid_channel':
    case 'rejected_invalid_state':
      return { text: 'The device rejected the command as invalid.', tone: 'error' };
    case 'publish_failed':
      return { text: 'The backend could not reach the MQTT broker.', tone: 'error' };
    case 'failed':
    default:
      return { text: 'The command could not be sent.', tone: 'error' };
  }
}
