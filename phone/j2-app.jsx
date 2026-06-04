/* j2-app.jsx — shell: nav rail + router + Hermes WS + simulation fallback */
const { useState: useJ2State, useEffect: useJ2Effect, useRef: useJ2Ref } = React;

let _j2uid = 0;
const j2uid = () => (++_j2uid);

const J2_NAV = [
  { id: "home",     label: "New build",  Icon: IconPlus    },
  { id: "console",  label: "Console",    Icon: IconConsole },
  { id: "runs",     label: "Runs",       Icon: IconRuns    },
  { id: "memory",   label: "Memory",     Icon: IconMemory  },
  { id: "storage",  label: "Storage",    Icon: IconStorage },
  { id: "settings", label: "Settings",   Icon: IconGear    },
];

const J2_ACCENTS = ["#C2603C", "#5E7066", "#7C6A86"];

// ── WS status dot ───────────────────────────────────────────
function J2WsDot({ status }) {
  const map = {
    online:     { color: "#6E8B73", label: "LIVE" },
    connecting: { color: "#C2603C", label: "CONNECTING" },
    error:      { color: "#B06A57", label: "ERR" },
    offline:    { color: "#928C80", label: "LOCAL" },
  };
  const { color, label } = map[status] || map.offline;
  return (
    <div style={{
      display: "flex", alignItems: "center", gap: 5,
      padding: "2px 8px", border: `1px solid ${color}33`,
      borderRadius: 4, fontFamily: "var(--mono)", fontSize: 8,
      letterSpacing: 1.2, color,
    }}>
      <span style={{
        width: 5, height: 5, borderRadius: "50%", background: color, flexShrink: 0,
        boxShadow: status === "online" ? `0 0 5px ${color}` : "none",
        animation: status === "online" ? "j2-ring 2s infinite" : "none",
      }} />
      {label}
    </div>
  );
}

function J2Rail({ page, setPage, running, wsStatus }) {
  return (
    <aside className="j2-rail">
      <div className="j2-rail-brand" onClick={() => setPage("home")}>
        <Logo size={30} />
        <div className="j2-rail-word serif">Jarvis</div>
      </div>

      <button className="j2-rail-new" onClick={() => setPage("home")}>
        <IconPlus size={16} /> <span>New build</span>
      </button>

      <nav className="j2-rail-nav">
        {J2_NAV.filter(n => n.id !== "home").map(n => {
          const active = page === n.id;
          return (
            <button key={n.id} className={`j2-rail-item ${active ? "on" : ""}`} onClick={() => setPage(n.id)}>
              <n.Icon size={17} />
              <span>{n.label}</span>
              {n.id === "console" && running && <span className="j2-rail-live" />}
            </button>
          );
        })}
      </nav>

      <div className="j2-rail-foot">
        <div style={{ marginBottom: 10, paddingLeft: 8 }}>
          <J2WsDot status={wsStatus} />
        </div>
        <div className="j2-rail-user">
          <span className="j2-rail-avatar">H</span>
          <div className="j2-rail-user-meta">
            <div className="j2-rail-user-name">Hasin</div>
            <div className="j2-rail-user-plan mono">Pro · self-hosted</div>
          </div>
        </div>
      </div>
    </aside>
  );
}

