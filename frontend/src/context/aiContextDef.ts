import { createContext } from 'react';
import type {
  ActionResult,
  AIStatus,
  Conflict,
  ConversationSummary,
  DailyInsight,
  Segment,
  Suggestion,
} from '../api/aiTypes';

export interface ToolActivity {
  id: string;
  name: string;
  label: string;
  status: 'running' | 'ok' | 'error';
  summary: string | null;
}

/** A chat message as rendered (streamed or loaded from history). */
export interface UiMessage {
  key: string;
  role: 'user' | 'assistant';
  segments: Segment[];
  followups: string[];
  actions: ActionResult[];
  tools: ToolActivity[];
  provider: string | null;
  streaming: boolean;
  error: string | null;
  notice: string | null;
}

export interface AIContextType {
  open: boolean;
  setOpen: (open: boolean) => void;
  status: AIStatus | null;
  suggestions: Suggestion[];
  conflicts: Conflict[];
  /** Count of open warning/critical conflicts (FAB badge). */
  alertCount: number;
  dismissConflict: (id: string) => Promise<void>;
  insight: DailyInsight | null;
  insightLoading: boolean;
  generateInsight: () => Promise<void>;
  conversations: ConversationSummary[];
  loadConversations: () => Promise<void>;
  conversationId: string | null;
  messages: UiMessage[];
  streaming: boolean;
  send: (text: string) => void;
  stop: () => void;
  newChat: () => void;
  openConversation: (id: string) => Promise<void>;
  removeConversation: (id: string) => Promise<void>;
  /** Live status of relay commands started by SHEM AI (commandId → status). */
  commandStatus: Record<string, string>;
}

export const AIContext = createContext<AIContextType | null>(null);
