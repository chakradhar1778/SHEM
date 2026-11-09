import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  AI_CONFLICT_EVENT,
  AI_DAILY_INSIGHT_EVENT,
  ApiError,
  CONNECTION_CHANGED_EVENT,
  DATA_CHANGED_EVENT,
  emitWindowEvent,
  errorMessage,
  RELAY_UPDATE_EVENT,
  websocketUrl,
} from '../api/backendApi';
import { fetchRelayCommand, sendRelayCommand as postRelayCommand } from '../api/relayApi';
import { resumeSimRoutine as postResumeSim, sendSimCommand as postSimCommand } from '../api/simulationApi';
import { fetchDeviceStatus, fetchTelemetryHistory } from '../api/telemetryApi';
import type {
  DeviceStatus,
  RelayCommandDetail,
  RelayState,
  RelayStatus,
  SimApplianceLive,
  SimStatus,
  StreamEvent,
  TelemetryReading,
} from '../api/types';
import {
  LiveDataContext,
  TERMINAL_RELAY_STATUSES,
  type LiveDataContextType,
  type LivePoint,
  type RelayCommandUiState,
  type StreamStatus,
} from './liveDataContextDef';

/** A reading older than this (by receive time) is not shown as live. */
const LIVE_MAX_AGE_S = 15;
const BUFFER_WINDOW_MS = 10 * 60 * 1000;
const BUFFER_MAX_POINTS = 400;
const PING_INTERVAL_MS = 25_000;

function toPoint(reading: TelemetryReading, fallbackTime: number): LivePoint | null {
  if (reading.activePowerW == null) return null;
  const t = reading.measuredAt ? Date.parse(reading.measuredAt) : fallbackTime;
  return { t: Number.isFinite(t) ? t : fallbackTime, powerW: reading.activePowerW };
}

function trimBuffer(points: LivePoint[]): LivePoint[] {
  const cutoff = Date.now() - BUFFER_WINDOW_MS;
  const kept = points.filter((p) => p.t >= cutoff);
  return kept.length > BUFFER_MAX_POINTS ? kept.slice(kept.length - BUFFER_MAX_POINTS) : kept;
}