function J2ConsoleView({ messages, onSend, running, statuses, plan, revealed, telemetry, activity, tab, setTab, onNew, task, wsStatus }) {
  const empty = messages.length === 0;
  return (
    <div className="j2-console">
      <div className="j2-console-bar">
        <div className="j2-console-bar-left">
          <span className={`j2-run-status ${running ? "running" : empty ? "idle" : "done"}`} />
          <span className="j2-console-task">{empty ? "New build" : (task || J2_TASK)}</span>
          <J2WsDot status={wsStatus} />
        </div>
        <button className="j2-ghost-btn" onClick={onNew}>+ New build</button>
      </div>
      <div className="j2-console-split">
        <div className="j2-console-left">
          {empty ? (
            <div className="j2-thread">
              <div className="j2-thread-scroll j2-thread-center">
                <div className="j2-console-empty">
                  <span className="j2-home-spark"><IconSpark size={20} /></span>
                  <p className="serif">Describe a build to begin.</p>
                  <span className="j2-console-empty-sub">
                    {wsStatus === "online"
                      ? "Connected to Jarvis — agents will run for real."
                      : "Jarvis will plan it, run the agents, and stream the work into the panel on the right."}
                  </span>
                </div>
              </div>
              <div className="j2-thread-foot"><J2Composer onSend={onSend} /></div>
            </div>
          ) : (
            <J2Thread messages={messages} onSend={onSend} running={running} />
          )}
        </div>
        <div className="j2-console-right">
          <J2Workspace
            tab={tab} setTab={setTab} task={task}
            statuses={statuses} plan={plan}
            revealedAgents={revealed} telemetry={telemetry} activity={activity}
          />
        </div>
      </div>
    </div>
  );
}

