import { useEffect, useRef, useState } from 'react';
import { createRoot } from 'react-dom/client';
import '@fontsource/inter/400.css';
import '@fontsource/inter/500.css';
import '@fontsource/inter/600.css';
import './style.css';
import { Display } from './Display';
import type { Item, StudioState } from './types';

const labels: Record<string, string> = { queued: '排队', checking: '检查弹幕', generating: '生成回答', checking_output: '审核回答', synthesizing: '合成语音', playing: '播放中', done: '已播出', review: '待人工', refused: '已拦截', discarded: '已丢弃', cancelled: '已取消' };
const empty: StudioState = { stopped: true, mode: 'auto', epoch: 0, player_connected: false, items: [], events: [], debug: false, metrics: [] };
async function api(path: string, body?: object) { const r = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json', 'X-Studio': '1' }, body: body ? JSON.stringify(body) : undefined }); const value = await r.json(); if (!r.ok) throw new Error(typeof value.detail === 'string' ? value.detail : '输入格式错误'); return value; }

function Review({ item, run }: { item: Item; run: (work: () => Promise<unknown>) => void }) {
  const [text, setText] = useState(item.candidate);
  return <article className="review-row"><div className="row"><strong>{item.nickname}</strong><span className="warning">{item.category}</span></div><p>{item.text}</p><label htmlFor={`reply-${item.id}`}>编辑回复 · 重新审核后播放</label><textarea id={`reply-${item.id}`} maxLength={1600} value={text} onChange={e => setText(e.target.value)} /><div className="row"><button onClick={() => run(() => api(`/api/review/${item.id}/discard`))}>丢弃</button><button className="primary" disabled={!text.trim()} onClick={() => run(() => api(`/api/review/${item.id}/edit`, { text }))}>重新审核</button></div></article>;
}

function Studio() {
  const [state, setState] = useState(empty), [connected, setConnected] = useState(false), [health, setHealth] = useState<Record<string, unknown>>({}), [error, setError] = useState(''), [busy, setBusy] = useState(false), [nickname, setNickname] = useState('小麦'), [text, setText] = useState(''), [view, setView] = useState('studio'), [embed, setEmbed] = useState(true);
  const socket = useRef<WebSocket | null>(null);
  useEffect(() => {
    let disposed = false, retry: ReturnType<typeof setTimeout>;
    async function connect() { try { await fetch('/api/session'); if (disposed) return; const ws = new WebSocket(`ws://${location.host}/ws/control`); socket.current = ws; ws.onopen = () => setConnected(true); ws.onmessage = e => { const event = JSON.parse(e.data); if (event.type === 'state') setState(event); }; ws.onclose = () => { setConnected(false); if (!disposed) retry = setTimeout(connect, 1500); }; } catch { if (!disposed) retry = setTimeout(connect, 1500); } }
    void connect(); const ping = setInterval(() => { if (socket.current?.readyState === 1) socket.current.send(JSON.stringify({ type: 'ping' })); }, 3000);
    async function check() { try { const r = await fetch('/api/health'); if (r.ok) setHealth(await r.json()); } catch { setHealth({}); } }
    void check(); const poll = setInterval(check, 10000);
    return () => { disposed = true; clearTimeout(retry); clearInterval(ping); clearInterval(poll); socket.current?.close(); };
  }, []);
  async function run(work: () => Promise<unknown>) { setError(''); setBusy(true); try { await work(); } catch (e) { setError((e as Error).message); } finally { setBusy(false); } }
  const pending = state.items.filter(x => x.status === 'review');
  const active = state.items.find(x => ['checking', 'generating', 'checking_output', 'synthesizing', 'playing'].includes(x.status));
  const latencies = state.metrics.flatMap(x => x.latency === undefined ? [] : [x.latency]).sort((a, b) => a - b);
  const p95 = latencies.length ? latencies[Math.ceil(latencies.length * .95) - 1].toFixed(1) : '—';
  const fps = state.metrics.filter(x => x.fps !== undefined).at(-1)?.fps;
  const serviceLabel = (v: unknown) => v === 'ready' ? '已就绪' : v === 'model_missing' ? '缺少模型' : v === 'unavailable' ? '未连接' : '检查中';
  return <div className="studio-shell">
    <header className="topbar"><a className="brand" href="/" aria-label="一二布布工作室首页"><svg viewBox="0 0 28 28" aria-hidden="true"><path d="M3 20V8h5v12M12 25V3h5v22M21 18v-8h4v8" fill="currentColor" /></svg>一二布布工作室</a><nav aria-label="工作室导航"><button className={view === 'studio' ? 'selected' : ''} onClick={() => setView('studio')}>导播台</button><button className={view === 'safety' ? 'selected' : ''} onClick={() => setView('safety')}>风控与运行</button></nav><span className={connected ? 'signal' : 'warning'}>{connected ? '本地连接' : '连接中'}</span></header>
    <main>
      <div className="titlebar"><div><h1>{view === 'studio' ? '直播导播台' : '风控与运行'}</h1><p className="muted">{state.stopped ? '当前暂停 · 启用角色后，可恢复回答' : active ? `${labels[active.status]} · 正在处理一条弹幕` : '自动待机 · 等待新的弹幕'}</p></div><div className="actions"><button disabled={busy || !connected} onClick={() => void run(() => api('/api/control/resume'))}>{state.stopped ? '恢复回答' : '回答已启用'}</button><button className="stop" disabled={!connected} onClick={() => void run(() => api('/api/control/stop'))}>停止发声与清空队列</button></div></div>
      {error && <div className="notice" role="alert">{error}<button onClick={() => setError('')} aria-label="关闭错误提示">关闭</button></div>}
      <div className="runtime-strip"><span><i className={state.stopped ? 'dot' : 'dot live'} />{state.stopped ? '暂停' : state.mode === 'auto' ? '日常自主' : '人工审核'}</span><span>对话 <b className={health.llm === 'ready' ? 'signal' : ''}>{serviceLabel(health.llm)}</b></span><span>语音 <b className={health.voice === 'ready' ? 'signal' : ''}>{serviceLabel(health.voice)}</b></span><span>待审 <b>{pending.length}</b></span><span>播放延迟 P95 <b>{p95} 秒</b></span><span>渲染 <b>{fps === undefined ? '—' : fps.toFixed(0)} FPS</b></span></div>
      <div className={view === 'studio' ? 'workspace' : 'workspace hidden'}>
        <section className="preview-panel"><div className="panel-head"><h2>角色预览</h2><button onClick={() => { setEmbed(!embed); if (embed) window.open('/display', '_blank', 'noopener'); }}>{embed ? '切换独立展示页' : '返回内嵌预览'}</button></div>{embed ? <iframe src="/display?embedded=1" title="小岚角色展示" allow="autoplay" /> : <div className="detached"><p>展示页已独立打开</p><p className="muted">若页面被浏览器拦截，请 <a href="/display" target="_blank" rel="noreferrer">打开角色展示</a>。</p></div>}<div className="pipeline"><span>弹幕检查</span><span>生成回答</span><span>回答审核</span><span>语音与动作</span></div></section>
        <aside className="side-stack"><section className="panel"><div className="panel-head"><h2>模拟弹幕</h2><span className="muted">仅本机</span></div><form onSubmit={e => { e.preventDefault(); void run(async () => { await api('/api/messages', { nickname, text }); setText(''); }); }}><label htmlFor="nickname">观众昵称</label><input id="nickname" value={nickname} maxLength={24} required onChange={e => setNickname(e.target.value)} /><label htmlFor="message">弹幕内容</label><textarea id="message" value={text} maxLength={500} required onChange={e => setText(e.target.value)} placeholder="今天有什么想聊的？" /><div className="row"><span className="muted">{text.length} / 500 字</span><button className="primary" disabled={busy || state.stopped || !connected}>发送弹幕</button></div></form></section>
          <section className="panel review-panel"><div className="panel-head"><h2>人工待审 <span className="count">{pending.length}</span></h2><span className="warning">不自动放行</span></div><div className="review-list">{pending.length ? pending.map(item => <Review key={item.id} item={item} run={work => void run(work)} />) : <div className="empty"><strong>没有待审内容</strong><p>需要判断的弹幕会留在这里。未处理时，角色保持待机。</p></div>}</div></section>
        </aside>
      </div>
      {view === 'studio' ? <section className="panel session"><div className="panel-head"><h2>本场对话</h2><span className="muted">最近 {state.items.length} 条 · 仅保存在当前进程</span></div>{state.items.length ? <div className="table-scroll"><table><thead><tr><th>观众与弹幕</th><th>回答 / 处置原因</th><th>状态</th><th className="num">开始播放耗时</th></tr></thead><tbody>{state.items.slice(0, 20).map(item => <tr key={item.id}><td><strong>{item.nickname}</strong><p>{item.text}</p></td><td>{item.status === 'done' || item.status === 'playing' ? item.candidate : item.category}</td><td><span className={item.status === 'refused' ? 'danger' : item.status === 'review' ? 'warning' : ''}>{labels[item.status] || item.status}</span></td><td className="num">{item.latency === null ? '—' : `${item.latency.toFixed(1)} 秒`}</td></tr>)}</tbody></table></div> : <div className="empty horizontal"><strong>等待第一条弹幕</strong><p>在预览中启用声音，点击恢复回答，然后发送一条日常问题。</p></div>}</section> : <div className="settings">
        <section className="panel"><h2>控制模式</h2><p className="muted">切换模式会暂停并作废当前任务。恢复回答后生效。</p><div className="actions"><button className={state.mode === 'auto' ? 'primary' : ''} onClick={() => void run(() => api('/api/control/auto'))}>日常自主，高风险转人工</button><button className={state.mode === 'manual' ? 'primary' : ''} onClick={() => void run(() => api('/api/control/manual'))}>每条回答人工审核</button></div><h2>风控规则</h2><p>输入审核、回答审核、动作白名单共同约束播出。规则命中不等于完整语义判断，无法判断时转人工。</p><p className="muted">修改 config/rules.json 后重载。重载会暂停回答，硬性拦截不能由人工编辑跳过。</p><button onClick={() => void run(() => api('/api/control/reload-rules'))}>重载规则并暂停</button></section>
        <section className="panel"><h2>本地日志</h2><p>默认仅记录分类、耗时和时间，不记录弹幕原文。</p><p className="muted">原文调试：{state.debug ? '已开启，原文将写入本机 data/debug.jsonl' : '已关闭'}</p><div className="actions"><button onClick={() => void run(() => api(`/api/control/debug-${state.debug ? 'off' : 'on'}`))}>{state.debug ? '关闭原文调试' : '开启原文调试'}</button><button onClick={() => void run(() => api('/api/control/clear-logs'))}>清除日志并关闭调试</button></div><h2>最近风控事件</h2>{state.events.length ? <ul className="events">{state.events.slice(0, 8).map((event, i) => <li key={i}><span>{event.category}</span><span className="muted">{event.duration.toFixed(1)} 秒</span></li>)}</ul> : <p className="muted">暂无事件</p>}</section>
      </div>}
      <footer>一二和布布 / 本地数字人实验室<span>模拟弹幕 · 无外部操作权限 · 公开使用前需复核平台规范</span></footer>
    </main>
  </div>;
}
createRoot(document.getElementById('root')!).render(location.pathname === '/display' ? <Display /> : <Studio />);
