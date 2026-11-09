/**
 * SHEM AI Live — browser audio plumbing.
 *
 * MicCapture: getUserMedia → AudioWorklet that box-filters + decimates to 16 kHz mono and emits
 *             Int16 little-endian PCM in 100 ms frames (1600 samples = 3200 bytes), plus an RMS level.
 * SpeechPlayer: plays base64 WAV sentences strictly in seq order per turn, gapless on the
 *               AudioContext timeline, and can stop everything instantly (barge-in).
 */

const TARGET_RATE = 16000;
const FRAME_SAMPLES = 1600; // 100 ms at 16 kHz

const WORKLET_SOURCE = `
class ShemPcm16k extends AudioWorkletProcessor {
  constructor() {
    super();
    this.ratio = sampleRate / ${TARGET_RATE};
    this.pos = 0; this.acc = 0; this.cnt = 0;
    this.rmsAcc = 0; this.rmsN = 0;
    this.buf = new Int16Array(${FRAME_SAMPLES}); this.n = 0;
    this.enabled = true;
    this.port.onmessage = (e) => { if (e.data && 'enabled' in e.data) this.enabled = !!e.data.enabled; };
  }
  process(inputs) {
    const ch = inputs[0] && inputs[0][0];
    if (!ch) return true;
    for (let i = 0; i < ch.length; i++) {
      const s = ch[i];
      this.acc += s; this.cnt++;
      this.rmsAcc += s * s; this.rmsN++;
      this.pos += 1;
      if (this.pos >= this.ratio) {
        this.pos -= this.ratio;
        const v = Math.max(-1, Math.min(1, this.acc / this.cnt));
        this.acc = 0; this.cnt = 0;
        this.buf[this.n++] = v < 0 ? v * 0x8000 : v * 0x7fff;
        if (this.n === this.buf.length) {
          const rms = Math.sqrt(this.rmsAcc / Math.max(1, this.rmsN));
          this.rmsAcc = 0; this.rmsN = 0; this.n = 0;
          if (this.enabled) {
            const out = this.buf;
            this.buf = new Int16Array(${FRAME_SAMPLES});
            this.port.postMessage({ pcm: out.buffer, rms }, [out.buffer]);
          } else {
            this.port.postMessage({ rms: 0 });
          }
        }
      }
    }
    return true;
  }
}
registerProcessor('shem-pcm16k', ShemPcm16k);
`;

export class MicPermissionError extends Error {}

export class MicCapture {
  private stream: MediaStream | null = null;
  private source: MediaStreamAudioSourceNode | null = null;
  private node: AudioWorkletNode | null = null;
  private sink: GainNode | null = null;
  private ctx: AudioContext;
  private onFrame: (pcm: ArrayBuffer) => void;
  private onLevel: (rms: number) => void;

  constructor(ctx: AudioContext, onFrame: (pcm: ArrayBuffer) => void, onLevel: (rms: number) => void) {
    this.ctx = ctx;
    this.onFrame = onFrame;
    this.onLevel = onLevel;
  }

  async start(): Promise<void> {
    if (!navigator.mediaDevices?.getUserMedia) throw new MicPermissionError('This browser cannot access the microphone (HTTPS is required).');
    try {
      this.stream = await navigator.mediaDevices.getUserMedia({
        audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true, channelCount: 1 },
      });
    } catch (err) {
      const name = err instanceof DOMException ? err.name : '';
      throw new MicPermissionError(
        name === 'NotAllowedError' || name === 'SecurityError'
          ? 'Microphone access was blocked. Allow the microphone for this site and try again.'
          : name === 'NotFoundError'
            ? 'No microphone was found on this device.'
            : 'Could not start the microphone.'
      );
    }
    const url = URL.createObjectURL(new Blob([WORKLET_SOURCE], { type: 'application/javascript' }));
    try {
      await this.ctx.audioWorklet.addModule(url);
    } finally {
      URL.revokeObjectURL(url);
    }
    this.source = this.ctx.createMediaStreamSource(this.stream);
    this.node = new AudioWorkletNode(this.ctx, 'shem-pcm16k', { numberOfInputs: 1, numberOfOutputs: 1, channelCount: 1 });
    this.node.port.onmessage = (e: MessageEvent<{ pcm?: ArrayBuffer; rms: number }>) => {
      this.onLevel(e.data.rms);
      if (e.data.pcm) this.onFrame(e.data.pcm);
    };
    // Keep the worklet pulled by the graph without making the mic audible.
    this.sink = this.ctx.createGain();
    this.sink.gain.value = 0;
    this.source.connect(this.node).connect(this.sink).connect(this.ctx.destination);
  }

  setEnabled(enabled: boolean): void {
    this.node?.port.postMessage({ enabled });
    this.stream?.getAudioTracks().forEach((t) => { t.enabled = enabled; });
  }

  stop(): void {
    try {
      this.source?.disconnect();
      this.node?.disconnect();
      this.sink?.disconnect();
    } catch {
      /* already disconnected */
    }
    this.node?.port.close();
    this.stream?.getTracks().forEach((t) => t.stop());
    this.stream = this.source = this.node = this.sink = null;
  }
}

