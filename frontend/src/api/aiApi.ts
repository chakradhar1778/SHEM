import { ApiError, apiRequest, getConnection } from './backendApi';
import type {
  AIActionLogEntry,
  AIStatus,
  ChatMessage,
  ChatStreamEvent,
  ConflictsResponse,
  ConversationDetail,
  ConversationSummary,
  DailyInsight,
  Suggestion,
  VoiceStatus,
} from './aiTypes';

export const fetchAIStatus = () => apiRequest<AIStatus>('/api/ai/status');

export const fetchSuggestions = () =>
  apiRequest<{ suggestions: Suggestion[] }>('/api/ai/suggestions').then((r) => r.suggestions);

export const fetchConversations = () => apiRequest<ConversationSummary[]>('/api/ai/conversations');

export const fetchConversation = (id: string) =>
  apiRequest<ConversationDetail>(`/api/ai/conversations/${encodeURIComponent(id)}`);

export const deleteConversation = (id: string) =>
  apiRequest<void>(`/api/ai/conversations/${encodeURIComponent(id)}`, { method: 'DELETE' });

export const fetchConflicts = (includeDismissed = false) =>
  apiRequest<ConflictsResponse>(`/api/ai/conflicts?includeDismissed=${includeDismissed}`);

export const dismissConflict = (id: string) =>
  apiRequest<void>(`/api/ai/conflicts/${encodeURIComponent(id)}/dismiss`, { method: 'POST' });

export const fetchDailyInsights = (limit = 7) => apiRequest<DailyInsight[]>(`/api/ai/daily-insights?limit=${limit}`);

/** Latest daily briefing, or null if none has been generated yet. */
export async function fetchLatestDailyInsight(): Promise<DailyInsight | null> {
  try {
    return await apiRequest<DailyInsight>('/api/ai/daily-insights/latest');
  } catch (err) {
    if (err instanceof ApiError && err.status === 404) return null;
    throw err;
  }
}

export const generateDailyInsight = (date?: string) =>
  apiRequest<DailyInsight>('/api/ai/daily-insights/generate', { method: 'POST', body: date ? { date } : {} });

export const fetchAIActions = (limit = 50) => apiRequest<AIActionLogEntry[]>(`/api/ai/actions?limit=${limit}`);

export const sendChat = (message: string, conversationId?: string) =>
  apiRequest<{ conversationId: string; message: ChatMessage }>('/api/ai/chat', {
    method: 'POST',
    body: { message, conversationId },
  });

/**
 * POST /api/ai/chat/stream and call `onEvent` for every server-sent event.
 * Resolves when the stream ends; rejects with ApiError on HTTP errors.
 * Abort with `signal` (rejects with an AbortError DOMException).
 */
export async function streamChat(
  body: { message: string; conversationId?: string },
  onEvent: (event: ChatStreamEvent) => void,
  signal?: AbortSignal
): Promise<void> {
  const { baseUrl, apiKey } = getConnection();
  const headers: Record<string, string> = { 'Content-Type': 'application/json', Accept: 'text/event-stream' };
  if (apiKey) headers['X-API-Key'] = apiKey;

  let response: Response;
  try {
    response = await fetch(`${baseUrl}/api/ai/chat/stream`, {
      method: 'POST',
      headers,
      body: JSON.stringify(body),
      signal,
    });
  } catch (err) {
    if (err instanceof DOMException && err.name === 'AbortError') throw err;
    throw new ApiError(0, 'Cannot reach the SHEM backend.');
  }

  if (!response.ok || !response.body) {
    let detail = '';
    try {
      const j = (await response.json()) as { detail?: unknown };
      if (typeof j.detail === 'string') detail = j.detail;
    } catch {
      /* not JSON */
    }
    if (response.status === 401) detail = 'The backend rejected the API key. Set it in Settings → Backend connection.';
    if (response.status === 429) detail = 'You are sending messages too quickly — wait a moment.';
    throw new ApiError(response.status, detail || `SHEM AI request failed (${response.status})`);
  }

  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = '';

  const dispatch = (block: string) => {
    let name = 'message';
    const data: string[] = [];
    for (const line of block.split('\n')) {
      if (line.startsWith(':')) continue; // comment / keep-alive
      if (line.startsWith('event:')) name = line.slice(6).trim();
      else if (line.startsWith('data:')) data.push(line.slice(5).replace(/^ /, ''));
    }
    if (!data.length) return;
    try {
      onEvent({ event: name, data: JSON.parse(data.join('\n')) } as ChatStreamEvent);
    } catch {
      /* ignore malformed event */
    }
  };

  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true }).replace(/\r\n?/g, '\n');
    let idx: number;
    while ((idx = buffer.indexOf('\n\n')) !== -1) {
      dispatch(buffer.slice(0, idx));
      buffer = buffer.slice(idx + 2);
    }
  }
  buffer += decoder.decode();
  if (buffer.trim()) dispatch(buffer);
}

/** Sarvam voice (Live mode) availability. */
export const fetchVoiceStatus = () => apiRequest<VoiceStatus>('/api/ai/voice/status');