export function LiveDataProvider({ children }: { children: ReactNode }) {
  const [streamStatus, setStreamStatus] = useState<StreamStatus>('connecting');
  const [mqttConnected, setMqttConnected] = useState<boolean | null>(null);
  const [device, setDevice] = useState<DeviceStatus | null>(null);
  const [latest, setLatest] = useState<TelemetryReading | null>(null);
  const [latestReceivedAt, setLatestReceivedAt] = useState<number | null>(null);
  const [points, setPoints] = useState<LivePoint[]>([]);
  const [relay, setRelay] = useState<RelayStatus | null>(null);
  const [command, setCommand] = useState<RelayCommandUiState | null>(null);
  const [now, setNow] = useState(() => Date.now());
  const [connectionVersion, setConnectionVersion] = useState(0);
  const [sim, setSim] = useState<SimStatus | null>(null);
  const [simReceivedAt, setSimReceivedAt] = useState<number | null>(null);
  const [homePoints, setHomePoints] = useState<LivePoint[]>([]);
  const [simPending, setSimPending] = useState<ReadonlySet<string>>(new Set());
  const [simError, setSimError] = useState<{ applianceId: string; message: string } | null>(null);
  // Latest live metered watts, read when a sim update arrives (0 when the meter is not live).
  const meteredRef = useRef<{ w: number; at: number }>({ w: 0, at: 0 });

  // relay_update events that arrive before the POST response returns
  const earlyUpdates = useRef<Map<string, RelayCommandDetail>>(new Map());
  const pollTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const applyCommandDetail = useCallback((detail: RelayCommandDetail) => {
    setCommand((prev) => {
      if (!prev || prev.commandId !== detail.commandId) return prev;
      if (TERMINAL_RELAY_STATUSES.has(prev.status) && prev.status !== 'timeout') return prev;
      return { ...prev, status: detail.status, message: detail.errorMessage };
    });
    if (detail.status === 'applied' && detail.commandedState) {
      setRelay((prev) => ({
        deviceId: prev?.deviceId ?? detail.deviceId,
        channel: 1,
        commandedState: detail.commandedState ?? prev?.commandedState ?? null,
        lastReportedAt: detail.acknowledgedAt,
      }));
    }
  }, []);

  const handleEvent = useCallback(
    (event: StreamEvent) => {
      const receivedAt = Date.now();
      switch (event.type) {
        case 'init_snapshot': {
          const { deviceStatus, latestTelemetry, relayStatus } = event.data;
          setDevice(deviceStatus);
          setMqttConnected(deviceStatus.mqttConnected);
          setRelay(relayStatus);
          if (event.data.simStatus) {
            setSim(event.data.simStatus);
            setSimReceivedAt(receivedAt);
          }
          if (latestTelemetry.available && latestTelemetry.reading) {
            setLatest(latestTelemetry.reading);
            setLatestReceivedAt(receivedAt - (latestTelemetry.ageSeconds ?? 0) * 1000);
          }
          break;
        }
        case 'telemetry': {
          setLatest(event.data);
          setLatestReceivedAt(receivedAt);
          const p = toPoint(event.data, receivedAt);
          if (p) {
            setPoints((prev) => trimBuffer([...prev, p]));
            meteredRef.current = { w: p.powerW, at: receivedAt };
          }
          break;
        }
        case 'sim_update': {
          setSim(event.data);
          setSimReceivedAt(receivedAt);
          const metered = receivedAt - meteredRef.current.at <= LIVE_MAX_AGE_S * 1000 ? meteredRef.current.w : 0;
          const t = event.data.serverTime ? Date.parse(event.data.serverTime) : receivedAt;
          setHomePoints((prev) => trimBuffer([...prev, { t: Number.isFinite(t) ? t : receivedAt, powerW: metered + event.data.totalPowerW }]));
          break;
        }
        case 'device_status':
          setDevice(event.data);
          setMqttConnected(event.data.mqttConnected);
          break;
        case 'relay_state':
          setRelay(event.data);
          break;
        case 'relay_update':
          earlyUpdates.current.set(event.data.commandId, event.data);
          applyCommandDetail(event.data);
          emitWindowEvent(RELAY_UPDATE_EVENT, event.data);
          break;
        case 'heartbeat':
          setMqttConnected(event.data.mqttConnected);
          break;
        // SHEM AI changed data / found conflicts / wrote a daily briefing
        case 'ai_action':
          emitWindowEvent(DATA_CHANGED_EVENT, event.data);
          break;
        case 'ai_conflict':
          emitWindowEvent(AI_CONFLICT_EVENT, event.data);
          break;
        case 'ai_daily_insight':
          emitWindowEvent(AI_DAILY_INSIGHT_EVENT, event.data);
          break;
        default:
          break;
      }
    },
    [applyCommandDetail]
  );

  // ── WebSocket lifecycle with exponential back-off ──────────────────────────
  useEffect(() => {
    let ws: WebSocket | null = null;
    let retry = 0;
    let disposed = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;

    const seedChart = async () => {
      try {
        const history = await fetchTelemetryHistory({
          from: new Date(Date.now() - BUFFER_WINDOW_MS),
          resolution: 'raw',
          limit: BUFFER_MAX_POINTS,
        });
        if (disposed) return;
        const seeded = history.readings
          .filter((r) => r.activePowerW != null)
          .map((r) => ({ t: Date.parse(r.timestamp), powerW: r.activePowerW as number }));
        setPoints((live) => {
          const lastSeeded = seeded.length ? seeded[seeded.length - 1].t : 0;
          return trimBuffer([...seeded, ...live.filter((p) => p.t > lastSeeded)]);
        });
      } catch {
        /* chart simply starts empty */
      }
    };

    const diagnose = async () => {
      try {
        await fetchDeviceStatus();
        if (!disposed) setStreamStatus('reconnecting');
      } catch (err) {
        if (disposed) return;
        if (err instanceof ApiError && err.status === 401) setStreamStatus('unauthorized');
        else if (err instanceof ApiError && err.status === 0) setStreamStatus('unreachable');
        else setStreamStatus('reconnecting');
      }
    };

    const connect = () => {
      if (disposed) return;
      if (retry === 0) setStreamStatus('connecting');
      try {
        ws = new WebSocket(websocketUrl('/api/stream'));
      } catch {
        void diagnose();
        schedule();
        return;
      }
      ws.onopen = () => {
        retry = 0;
        setStreamStatus('open');
        void seedChart();
      };
      ws.onmessage = (msg) => {
        try {
          handleEvent(JSON.parse(String(msg.data)) as StreamEvent);
        } catch {
          /* ignore malformed frames */
        }
      };
      ws.onclose = () => {
        ws = null;
        if (disposed) return;
        void diagnose();
        schedule();
      };
    };

    const schedule = () => {
      const delay = Math.min(15_000, 1000 * 2 ** retry);
      retry += 1;
      reconnectTimer = setTimeout(connect, delay);
    };

    connect();
    const ping = setInterval(() => {
      if (ws && ws.readyState === WebSocket.OPEN) ws.send('ping');
    }, PING_INTERVAL_MS);

    return () => {
      disposed = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      clearInterval(ping);
      ws?.close();
    };
  }, [connectionVersion, handleEvent]);

  // Reconnect when the user changes backend URL / API key
  useEffect(() => {
    const onChange = () => setConnectionVersion((v) => v + 1);
    window.addEventListener(CONNECTION_CHANGED_EVENT, onChange);
    return () => window.removeEventListener(CONNECTION_CHANGED_EVENT, onChange);
  }, []);

  // 1 s clock so reading age / staleness updates even between messages
  useEffect(() => {
    const t = setInterval(() => setNow(Date.now()), 1000);
    return () => clearInterval(t);
  }, []);

  useEffect(() => () => {
    if (pollTimer.current) clearTimeout(pollTimer.current);
  }, []);

  // ── Relay commands ─────────────────────────────────────────────────────────
  const sendRelayCommand = useCallback(
    async (state: RelayState) => {
      if (pollTimer.current) clearTimeout(pollTimer.current);
      setCommand({ commandId: null, requestedState: state, status: 'sending', message: null, startedAt: Date.now() });
      try {
        const res = await postRelayCommand(state);
        setCommand({
          commandId: res.commandId,
          requestedState: state,
          status: res.status,
          message: 'Waiting for the device to confirm…',
          startedAt: Date.now(),
        });
        const early = earlyUpdates.current.get(res.commandId);
        if (early) applyCommandDetail(early);

        // Fallback if the stream misses the ack: check the command after it expires.
        const waitMs = Math.max(0, Date.parse(res.expiresAt) - Date.now()) + 6000;
        pollTimer.current = setTimeout(async () => {
          try {
            applyCommandDetail(await fetchRelayCommand(res.commandId));
          } catch {
            /* stream state remains */
          }
        }, waitMs);
      } catch (err) {
        setCommand({
          commandId: null,
          requestedState: state,
          status: 'failed',
          message: errorMessage(err),
          startedAt: Date.now(),
        });
      }
    },
    [applyCommandDetail]
  );

  // ── Simulated appliances ───────────────────────────────────────────────────
  const runSim = useCallback(async (applianceId: string, request: () => Promise<SimStatus>) => {
    setSimPending((prev) => new Set(prev).add(applianceId));
    setSimError(null);
    try {
      const status = await request();
      setSim(status);
      setSimReceivedAt(Date.now());
    } catch (err) {
      setSimError({ applianceId, message: errorMessage(err) });
    } finally {
      setSimPending((prev) => {
        const next = new Set(prev);
        next.delete(applianceId);
        return next;
      });
    }
  }, []);

  const sendSimCommand = useCallback(
    (applianceId: string, state: RelayState) => runSim(applianceId, () => postSimCommand(applianceId, state)),
    [runSim]
  );
  const resumeSimRoutine = useCallback(
    (applianceId: string) => runSim(applianceId, () => postResumeSim(applianceId)),
    [runSim]
  );

  const dismissCommand = useCallback(() => setCommand(null), []);
  const reconnect = useCallback(() => setConnectionVersion((v) => v + 1), []);

  const latestAgeSeconds = latestReceivedAt == null ? null : Math.max(0, Math.round((now - latestReceivedAt) / 1000));
  const isLive =
    streamStatus === 'open' &&
    !!device?.deviceOnline &&
    latest != null &&
    latestAgeSeconds != null &&
    latestAgeSeconds <= LIVE_MAX_AGE_S;

  const simById = useMemo(() => {
    const map: Record<string, SimApplianceLive> = {};
    for (const a of sim?.appliances ?? []) map[a.applianceId] = a;
    return map;
  }, [sim]);
  const simFresh = streamStatus === 'open' && simReceivedAt != null && now - simReceivedAt <= LIVE_MAX_AGE_S * 1000;
  const meteredPowerW = isLive ? latest?.activePowerW ?? 0 : 0;
  const simPowerW = simFresh ? sim?.totalPowerW ?? 0 : 0;
  const hasSim = (sim?.appliances.length ?? 0) > 0;
  const homeLive = isLive || (simFresh && hasSim);
  const homePowerW = homeLive ? meteredPowerW + simPowerW : latest?.activePowerW ?? null;
  // Without simulated appliances the home chart is just the metered chart (which is seeded from history).
  const homeChart = hasSim ? homePoints : points;

  const value = useMemo<LiveDataContextType>(
    () => ({
      streamStatus,
      mqttConnected,
      device,
      latest,
      isLive,
      latestAgeSeconds,
      points,
      relay,
      command,
      sendRelayCommand,
      dismissCommand,
      reconnect,
      sim,
      simById,
      sendSimCommand,
      resumeSimRoutine,
      simPending,
      simError,
      homePowerW,
      meteredPowerW,
      homePoints: homeChart,
      homeLive,
    }),
    [streamStatus, mqttConnected, device, latest, isLive, latestAgeSeconds, points, relay, command,
      sendRelayCommand, dismissCommand, reconnect, sim, simById, sendSimCommand, resumeSimRoutine, simPending,
      simError, homePowerW, meteredPowerW, homeChart, homeLive]
  );

  return <LiveDataContext.Provider value={value}>{children}</LiveDataContext.Provider>;
}
