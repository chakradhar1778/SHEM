import { useEffect, useState } from 'react';
import { Link } from 'react-router-dom';
import { fetchAIStatus } from '../api/aiApi';
import type { AIStatus } from '../api/aiTypes';
import { clearSavedConnection, errorMessage, getConnection, saveConnection } from '../api/backendApi';
import { fetchHealth } from '../api/telemetryApi';
import type { HealthResponse } from '../api/types';
import { useHomeConfig } from '../hooks/useHomeConfig';
import { useLiveData } from '../hooks/useLiveData';
import { notifyRelayMismatchChanged } from '../hooks/useRelayMismatch';
import { PageHero } from '../components/art/PageHero';
import { TariffEditor } from '../components/bill/TariffEditor';
import { ChevronRight, HomeTypeIcon } from '../components/ui/icons';
import { formatAge, formatDateTime } from '../utils/liveFormat';
import './SettingsPage.css';

/** Settings: electricity tariff, relay mismatch sensitivity, backend connection and live diagnostics. */
export function SettingsPage() {
  const initial = getConnection();
  const { config, updateConfig } = useHomeConfig();
  const live = useLiveData();

  const [baseUrl, setBaseUrl] = useState(initial.baseUrl);
  const [apiKey, setApiKey] = useState(initial.apiKey);
  const [showKey, setShowKey] = useState(false);
  const [connSaved, setConnSaved] = useState(false);
  const [thresholdDraft, setThresholdDraft] = useState<number | null>(null);
  const threshold = thresholdDraft ?? config.relayMismatchThresholdPercent;
  const [thresholdSaved, setThresholdSaved] = useState(false);
  const [aiStatus, setAiStatus] = useState<AIStatus | null>(null);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);

  useEffect(() => {
    fetchAIStatus().then(setAiStatus).catch(() => undefined);
  }, []);

  const saveThreshold = () => {
    const clamped = Math.max(5, Math.min(100, Math.round(Number(threshold) || 30)));
    setThresholdDraft(null);
    updateConfig({ relayMismatchThresholdPercent: clamped });
    notifyRelayMismatchChanged();
    setThresholdSaved(true);
    window.setTimeout(() => setThresholdSaved(false), 2500);
  };

  const saveConn = () => {
    saveConnection({ baseUrl, apiKey });
    setConnSaved(true);
    window.setTimeout(() => setConnSaved(false), 2500);
  };

  const test = async () => {
    setTesting(true);
    setHealth(null);
    setHealthError(null);
    try {
      setHealth(await fetchHealth());
    } catch (e) {
      setHealthError(errorMessage(e));
    } finally {
      setTesting(false);
    }
  };

  const diag: [string, string][] = [
    ['Live stream', live.streamStatus],
    ['MQTT broker', live.mqttConnected == null ? 'unknown' : live.mqttConnected ? 'connected' : 'disconnected'],
    ['Energy meter', live.device ? (live.device.deviceOnline ? 'online' : 'offline') : 'unknown'],
    ['Last seen', formatDateTime(live.device?.lastSeenAt)],
    ['Meter readings', live.device ? (live.device.pzemReadingsValid ? 'valid' : 'unavailable') : 'unknown'],
    ['Latest reading', live.latest ? formatAge(live.latestAgeSeconds) : 'none'],
    ['Relay 1', live.relay?.commandedState ?? 'unknown'],
    ...(aiStatus?.providers ?? []).map((p): [string, string] => {
      const total = p.keyCount ?? (p.configured ? 1 : 0);
      const healthy = p.healthyKeyCount ?? total;
      const label = p.name.charAt(0).toUpperCase() + p.name.slice(1);
      return [
        `AI (${label})`,
        total > 0 ? `${healthy}/${total} ${total === 1 ? 'key' : 'keys'} ready` : 'not configured',
      ];
    }),
  ];

  return (
    <div className="page">
      <PageHero art="room" title="Settings" subtitle="Rates, connection and diagnostics." />

      <div className="sheet settings">
        <Link to="/setup" className="row row--cta">
          <span className="row__icon"><HomeTypeIcon size={26} /></span>
          <span className="row__body">
            <span className="row__title">{config.homeName || 'My Home'}</span>
            <span className="row__sub">{config.homeType} · {config.occupants} occupants{config.location ? ` · ${config.location}` : ''}</span>
          </span>
          <span className="row__end">Configure <ChevronRight /></span>
        </Link>

        <TariffEditor />

        <section className="settings__block" aria-label="Relay load mismatch detection">
          <h2 className="card__title">Relay load mismatch</h2>
          <p className="sheet__hint">
            Alert when live Relay 1 power differs from the registered appliance’s rated watts by more than this percentage.
            Small voltage fluctuations stay below the threshold; plugging in another appliance triggers a notification and warning tag.
          </p>
          <div className="settings__threshold">
            <label className="form__field settings__threshold-slider">
              <span className="form__label settings__label-row">
                <span>Mismatch threshold</span>
                <strong>±{threshold}%</strong>
              </span>
              <input
                type="range"
                min={5}
                max={100}
                step={5}
                value={threshold}
                onChange={(e) => setThresholdDraft(Number(e.target.value))}
                aria-label="Relay load mismatch threshold percent"
              />
            </label>
            <input
              className="form__input settings__threshold-num"
              type="number"
              min={5}
              max={100}
              step={1}
              value={threshold}
              onChange={(e) => setThresholdDraft(Math.max(5, Math.min(100, Number(e.target.value) || 5)))}
              aria-label="Mismatch threshold value"
            />
          </div>
          <div className="btn-row">
            <button
              type="button"
              className="btn btn--soft btn--small"
              onClick={() => setThresholdDraft(30)}
              disabled={threshold === 30}
            >
              Default (30%)
            </button>
            <button type="button" className="btn btn--primary btn--small" onClick={saveThreshold}>
              {thresholdSaved ? '✓ Saved' : 'Save threshold'}
            </button>
          </div>
        </section>

        <section className="settings__block">
          <h2 className="card__title">Backend connection</h2>
          <p className="sheet__hint">SHEM talks only to your backend, never directly to the MQTT broker. Leave the URL empty when the app is served by the backend.</p>
          <label className="form__field">
            <span className="form__label">Backend URL</span>
            <input className="form__input" type="url" placeholder="Same origin" value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} autoComplete="off" />
          </label>
          <label className="form__field">
            <span className="form__label settings__label-row">
              API key
              <button type="button" className="link-more" onClick={() => setShowKey((s) => !s)}>{showKey ? 'Hide' : 'Show'}</button>
            </span>
            <input className="form__input" type={showKey ? 'text' : 'password'} placeholder="Key set on the backend" value={apiKey} onChange={(e) => setApiKey(e.target.value)} autoComplete="off" />
            <span className="sheet__hint">Stored only on this device.</span>
          </label>
          <div className="btn-row">
            <button type="button" className="btn btn--soft btn--small" onClick={() => void test()} disabled={testing}>{testing ? 'Testing…' : 'Test'}</button>
            <button
              type="button"
              className="btn btn--soft btn--small"
              onClick={() => { clearSavedConnection(); const c = getConnection(); setBaseUrl(c.baseUrl); setApiKey(c.apiKey); }}
            >
              Use defaults
            </button>
            <button type="button" className="btn btn--primary btn--small" onClick={saveConn}>{connSaved ? '✓ Saved' : 'Save'}</button>
          </div>
          {health && (
            <p className={`settings__result ${health.status === 'ok' ? 'is-ok' : 'is-warn'}`}>
              Backend v{health.version} reachable · database {health.dbOk ? 'OK' : 'error'} · MQTT {health.mqttConnected ? 'connected' : 'disconnected'}
            </p>
          )}
          {healthError && <p className="settings__result is-bad">{healthError}</p>}
        </section>

        <details className="settings__block settings__diag">
          <summary className="card__title">Live diagnostics</summary>
          <dl>
            {diag.map(([k, v]) => (
              <div key={k}><dt>{k}</dt><dd>{v}</dd></div>
            ))}
          </dl>
          <button type="button" className="btn btn--soft btn--small settings__btn" onClick={live.reconnect}>Reconnect live stream</button>
        </details>
      </div>
    </div>
  );
}
