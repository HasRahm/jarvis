// mc-engine.jsx — Simulation engine for the Jarvis DAG + voice + telemetry.
// One hook (useMissionControl) drives a believable multi-agent task.

const TASKS = [
  {
    id: 'todo-api',
    prompt: 'Build a REST API for a todo list with frontend',
    plan: 'Decomposing into 6 steps — schema, endpoints, UI, QA, deploy.',
    nodes: [
      { id: 'plan',    label: 'Plan task',                   role: 'orchestrator', model: 'gemma4:31b',     duration: 1800, dep: [] },
      { id: 'schema',  label: 'Migrate users + todos schema', role: 'backend',      model: 'claude-sonnet-4-6', duration: 2200, dep: ['plan'] },
      { id: 'api',     label: 'POST /api/todos endpoint',     role: 'backend',      model: 'claude-sonnet-4-6', duration: 2400, dep: ['schema'] },
      { id: 'ui',      label: 'TodoList.tsx + composer',      role: 'frontend',     model: 'gemini-3.1-pro',    duration: 2600, dep: ['plan'] },
      { id: 'qa',      label: 'Verify contract + UI flow',    role: 'qa',           model: 'gpt-5.4',           duration: 2000, dep: ['api','ui'] },
      { id: 'deploy',  label: 'Deploy migrations + service',  role: 'iac',          model: 'claude-sonnet-4-6', duration: 1600, dep: ['qa'] },
    ],
    voice: [
      { at: 0,    text: 'On it. Decomposing into a six-step graph.' },
      { at: 2200, text: 'Backend is migrating the schema now.' },
      { at: 5400, text: 'Frontend and API in parallel — looking good.' },
      { at: 9000, text: 'QA flagged a contract drift. Auto-healing.' },
      { at: 11200, text: 'All green. Ready to deploy.' },
    ],
    heal: { at: 8400, intent: 'POST /api/todos returns wrong shape', element: 'TodoList.tsx · row 47' },
  },
];

const SEED_MESSAGES = [
  { role: 'jarvis', t: '23:38:14', text: 'Secure link established over Hermes WebSocket.' },
  { role: 'user',   t: '23:40:02', text: 'How did the auth migration go last night?' },
  { role: 'jarvis', t: '23:40:04', text: 'Clean. 312 rows migrated, zero contract drift. QA passed on the second pass after I patched the email index.' },
  { role: 'user',   t: '23:41:09', text: 'Good. Let\u2019s do the todos API next.' },
];

const SEED_LOGS = [
  { t: '23:38:14', tag: 'HERMES',   text: 'auth_ok · user=hasin · ws/9000' },
  { t: '23:38:15', tag: 'GBRAIN',   text: 'context restored · 12,408 nodes · 41,902 edges' },
  { t: '23:38:16', tag: 'ROUTER',   text: 'adaptive override: qa role → gpt-5.4 (win rate 0.91 / n=42)' },
  { t: '23:40:04', tag: 'QA',       text: 'task-auth-migration · PASSED · 0 regressions' },
  { t: '23:40:18', tag: 'GBRAIN',   text: '+1 learning · "email index must be UNIQUE on case-folded value"' },
  { t: '23:41:09', tag: 'ORCHESTR', text: 'intent classified: code-task · confidence 0.94' },
];

const ROLE_META = {
  orchestrator: { name: 'Orchestrator', short: 'ORCH', color: '#FFB547', glyph: '◇' },
  frontend:     { name: 'Frontend',     short: 'FE',   color: '#7DD3FC', glyph: '◐' },
  backend:      { name: 'Backend',      short: 'BE',   color: '#A78BFA', glyph: '◑' },
  qa:           { name: 'QA',           short: 'QA',   color: '#34D399', glyph: '◈' },
  iac:          { name: 'IaC',          short: 'IAC',  color: '#F472B6', glyph: '◇' },
};

