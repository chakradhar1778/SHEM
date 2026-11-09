import { useEffect, useLayoutEffect, useRef, useState } from 'react';
import type { LiveTurn, LiveVoice } from '../../hooks/useLiveVoice';
import { ActionResultCard, AIComponentView } from './AIComponents';
import { Markdown } from './Markdown';
import './live.css';

const LANGUAGE_NAMES: Record<string, string> = {
  'en-IN': 'English', 'hi-IN': 'Hindi', 'bn-IN': 'Bengali', 'ta-IN': 'Tamil', 'te-IN': 'Telugu',
  'kn-IN': 'Kannada', 'ml-IN': 'Malayalam', 'mr-IN': 'Marathi', 'gu-IN': 'Gujarati', 'pa-IN': 'Punjabi',
  'od-IN': 'Odia', 'or-IN': 'Odia', 'as-IN': 'Assamese', 'ur-IN': 'Urdu', 'ne-IN': 'Nepali',
};

type OrbMode = 'connecting' | 'listening' | 'user' | 'thinking' | 'speaking' | 'muted' | 'error';

function orbMode(live: LiveVoice): OrbMode {
  if (live.phase === 'connecting') return 'connecting';
  if (live.phase !== 'live') return 'error';
  if (live.aiSpeaking) return 'speaking';
  if (live.userSpeaking) return 'user';
  if (live.agentState === 'thinking') return 'thinking';
  if (live.agentState === 'speaking') return 'speaking';
  if (live.muted) return 'muted';
  return 'listening';
}

const ORB_LABEL: Record<OrbMode, string> = {
  connecting: 'Connecting…',
  listening: 'Listening — just talk',
  user: 'Hearing you…',
  thinking: 'Thinking…',
  speaking: 'Speaking — tap to interrupt',
  muted: 'Mic muted',
  error: 'Not connected',
};

