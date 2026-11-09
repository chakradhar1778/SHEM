import { createContext } from 'react';
import type {
  DeviceStatus,
  RelayCommandStatus,
  RelayState,
  RelayStatus,
  SimApplianceLive,
  SimStatus,
  TelemetryReading,
} from '../api/types';

/** WebSocket stream state (backend ⇄ browser). */
export type StreamStatus = 'connecting' | 'open' | 'reconnecting' | 'unauthorized' | 'unreachable';

/** One point in the live power chart buffer. */
export interface LivePoint {
  t: number;        // epoch ms of measurement
  powerW: number;
}

export type RelayUiStatus = RelayCommandStatus | 'sending' | 'failed';

export interface RelayCommandUiState {
  commandId: string | null;
  requestedState: RelayState;
  status: RelayUiStatus;
  message: string | null;
  startedAt: number;
}

export interface LiveDataContextType {
  streamStatus: StreamStatus;
  /** Backend ⇄ EMQX broker connection (from heartbeat / device status). */
  mqttConnected: boolean | null;
  device: DeviceStatus | null;
  /** Most recent valid AC reading (may be old — check `isLive`). */
  latest: TelemetryReading | null;
  /** True only when the stream is open, the ESP32 is online and the reading is fresh. */
  isLive: boolean;
  /** Seconds since the latest reading was measured (null when none). */
  latestAgeSeconds: number | null;
  /** Recent power samples for charts (oldest → newest, ≈ last 10 minutes). */
  points: LivePoint[];
  relay: RelayStatus | null;
  command: RelayCommandUiState | null;
  /** Ask the backend to switch relay 1; resolves when the request is accepted (not applied). */
  sendRelayCommand: (state: RelayState) => Promise<void>;
  dismissCommand: () => void;
  reconnect: () => void;

  // ── Simulated appliances (every appliance without a relay) ──
  /** Latest simulation snapshot (pushed every ~2 s). */
  sim: SimStatus | null;
  /** Live state of one simulated appliance by id. */
  simById: Record<string, SimApplianceLive>;
  /** Switch a simulated appliance (applies immediately). */
  sendSimCommand: (applianceId: string, state: RelayState) => Promise<void>;
  /** Drop a manual override so the appliance follows its routine again. */
  resumeSimRoutine: (applianceId: string) => Promise<void>;
  /** Appliance ids with a sim command in flight. */
  simPending: ReadonlySet<string>;
  simError: { applianceId: string; message: string } | null;
  /** Live metered watts (only when the meter is live) + simulated watts. */
  homePowerW: number | null;
  /** Live metered watts counted in homePowerW (0 when the meter isn't live). */
  meteredPowerW: number;
  /** Home power samples (metered + simulated) for charts, ≈ last 10 minutes. */
  homePoints: LivePoint[];
  /** True when there is live data from the meter or from running simulations. */
  homeLive: boolean;
}

export const LiveDataContext = createContext<LiveDataContextType | null>(null);

export const TERMINAL_RELAY_STATUSES: ReadonlySet<RelayUiStatus> = new Set<RelayUiStatus>([
  'applied',
  'rejected_expired',
  'rejected_invalid_channel',
  'rejected_invalid_state',
  'rejected_time_unsynchronized',
  'timeout',
  'publish_failed',
  'failed',
]);
