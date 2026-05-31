/* j2-workspace.jsx — right pane: tabs over the live build */

function J2TabBar({ tab, setTab, telemetry }) {
  const tabs = [
    { id: "plan",     label: "Plan" },
    { id: "files",    label: "Files" },
    { id: "preview",  label: "Preview" },
    { id: "activity", label: "Activity" },
  ];
  return (
    <div className="j2-ws-tabbar">
      <div className="j2-ws-tabs">
        {tabs.map(t => (
          <button key={t.id} className={`j2-ws-tab ${tab === t.id ? "on" : ""}`} onClick={() => setTab(t.id)}>
            {t.label}
          </button>
        ))}
      </div>
      <div className="j2-ws-telem">
        <span className="j2-ws-telem-k">tokens</span>
        <span className="j2-ws-telem-v">{telemetry.tokens.toLocaleString()}</span>
        <span className="j2-ws-telem-sep" />
        <span className="j2-ws-telem-k">cost</span>
        <span className="j2-ws-telem-v clay">${telemetry.cost.toFixed(4)}</span>
      </div>
    </div>
  );
}

function J2PlanView({ statuses, plan, task }) {
  const order = ["plan", "backend", "frontend", "iac", "qa", "done"];
  const doneCount = Object.values(statuses).filter(s => s === "done").length;
  return (
    <div className="j2-ws-body">
      <div className="j2-ws-head">
        <div>
          <div className="j2-ws-eyebrow">Execution graph</div>
          <div className="j2-ws-title">{task || J2_TASK}</div>
        </div>
        <div className="j2-ws-progress">
          <span className="mono">{doneCount}/{J2_NODES.length}</span> stages
        </div>
      </div>
      <J2DAG statuses={statuses} />
      {plan && plan.length > 0 && (
        <div className="j2-plan-list">
          <div className="j2-ws-eyebrow" style={{ marginBottom: 10 }}>Subtasks</div>
          {plan.map((p, i) => {
            const ids = ["backend", "frontend", "iac", "qa"];
            const st  = statuses[ids[i]] || "pending";
            return (
              <div className={`j2-plan-item ${st}`} key={i}>
                <span className="j2-plan-idx mono">{String(i+1).padStart(2,"0")}</span>
                <span className="j2-plan-text">{p}</span>
                <span className="j2-plan-state">{st === "done" ? "done" : st === "running" ? "running" : "queued"}</span>
              </div>
            );
          })}
        </div>
      )}
    </div>
  );
}

function J2FilesView({ revealed }) {
  const shown = J2_FILES.filter(f => revealed.includes(f.agent));
  return (
    <div className="j2-ws-body">
      <div className="j2-ws-head">
        <div>
          <div className="j2-ws-eyebrow">Working tree</div>
          <div className="j2-ws-title">{shown.length} files written</div>
        </div>
      </div>
      <div className="j2-file-list">
        {shown.length === 0 && <div className="j2-ws-empty">Files will appear here as agents complete.</div>}
        {shown.map((f, i) => (
          <div className="j2-file-row" key={f.path} style={{ animationDelay: `${(i % 3) * 50}ms` }}>
            <span className="j2-file-ico"><IconFile size={15} /></span>
            <span className="j2-file-path mono">{f.path}</span>
            <span className="j2-file-agent">{J2_AGENTS[f.agent].name}</span>
            <span className="j2-file-lines mono">+{f.lines}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function J2PreviewView({ ready }) {
  return (
    <div className="j2-ws-body">
      <div className="j2-ws-head">
        <div>
          <div className="j2-ws-eyebrow">Live viewport</div>
          <div className="j2-ws-title">{ready ? "dashboard.html" : "Waiting for frontend…"}</div>
        </div>
        {ready && <div className="j2-ws-progress">tap an element to correct it</div>}
      </div>
      <div className="j2-preview-frame">
        {ready ? (
          <div className="j2-ph-shot">
            <div className="j2-ph-grid" />
            <div className="j2-ph-tag mono">rendered preview · dashboard.html</div>
            <div className="j2-ph-hint">live preview renders here once agents ship</div>
          </div>
        ) : (
          <div className="j2-ph-shot pending">
            <div className="j2-ph-grid" />
            <div className="j2-ph-tag mono">awaiting build</div>
          </div>
        )}
      </div>
    </div>
  );
}

function J2ActivityView({ log, telemetry }) {
  return (
    <div className="j2-ws-body">
      <div className="j2-ws-head">
        <div>
          <div className="j2-ws-eyebrow">Run activity</div>
          <div className="j2-ws-title">Telemetry &amp; events</div>
        </div>
      </div>
      <div className="j2-metric-row">
        <div className="j2-metric">
          <div className="j2-metric-v serif">{telemetry.tokens.toLocaleString()}</div>
          <div className="j2-metric-k">tokens used</div>
        </div>
        <div className="j2-metric">
          <div className="j2-metric-v serif clay">${telemetry.cost.toFixed(4)}</div>
          <div className="j2-metric-k">spend</div>
        </div>
        <div className="j2-metric">
          <div className="j2-metric-v serif">{log.length}</div>
          <div className="j2-metric-k">events</div>
        </div>
      </div>
      <div className="j2-log-list">
        {log.map((l, i) => (
          <div className="j2-log-row" key={i}>
            <span className="j2-log-dot" />
            <span className="j2-log-text">{l}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

function J2Workspace({ tab, setTab, statuses, plan, revealedAgents, telemetry, activity, task }) {
  const previewReady = revealedAgents.includes("frontend");
  return (
    <div className="j2-workspace">
      <J2TabBar tab={tab} setTab={setTab} telemetry={telemetry} />
      {tab === "plan"     && <J2PlanView statuses={statuses} plan={plan} task={task} />}
      {tab === "files"    && <J2FilesView revealed={revealedAgents} />}
      {tab === "preview"  && <J2PreviewView ready={previewReady} />}
      {tab === "activity" && <J2ActivityView log={activity} telemetry={telemetry} />}
    </div>
  );
}

window.J2Workspace = J2Workspace;
