import { useCallback, useEffect, useRef, useState } from 'react';
import { Avatar } from './Avatar';
import type { Action, Play } from './types';

export function Display() {
  const ws = useRef<WebSocket | null>(null), epoch = useRef(0), lastBeat = useRef(0), mouth = useRef(0);
  const audio = useRef<HTMLAudioElement | null>(null), context = useRef<AudioContext | null>(null), anim = useRef(0), generation = useRef(0);
  const [connected, setConnected] = useState(false), [ready, setReady] = useState(false), [enabled, setEnabled] = useState(false), [paused, setPaused] = useState(true), [subtitle, setSubtitle] = useState(''), [action, setAction] = useState<Action>('idle'), [error, setError] = useState('');
  const enabledRef = useRef(false), readyRef = useRef(false);
  const send = useCallback((value: object) => { if (ws.current?.readyState === WebSocket.OPEN) ws.current.send(JSON.stringify(value)); }, []);
  const stop = useCallback(() => { generation.current++; cancelAnimationFrame(anim.current); if (audio.current) { audio.current.pause(); audio.current.src = ''; audio.current = null; } mouth.current = 0; setAction('idle'); setSubtitle(''); setPaused(true); }, []);
  const playback = useCallback(async (p: Play) => {
    stop(); const ticket = generation.current; epoch.current = p.epoch;
    if (!enabledRef.current || !readyRef.current) { send({ type: 'playback', id: p.id, playback_id: p.playback_id, epoch: p.epoch, phase: 'error' }); return; }
    const element = new Audio(p.audio); audio.current = element;
    try {
      const ctx = context.current!; await ctx.resume();
      if (ticket !== generation.current) return;
      const source = ctx.createMediaElementSource(element), analyser = ctx.createAnalyser(); analyser.fftSize = 256;
      source.connect(analyser); analyser.connect(ctx.destination); const values = new Uint8Array(analyser.fftSize);
      const detach = () => { source.disconnect(); analyser.disconnect(); };
      const report = (phase: string) => send({ type: 'playback', id: p.id, playback_id: p.playback_id, epoch: p.epoch, phase });
      element.onended = () => { if (ticket !== generation.current) return; detach(); stop(); report('ended'); };
      element.onerror = () => { if (ticket !== generation.current) return; detach(); stop(); setError('语音播放失败'); report('error'); };
      await element.play();
      if (ticket !== generation.current) { element.pause(); detach(); return; }
      setPaused(false); setSubtitle(p.text); setAction(p.action); report('started');
      function sample() { if (ticket !== generation.current) return; analyser.getByteTimeDomainData(values); let sum = 0; for (const v of values) sum += ((v - 128) / 128) ** 2; mouth.current = Math.min(1, Math.sqrt(sum / values.length) * 5); anim.current = requestAnimationFrame(sample); } sample();
    } catch { if (ticket === generation.current) { stop(); setError('请点击启用声音，再由导播台恢复'); send({ type: 'playback', id: p.id, playback_id: p.playback_id, epoch: p.epoch, phase: 'error' }); } }
  }, [send, stop]);
  useEffect(() => {
    let disposed = false, retry: ReturnType<typeof setTimeout>;
    async function connect() {
      try { await fetch('/api/session'); } catch { if (!disposed) retry = setTimeout(connect, 1500); return; }
      if (disposed) return;
      const socket = new WebSocket(`${location.protocol === 'https:' ? 'wss' : 'ws'}://${location.host}/ws/display`); ws.current = socket;
      socket.onopen = () => { lastBeat.current = performance.now(); setConnected(true); if (enabledRef.current && readyRef.current) send({ type: 'ready' }); };
      socket.onmessage = event => {
const data = JSON.parse(event.data); lastBeat.current = performance.now();
        if (data.type === 'play') { if (data.epoch >= epoch.current) void playback(data); return; }
        if (data.type === 'stop' || ((data.type === 'state' || data.type === 'heartbeat') && (data.stopped || data.epoch !== epoch.current))) { epoch.current = data.epoch; stop(); }
        if (data.type === 'error') { setError(data.message); stop(); }
      };
      socket.onclose = () => { setConnected(false); stop(); if (!disposed) retry = setTimeout(connect, 1500); };
    }
    void connect(); const heartbeat = setInterval(() => { send({ type: 'ping' }); if (performance.now() - lastBeat.current > 6000) stop(); }, 2000);
    return () => { disposed = true; clearTimeout(retry); clearInterval(heartbeat); ws.current?.close(); stop(); };
  }, [playback, send, stop]);
  const modelReady = useCallback((ok: boolean) => { setReady(ok); readyRef.current = ok; if (ok && enabledRef.current) send({ type: 'ready' }); }, [send]);
  const fps = useCallback((value: number) => send({ type: 'fps', value }), [send]);
  async function enable() { context.current ??= new AudioContext(); await context.current.resume(); enabledRef.current = true; setEnabled(true); setError(''); if (readyRef.current) send({ type: 'ready', replace: true }); }
  return <div className="display">
    <div className="display-top"><span>一二和布布 <span className="muted">/ AI 虚拟主播</span></span><span className={connected && ready ? 'signal' : 'muted'}>{!connected ? '连接中' : !ready ? '加载角色' : paused ? '待机' : '一二正在说话'}</span></div>
    <Avatar mouth={mouth} action={action} paused={paused} onReady={modelReady} onFps={fps} />
    {!enabled && <div className="enable"><p>一二和布布来啦。</p><span>一二主讲，布布陪伴。开启声音，一起聊聊。</span><button onClick={() => void enable()} disabled={!connected || !ready}>启用声音与角色</button></div>}
    {error && <div className="display-error" role="alert">{error}</div>}
    <div className="subtitles" aria-live="polite">{subtitle}</div>
    <div className="display-footer">一二主讲 · 布布陪伴 <span>仅播出已审核内容</span></div>
  </div>;
}