function J2App() {
  const [t, setTweak]    = useTweaks(J2_TWEAK_DEFAULTS);
  const [page, setPage]  = useJ2State("home");
  const [messages, setMessages] = useJ2State([]);
  const [statuses, setStatuses] = useJ2State({});
  const [plan,     setPlan]     = useJ2State(null);
  const [revealed, setRevealed] = useJ2State([]);
  const [telemetry, setTelemetry] = useJ2State({ tokens: 0, cost: 0 });
  const [activity,  setActivity]  = useJ2State([]);
  const [tab,       setTab]       = useJ2State("plan");
  const [running,   setRunning]   = useJ2State(false);
  const [task,      setTask]      = useJ2State("");
  const [wsStatus,  setWsStatus]  = useJ2State("offline");

  const timers     = useJ2Ref([]);
  const wsRef      = useJ2Ref(null);
  const streamRef  = useJ2Ref(null); // id of message currently streaming in
  const taskRef    = useJ2Ref("");   // task text to send after auth_ok

  /* Apply tweaks to :root */
  useJ2Effect(() => {
    const r = document.documentElement;
    r.dataset.theme   = t.theme;
    r.dataset.density = t.density;
    r.style.setProperty("--clay", t.accent);
    r.style.setProperty("--serif-active", t.showSerif ? "var(--serif)" : "var(--sans)");
  }, [t]);

  const clearTimers = () => { timers.current.forEach(clearTimeout); timers.current = []; };
  useJ2Effect(() => clearTimers, []);

  // ── Telemetry Polling ─────────────────────────────────────────
  useJ2Effect(() => {
    const rawUrl = localStorage.getItem("hermesUrl") || "http://localhost:9000";
    const token  = localStorage.getItem("hermesToken") || "jarvis_hermes_2026";
    let apiBase;
    try { apiBase = new URL(rawUrl).origin; } catch (_) { apiBase = "http://localhost:9000"; }

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
    return () => clearInterval(pollId);
  }, []);

  // ── WS event handler ────────────────────────────────────────
  const handleWsMessage = (evt) => {
    // Binary frames are audio — ignore in Console 2.0
    if (evt.data instanceof ArrayBuffer || evt.data instanceof Blob) return;

    let msg;
    try { msg = JSON.parse(evt.data); } catch (_) { return; }

    const type = msg.type;

    if (type === "auth_ok") {
      setWsStatus("online");
      setActivity(p => [...p, "Hermes connected — dispatching task to agents"]);
      wsRef.current && wsRef.current.send(JSON.stringify({ type: "run_task", text: taskRef.current }));
      return;
    }

    if (type === "task_status") {
      const s = msg.status;
      setActivity(p => [...p, `Task ${s.toLowerCase()}${msg.task ? ` · ${msg.task.slice(0, 60)}` : ""}`]);
      if (s === "PLANNING") {
        setStatuses(prev => ({ ...prev, input: "done", plan: "running" }));
        setTab("plan");
      } else if (s === "EXECUTING") {
        setStatuses(prev => ({ ...prev, plan: "done" }));
      } else if (s === "COMPLETED") {
        setStatuses(prev => ({ ...prev, done: "done" }));
        setRunning(false);
      } else if (s === "FAILED" || s === "ERROR") {
        setRunning(false);
        const errMsg = msg.error || "Task failed.";
        setMessages(p => [...p, { id: j2uid(), role: "jarvis", text: `Something went wrong: ${errMsg}`, stream: false }]);
      }
      return;
    }

    if (type === "dag_update") {
      const role   = msg.role;
      const status = msg.status; // "active" | "done" | "error"
      if (!role) return;
      if (status === "active") {
        setStatuses(prev => ({ ...prev, [role]: "running" }));
        setRevealed(p => p.includes(role) ? p : [...p, role]);
        setActivity(p => [...p, `${role} agent started`]);
        if (role === "backend" || role === "frontend") setTab("files");
        if (role === "qa") setTab("preview");
      } else if (status === "done") {
        setStatuses(prev => ({ ...prev, [role]: "done" }));
        const files = msg.files || [];
        if (files.length) setActivity(p => [...p, `${role} wrote ${files.length} file${files.length > 1 ? "s" : ""}`]);
      } else if (status === "error") {
        setStatuses(prev => ({ ...prev, [role]: "error" }));
        setActivity(p => [...p, `${role} agent errored`]);
      }
      return;
    }

    // ── Text streaming ─────────────────────────────────────────
    if (type === "text_start") {
      const id = j2uid();
      streamRef.current = id;
      setMessages(p => [...p, { id, role: "jarvis", text: "", stream: false }]);
      return;
    }

    if (type === "text" && streamRef.current != null) {
      const id = streamRef.current;
      setMessages(p => p.map(m => m.id === id ? { ...m, text: m.text + (msg.content || "") } : m));
      return;
    }

    if (type === "done") {
      if (streamRef.current != null) {
        const id = streamRef.current;
        // Capture final text to activity log
        setMessages(p => {
          const m = p.find(x => x.id === id);
          if (m) setActivity(act => [...act, m.text.slice(0, 80)]);
          return p;
        });
        streamRef.current = null;
      }
      return;
    }

    if (type === "interrupt") {
      streamRef.current = null;
      return;
    }
  };

  // ── Close WS helper ─────────────────────────────────────────
  const closeWs = () => {
    if (wsRef.current) {
      wsRef.current.onclose = null;
      wsRef.current.onerror = null;
      wsRef.current.onmessage = null;
      wsRef.current.close();
      wsRef.current = null;
    }
  };

  useJ2Effect(() => () => closeWs(), []);

  // ── startRun — try Hermes first, fall back to simulation ────
  const startRun = (taskText) => {
    clearTimers();
    closeWs();
    setPage("console");
    setRunning(true);
    setTask(taskText);
    setStatuses({});
    setPlan(null);
    setRevealed([]);
    setTelemetry({ tokens: 0, cost: 0 });
    setActivity([`Task received · ${taskText.slice(0, 60)}`]);
    setTab("plan");
    setMessages([{ id: j2uid(), role: "user", text: taskText }]);
    taskRef.current = taskText;

    const rawUrl = localStorage.getItem("hermesUrl") || "http://localhost:9000";
    const token  = localStorage.getItem("hermesToken") || "jarvis_hermes_2026";
    let wsUrl;
    try { wsUrl = new URL("/ws", rawUrl.replace(/^http/, "ws")).href; } catch (_) { wsUrl = null; }

    if (!wsUrl) {
      setWsStatus("error");
      setActivity(p => [...p, "No Hermes URL configured"]);
      setRunning(false);
      return;
    }

    setWsStatus("connecting");
    let authed = false;

    // If no auth_ok within 4s, fail cleanly
    const failTimer = setTimeout(() => {
      if (!authed) {
        setWsStatus("error");
        setActivity(p => [...p, "Hermes unreachable — connection timeout"]);
        closeWs();
        setRunning(false);
      }
    }, 4000);

    try {
      const ws = new WebSocket(wsUrl);
      ws.binaryType = "arraybuffer";
      wsRef.current = ws;

      ws.onopen = () => {
        ws.send(JSON.stringify({ type: "auth", token }));
      };

      ws.onmessage = (evt) => {
        // Watch for auth_ok before handing off to main handler
        if (!authed) {
          try {
            const m = JSON.parse(evt.data);
            if (m.type === "auth_ok") {
              authed = true;
              clearTimeout(failTimer);
            } else if (m.type === "auth_error") {
              clearTimeout(failTimer);
              setWsStatus("error");
              setActivity(p => [...p, "Auth failed — check HERMES_SECRET"]);
              setRunning(false);
              return;
            }
          } catch (_) {}
        }
        handleWsMessage(evt);
      };

      ws.onerror = () => {
        clearTimeout(failTimer);
        if (!authed) {
          setWsStatus("error");
          setActivity(p => [...p, "WS error — check backend"]);
          setRunning(false);
        }
      };

      ws.onclose = () => {
        clearTimeout(failTimer);
        setWsStatus("offline");
        if (running) setRunning(false);
      };
    } catch (_) {
      clearTimeout(failTimer);
      setWsStatus("error");
      setRunning(false);
    }
  };

  const onNew = () => {
    clearTimers();
    closeWs();
    setWsStatus("offline");
    setRunning(false); setMessages([]); setStatuses({});
    setPlan(null); setRevealed([]); setTelemetry({ tokens: 0, cost: 0 });
    setActivity([]); setTask(""); setPage("home");
  };

  return (
    <div className="j2-shell">
      <J2Rail page={page} setPage={setPage} running={running} wsStatus={wsStatus} />
      <main className="j2-stage">
        {page === "home"    && <J2Home onSend={startRun} onOpenRun={() => startRun(J2_TASK)} onViewAll={() => setPage("runs")} />}
        {page === "console" && (
          <J2ConsoleView
            messages={messages} onSend={startRun} running={running} task={task}
            statuses={statuses} plan={plan} revealed={revealed}
            telemetry={telemetry} activity={activity} tab={tab} setTab={setTab}
            onNew={onNew} wsStatus={wsStatus}
          />
        )}
        {page === "runs"    && <J2RunsPage    onOpenRun={() => startRun(J2_TASK)} />}
        {page === "memory"  && <J2MemoryPage  />}
        {page === "storage" && <J2StoragePage />}
        {page === "settings"&& <J2SettingsPage />}
      </main>

      <TweaksPanel>
        <TweakSection label="Theme" />
        <TweakRadio  label="Mode"    value={t.theme}    options={["light","dark"]}             onChange={v => setTweak("theme", v)} />
        <TweakColor  label="Accent"  value={t.accent}   options={J2_ACCENTS}                   onChange={v => setTweak("accent", v)} />
        <TweakSection label="Type & density" />
        <TweakToggle label="Serif headings"  value={t.showSerif}                               onChange={v => setTweak("showSerif", v)} />
        <TweakRadio  label="Density" value={t.density}  options={["compact","regular","comfy"]} onChange={v => setTweak("density", v)} />
      </TweaksPanel>
    </div>
  );
}

const J2_TWEAK_DEFAULTS = /*EDITMODE-BEGIN*/{
  "theme": "light",
  "accent": "#C2603C",
  "showSerif": true,
  "density": "regular"
}/*EDITMODE-END*/;

ReactDOM.createRoot(document.getElementById("root")).render(<J2App />);
