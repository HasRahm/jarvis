/* j2-home.jsx — warm landing: greeting + composer + recent runs */

function J2HomeRunCard({ run, onOpen }) {
  return (
    <button className="j2-home-run" onClick={onOpen}>
      <span className={`j2-run-status ${run.status}`} />
      <span className="j2-home-run-task">{run.task}</span>
      <span className="j2-home-run-meta mono">{run.when}</span>
    </button>
  );
}

function J2Home({ onSend, onOpenRun, onViewAll }) {
  return (
    <div className="j2-home">
      <div className="j2-home-inner">
        <div className="j2-home-greet">
          <span className="j2-home-spark"><IconSpark size={22} /></span>
          <h1 className="serif">{greeting()}.<br/>What should we build?</h1>
          <p className="j2-home-sub">
            Describe it in plain English. Jarvis decomposes the task and runs a graph of
            specialised agents — backend, frontend, QA and infra — then streams the build
            back to you here.
          </p>
        </div>

        <J2Composer onSend={onSend} placeholder="e.g. Build a SaaS REST API with JWT auth and user management" big />

        <div className="j2-home-chips">
          {J2_SUGGESTIONS.map(s => (
            <button key={s} className="j2-chip" onClick={() => onSend(s)}>{s}</button>
          ))}
        </div>

        <div className="j2-home-recent">
          <div className="j2-home-recent-head">
            <span className="j2-ws-eyebrow">Recent runs</span>
            <button className="j2-link-btn" onClick={onViewAll}>View all</button>
          </div>
          <div className="j2-home-run-list">
            {J2_RUNS.slice(0, 4).map((r, i) => (
              <J2HomeRunCard key={i} run={r} onOpen={() => onOpenRun(i)} />
            ))}
          </div>
        </div>
      </div>
    </div>
  );
}

window.J2Home = J2Home;
