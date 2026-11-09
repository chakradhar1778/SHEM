import type { ChatMessage, ChatStreamEvent, Segment } from '../api/aiTypes';
import type { UiMessage } from './aiContextDef';

let keySeq = 0;
export const nextKey = (p: string) => `${p}-${Date.now().toString(36)}-${(keySeq += 1)}`;

export function fromChatMessage(m: ChatMessage): UiMessage {
  return {
    key: `m-${m.id}`,
    role: m.role,
    segments: m.segments?.length ? m.segments : m.content ? [{ type: 'text', content: m.content }] : [],
    followups: m.followups ?? [],
    actions: m.actions ?? [],
    tools: [],
    provider: m.provider,
    streaming: false,
    error: null,
    notice: null,
  };
}

export function emptyAssistant(key: string): UiMessage {
  return { key, role: 'assistant', segments: [], followups: [], actions: [], tools: [], provider: null, streaming: true, error: null, notice: null };
}

export function userMessage(key: string, text: string): UiMessage {
  return { key, role: 'user', segments: [{ type: 'text', content: text }], followups: [], actions: [], tools: [], provider: null, streaming: false, error: null, notice: null };
}

function appendText(segments: Segment[], delta: string): Segment[] {
  const last = segments[segments.length - 1];
  if (last && last.type === 'text') return [...segments.slice(0, -1), { type: 'text', content: last.content + delta }];
  return [...segments, { type: 'text', content: delta }];
}

/**
 * Apply one agent stream event (chat SSE or Live `agent` frame) to the assistant message being built.
 * Shared by Chat and Live so both render the reply identically.
 */
export function applyStreamEvent(m: UiMessage, ev: ChatStreamEvent): UiMessage {
  switch (ev.event) {
    case 'provider':
      return { ...m, provider: ev.data.name };
    case 'text':
      return { ...m, segments: appendText(m.segments, ev.data.delta) };
    case 'component':
      return { ...m, segments: [...m.segments, { type: 'component', component: ev.data.component }] };
    case 'tool_start':
      return { ...m, tools: [...m.tools, { id: ev.data.id, name: ev.data.name, label: ev.data.label, status: 'running', summary: null }] };
    case 'tool_end':
      return { ...m, tools: m.tools.map((t) => (t.id === ev.data.id ? { ...t, status: ev.data.ok ? 'ok' : 'error', summary: ev.data.summary } : t)) };
    case 'action':
      return { ...m, actions: [...m.actions, ev.data.component] };
    case 'fallback':
      return { ...m, notice: `${ev.data.from} was unavailable — switched to ${ev.data.to}` };
    case 'reset':
      return { ...m, segments: ev.data.segments };
    case 'followups':
      return { ...m, followups: ev.data.followups };
    case 'done': {
      const final = fromChatMessage(ev.data.message);
      return { ...final, key: m.key, tools: m.tools, notice: m.notice };
    }
    case 'error':
      return { ...m, error: ev.data.message };
    default:
      return m;
  }
}

/** Close any still-running tool chips once a reply has finished. */
export function finishMessage(m: UiMessage): UiMessage {
  return { ...m, streaming: false, tools: m.tools.map((t) => (t.status === 'running' ? { ...t, status: 'error' } : t)) };
}
