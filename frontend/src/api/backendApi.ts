/**
 * SHEM — Backend API client.
 *
 * The frontend talks ONLY to the SHEM FastAPI backend (never to EMQX).
 *
 * Connection settings (base URL + API key) come from, in order:
 *   1. values saved on this device in Settings → Backend connection
 *   2. build-time env: VITE_API_BASE_URL, VITE_API_KEY
 *   3. defaults: same origin ('' → Vite dev proxy or the backend serving the build)
 *
 * Only these connection settings are stored in localStorage; no household,
 * bill, target or telemetry data is kept in the browser.
 */

const CONNECTION_STORAGE_KEY = 'shem_backend_connection';
export const CONNECTION_CHANGED_EVENT = 'shem:connection-changed';
/** Fired (CustomEvent, detail = AIActionEvent) when backend data changed elsewhere, e.g. by SHEM AI. */
export const DATA_CHANGED_EVENT = 'shem:data-changed';
/** AI stream events re-broadcast on window by LiveDataProvider. */
export const AI_CONFLICT_EVENT = 'shem:ai-conflict';
export const AI_DAILY_INSIGHT_EVENT = 'shem:ai-daily-insight';
export const RELAY_UPDATE_EVENT = 'shem:relay-update';
/** A new notification arrived on the live stream (detail = NotificationItem). */
export const NOTIFICATION_EVENT = 'shem:notification';

export function emitWindowEvent(name: string, detail?: unknown): void {
  window.dispatchEvent(new CustomEvent(name, { detail }));
}

export interface BackendConnection {
  baseUrl: string;
  apiKey: string;
}

function readStoredConnection(): Partial<BackendConnection> {
  try {
    const raw = localStorage.getItem(CONNECTION_STORAGE_KEY);
    return raw ? (JSON.parse(raw) as Partial<BackendConnection>) : {};
  } catch {
    return {};
  }
}

export function getConnection(): BackendConnection {
  const stored = readStoredConnection();
  const baseUrl = (stored.baseUrl ?? import.meta.env.VITE_API_BASE_URL ?? '').trim().replace(/\/+$/, '');
  const apiKey = (stored.apiKey ?? import.meta.env.VITE_API_KEY ?? '').trim();
  return { baseUrl, apiKey };
}

export function saveConnection(connection: BackendConnection): void {
  try {
    localStorage.setItem(
      CONNECTION_STORAGE_KEY,
      JSON.stringify({ baseUrl: connection.baseUrl.trim(), apiKey: connection.apiKey.trim() })
    );
  } catch {
    /* storage unavailable — settings apply for this session only */
  }
  window.dispatchEvent(new Event(CONNECTION_CHANGED_EVENT));
}

export function clearSavedConnection(): void {
  try {
    localStorage.removeItem(CONNECTION_STORAGE_KEY);
  } catch {
    /* ignore */
  }
  window.dispatchEvent(new Event(CONNECTION_CHANGED_EVENT));
}

export class ApiError extends Error {
  status: number;

  constructor(status: number, message: string) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
  }
}

export function errorMessage(err: unknown): string {
  if (err instanceof ApiError) return err.message;
  if (err instanceof Error) return err.message;
  return 'Unexpected error';
}

interface RequestOptions {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE';
  body?: unknown;
  signal?: AbortSignal;
}

function describeFailure(status: number, detail: unknown, fallback: string): string {
  if (status === 401) return 'The backend rejected the API key. Set it in Settings → Backend connection.';
  if (status === 429) return 'Too many requests — please wait a moment and try again.';
  if (typeof detail === 'string' && detail) return detail;
  if (Array.isArray(detail)) {
    const msgs = detail
      .map((d) => (d && typeof d === 'object' && 'msg' in d ? String((d as { msg: unknown }).msg) : ''))
      .filter(Boolean);
    if (msgs.length) return msgs.join('; ');
  }
  return fallback;
}

export async function apiRequest<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const { baseUrl, apiKey } = getConnection();
  const headers: Record<string, string> = {};
  if (options.body !== undefined) headers['Content-Type'] = 'application/json';
  if (apiKey) headers['X-API-Key'] = apiKey;

  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, {
      method: options.method ?? 'GET',
      headers,
      body: options.body !== undefined ? JSON.stringify(options.body) : undefined,
      signal: options.signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err;
    throw new ApiError(0, 'Cannot reach the SHEM backend. Check that it is running and the backend URL is correct.');
  }

  if (!response.ok) {
    let detail: unknown;
    try {
      detail = ((await response.json()) as { detail?: unknown }).detail;
    } catch {
      detail = undefined;
    }
    throw new ApiError(response.status, describeFailure(response.status, detail, `Request failed (${response.status})`));
  }

  if (response.status === 204) return undefined as T;
  return (await response.json()) as T;
}

async function rawFetch(path: string, init: RequestInit): Promise<Response> {
  const { baseUrl, apiKey } = getConnection();
  const headers = new Headers(init.headers);
  if (apiKey) headers.set('X-API-Key', apiKey);
  let response: Response;
  try {
    response = await fetch(`${baseUrl}${path}`, { ...init, headers });
  } catch {
    throw new ApiError(0, 'Cannot reach the SHEM backend. Check that it is running and the backend URL is correct.');
  }
  if (!response.ok) {
    let detail: unknown;
    try {
      detail = ((await response.json()) as { detail?: unknown }).detail;
    } catch {
      detail = undefined;
    }
    throw new ApiError(response.status, describeFailure(response.status, detail, `Request failed (${response.status})`));
  }
  return response;
}

/** Send a file as the raw request body (Content-Type = the file's type); JSON response. */
export async function apiUpload<T>(path: string, file: Blob, method = 'PUT'): Promise<T> {
  const response = await rawFetch(path, {
    method,
    body: file,
    headers: { 'Content-Type': file.type || 'application/octet-stream' },
  });
  return (await response.json()) as T;
}

/** Download an authenticated file as a Blob (e.g. to show it via an object URL). */
export async function apiBlob(path: string): Promise<Blob> {
  return (await rawFetch(path, { method: 'GET' })).blob();
}

/** ws(s):// URL for the live stream; browsers cannot send headers, so the key goes in the query. */
export function websocketUrl(path: string): string {
  const { baseUrl, apiKey } = getConnection();
  const url = new URL(`${baseUrl}${path}`, window.location.href);
  url.protocol = url.protocol === 'https:' ? 'wss:' : 'ws:';
  if (apiKey) url.searchParams.set('api_key', apiKey);
  return url.toString();
}

/** Client-generated IDs let optimistic UI updates and the server agree on identity. */
export function newId(prefix: string): string {
  const rand = typeof crypto !== 'undefined' && 'randomUUID' in crypto
    ? crypto.randomUUID().replace(/-/g, '').slice(0, 12)
    : Math.random().toString(36).slice(2, 14);
  return `${prefix}-${rand}`;
}
