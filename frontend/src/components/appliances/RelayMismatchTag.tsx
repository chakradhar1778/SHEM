import { openRelayMismatchModal, useRelayMismatch } from '../../hooks/useRelayMismatch';
import './RelayMismatch.css';

interface RelayMismatchTagProps {
  applianceId: string;
  compact?: boolean;
}

/**
 * Clickable warning tag displayed on the Relay 1 appliance whenever its live
 * wattage deviates beyond the configured threshold.
 */
export function RelayMismatchTag({ applianceId, compact = false }: RelayMismatchTagProps) {
  const { mismatch } = useRelayMismatch();

  if (!mismatch?.active || mismatch.applianceId !== applianceId) return null;

  const isBig = mismatch.isBigDiff;
  const label = isBig
    ? compact
      ? '⚠ Unexpected load'
      : `⚠ Unexpected load · ${Math.round(mismatch.liveWatts ?? 0)} W`
    : compact
      ? '⚠ Load mismatch'
      : `⚠ Load mismatch · ${Math.round(mismatch.liveWatts ?? 0)} W`;

  return (
    <button
      type="button"
      className={`mismatch-tag ${isBig ? 'mismatch-tag--critical' : ''}`}
      title="Live power differs from rated watts. Click to check or switch appliance."
      onClick={(e) => {
        e.preventDefault();
        e.stopPropagation();
        openRelayMismatchModal();
      }}
    >
      {label}
    </button>
  );
}
