import { useCallback, useEffect, useLayoutEffect, useRef, useState, type KeyboardEvent } from 'react';
import type { Conflict, DailyInsight, Segment } from '../../api/aiTypes';
import { useAI } from '../../hooks/useAI';
import type { UiMessage } from '../../context/aiContextDef';
import { ActionResultCard, AIComponentView } from './AIComponents';
import { Markdown } from './Markdown';
import { LiveView } from './LiveView';
import { useLiveVoice } from '../../hooks/useLiveVoice';
import './ai.css';

const SUGGESTION_ICONS: Record<string, string> = {
  bolt: '⚡', chart: '📈', target: '🎯', bill: '🧾', alert: '⚠️', power: '🔌', tips: '💡', home: '🏠',
};

function SparkIcon({ size = 24 }: { size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="currentColor" aria-hidden="true">
      <path d="M12 2.5c.4 3.9 1.9 6.4 5.9 7.4-4 1-5.5 3.5-5.9 7.4-.4-3.9-1.9-6.4-5.9-7.4 4-1 5.5-3.5 5.9-7.4z" />
      <path d="M19 14.5c.2 1.9.9 3 2.8 3.5-1.9.5-2.6 1.6-2.8 3.5-.2-1.9-.9-3-2.8-3.5 1.9-.5 2.6-1.6 2.8-3.5z" opacity=".75" />
    </svg>
  );
}

function MicIcon({ size = 18 }: { size?: number }) {
  return (
    <svg viewBox="0 0 24 24" width={size} height={size} fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
      <rect x="9" y="3" width="6" height="11" rx="3" />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
    </svg>
  );
}

function Segments({ segments }: { segments: Segment[] }) {
  return (
    <>
      {segments.map((s, i) =>
        s.type === 'text' ? (s.content.trim() ? <Markdown key={i} text={s.content} /> : null) : <AIComponentView key={i} component={s.component} />
      )}
    </>
  );
}

function greeting(): string {
  const h = new Date().getHours();
  return h < 12 ? 'Good morning' : h < 17 ? 'Good afternoon' : 'Good evening';
}

// ── Empty state ──────────────────────────────────────────────────────────────
function InsightCard({ insight, loading, onRefresh }: { insight: DailyInsight; loading: boolean; onRefresh: () => void }) {
  const [expanded, setExpanded] = useState(false);
  return (
    <section className="ai-insight">
      <div className="ai-insight__head">
        <span className="ai-insight__tag">Daily briefing · {insight.date}</span>
        <button type="button" className="ai-icon-btn ai-icon-btn--sm" onClick={onRefresh} disabled={loading} aria-label="Regenerate briefing" title="Regenerate">
          {loading ? <span className="ai-spinner" /> : '↻'}
        </button>
      </div>
      <h3 className="ai-insight__headline">{insight.headline}</h3>
      <div className={`ai-insight__body ${expanded ? 'is-open' : ''}`}>
        <Segments segments={insight.segments} />
      </div>
      <button type="button" className="link-more" onClick={() => setExpanded((e) => !e)}>{expanded ? 'Show less' : 'Read briefing'}</button>
    </section>
  );
}

function ConflictList({ conflicts }: { conflicts: Conflict[] }) {
  const { dismissConflict, send, streaming } = useAI();
  if (!conflicts.length) return null;
  const order = { critical: 0, warning: 1, info: 2 } as const;
  const sorted = [...conflicts].sort((a, b) => order[a.severity] - order[b.severity]).slice(0, 4);
  return (
    <section className="ai-conflicts">
      <div className="ai-section-title">Flagged by SHEM AI</div>
      {sorted.map((c) => (
        <div key={c.id} className={`ai-alert ai-alert--${c.severity}`}>
          <span className="ai-alert__icon" aria-hidden="true">{c.severity === 'critical' ? '⛔' : c.severity === 'warning' ? '⚠️' : 'ℹ️'}</span>
          <div className="ai-alert__body">
            <b>{c.title}</b>
            <p>{c.message}</p>
            <div className="ai-alert__actions">
              <button type="button" className="link-more" disabled={streaming} onClick={() => send(`Explain this issue and how to fix it: "${c.title}" — ${c.message}`)}>Ask SHEM AI</button>
              <button type="button" className="link-more ai-muted-link" onClick={() => void dismissConflict(c.id)}>Dismiss</button>
            </div>
          </div>
        </div>
      ))}
    </section>
  );
}