function Orb({ live, mode }: { live: LiveVoice; mode: OrbMode }) {
  const ref = useRef<HTMLButtonElement>(null);
  useEffect(() => {
    let raf = 0;
    let smooth = 0;
    const tick = () => {
      const target = mode === 'user' || mode === 'listening' ? live.levelRef.current : 0;
      smooth += (target - smooth) * 0.25;
      ref.current?.style.setProperty('--level', smooth.toFixed(3));
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => cancelAnimationFrame(raf);
  }, [live.levelRef, mode]);
  return (
    <button
      ref={ref}
      type="button"
      className={`ai-orb ai-orb--${mode}`}
      onClick={() => mode === 'speaking' && live.interrupt()}
      aria-label={mode === 'speaking' ? 'Stop SHEM AI speaking' : ORB_LABEL[mode]}
    >
      <span className="ai-orb__ring" />
      <span className="ai-orb__ring ai-orb__ring--2" />
      <span className="ai-orb__core">
        {mode === 'speaking' ? (
          <span className="ai-orb__bars" aria-hidden="true"><i /><i /><i /><i /></span>
        ) : mode === 'thinking' || mode === 'connecting' ? (
          <span className="ai-spinner ai-spinner--light" aria-hidden="true" />
        ) : (
          <svg viewBox="0 0 24 24" width="30" height="30" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <rect x="9" y="3" width="6" height="11" rx="3" />
            <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
            {mode === 'muted' && <path d="M4 4l16 16" />}
          </svg>
        )}
      </span>
    </button>
  );
}

function LiveTurnView({ turn, onFollowup }: { turn: LiveTurn; onFollowup?: (f: string) => void }) {
  const m = turn.message;
  const components = m.segments.filter((s) => s.type === 'component');
  const text = m.segments.filter((s) => s.type === 'text').map((s) => (s.type === 'text' ? s.content : '')).join('\n\n').trim();
  return (
    <div className="ai-live-turn">
      {turn.userText && <div className="ai-live-turn__user">“{turn.userText}”</div>}
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
      {components.map((s, i) => (s.type === 'component' ? <AIComponentView key={i} component={s.component} /> : null))}
      {m.actions.map((a, i) => <ActionResultCard key={i} action={a} />)}
      {text && (
        <details className="ai-live-turn__text">
          <summary>Reply text</summary>
          <Markdown text={text} />
        </details>
      )}
      {!turn.done && !components.length && !text && !m.error && (
        <div className="ai-typing" aria-label="SHEM AI is working"><i /><i /><i /></div>
      )}
      {m.error && <div className="ai-msg__error" role="alert">{m.error}</div>}
      {onFollowup && turn.done && m.followups.length > 0 && (
        <div className="ai-followups">
          {m.followups.map((f, i) => (
            <button key={i} type="button" className="ai-followup" onClick={() => onFollowup(f)}>{f}</button>
          ))}
        </div>
      )}
    </div>
  );
}

function Blocked({ live, onExit }: { live: LiveVoice; onExit: () => void }) {
  const info: Record<string, { icon: string; title: string; body: string }> = {
    unconfigured: {
      icon: '🎙️',
      title: 'Voice isn’t set up yet',
      body: 'Add SARVAM_API_KEY to the backend .env and restart it to use SHEM AI Live.',
    },
    'mic-denied': {
      icon: '🔇',
      title: 'Microphone unavailable',
      body: live.error ?? 'Allow microphone access for this site and try again.',
    },
    dropped: { icon: '📡', title: 'Connection lost', body: live.error ?? 'The live connection dropped.' },
    error: { icon: '⚠️', title: 'Live mode error', body: live.error ?? 'Something went wrong.' },
  };
  const i = info[live.phase] ?? info.error;
  const canRetry = live.phase !== 'unconfigured';
  return (
    <div className="ai-live-blocked" role="alert">
      <span className="ai-live-blocked__icon" aria-hidden="true">{i.icon}</span>
      <b>{i.title}</b>
      <p>{i.body}</p>
      <div className="ai-live-blocked__actions">
        {canRetry && (
          <button type="button" className="ai-live-btn ai-live-btn--primary" onClick={() => (live.phase === 'dropped' ? live.reconnect() : live.start(live.conversationId))}>
            {live.phase === 'dropped' ? 'Reconnect' : 'Try again'}
          </button>
        )}
        <button type="button" className="ai-live-btn" onClick={onExit}>Back to chat</button>
      </div>
    </div>
  );
}

/** SHEM AI Live: voice conversation with the AI's UI components rendered underneath. */
export function LiveView({ live, onExit }: { live: LiveVoice; onExit: () => void }) {
  const [text, setText] = useState('');
  const streamRef = useRef<HTMLDivElement>(null);
  const stick = useRef(true);
  const mode = orbMode(live);
  const blocked = live.phase === 'unconfigured' || live.phase === 'mic-denied' || live.phase === 'dropped' || live.phase === 'error';

  useLayoutEffect(() => {
    const el = streamRef.current;
    if (el && stick.current) el.scrollTop = el.scrollHeight;
  }, [live.turns]);

  const langName = live.language ? LANGUAGE_NAMES[live.language] ?? live.language : null;
  const lastTurn = live.turns[live.turns.length - 1];

  return (
    <div className="ai-live">
      <section className="ai-live__stage">
        <Orb live={live} mode={mode} />
        <div className="ai-live__status">
          <span>{ORB_LABEL[mode]}</span>
          {langName && <span className="ai-live__lang" title="Detected language">🌐 {langName}</span>}
        </div>
        <div className="ai-live__captions" aria-live="polite">
          {live.partial ? (
            <p className="ai-live__partial">{live.partial}</p>
          ) : live.lastUserText ? (
            <p className="ai-live__you"><b>You</b> {live.lastUserText}</p>
          ) : (
            !blocked && live.phase === 'live' && <p className="ai-live__hint">Try “How much energy did I use today?” or “Turn off the bulb”.</p>
          )}
          {live.spokenText && <p className="ai-live__ai"><b>SHEM AI</b> {live.spokenText}</p>}
        </div>
      </section>

      {blocked ? (
        <Blocked live={live} onExit={onExit} />
      ) : (
        <div
          className="ai-live__stream"
          ref={streamRef}
          onScroll={(e) => {
            const el = e.currentTarget;
            stick.current = el.scrollHeight - el.scrollTop - el.clientHeight < 80;
          }}
        >
          {!live.turns.length && <p className="ai-muted ai-live__empty">Charts, cards and controls SHEM AI creates will appear here while you talk.</p>}
          {live.turns.map((t) => (
            <LiveTurnView key={t.turnId} turn={t} onFollowup={t === lastTurn ? live.sendText : undefined} />
          ))}
        </div>
      )}

      <form
        className="ai-live__controls"
        onSubmit={(e) => {
          e.preventDefault();
          if (!text.trim() || live.phase !== 'live') return;
          live.sendText(text);
          setText('');
        }}
      >
        <button
          type="button"
          className={`ai-live-ctl ${live.muted ? 'is-off' : ''}`}
          onClick={() => live.setMuted(!live.muted)}
          disabled={live.phase !== 'live'}
          aria-pressed={live.muted}
          aria-label={live.muted ? 'Unmute microphone' : 'Mute microphone'}
          title={live.muted ? 'Unmute' : 'Mute'}
        >
          <svg viewBox="0 0 24 24" width="19" height="19" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" aria-hidden="true">
            <rect x="9" y="3" width="6" height="11" rx="3" />
            <path d="M5 11a7 7 0 0 0 14 0M12 18v3" />
            {live.muted && <path d="M4 4l16 16" />}
          </svg>
        </button>
        <input
          className="ai-live__input"
          value={text}
          maxLength={4000}
          onChange={(e) => setText(e.target.value)}
          placeholder={live.phase === 'live' ? 'Or type here…' : 'Not connected'}
          disabled={live.phase !== 'live'}
          aria-label="Type a message in Live mode"
        />
        <button type="button" className="ai-live-ctl ai-live-ctl--end" onClick={onExit} aria-label="End live session" title="End live">
          <svg viewBox="0 0 24 24" width="19" height="19" fill="currentColor" aria-hidden="true">
            <path d="M12 9c-2.6 0-5 .6-7.2 1.7-.7.3-1 1-.9 1.7l.4 2c.1.6.7 1 1.3.9l2.6-.4c.6-.1 1-.6 1-1.2v-1.5c1.8-.5 3.8-.5 5.6 0v1.5c0 .6.4 1.1 1 1.2l2.6.4c.6.1 1.2-.3 1.3-.9l.4-2c.1-.7-.2-1.4-.9-1.7C17 9.6 14.6 9 12 9z" />
          </svg>
        </button>
      </form>
    </div>
  );
}
