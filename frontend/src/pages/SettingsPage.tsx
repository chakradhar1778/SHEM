import { useState } from 'react';
import { Link } from 'react-router-dom';
import { clearSavedConnection, errorMessage, getConnection, saveConnection } from '../api/backendApi';
import { fetchHealth } from '../api/telemetryApi';
import type { HealthResponse } from '../api/types';
import { useHomeConfig } from '../hooks/useHomeConfig';
import { useLiveData } from '../hooks/useLiveData';
import { PageHero } from '../components/art/PageHero';
import { TariffEditor } from '../components/bill/TariffEditor';
import { ChevronRight, HomeTypeIcon } from '../components/ui/icons';
import { formatAge, formatDateTime } from '../utils/liveFormat';
import './SettingsPage.css';

/** Settings: electricity tariff, backend connection and live diagnostics. (Home details live in Configure home.) */
export function SettingsPage() {
  const initial = getConnection();
  const { config } = useHomeConfig();
  const live = useLiveData();

  const [baseUrl, setBaseUrl] = useState(initial.baseUrl);
  const [apiKey, setApiKey] = useState(initial.apiKey);
  const [showKey, setShowKey] = useState(false);
  const [connSaved, setConnSaved] = useState(false);
  const [health, setHealth] = useState<HealthResponse | null>(null);
  const [healthError, setHealthError] = useState<string | null>(null);
  const [testing, setTesting] = useState(false);

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
