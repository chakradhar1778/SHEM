import { useCallback, useEffect, useMemo, useRef, useState } from 'react';
import { errorMessage, websocketUrl } from '../api/backendApi';
import { fetchVoiceStatus } from '../api/aiApi';
import type { ChatStreamEvent, LiveAgentState, LiveClientMessage, LiveServerMessage, VoiceStatus } from '../api/aiTypes';
import type { UiMessage } from '../context/aiContextDef';
import { applyStreamEvent, emptyAssistant, finishMessage, nextKey } from '../context/aiStream';
import { MicCapture, MicPermissionError, SpeechPlayer } from '../utils/liveAudio';

export type LivePhase =
  | 'idle'
  | 'connecting'
  | 'live'
  | 'unconfigured'   // backend has no Sarvam key
  | 'mic-denied'
  | 'dropped'        // socket closed unexpectedly — can reconnect
  | 'error';

export interface LiveTurn {
  turnId: string;
  userText: string;
  message: UiMessage;
  done: boolean;
}

export interface LiveVoice {
  phase: LivePhase;
  error: string | null;
  voiceStatus: VoiceStatus | null;
  agentState: LiveAgentState;
  userSpeaking: boolean;
  aiSpeaking: boolean;
  muted: boolean;
  partial: string;
  lastUserText: string;
  spokenText: string;
  language: string | null;
  turns: LiveTurn[];
  conversationId: string | null;
  /** Mic RMS level 0..1, updated without re-rendering (read it in rAF). */
  levelRef: React.MutableRefObject<number>;
  /** Must be called from a click/tap handler (autoplay + mic permission). */
  start: (conversationId: string | null) => void;
  reconnect: () => void;
  /** End the session; resolves with the conversation id used (for reloading Chat). */
  stop: () => string | null;
  setMuted: (muted: boolean) => void;
  interrupt: () => void;
  sendText: (text: string) => void;
}

const CLOSE_UNAUTHORIZED = 1008;
const CLOSE_NOT_CONFIGURED = 1013;

