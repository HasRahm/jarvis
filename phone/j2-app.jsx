/* j2-app.jsx — shell: nav rail + router + run simulation + Hermes integration */
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

function J2Rail({ page, setPage, running }) {
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

function J2ConsoleView({ messages, onSend, running, statuses, plan, revealed, telemetry, activity, tab, setTab, onNew, task }) {
  const empty = messages.length === 0;
  return (
    <div className="j2-console">
      <div className="j2-console-bar">
        <div className="j2-console-bar-left">
          <span className={`j2-run-status ${running ? "running" : empty ? "idle" : "done"}`} />
          <span className="j2-console-task">{empty ? "New build" : (task || J2_TASK)}</span>
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
                    Jarvis will plan it, run the agents, and stream the work into the panel on the right.
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
  const timers = useJ2Ref([]);

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

  const applyEvent = (ev) => {
    setStatuses(prev => {
      const n = { ...prev };
      (ev.done || []).forEach(id => { n[id] = "done"; });
      if (ev.doneOne) n[ev.doneOne] = "done";
      const r = ev.running ? (Array.isArray(ev.running) ? ev.running : [ev.running]) : [];
      r.forEach(id => { if (n[id] !== "done") n[id] = "running"; });
      return n;
    });
    if (ev.doneOne && J2_AGENTS[ev.doneOne]) {
      setRevealed(p => p.includes(ev.doneOne) ? p : [...p, ev.doneOne]);
    }
    if (ev.plan)   setPlan(ev.plan);
    if (ev.tokens != null) setTelemetry({ tokens: ev.tokens, cost: ev.cost });
    if (ev.tab)    setTab(ev.tab);
    if (ev.say) {
      setMessages(p => [...p, { id: j2uid(), role: ev.say.role, text: ev.say.text, stream: true }]);
      setActivity(p => [...p, ev.say.text]);
    }
  };

  const startRun = (taskText) => {
    clearTimers();
    setPage("console");
    setRunning(true);
    setTask(taskText);
    setStatuses({});
    setPlan(null);
    setRevealed([]);
    setTelemetry({ tokens: 0, cost: 0 });
    setActivity([`Task received · ${taskText.slice(0, 48)}`]);
    setTab("plan");
    setMessages([{ id: j2uid(), role: "user", text: taskText }]);

    // Simulate run using the timeline
    let acc = 0;
    J2_TIMELINE.forEach(ev => {
      acc += ev.wait;
      timers.current.push(setTimeout(() => applyEvent(ev), acc));
    });
    timers.current.push(setTimeout(() => setRunning(false), acc + 300));
  };

  const onNew = () => {
    clearTimers();
    setRunning(false); setMessages([]); setStatuses({});
    setPlan(null); setRevealed([]); setTelemetry({ tokens: 0, cost: 0 });
    setActivity([]); setTask(""); setPage("home");
  };

  return (
    <div className="j2-shell">
      <J2Rail page={page} setPage={setPage} running={running} />
      <main className="j2-stage">
        {page === "home"    && <J2Home onSend={startRun} onOpenRun={() => startRun(J2_TASK)} onViewAll={() => setPage("runs")} />}
        {page === "console" && (
          <J2ConsoleView
            messages={messages} onSend={startRun} running={running} task={task}
            statuses={statuses} plan={plan} revealed={revealed}
            telemetry={telemetry} activity={activity} tab={tab} setTab={setTab}
            onNew={onNew}
          />
        )}
        {page === "runs"    && <J2RunsPage    onOpenRun={() => startRun(J2_TASK)} />}
        {page === "memory"  && <J2MemoryPage  />}
        {page === "storage" && <J2StoragePage />}
        {page === "settings"&& <J2SettingsPage />}
      </main>

      <TweaksPanel>
        <TweakSection label="Theme" />
        <TweakRadio  label="Mode"    value={t.theme}    options={["light","dark"]}                    onChange={v => setTweak("theme", v)} />
        <TweakColor  label="Accent"  value={t.accent}   options={J2_ACCENTS}                          onChange={v => setTweak("accent", v)} />
        <TweakSection label="Type & density" />
        <TweakToggle label="Serif headings"  value={t.showSerif}                                      onChange={v => setTweak("showSerif", v)} />
        <TweakRadio  label="Density" value={t.density}  options={["compact","regular","comfy"]}        onChange={v => setTweak("density", v)} />
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