function EmptyState({ onGoLive }: { onGoLive: () => void }) {
  const { suggestions, send, insight, insightLoading, generateInsight, conflicts, status } = useAI();
  return (
    <div className="ai-empty">
      <div className="ai-empty__hero">
        <span className="ai-empty__orb"><SparkIcon size={30} /></span>
        <h2>{greeting()}!</h2>
        <p>I'm SHEM AI, your energy guide. Ask about your usage, bills and targets, or tell me to switch things on and off.</p>
        <button type="button" className="ai-golive" onClick={onGoLive}>
          <span className="ai-golive__pulse" aria-hidden="true" /><MicIcon size={17} /> Go live — talk to SHEM AI
        </button>
      </div>
      {status && !status.configured && (
        <div className="ai-alert ai-alert--warning">
          <span className="ai-alert__icon" aria-hidden="true">⚠️</span>
          <div className="ai-alert__body"><b>AI provider not configured</b><p>Add GEMINI_API_KEY or GROQ_API_KEY to the backend .env and restart it.</p></div>
        </div>
      )}
      <ConflictList conflicts={conflicts.filter((c) => !c.dismissed)} />
      {insight ? (
        <InsightCard insight={insight} loading={insightLoading} onRefresh={() => void generateInsight()} />
      ) : (
        <button type="button" className="ai-insight ai-insight--cta" onClick={() => void generateInsight()} disabled={insightLoading}>
          {insightLoading ? <span className="ai-spinner" /> : '☀️'} Generate today's briefing
        </button>
      )}
      {suggestions.length > 0 && (
        <div className="ai-suggestions">
          <div className="ai-section-title">Try asking</div>
          {suggestions.map((s, i) => (
            <button key={i} type="button" className="ai-suggestion" onClick={() => send(s.prompt)}>
              <span aria-hidden="true">{SUGGESTION_ICONS[s.icon] ?? '✨'}</span>
              {s.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}

// ── Messages ─────────────────────────────────────────────────────────────────
function AssistantMessage({ m, isLast }: { m: UiMessage; isLast: boolean }) {
  const { send, streaming } = useAI();
  const empty = !m.segments.some((s) => s.type === 'component' || s.content.trim());
  return (
    <div className="ai-msg ai-msg--assistant">
      <span className="ai-msg__avatar"><SparkIcon size={16} /></span>
      <div className="ai-msg__content">
        {m.tools.length > 0 && (
          <div className="ai-tools">
            {m.tools.map((t) => (
              <span key={t.id} className={`ai-tool ai-tool--${t.status}`} title={t.summary ?? undefined}>
                {t.status === 'running' ? <span className="ai-spinner" /> : t.status === 'ok' ? '✓' : '!'} {t.label || t.name}
              </span>
            ))}
          </div>
        )}
        {m.notice && <div className="ai-notice">{m.notice}</div>}
        <Segments segments={m.segments} />
        {m.actions.map((a, i) => <ActionResultCard key={i} action={a} />)}
        {m.streaming && empty && (
          <div className="ai-typing" aria-label="SHEM AI is thinking"><i /><i /><i /></div>
        )}
        {m.error && <div className="ai-msg__error" role="alert">{m.error}</div>}
        {isLast && !m.streaming && m.followups.length > 0 && (
          <div className="ai-followups">
            {m.followups.map((f, i) => (
              <button key={i} type="button" className="ai-followup" disabled={streaming} onClick={() => send(f)}>{f}</button>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

function MessageList() {
  const { messages } = useAI();
  const ref = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  useLayoutEffect(() => {
    const el = ref.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [messages]);
  const lastAssistant = [...messages].reverse().find((m) => m.role === 'assistant')?.key;
  return (
    <div
      className="ai-messages"
      ref={ref}
      onScroll={(e) => {
        const el = e.currentTarget;
        stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
      }}
      aria-live="polite"
    >
      {messages.map((m) =>
        m.role === 'user' ? (
          <div key={m.key} className="ai-msg ai-msg--user">
            <div className="ai-bubble">{m.segments.map((s) => (s.type === 'text' ? s.content : '')).join('')}</div>
          </div>
        ) : (
          <AssistantMessage key={m.key} m={m} isLast={m.key === lastAssistant} />
        )
      )}
    </div>
  );
}

function History({ onPick }: { onPick: () => void }) {
  const { conversations, loadConversations, openConversation, removeConversation, conversationId } = useAI();
  useEffect(() => {
    void loadConversations();
  }, [loadConversations]);
  return (
    <div className="ai-history">
      <div className="ai-section-title">Recent chats</div>
      {!conversations.length && <p className="ai-muted">No conversations yet.</p>}
      {conversations.map((c) => (
        <div key={c.id} className={`ai-history__row ${c.id === conversationId ? 'is-current' : ''}`}>
          <button type="button" className="ai-history__open" onClick={() => { void openConversation(c.id); onPick(); }}>
            <b>{c.title || 'Chat'}</b>
            <span>{new Date(c.updatedAt).toLocaleString('en-IN', { dateStyle: 'medium', timeStyle: 'short' })}</span>
          </button>
          <button type="button" className="ai-icon-btn ai-icon-btn--sm" aria-label={`Delete ${c.title}`} onClick={() => void removeConversation(c.id)}>🗑</button>
        </div>
      ))}
    </div>
  );
}

function Composer({ onGoLive }: { onGoLive: () => void }) {
  const { send, stop, streaming, status } = useAI();
  const [text, setText] = useState('');
  const ref = useRef<HTMLTextAreaElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.style.height = 'auto';
    el.style.height = `${Math.min(el.scrollHeight, 120)}px`;
  }, [text]);
  useEffect(() => ref.current?.focus(), []);
  const submit = () => {
    if (!text.trim() || streaming) return;
    send(text);
    setText('');
  };
  const onKey = (e: KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey && !e.nativeEvent.isComposing) {
      e.preventDefault();
      submit();
    }
  };
  return (
    <form className="ai-composer" onSubmit={(e) => { e.preventDefault(); submit(); }}>
      <textarea
        ref={ref}
        rows={1}
        value={text}
        maxLength={4000}
        placeholder={status && !status.configured ? 'SHEM AI is not configured yet' : 'Ask SHEM AI anything…'}
        onChange={(e) => setText(e.target.value)}
        onKeyDown={onKey}
        aria-label="Message SHEM AI"
      />
      <button type="button" className="ai-icon-btn ai-composer__live" onClick={onGoLive} aria-label="Go live (voice)" title="Go live">
        <MicIcon />
      </button>
      {streaming ? (
        <button type="button" className="ai-send ai-send--stop" onClick={stop} aria-label="Stop generating"><span className="ai-stop-square" /></button>
      ) : (
        <button type="submit" className="ai-send" disabled={!text.trim()} aria-label="Send">
          <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2.2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 19V5M5 12l7-7 7 7" /></svg>
        </button>
      )}
    </form>
  );
}

function ChatPanel() {
  const { setOpen, newChat, messages, status, conversationId, openConversation, stop: stopChat } = useAI();
  const [view, setView] = useState<'chat' | 'history'>('chat');
  const [mode, setMode] = useState<'chat' | 'live'>('chat');
  const live = useLiveVoice();
  const liveStop = live.stop;
  const liveConvRef = useRef<string | null>(null);
  useEffect(() => {
    liveConvRef.current = live.conversationId;
  }, [live.conversationId]);

  // Must run inside the click handler: creates the AudioContext and asks for the mic.
  const goLive = useCallback(() => {
    stopChat();
    setView('chat');
    setMode('live');
    live.start(conversationId);
  }, [stopChat, live, conversationId]);

  const exitLive = useCallback(() => {
    const id = liveStop();
    setMode('chat');
    if (id) void openConversation(id); // show the live exchange as normal chat messages
  }, [liveStop, openConversation]);

  // Closing the popup while live: still bring the conversation into Chat for next time.
  const modeRef = useRef(mode);
  useEffect(() => {
    modeRef.current = mode;
  }, [mode]);
  useEffect(
    () => () => {
      if (modeRef.current === 'live' && liveConvRef.current) void openConversation(liveConvRef.current);
    },
    [openConversation]
  );
  const providerName = status?.providers.find((p) => p.configured && p.name === status.primaryProvider)?.name
    ?? status?.providers.find((p) => p.configured)?.name;

  useEffect(() => {
    const onKey = (e: globalThis.KeyboardEvent) => e.key === 'Escape' && setOpen(false);
    document.addEventListener('keydown', onKey);
    document.body.classList.add('ai-panel-open');
    return () => {
      document.removeEventListener('keydown', onKey);
      document.body.classList.remove('ai-panel-open');
    };
  }, [setOpen]);

  return (
    <>
      <div className="ai-backdrop" onClick={() => setOpen(false)} aria-hidden="true" />
      <aside className="ai-panel" role="dialog" aria-modal="true" aria-label={mode === 'live' ? 'SHEM AI Live' : 'SHEM AI chat'}>
        <header className="ai-panel__head">
          <span className="ai-panel__logo"><SparkIcon size={18} /></span>
          <div className="ai-panel__title">
            <b>SHEM AI</b>
            <span>
              <i className={`ai-dot ${status?.configured ? 'is-on' : ''}`} />
              {status?.configured ? `Energy guide · ${providerName ?? ''}` : status ? 'Not configured' : 'Connecting…'}
            </span>
          </div>
          <div className="ai-mode" role="tablist" aria-label="SHEM AI mode">
            <button type="button" role="tab" aria-selected={mode === 'chat'} className={mode === 'chat' ? 'is-active' : ''} onClick={() => mode === 'live' && exitLive()}>Chat</button>
            <button type="button" role="tab" aria-selected={mode === 'live'} className={mode === 'live' ? 'is-active' : ''} onClick={() => mode === 'chat' && goLive()}>
              <i className={`ai-mode__dot ${mode === 'live' && live.phase === 'live' ? 'is-on' : ''}`} />Live
            </button>
          </div>
          {mode === 'chat' && <><button type="button" className={`ai-icon-btn ${view === 'history' ? 'is-active' : ''}`} aria-label="Chat history" title="History" onClick={() => setView((v) => (v === 'history' ? 'chat' : 'history'))}>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M3 12a9 9 0 1 0 3-6.7L3 8" /><path d="M3 3v5h5M12 7v5l3 2" /></svg>
          </button>
          <button type="button" className="ai-icon-btn" aria-label="New chat" title="New chat" disabled={!messages.length && view === 'chat'} onClick={() => { newChat(); setView('chat'); }}>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="1.9" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true"><path d="M12 20h9M16.5 3.5a2.1 2.1 0 1 1 3 3L7 19l-4 1 1-4z" /></svg>
          </button></>}
          <button type="button" className="ai-icon-btn" aria-label="Close" onClick={() => setOpen(false)}>
            <svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true"><path d="M6 6l12 12M18 6 6 18" /></svg>
          </button>
        </header>
        {mode === 'live' ? (
          <LiveView live={live} onExit={exitLive} />
        ) : (
          <>
            {view === 'history' ? <History onPick={() => setView('chat')} /> : messages.length ? <MessageList /> : <div className="ai-messages"><EmptyState onGoLive={goLive} /></div>}
            <Composer onGoLive={goLive} />
          </>
        )}
      </aside>
    </>
  );
}

/** Floating SHEM AI button + chat panel; mount once inside AIProvider. */
export function AIAssistant() {
  const { open, setOpen, alertCount } = useAI();
  return (
    <>
      {!open && (
        <button type="button" className="ai-fab" onClick={() => setOpen(true)} aria-label={alertCount ? `Open SHEM AI (${alertCount} issues flagged)` : 'Open SHEM AI'}>
          <SparkIcon size={26} />
          {alertCount > 0 && <span className="ai-fab__badge">{alertCount > 9 ? '9+' : alertCount}</span>}
        </button>
      )}
      {open && <ChatPanel />}
    </>
  );
}