function base64ToArrayBuffer(b64: string): ArrayBuffer {
  const bin = atob(b64);
  const bytes = new Uint8Array(bin.length);
  for (let i = 0; i < bin.length; i++) bytes[i] = bin.charCodeAt(i);
  return bytes.buffer;
}

interface TurnQueue {
  turnId: string;
  nextSeq: number | null;
  ready: Map<number, { buffer: AudioBuffer; text: string }>;
  ended: boolean;          // audio_end received
  pendingDecodes: number;
}

export interface SpeechPlayerCallbacks {
  /** A sentence started playing (caption). */
  onSentence: (turnId: string, text: string) => void;
  /** All audio of the turn has finished playing after audio_end. */
  onDrained: (turnId: string) => void;
  /** Playing / silent transitions. */
  onPlaying: (playing: boolean) => void;
}

export class SpeechPlayer {
  private ctx: AudioContext;
  private cb: SpeechPlayerCallbacks;
  private turn: TurnQueue | null = null;
  private sources = new Set<AudioBufferSourceNode>();
  private timers = new Set<number>();
  private nextTime = 0;
  private generation = 0;
  private cancelled = new Set<string>();

  constructor(ctx: AudioContext, cb: SpeechPlayerCallbacks) {
    this.ctx = ctx;
    this.cb = cb;
  }

  get playing(): boolean {
    return this.sources.size > 0;
  }

  enqueue(turnId: string, seq: number, b64: string, text: string): void {
    if (this.cancelled.has(turnId)) return;
    if (!this.turn || this.turn.turnId !== turnId) {
      // A new turn supersedes whatever was still playing.
      if (this.turn) this.stopAll();
      this.turn = { turnId, nextSeq: null, ready: new Map(), ended: false, pendingDecodes: 0 };
    }
    const turn = this.turn;
    if (turn.nextSeq === null) turn.nextSeq = seq; // frames arrive in order; first one starts the sequence
    turn.pendingDecodes += 1;
    const gen = this.generation;
    this.ctx
      .decodeAudioData(base64ToArrayBuffer(b64))
      .then((buffer) => {
        if (gen !== this.generation || this.turn !== turn) return;
        turn.ready.set(seq, { buffer, text });
      })
      .catch(() => {
        // Undecodable sentence: skip it so the rest of the turn still plays.
        if (gen === this.generation && this.turn === turn && turn.nextSeq === seq) turn.nextSeq = seq + 1;
      })
      .finally(() => {
        if (gen !== this.generation || this.turn !== turn) return;
        turn.pendingDecodes -= 1;
        this.pump();
      });
  }

  end(turnId: string): void {
    if (this.turn?.turnId === turnId) {
      this.turn.ended = true;
      this.pump();
    } else if (!this.cancelled.has(turnId)) {
      this.cb.onDrained(turnId); // nothing was queued for this turn
    }
  }

  private pump(): void {
    const turn = this.turn;
    if (!turn || turn.nextSeq === null) return;
    while (turn.ready.has(turn.nextSeq)) {
      const { buffer, text } = turn.ready.get(turn.nextSeq)!;
      turn.ready.delete(turn.nextSeq);
      turn.nextSeq += 1;
      const startAt = Math.max(this.ctx.currentTime + 0.03, this.nextTime);
      this.nextTime = startAt + buffer.duration;
      const src = this.ctx.createBufferSource();
      src.buffer = buffer;
      src.connect(this.ctx.destination);
      const wasPlaying = this.playing;
      this.sources.add(src);
      if (!wasPlaying) this.cb.onPlaying(true);
      const delayMs = Math.max(0, (startAt - this.ctx.currentTime) * 1000);
      const timer = window.setTimeout(() => {
        this.timers.delete(timer);
        this.cb.onSentence(turn.turnId, text);
      }, delayMs);
      this.timers.add(timer);
      src.onended = () => {
        this.sources.delete(src);
        if (this.turn === turn) this.checkDrained();
        if (!this.playing) this.cb.onPlaying(false);
      };
      src.start(startAt);
    }
    this.checkDrained();
  }

  private checkDrained(): void {
    const turn = this.turn;
    if (turn && turn.ended && turn.ready.size === 0 && turn.pendingDecodes === 0 && this.sources.size === 0) {
      this.turn = null;
      this.cb.onDrained(turn.turnId);
    }
  }

  private stopAll(): void {
    this.generation += 1;
    this.timers.forEach((t) => clearTimeout(t));
    this.timers.clear();
    const had = this.playing;
    this.sources.forEach((s) => {
      s.onended = null;
      try {
        s.stop();
      } catch {
        /* not started */
      }
    });
    this.sources.clear();
    this.nextTime = 0;
    if (had) this.cb.onPlaying(false);
  }

  /** Stop immediately; further audio for that turn (or the current one) is ignored. */
  interrupt(turnId?: string | null): string | null {
    const id = turnId ?? this.turn?.turnId ?? null;
    if (id) this.cancelled.add(id);
    if (!turnId || this.turn?.turnId === turnId) {
      this.stopAll();
      this.turn = null;
    }
    return id;
  }

  close(): void {
    this.stopAll();
    this.turn = null;
  }
}
