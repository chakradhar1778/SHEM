import { useCallback, useEffect, useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { errorMessage } from '../../api/backendApi';
import { confirmRelaySameAppliance, fetchRelayMismatch, switchRelayAppliance } from '../../api/relayApi';
import type { RelayMismatchStatus } from '../../api/types';
import { useInventory } from '../../hooks/useInventory';
import { useLiveData } from '../../hooks/useLiveData';
import {
  notifyRelayMismatchChanged,
  OPEN_RELAY_MISMATCH_EVENT,
} from '../../hooks/useRelayMismatch';
import { ApplianceIcon } from './ApplianceIcons';
import { CloseIcon } from '../ui/icons';
import './RelayMismatch.css';

/**
 * Global interactive popup for resolving a Relay 1 load mismatch.
 * Opened either by clicking a `relay_mismatch` notification in the bell
 * or by clicking the warning tag on the relay appliance.
 */
export function RelayMismatchModal() {
  const navigate = useNavigate();
  const { refresh: refreshInventory } = useInventory();
  const { sendRelayCommand, sendSimCommand } = useLiveData();
  const [open, setOpen] = useState(false);
  const [loading, setLoading] = useState(false);
  const [busy, setBusy] = useState(false);
  const [status, setStatus] = useState<RelayMismatchStatus | null>(null);
  const [step, setStep] = useState<'ask' | 'big-warn'>('ask');
  const [warningText, setWarningText] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [feedback, setFeedback] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    setFeedback(null);
    setStep('ask');
    setWarningText(null);
    try {
      setStatus(await fetchRelayMismatch());
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const onOpen = () => {
      setOpen(true);
      void load();
    };
    window.addEventListener(OPEN_RELAY_MISMATCH_EVENT, onOpen);
    return () => window.removeEventListener(OPEN_RELAY_MISMATCH_EVENT, onOpen);
  }, [load]);

  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === 'Escape') setOpen(false);
    };
    document.addEventListener('keydown', onKey);
    return () => document.removeEventListener('keydown', onKey);
  }, [open]);

  if (!open) return null;

  const applianceName = status?.applianceName ?? 'this appliance';
  const liveW = status?.liveWatts ?? 0;
  const ratedW = status?.ratedWatts ?? 0;
  const devPct = status?.deviationPercent ?? 0;

  const handleConfirmSame = async () => {
    setBusy(true);
    setError(null);
    try {
      const res = await confirmRelaySameAppliance();
      if (res.requiresWarning || !res.accepted) {
        setWarningText(res.message);
        setStep('big-warn');
        return;
      }
      notifyRelayMismatchChanged();
      setFeedback(res.message);
      window.setTimeout(() => setOpen(false), 900);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const handleSwitchToExisting = async (targetId: string, targetName: string) => {
    setBusy(true);
    setError(null);
    try {
      const prevOwnerId = status?.applianceId;
      await switchRelayAppliance(targetId);
      if (prevOwnerId) {
        sendSimCommand(prevOwnerId, 'OFF').catch(() => {});
      }
      sendRelayCommand('ON').catch(() => {});
      await refreshInventory();
      notifyRelayMismatchChanged();
      setFeedback(`Relay 1 switched to ${targetName} (now ON). ${applianceName} turned OFF.`);
      window.setTimeout(() => setOpen(false), 1000);
    } catch (err) {
      setError(errorMessage(err));
    } finally {
      setBusy(false);
    }
  };

  const handleAddOtherAppliance = () => {
    setOpen(false);
    navigate('/devices/custom', {
      state: {
        presetRelay: status?.channel ?? 1,
        presetWatts: liveW > 0 ? Math.round(liveW) : undefined,
        replaceRelayOwner: true,
        previousApplianceName: status?.applianceName ?? undefined,
        previousApplianceId: status?.applianceId ?? undefined,
      },
    });
  };

  return (
    <div className="mismatch-backdrop" role="presentation" onClick={() => setOpen(false)}>
      <div
        className="mismatch-modal"
        role="dialog"
        aria-modal="true"
        aria-labelledby="mismatch-modal-title"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="mismatch-modal__head">
          <div>
            <h2 className="mismatch-modal__title" id="mismatch-modal-title">
              {step === 'big-warn'
                ? '⚠️ Unusual power reading'
                : status?.isBigDiff
                  ? 'Unexpected load on Relay 1'
                  : 'Different load detected on Relay 1'}
            </h2>
            <p className="mismatch-modal__sub">
              Threshold: ±{status?.thresholdPercent ?? 30}% (adjustable in Settings)
            </p>
          </div>
          <button type="button" className="icon-btn" aria-label="Close" onClick={() => setOpen(false)}>
            <CloseIcon size={18} />
          </button>
        </div>

        {loading ? (
          <p className="mismatch-modal__question">Checking live Relay 1 power…</p>
        ) : !status?.active ? (
          <>
            <p className="mismatch-modal__question">
              No active load mismatch on Relay 1 right now.
              {status?.applianceName && status.ratedWatts
                ? ` Currently assigned to ${status.applianceName} (${status.ratedWatts} W).`
                : ''}
            </p>
            <div className="mismatch-modal__actions">
              <button type="button" className="btn btn--soft btn--small" onClick={() => setOpen(false)}>
                Close
              </button>
            </div>
          </>
        ) : step === 'big-warn' ? (
          <>
            <div className="mismatch-modal__danger" role="alert">
              <b>Please check the appliance and socket!</b>
              <p>
                {warningText ||
                  `Live power (${liveW.toFixed(0)} W) is far above what a ${ratedW.toFixed(0)} W ${applianceName} can draw — even during low/high voltage swings. Inspect the appliance for faults, or go back and add it as a different appliance on Relay 1.`}
              </p>
            </div>

            <div className="mismatch-modal__stats">
              <div className="mismatch-modal__stat">
                <span>Registered ({applianceName})</span>
                <b>{ratedW.toFixed(0)} W</b>
              </div>
              <div className="mismatch-modal__stat is-crit">
                <span>Live meter</span>
                <b>{liveW.toFixed(0)} W</b>
              </div>
              <div className="mismatch-modal__stat is-crit">
                <span>Difference</span>
                <b>{devPct.toFixed(0)}%</b>
              </div>
            </div>

            {error && <p className="mismatch-modal__error" role="alert">{error}</p>}

            <div className="mismatch-modal__actions">
              <button type="button" className="btn btn--soft btn--small" onClick={() => setStep('ask')}>
                ← Back
              </button>
              <button type="button" className="btn btn--primary btn--small" onClick={handleAddOtherAppliance}>
                Add as other appliance
              </button>
            </div>
          </>
        ) : (
          <>
            <div className="mismatch-modal__stats">
              <div className="mismatch-modal__stat">
                <span>Registered</span>
                <b>{ratedW.toFixed(0)} W</b>
              </div>
              <div className={`mismatch-modal__stat ${status.isBigDiff ? 'is-crit' : 'is-warn'}`}>
                <span>Live meter</span>
                <b>{liveW.toFixed(0)} W</b>
              </div>
              <div className={`mismatch-modal__stat ${status.isBigDiff ? 'is-crit' : 'is-warn'}`}>
                <span>Deviation</span>
                <b>{devPct.toFixed(0)}%</b>
              </div>
            </div>

            {status.matchingAppliances.length > 0 && (
              <div className="mismatch-modal__match">
                <div className="mismatch-modal__match-head">
                  <b>Matches an existing appliance in your home</b>
                </div>
                <div className="mismatch-modal__match-list">
                  {status.matchingAppliances.map((cand) => (
                    <button
                      key={cand.applianceId}
                      type="button"
                      className="mismatch-modal__match-btn"
                      disabled={busy}
                      onClick={() => void handleSwitchToExisting(cand.applianceId, cand.name)}
                    >
                      <span>
                        <ApplianceIcon type={cand.iconType ?? 'bulb'} size={22} />
                        {cand.name} ({cand.ratedWatts} W)
                      </span>
                      <small>{cand.wasOnRelay ? 'Previously on Relay 1 · Switch' : 'Switch Relay 1 →'}</small>
                    </button>
                  ))}
                </div>
              </div>
            )}

            <p className="mismatch-modal__question">
              Relay 1 is set to <strong>{applianceName}</strong> ({ratedW.toFixed(0)} W), but live power is{' '}
              <strong>{liveW.toFixed(0)} W</strong>. Is it still {applianceName}, or did you plug in another appliance?
            </p>

            {error && <p className="mismatch-modal__error" role="alert">{error}</p>}
            {feedback && <p className="mismatch-modal__feedback" role="status">{feedback}</p>}

            <div className="mismatch-modal__actions">
              <button
                type="button"
                className="btn btn--soft btn--small"
                disabled={busy}
                onClick={() => void handleConfirmSame()}
              >
                Still {applianceName}
              </button>
              <button
                type="button"
                className="btn btn--primary btn--small"
                disabled={busy}
                onClick={handleAddOtherAppliance}
              >
                Other appliance
              </button>
            </div>
          </>
        )}
      </div>
    </div>
  );
}