// Format helpers
function fmtTime(d) {
  const h = String(d.getHours()).padStart(2, '0');
  const m = String(d.getMinutes()).padStart(2, '0');
  const s = String(d.getSeconds()).padStart(2, '0');
  return `${h}:${m}:${s}`;
}

// ─────────────────────────────────────────────────────────────
// useMissionControl — drives a fake DAG execution.
// ─────────────────────────────────────────────────────────────
function useMissionControl(opts = {}) {
  const { live = false } = opts;
  const task = TASKS[0];
  const [messages, setMessages] = React.useState(SEED_MESSAGES);
  const [logs, setLogs] = React.useState(SEED_LOGS);
  const [nodes, setNodes] = React.useState(() =>
    task.nodes.map((n) => ({ ...n, status: 'idle', progress: 0, startedAt: null, finishedAt: null }))
  );
  const [agents, setAgents] = React.useState(() => ({
    orchestrator: { status: 'idle', step: '—' },
    frontend:     { status: 'idle', step: '—' },
    backend:      { status: 'idle', step: '—' },
    qa:           { status: 'idle', step: '—' },
    iac:          { status: 'idle', step: '—' },
  }));
  const [telemetry, setTelemetry] = React.useState({
    tokens: 193263, cost: 0.866, calls: 99, latency: 312,
  });
  const [voiceLevel, setVoiceLevel] = React.useState(0);
  const [healToast, setHealToast] = React.useState(null);
  const [running, setRunning] = React.useState(false);
  const [taskStatus, setTaskStatus] = React.useState('READY'); // READY / PLANNING / EXECUTING / HEALING / DONE
  const [activeVoice, setActiveVoice] = React.useState(null);

  const timers = React.useRef([]);
  const voiceRaf = React.useRef(null);
  const wsRef = React.useRef(null);         // live mode: shared WS handle
  const [wsStatus, setWsStatus] = React.useState('offline'); // offline | connecting | online | error

  React.useEffect(() => () => {
    timers.current.forEach((t) => clearTimeout(t));
    if (voiceRaf.current) cancelAnimationFrame(voiceRaf.current);
  }, []);

  function pushLog(tag, text) {
    setLogs((prev) => [...prev, { t: fmtTime(new Date()), tag, text }].slice(-80));
  }
  function pushMsg(role, text) {
    setMessages((prev) => [...prev, { role, t: fmtTime(new Date()), text }].slice(-30));
  }
  function patchNode(id, patch) {
    setNodes((prev) => prev.map((n) => (n.id === id ? { ...n, ...patch } : n)));
  }
  function patchAgent(role, patch) {
    setAgents((prev) => ({ ...prev, [role]: { ...prev[role], ...patch } }));
  }

  // Voice ‘speaking’ simulation — drives the audio visualizer.
  function startVoice(durationMs, text) {
    setActiveVoice(text);
    const start = performance.now();
    const tick = () => {
      const elapsed = performance.now() - start;
      if (elapsed > durationMs) {
        setVoiceLevel(0);
        setActiveVoice(null);
        voiceRaf.current = null;
        return;
      }
      // Layered noise: slow envelope + fast jitter
      const env = 0.45 + 0.35 * Math.sin(elapsed / 320);
      const jit = 0.15 * Math.sin(elapsed / 47) + 0.1 * Math.sin(elapsed / 23);
      const fade = elapsed < 200 ? elapsed / 200 : (elapsed > durationMs - 200 ? (durationMs - elapsed) / 200 : 1);
      setVoiceLevel(Math.max(0, Math.min(1, (env + jit) * fade)));
      voiceRaf.current = requestAnimationFrame(tick);
    };
    voiceRaf.current = requestAnimationFrame(tick);
  }

  function scheduleAt(ms, fn) {
    const t = setTimeout(fn, ms);
    timers.current.push(t);
    return t;
  }

  function reset() {
    timers.current.forEach((t) => clearTimeout(t));
    timers.current = [];
    if (voiceRaf.current) cancelAnimationFrame(voiceRaf.current);
    setVoiceLevel(0);
    setActiveVoice(null);
    setHealToast(null);
    setRunning(false);
    setTaskStatus('READY');
    setNodes(task.nodes.map((n) => ({ ...n, status: 'idle', progress: 0, startedAt: null, finishedAt: null })));
    setAgents({
      orchestrator: { status: 'idle', step: '—' },
      frontend:     { status: 'idle', step: '—' },
      backend:      { status: 'idle', step: '—' },
      qa:           { status: 'idle', step: '—' },
      iac:          { status: 'idle', step: '—' },
    });
  }

  // Telemetry ticker — runs whenever a node is active.
  React.useEffect(() => {
    if (!running) return;
    const id = setInterval(() => {
      setTelemetry((t) => ({
        tokens: t.tokens + Math.floor(40 + Math.random() * 90),
        cost:   +(t.cost + (0.0008 + Math.random() * 0.0012)).toFixed(4),
        calls:  t.calls + (Math.random() < 0.18 ? 1 : 0),
        latency: Math.round(280 + Math.random() * 80),
      }));
    }, 360);
    return () => clearInterval(id);
  }, [running]);

  function runTask(text) {
    if (running) return;
    // In live mode: dispatch to real Hermes backend instead of simulation
    if (live && wsRef.current && wsRef.current.readyState === 1) {
      pushMsg('user', text);
      pushLog('HERMES', `dispatching: ${text.slice(0, 72)}`);
      wsRef.current.send(JSON.stringify({ type: 'run_task', text }));
      setTaskStatus('PLANNING');
      setRunning(true);
      return;
    }
    reset();
    pushMsg('user', text);
    pushLog('ORCHESTR', 'intent classified: code-task · confidence 0.94');
    setRunning(true);
    setTaskStatus('PLANNING');

    // Stage 1: orchestrator
    scheduleAt(220, () => {
      patchNode('plan', { status: 'active', startedAt: Date.now() });
      patchAgent('orchestrator', { status: 'active', step: 'Decomposing into DAG' });
      pushLog('ORCHESTR', 'plan() · gemma4:31b · streaming');
      startVoice(2800, task.voice[0].text);
      pushMsg('jarvis', task.voice[0].text);
    });
    scheduleAt(2000, () => {
      patchNode('plan', { status: 'done', progress: 1, finishedAt: Date.now() });
      patchAgent('orchestrator', { status: 'done', step: 'DAG · 6 nodes · 2 layers' });
      pushLog('DAG', 'graph compiled · 6 nodes · 7 edges');
      setTaskStatus('EXECUTING');
    });

    // Stage 2: backend (schema → api), parallel with frontend (ui)
    scheduleAt(2100, () => {
      patchNode('schema', { status: 'active', startedAt: Date.now() });
      patchAgent('backend', { status: 'active', step: 'Writing migration 002_create_todos.sql' });
      pushLog('BACKEND', 'started: migrate users + todos schema');
      startVoice(2200, task.voice[1].text);
    });
    scheduleAt(2200, () => {
      patchNode('ui', { status: 'active', startedAt: Date.now() });
      patchAgent('frontend', { status: 'active', step: 'TodoList.tsx · composer · empty state' });
      pushLog('FRONTEND', 'started: TodoList.tsx + composer');
    });

    scheduleAt(4300, () => {
      patchNode('schema', { status: 'done', progress: 1, finishedAt: Date.now() });
      pushLog('BACKEND', 'schema · 2 tables · 4 indexes · OK');
      patchNode('api', { status: 'active', startedAt: Date.now() });
      patchAgent('backend', { status: 'active', step: 'Implementing POST /api/todos' });
      pushLog('BACKEND', 'started: POST /api/todos endpoint');
      startVoice(2800, task.voice[2].text);
      pushMsg('jarvis', task.voice[2].text);
    });

    scheduleAt(6700, () => {
      patchNode('ui', { status: 'done', progress: 1, finishedAt: Date.now() });
      patchAgent('frontend', { status: 'done', step: '3 components · 142 LOC' });
      pushLog('FRONTEND', 'completed · 3 components · 142 LOC');
    });

    scheduleAt(7000, () => {
      patchNode('api', { status: 'done', progress: 1, finishedAt: Date.now() });
      patchAgent('backend', { status: 'done', step: 'POST /api/todos shipped' });
      pushLog('BACKEND', 'completed · POST /api/todos · contract published');

      // QA starts
      patchNode('qa', { status: 'active', startedAt: Date.now() });
      patchAgent('qa', { status: 'active', step: 'Asserting contract on /api/todos' });
      pushLog('QA', 'started: verify contract + UI flow');
    });

    // Stage 3: auto-heal mid-QA
    scheduleAt(8400, () => {
      setTaskStatus('HEALING');
      setHealToast({ intent: task.heal.intent, element: task.heal.element });
      pushLog('AUTOHEAL', `intent mismatch · ${task.heal.intent}`);
      pushLog('AUTOHEAL', `tap → ${task.heal.element}`);
      patchAgent('qa', { status: 'active', step: 'Drift detected · re-running' });
      startVoice(2400, task.voice[3].text);
      pushMsg('jarvis', task.voice[3].text);
    });
    scheduleAt(10800, () => {
      setHealToast(null);
      pushLog('AUTOHEAL', 'patched · TodoList row shape updated · re-running QA');
    });

    scheduleAt(11200, () => {
      patchNode('qa', { status: 'done', progress: 1, finishedAt: Date.now() });
      patchAgent('qa', { status: 'done', step: 'PASSED · 12/12 assertions' });
      pushLog('QA', 'PASSED · 12/12 assertions · 0 regressions');
      patchNode('deploy', { status: 'active', startedAt: Date.now() });
      patchAgent('iac', { status: 'active', step: 'Applying terraform plan' });
      pushLog('IAC', 'started: deploy migrations + service');
      setTaskStatus('EXECUTING');
      startVoice(2200, task.voice[4].text);
      pushMsg('jarvis', task.voice[4].text);
    });

    scheduleAt(13000, () => {
      patchNode('deploy', { status: 'done', progress: 1, finishedAt: Date.now() });
      patchAgent('iac', { status: 'done', step: '2 resources applied' });
      pushLog('IAC', 'completed · 2 resources · service healthy');
      pushLog('GBRAIN', '+3 learnings stored · contract, indexes, deploy hash');
      setTaskStatus('DONE');
      setRunning(false);
    });
  }

  // ── Live backend integration ───────────────────────────────────
  // When live=true: poll /api/telemetry and connect to the Hermes WebSocket.
  // The simulation still drives DAG + voice animation; real data overlays
  // the metrics counters and appends real agent speech to the transcript.
  React.useEffect(() => {
    if (!live) return;

    const token   = localStorage.getItem('hermesToken') || '';
    const rawUrl  = localStorage.getItem('hermesUrl') || 'http://localhost:9000';
    let apiBase;
    try { apiBase = new URL(rawUrl).origin; } catch (_) { apiBase = 'http://localhost:9000'; }

    // 1. Telemetry polling (every 5 s)
    let pollId;
    async function pollTelemetry() {
      try {
        const res = await fetch(`${apiBase}/api/telemetry`, {
          headers: token ? { Authorization: `Bearer ${token}` } : {},
        });
        if (!res.ok) return;
        const d = await res.json();
        setTelemetry({
          tokens: d.total_calls * 1800 || 0,
          cost:   +(d.total_cost   || 0).toFixed(4),
          calls:  d.total_calls    || 0,
          latency: Math.round((d.avg_latency || 0) * 1000),
        });
      } catch (_) {}
    }
    pollTelemetry();
    pollId = setInterval(pollTelemetry, 5000);

    // 2. Hermes WebSocket
    const wsBase = apiBase.replace(/^http/, 'ws');
    let ws;
    try {
      setWsStatus('connecting');
      ws = new WebSocket(`${wsBase}/ws`);
      wsRef.current = ws;
      ws.onopen = () => {
        ws.send(JSON.stringify({ type: 'auth', token }));
      };
      ws.onmessage = (evt) => {
        try {
          const msg = JSON.parse(evt.data);
          if (msg.type === 'auth_ok') {
            setWsStatus('online');
            setTaskStatus('READY');
            setRunning(false);
            pushLog('HERMES', 'auth_ok · live connection established');

          } else if (msg.type === 'task_status') {
            const s = msg.status;
            setTaskStatus(s);
            if (s === 'PLANNING') {
              setRunning(true);
              pushLog('DAG', `planning: ${(msg.task || '').slice(0, 60)}`);
            } else if (s === 'EXECUTING') {
              setRunning(true);
              // Rebuild DAG nodes from real plan when backend sends it
              if (msg.plan && msg.plan.length > 0) {
                setNodes(msg.plan.map((n, i) => ({
                  id: n.id, label: n.label, role: n.role,
                  model: '', dep: i > 0 ? [msg.plan[i-1].id] : [],
                  status: 'idle', progress: 0,
                })));
              }
              pushLog('DAG', `executing · ${msg.plan ? msg.plan.length : '?'} subtasks`);
            } else if (s === 'HEALING') {
              pushLog('AUTOHEAL', `healing · ${(msg.selector || '')}`);
            } else if (s === 'COMPLETED' || s === 'FAILED') {
              setRunning(false);
              const files = msg.files || [];
              pushLog('DAG', `${s} · ${files.length} files`);
              if (files.length > 0) pushMsg('jarvis', `Done. Created: ${files.slice(0,3).join(', ')}${files.length > 3 ? '…' : ''}`);
            }

          } else if (msg.type === 'dag_update') {
            // Real agent started / finished — update nodes and agent roster
            const { node_id, role, status, label } = msg;
            setNodes(prev => prev.map(n =>
              (n.id === node_id || n.role === role)
                ? { ...n, status: status === 'done' ? 'done' : status === 'active' ? 'active' : status === 'error' ? 'error' : n.status }
                : n
            ));
            setAgents(prev => ({
              ...prev,
              [role]: {
                status: status === 'active' ? 'active' : status === 'done' || status === 'error' ? 'done' : 'idle',
                step: label || (status === 'done' ? 'Completed' : status === 'error' ? 'Error' : '—'),
              },
            }));
            pushLog(role.toUpperCase().slice(0, 8), `${status.toUpperCase()} · ${(label || '').slice(0, 55)}`);

          } else if (msg.type === 'agent_speech') {
            pushMsg('jarvis', msg.text);
            startVoice(Math.max(1500, msg.text.length * 55), msg.text);

          } else if (msg.type === 'auto_heal_detected') {
            setHealToast({ intent: msg.intent || 'correction', element: msg.element || 'element' });
            setTimeout(() => setHealToast(null), 3500);

          } else if (msg.type === 'error') {
            pushLog('HERMES', `error: ${msg.message}`);
          }
        } catch (_) {}
      };
      ws.onerror = () => { setWsStatus('error'); pushLog('HERMES', 'WS error — check token + server URL'); };
      ws.onclose = () => { setWsStatus('offline'); pushLog('HERMES', 'WS disconnected'); wsRef.current = null; };
    } catch (e) {
      setWsStatus('error');
      pushLog('HERMES', `WS init failed: ${e.message || e}`);
    }

    return () => {
      clearInterval(pollId);
      if (ws && ws.readyState <= 1) ws.close();
      wsRef.current = null;
    };
  }, [live]);

  return {
    task, messages, logs, nodes, agents, telemetry, voiceLevel,
    healToast, running, taskStatus, activeVoice, wsStatus,
    runTask, reset, ROLE_META,
  };
}

Object.assign(window, { useMissionControl, TASKS, SEED_MESSAGES, SEED_LOGS, ROLE_META, fmtTime });