export function useLiveVoice(): LiveVoice {
  const [phase, setPhase] = useState<LivePhase>('idle');
  const [error, setError] = useState<string | null>(null);
  const [voiceStatus, setVoiceStatus] = useState<VoiceStatus | null>(null);
  const [agentState, setAgentState] = useState<LiveAgentState>('listening');
  const [userSpeaking, setUserSpeaking] = useState(false);
  const [aiSpeaking, setAiSpeaking] = useState(false);
  const [muted, setMutedState] = useState(false);
  const [partial, setPartial] = useState('');
  const [lastUserText, setLastUserText] = useState('');
  const [spokenText, setSpokenText] = useState('');
  const [language, setLanguage] = useState<string | null>(null);
  const [turns, setTurns] = useState<LiveTurn[]>([]);
  const [conversationId, setConversationId] = useState<string | null>(null);

  const levelRef = useRef(0);
  const ctxRef = useRef<AudioContext | null>(null);
  const micRef = useRef<MicCapture | null>(null);
  const playerRef = useRef<SpeechPlayer | null>(null);
  const wsRef = useRef<WebSocket | null>(null);
  const convRef = useRef<string | null>(null);
  const mutedRef = useRef(false);
  const closingRef = useRef(false);
  const sessionRef = useRef(0);

  const send = useCallback((msg: LiveClientMessage) => {
    const ws = wsRef.current;
    if (ws && ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify(msg));
  }, []);

  const patchTurn = useCallback((turnId: string, fn: (t: LiveTurn) => LiveTurn) => {
    setTurns((prev) => prev.map((t) => (t.turnId === turnId ? fn(t) : t)));
  }, []);

  const ensureTurn = useCallback((turnId: string, userText: string) => {
    setTurns((prev) =>
      prev.some((t) => t.turnId === turnId)
        ? prev.map((t) => (t.turnId === turnId && userText ? { ...t, userText } : t))
        : [...prev, { turnId, userText, message: emptyAssistant(nextKey('live')), done: false }]
    );
  }, []);

  const handleMessage = useCallback(
    (msg: LiveServerMessage) => {
      switch (msg.type) {
        case 'ready':
          if (msg.conversationId) {
            convRef.current = msg.conversationId;
            setConversationId(msg.conversationId);
          }
          if (msg.language) setLanguage(msg.language);
          setPhase('live');
          break;
        case 'state':
          setAgentState(msg.state);
          break;
        case 'vad':
          setUserSpeaking(msg.speaking);
          if (msg.speaking) setPartial('');
          break;
        case 'transcript':
          if (msg.language) setLanguage(msg.language);
          if (msg.final) {
            setPartial('');
            if (msg.text.trim()) setLastUserText(msg.text);
          } else {
            setPartial(msg.text);
          }
          break;
        case 'turn_start':
          setLastUserText(msg.text);
          setPartial('');
          setSpokenText('');
          ensureTurn(msg.turnId, msg.text);
          break;
        case 'agent': {
          const ev = { event: msg.event, data: msg.data } as ChatStreamEvent;
          if ((ev.event === 'conversation' || ev.event === 'done') && ev.data.conversationId) {
            convRef.current = ev.data.conversationId;
            setConversationId(ev.data.conversationId);
          }
          // Data refresh after AI actions arrives via the main WebSocket's ai_action event.
          ensureTurn(msg.turnId, '');
          if (ev.event !== 'conversation') {
            patchTurn(msg.turnId, (t) => ({
              ...t,
              message: applyStreamEvent(t.message, ev),
              done: t.done || ev.event === 'done' || ev.event === 'error',
            }));
          }
          break;
        }
        case 'audio':
          playerRef.current?.enqueue(msg.turnId, msg.seq, msg.audio, msg.text);
          break;
        case 'audio_end':
          playerRef.current?.end(msg.turnId);
          break;
        case 'interrupt_playback':
          playerRef.current?.interrupt(msg.turnId);
          setSpokenText('');
          break;
        case 'turn_end':
          patchTurn(msg.turnId, (t) => ({ ...t, done: true, message: finishMessage(t.message) }));
          break;
        case 'error':
          setError(msg.message);
          if (msg.fatal) setPhase('error');
          break;
        default:
          break;
      }
    },
    [ensureTurn, patchTurn]
  );

  const openSocket = useCallback(() => {
    const session = sessionRef.current;
    closingRef.current = false;
    setPhase('connecting');
    setError(null);
    let ws: WebSocket;
    try {
      ws = new WebSocket(websocketUrl('/api/ai/voice/live'));
    } catch (err) {
      setPhase('error');
      setError(errorMessage(err));
      return;
    }
    ws.binaryType = 'arraybuffer';
    wsRef.current = ws;
    ws.onopen = () => {
      if (session !== sessionRef.current) return;
      ws.send(JSON.stringify({ type: 'start', ...(convRef.current ? { conversationId: convRef.current } : {}) }));
      if (mutedRef.current) ws.send(JSON.stringify({ type: 'mute', muted: true }));
    };
    ws.onmessage = (e: MessageEvent) => {
      if (session !== sessionRef.current || typeof e.data !== 'string') return;
      try {
        handleMessage(JSON.parse(e.data) as LiveServerMessage);
      } catch {
        /* ignore malformed frame */
      }
    };
    ws.onclose = (e: CloseEvent) => {
      if (session !== sessionRef.current || wsRef.current !== ws) return;
      wsRef.current = null;
      playerRef.current?.interrupt();
      setUserSpeaking(false);
      if (closingRef.current) return;
      if (e.code === CLOSE_UNAUTHORIZED) {
        setPhase('error');
        setError('The backend rejected the API key. Check Settings → Backend connection.');
      } else if (e.code === CLOSE_NOT_CONFIGURED) {
        setPhase('unconfigured');
      } else {
        setPhase('dropped');
        setError(e.reason || 'The live connection was lost.');
      }
    };
  }, [handleMessage]);

  const teardown = useCallback(() => {
    closingRef.current = true;
    sessionRef.current += 1;
    const ws = wsRef.current;
    wsRef.current = null;
    if (ws) {
      try {
        if (ws.readyState === WebSocket.OPEN) ws.send(JSON.stringify({ type: 'stop' }));
        ws.close(1000);
      } catch {
        /* already closed */
      }
    }
    micRef.current?.stop();
    micRef.current = null;
    playerRef.current?.close();
    playerRef.current = null;
    const ctx = ctxRef.current;
    ctxRef.current = null;
    if (ctx && ctx.state !== 'closed') void ctx.close().catch(() => undefined);
    levelRef.current = 0;
  }, []);

  const start = useCallback(
    (initialConversationId: string | null) => {
      teardown();
      const session = sessionRef.current;
      convRef.current = initialConversationId;
      setConversationId(initialConversationId);
      setTurns([]);
      setPartial('');
      setLastUserText('');
      setSpokenText('');
      setError(null);
      setAgentState('listening');
      setPhase('connecting');

      // Created synchronously inside the user gesture so playback is allowed.
      let ctx: AudioContext;
      try {
        ctx = new AudioContext();
      } catch {
        setPhase('error');
        setError('This browser does not support Web Audio.');
        return;
      }
      ctxRef.current = ctx;
      void ctx.resume().catch(() => undefined);
      playerRef.current = new SpeechPlayer(ctx, {
        onSentence: (_turnId, text) => setSpokenText(text),
        onDrained: (turnId) => {
          send({ type: 'playback_done', turnId });
        },
        onPlaying: (p) => setAiSpeaking(p),
      });

      void (async () => {
        try {
          const vs = await fetchVoiceStatus();
          if (session !== sessionRef.current) return;
          setVoiceStatus(vs);
          if (!vs.configured) {
            setPhase('unconfigured');
            return;
          }
          if (vs.language && vs.language !== 'auto') setLanguage(vs.language);
        } catch (err) {
          if (session !== sessionRef.current) return;
          setPhase('error');
          setError(errorMessage(err));
          return;
        }
        const mic = new MicCapture(
          ctx,
          (pcm) => {
            const ws = wsRef.current;
            if (!mutedRef.current && ws && ws.readyState === WebSocket.OPEN) ws.send(pcm);
          },
          (rms) => {
            levelRef.current = Math.min(1, rms * 4);
          }
        );
        try {
          await mic.start();
        } catch (err) {
          mic.stop();
          if (session !== sessionRef.current) return;
          setPhase(err instanceof MicPermissionError ? 'mic-denied' : 'error');
          setError(err instanceof Error ? err.message : 'Could not start the microphone.');
          return;
        }
        if (session !== sessionRef.current) {
          mic.stop();
          return;
        }
        micRef.current = mic;
        mic.setEnabled(!mutedRef.current);
        openSocket();
      })();
    },
    [teardown, send, openSocket]
  );

  const reconnect = useCallback(() => {
    if (!ctxRef.current || !micRef.current) {
      start(convRef.current);
      return;
    }
    void ctxRef.current.resume().catch(() => undefined);
    sessionRef.current += 1;
    openSocket();
  }, [start, openSocket]);

  const stop = useCallback(() => {
    const id = convRef.current;
    teardown();
    setPhase('idle');
    setAiSpeaking(false);
    setUserSpeaking(false);
    return id;
  }, [teardown]);

  const setMuted = useCallback(
    (m: boolean) => {
      mutedRef.current = m;
      setMutedState(m);
      micRef.current?.setEnabled(!m);
      if (m) levelRef.current = 0;
      send({ type: 'mute', muted: m });
    },
    [send]
  );

  const interrupt = useCallback(() => {
    playerRef.current?.interrupt();
    setSpokenText('');
    send({ type: 'interrupt' });
  }, [send]);

  const sendText = useCallback(
    (text: string) => {
      const t = text.trim();
      if (!t) return;
      void ctxRef.current?.resume().catch(() => undefined);
      if (playerRef.current?.playing) interrupt();
      setLastUserText(t);
      send({ type: 'text', message: t });
    },
    [send, interrupt]
  );

  useEffect(() => teardown, [teardown]);

  return useMemo(
    () => ({
      phase, error, voiceStatus, agentState, userSpeaking, aiSpeaking, muted, partial, lastUserText, spokenText,
      language, turns, conversationId, levelRef, start, reconnect, stop, setMuted, interrupt, sendText,
    }),
    [phase, error, voiceStatus, agentState, userSpeaking, aiSpeaking, muted, partial, lastUserText, spokenText,
      language, turns, conversationId, start, reconnect, stop, setMuted, interrupt, sendText]
  );
}
