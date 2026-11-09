import { useCallback, useEffect, useMemo, useRef, useState, type ReactNode } from 'react';
import {
  AI_CONFLICT_EVENT,
  AI_DAILY_INSIGHT_EVENT,
  CONNECTION_CHANGED_EVENT,
  DATA_CHANGED_EVENT,
  errorMessage,
  RELAY_UPDATE_EVENT,
} from '../api/backendApi';
import {
  deleteConversation,
  dismissConflict as apiDismissConflict,
  fetchAIStatus,
  fetchConflicts,
  fetchConversation,
  fetchConversations,
  fetchLatestDailyInsight,
  fetchSuggestions,
  generateDailyInsight,
  streamChat,
} from '../api/aiApi';
import type {
  AIStatus,
  ChatStreamEvent,
  Conflict,
  ConversationSummary,
  DailyInsight,
  Suggestion,
} from '../api/aiTypes';
import type { RelayCommandDetail } from '../api/types';
import { AIContext, type AIContextType, type UiMessage } from './aiContextDef';
import { applyStreamEvent, emptyAssistant, finishMessage, fromChatMessage, nextKey, userMessage } from './aiStream';

const CONFLICT_POLL_MS = 120_000;

export function AIProvider({ children }: { children: ReactNode }) {
  const [open, setOpenState] = useState(false);
  const [status, setStatus] = useState<AIStatus | null>(null);
  const [suggestions, setSuggestions] = useState<Suggestion[]>([]);
  const [conflicts, setConflicts] = useState<Conflict[]>([]);
  const [insight, setInsight] = useState<DailyInsight | null>(null);
  const [insightLoading, setInsightLoading] = useState(false);
  const [conversations, setConversations] = useState<ConversationSummary[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);
  const [messages, setMessages] = useState<UiMessage[]>([]);
  const [streaming, setStreaming] = useState(false);
  const [commandStatus, setCommandStatus] = useState<Record<string, string>>({});
  const abortRef = useRef<AbortController | null>(null);
  const convRef = useRef<string | null>(null);
  useEffect(() => {
    convRef.current = conversationId;
  }, [conversationId]);

  // ── Background data: conflicts, status, daily insight ──────────────────────
  const loadConflicts = useCallback(async () => {
    try {
      setConflicts((await fetchConflicts(false)).conflicts);
    } catch {
      /* keep last known */
    }
  }, []);

  const loadInsight = useCallback(async () => {
    try {
      setInsight(await fetchLatestDailyInsight());
    } catch {
      /* keep last known */
    }
  }, []);

  const loadSuggestions = useCallback(async () => {
    try {
      setSuggestions(await fetchSuggestions());
    } catch {
      /* chips simply don't show */
    }
  }, []);

  const loadStatus = useCallback(async () => {
    try {
      setStatus(await fetchAIStatus());
    } catch {
      setStatus(null);
    }
  }, []);

  const loadConversations = useCallback(async () => {
    try {
      setConversations(await fetchConversations());
    } catch {
      /* ignore */
    }
  }, []);

  useEffect(() => {
    const all = () => {
      void loadConflicts();
      void loadInsight();
      void loadStatus();
    };
    all();
    const onData = () => void loadConflicts();
    const onConflict = () => void loadConflicts();
    const onInsight = (e: Event) => {
      const detail = (e as CustomEvent<DailyInsight>).detail;
      if (detail && detail.date) setInsight((prev) => (!prev || detail.date >= prev.date ? detail : prev));
      else void loadInsight();
    };
    const onRelay = (e: Event) => {
      const d = (e as CustomEvent<RelayCommandDetail>).detail;
      if (d?.commandId) setCommandStatus((prev) => ({ ...prev, [d.commandId]: d.status }));
    };
    window.addEventListener(CONNECTION_CHANGED_EVENT, all);
    window.addEventListener(DATA_CHANGED_EVENT, onData);
    window.addEventListener(AI_CONFLICT_EVENT, onConflict);
    window.addEventListener(AI_DAILY_INSIGHT_EVENT, onInsight);
    window.addEventListener(RELAY_UPDATE_EVENT, onRelay);
    const timer = setInterval(() => void loadConflicts(), CONFLICT_POLL_MS);
    return () => {
      window.removeEventListener(CONNECTION_CHANGED_EVENT, all);
      window.removeEventListener(DATA_CHANGED_EVENT, onData);
      window.removeEventListener(AI_CONFLICT_EVENT, onConflict);
      window.removeEventListener(AI_DAILY_INSIGHT_EVENT, onInsight);
      window.removeEventListener(RELAY_UPDATE_EVENT, onRelay);
      clearInterval(timer);
    };
  }, [loadConflicts, loadInsight, loadStatus]);

  const setOpen = useCallback(
    (next: boolean) => {
      setOpenState(next);
      if (next) {
        void loadSuggestions();
        void loadStatus();
        void loadConflicts();
      }
    },
    [loadSuggestions, loadStatus, loadConflicts]
  );

  const dismissConflict = useCallback(async (id: string) => {
    setConflicts((prev) => prev.filter((c) => c.id !== id));
    try {
      await apiDismissConflict(id);
    } catch {
      void loadConflicts();
    }
  }, [loadConflicts]);

  const generateInsight = useCallback(async () => {
    setInsightLoading(true);
    try {
      setInsight(await generateDailyInsight());
    } catch {
      /* leave previous insight */
    } finally {
      setInsightLoading(false);
    }
  }, []);

  // ── Chat ───────────────────────────────────────────────────────────────────
  const patchMessage = useCallback((key: string, fn: (m: UiMessage) => UiMessage) => {
    setMessages((prev) => prev.map((m) => (m.key === key ? fn(m) : m)));
  }, []);

  const send = useCallback(
    (raw: string) => {
      const text = raw.trim();
      if (!text || abortRef.current) return;
      const userKey = nextKey('u');
      const botKey = nextKey('a');
      setMessages((prev) => [
        ...prev.map((m) => (m.followups.length ? { ...m, followups: [] } : m)),
        userMessage(userKey, text),
        emptyAssistant(botKey),
      ]);
      const controller = new AbortController();
      abortRef.current = controller;
      setStreaming(true);

      const onEvent = (ev: ChatStreamEvent) => {
        if (ev.event === 'conversation' || ev.event === 'done') setConversationId(ev.data.conversationId);
        if (ev.event !== 'conversation') patchMessage(botKey, (m) => applyStreamEvent(m, ev));
      };

      streamChat({ message: text, conversationId: convRef.current ?? undefined }, onEvent, controller.signal)
        .catch((err) => {
          const aborted = err instanceof DOMException && err.name === 'AbortError';
          patchMessage(botKey, (m) => ({ ...m, error: aborted ? null : errorMessage(err), notice: aborted ? 'Stopped' : m.notice }));
        })
        .finally(() => {
          patchMessage(botKey, finishMessage);
          abortRef.current = null;
          setStreaming(false);
          void loadConversations();
          void loadSuggestions();
        });
    },
    [patchMessage, loadConversations, loadSuggestions]
  );

  const stop = useCallback(() => abortRef.current?.abort(), []);

  const newChat = useCallback(() => {
    abortRef.current?.abort();
    setConversationId(null);
    setMessages([]);
    void loadSuggestions();
  }, [loadSuggestions]);

  const openConversation = useCallback(async (id: string) => {
    abortRef.current?.abort();
    try {
      const detail = await fetchConversation(id);
      setConversationId(detail.id);
      const list = detail.messages.map(fromChatMessage);
      // follow-ups only make sense on the latest reply
      setMessages(list.map((m, i) => (i === list.length - 1 ? m : { ...m, followups: [] })));
    } catch (err) {
      setMessages([{ key: nextKey('e'), role: 'assistant', segments: [], followups: [], actions: [], tools: [], provider: null, streaming: false, error: errorMessage(err), notice: null }]);
    }
  }, []);

  const removeConversation = useCallback(async (id: string) => {
    setConversations((prev) => prev.filter((c) => c.id !== id));
    if (convRef.current === id) {
      setConversationId(null);
      setMessages([]);
    }
    try {
      await deleteConversation(id);
    } catch {
      void loadConversations();
    }
  }, [loadConversations]);

  useEffect(() => () => abortRef.current?.abort(), []);

  const alertCount = conflicts.filter((c) => !c.dismissed && (c.severity === 'critical' || c.severity === 'warning')).length;

  const value = useMemo<AIContextType>(
    () => ({
      open, setOpen, status, suggestions, conflicts, alertCount, dismissConflict, insight, insightLoading,
      generateInsight, conversations, loadConversations, conversationId, messages, streaming, send, stop,
      newChat, openConversation, removeConversation, commandStatus,
    }),
    [open, setOpen, status, suggestions, conflicts, alertCount, dismissConflict, insight, insightLoading,
      generateInsight, conversations, loadConversations, conversationId, messages, streaming, send, stop,
      newChat, openConversation, removeConversation, commandStatus]
  );

  return <AIContext.Provider value={value}>{children}</AIContext.Provider>;
}
