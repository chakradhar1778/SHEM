/** SHEM AI — wire types (mirror backend/app/ai). */

export type Tone = 'good' | 'warn' | 'bad' | 'neutral' | 'info';

export interface MetricItem {
  label: string;
  value: number | string;
  unit?: string;
  delta?: string;
  trend?: 'up' | 'down' | 'flat';
  tone?: Tone;
}

export interface ChartPoint { x: string | number; y: number | null }
export interface ChartSeries { name: string; points: ChartPoint[] }

export type AIComponent =
  | { type: 'metric_cards'; title?: string; items: MetricItem[] }
  | { type: 'chart'; chartType: 'line' | 'bar' | 'area'; title?: string; xLabel?: string; yLabel?: string; unit?: string; series: ChartSeries[] }
  | { type: 'breakdown'; title?: string; unit?: string; items: { label: string; value: number; unit?: string }[] }
  | { type: 'progress'; label: string; current: number; target: number; unit?: string; caption?: string; tone?: Tone }
  | { type: 'table'; title?: string; columns: string[]; rows: (string | number | null)[][] }
  | { type: 'appliance_card'; applianceId: string; name?: string }
  | { type: 'relay_control'; channel: number; label?: string }
  | { type: 'alert'; severity: 'info' | 'warning' | 'critical' | 'success'; title: string; message: string; conflictId?: string }
  | { type: 'recommendations'; title?: string; items: { title: string; description: string; impact?: string; priority?: 'high' | 'medium' | 'low' }[] }
  | { type: 'action_buttons'; buttons: { label: string; prompt: string }[] }
  | { type: 'bill_card'; billId: string }
  | { type: 'timeline'; title?: string; items: { time: string; title: string; description?: string }[] }
  | ActionResult;

export interface ActionResult {
  type: 'action_result';
  tool: string;
  status: 'success' | 'pending' | 'error';
  title: string;
  detail?: string;
  entityType?: string;
  entityId?: string;
  commandId?: string;
}

export type Segment =
  | { type: 'text'; content: string }
  | { type: 'component'; component: AIComponent };

export interface ChatMessage {
  id: number;
  role: 'user' | 'assistant';
  content: string;
  segments: Segment[];
  followups: string[];
  actions: ActionResult[];
  provider: string | null;
  createdAt: string;
}

export interface ConversationSummary {
  id: string;
  title: string;
  createdAt: string;
  updatedAt: string;
}

export interface ConversationDetail extends ConversationSummary {
  messages: ChatMessage[];
}

export interface AIStatus {
  enabled: boolean;
  configured: boolean;
  primaryProvider: 'gemini' | 'groq';
  providers: { name: string; model: string; configured: boolean }[];
}

export interface Suggestion {
  label: string;
  prompt: string;
  icon: string;
}

export type ConflictSeverity = 'info' | 'warning' | 'critical';

export interface Conflict {
  id: string;
  severity: ConflictSeverity;
  category: string;
  title: string;
  message: string;
  evidence: string;
  suggestion: string | null;
  entityType: string | null;
  entityId: string | null;
  dismissed: boolean;
}

export interface ConflictsResponse {
  scannedAt: string;
  conflicts: Conflict[];
}

export interface DailyInsight {
  date: string;
  headline: string;
  segments: Segment[];
  facts: Record<string, unknown>;
  provider: string | null;
  generatedAt: string;
}

export interface AIActionLogEntry {
  id: number;
  conversationId: string | null;
  tool: string;
  arguments: Record<string, unknown>;
  ok: boolean;
  summary: string | null;
  error: string | null;
  createdAt: string;
}

export interface AIActionEvent {
  tool: string;
  summary: string | null;
  entityType: string | null;
  entityId: string | null;
}

/** Server-sent events of POST /api/ai/chat/stream. */
export type ChatStreamEvent =
  | { event: 'conversation'; data: { conversationId: string; title: string } }
  | { event: 'provider'; data: { name: string } }
  | { event: 'text'; data: { delta: string } }
  | { event: 'component'; data: { component: AIComponent } }
  | { event: 'tool_start'; data: { id: string; name: string; label: string } }
  | { event: 'tool_end'; data: { id: string; name: string; ok: boolean; summary: string | null } }
  | { event: 'action'; data: { component: ActionResult } }
  | { event: 'fallback'; data: { from: string; to: string; discardPartial: boolean } }
  | { event: 'reset'; data: { segments: Segment[] } }
  | { event: 'followups'; data: { followups: string[] } }
  | { event: 'done'; data: { conversationId: string; message: ChatMessage } }
  | { event: 'error'; data: { message: string } };

// ── Live voice (WebSocket /api/ai/voice/live) ────────────────────────────────

export interface VoiceStatus {
  configured: boolean;
  sttModel: string;
  ttsModel: string;
  speaker: string;
  language: string;
  bargeIn: boolean;
}

export type LiveAgentState = 'listening' | 'thinking' | 'speaking';

/** JSON frames the server sends on the live socket. */
export type LiveServerMessage =
  | { type: 'ready'; conversationId: string | null; language: string }
  | { type: 'state'; state: LiveAgentState }
  | { type: 'vad'; speaking: boolean }
  | { type: 'transcript'; final: boolean; text: string; language: string | null }
  | { type: 'turn_start'; turnId: string; text: string }
  | { type: 'agent'; turnId: string; event: ChatStreamEvent['event']; data: unknown }
  | { type: 'audio'; turnId: string; seq: number; format: string; audio: string; text: string }
  | { type: 'audio_end'; turnId: string }
  | { type: 'interrupt_playback'; turnId: string | null }
  | { type: 'turn_end'; turnId: string }
  | { type: 'error'; message: string; fatal: boolean };

/** JSON frames the client sends (audio goes as binary PCM16LE 16 kHz mono). */
export type LiveClientMessage =
  | { type: 'start'; conversationId?: string }
  | { type: 'text'; message: string }
  | { type: 'mute'; muted: boolean }
  | { type: 'interrupt' }
  | { type: 'playback_done'; turnId: string }
  | { type: 'stop' };
