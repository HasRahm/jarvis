/* j2-pages.jsx — secondary pages: Runs, Memory, Settings, Storage */

function J2PageHead({ eyebrow, title, sub }) {
  return (
    <div className="j2-page-head">
      <div className="j2-ws-eyebrow">{eyebrow}</div>
      <h2 className="serif j2-page-title">{title}</h2>
      {sub && <p className="j2-page-sub">{sub}</p>}
    </div>
  );
}

function J2RunsPage({ onOpenRun }) {
  return (
    <div className="j2-page-scroll">
      <div className="j2-page">
        <J2PageHead eyebrow="History" title="Runs" sub="Every build Jarvis has orchestrated for you." />
        <div className="j2-runs-table">
          {J2_RUNS.map((r, i) => (
            <button className="j2-run-row" key={i} onClick={() => onOpenRun(i)}>
              <span className={`j2-run-status ${r.status}`} />
              <span className="j2-run-row-task">{r.task}</span>
              <span className="j2-run-row-meta">
                <span className="j2-run-tag mono">{r.agents} agents</span>
                <span className="j2-run-tag mono">{r.files} files</span>
                <span className="j2-run-tag mono clay">${r.cost}</span>
              </span>
              <span className="j2-run-row-when mono">{r.when}</span>
            </button>
          ))}
        </div>
      </div>
    </div>
  );
}

function J2MemoryPage() {
  const kinds = { contract: "API contract", decision: "Decision", schema: "Schema" };
  return (
    <div className="j2-page-scroll">
      <div className="j2-page">
        <J2PageHead
          eyebrow="GBrain"
          title="Memory"
          sub="What Jarvis remembers across sessions — contracts, decisions and schemas, so every new run starts with context."
        />
        <div className="j2-mem-grid">
          {J2_MEMORY.map((m, i) => (
            <div className="j2-mem-card" key={i}>
              <div className="j2-mem-kind mono">{kinds[m.kind]}</div>
              <div className="j2-mem-title">{m.title}</div>
              <div className="j2-mem-note">{m.note}</div>
              <div className="j2-mem-from mono">{m.from}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

function J2StoragePage() {
  const [scanData, setScanData] = React.useState(null);
  const [loading,  setLoading]  = React.useState(true);
  const [error,    setError]    = React.useState(null);
  const [cleaning, setCleaning] = React.useState(false);
  const [result,   setResult]   = React.useState(null);
  const [confirm,  setConfirm]  = React.useState(false);

  function fmtMB(bytes) {
    if (bytes == null) return "—";
    const mb = bytes / 1048576;
    return mb >= 1000 ? (mb / 1024).toFixed(1) + " GB" : mb.toFixed(0) + " MB";
  }

  async function fetchScan() {
    setLoading(true); setError(null);
    const baseUrl = localStorage.getItem("hermesUrl") || "http://localhost:9000";
    const token   = localStorage.getItem("hermesToken") || "";
    try {
      const res = await fetch(new URL("/api/cleanup/scan", new URL(baseUrl).origin).href,
        { headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      setScanData(await res.json());
    } catch(e) { setError(e.message); }
    finally    { setLoading(false); }
  }

  async function doSafeClean() {
    setConfirm(false); setCleaning(true); setResult(null);
    const baseUrl = localStorage.getItem("hermesUrl") || "http://localhost:9000";
    const token   = localStorage.getItem("hermesToken") || "";
    try {
      const res = await fetch(new URL("/api/cleanup/safe", new URL(baseUrl).origin).href,
        { method: "POST", headers: { Authorization: `Bearer ${token}` } });
      if (!res.ok) throw new Error(`HTTP ${res.status}`);
      const r = await res.json();
      setResult(r);
      fetchScan();
    } catch(e) { setError(e.message); }
    finally    { setCleaning(false); }
  }

  React.useEffect(() => { fetchScan(); }, []);

  const s = scanData || {};
  return (
    <div className="j2-page-scroll">
      <div className="j2-page">
        <J2PageHead
          eyebrow="Disk"
          title="Storage"
          sub="Scan and clean temporary files from your local machine via Hermes."
        />

        {/* Summary cards */}
        <div className="j2-storage-grid">
          {[
            { label: "Temp files",     val: fmtMB(s.temp_bytes)       },
            { label: "Cache files",    val: fmtMB(s.cache_bytes)      },
            { label: "Safe to remove", val: fmtMB(s.total_safe_bytes) },
          ].map(({ label, val }) => (
            <div className="j2-storage-card" key={label}>
              <div className="j2-storage-val mono">{loading ? "…" : val}</div>
              <div className="j2-storage-key">{label}</div>
            </div>
          ))}
        </div>

        {error && (
          <div className="j2-storage-error">
            <span className="mono">✕ {error}</span>
            <button className="j2-storage-retry" onClick={fetchScan}>Retry</button>
          </div>
        )}

        {result && (
          <div className="j2-storage-ok">
            ✓ Freed {fmtMB(result.freed_bytes)} — {result.deleted_files} files removed
          </div>
        )}

        {/* Actions */}
        <div className="j2-storage-actions">
          <button className="j2-storage-btn refresh" onClick={fetchScan} disabled={loading}>
            {loading ? "Scanning…" : "↻ Refresh"}
          </button>
          {confirm ? (
            <>
              <button className="j2-storage-btn confirm" onClick={doSafeClean} disabled={cleaning}>
                {cleaning ? "Cleaning…" : "Confirm delete"}
              </button>
              <button className="j2-storage-btn cancel" onClick={() => setConfirm(false)}>
                Cancel
              </button>
            </>
          ) : (
            <button className="j2-storage-btn clean" onClick={() => setConfirm(true)} disabled={loading || cleaning}>
              ⚡ Safe clean
            </button>
          )}
        </div>
      </div>
    </div>
  );
}

function J2SettingsRow({ label, value, hint }) {
  return (
    <div className="j2-set-row">
      <div>
        <div className="j2-set-label">{label}</div>
        {hint && <div className="j2-set-hint">{hint}</div>}
      </div>
      <div className="j2-set-value mono">{value}</div>
    </div>
  );
}

function J2SettingsPage() {
  const url   = localStorage.getItem("hermesUrl")   || "http://localhost:9000";
  const token = localStorage.getItem("hermesToken") || "—";
  const wsUrl = url.replace(/^http/, "ws") + "/ws";
  return (
    <div className="j2-page-scroll">
      <div className="j2-page">
        <J2PageHead eyebrow="Configuration" title="Settings" sub="Connection and orchestration preferences." />

        <div className="j2-set-section">
          <div className="j2-ws-eyebrow" style={{ marginBottom: 14 }}>Connection</div>
          <div className="j2-set-card">
            <J2SettingsRow label="Hermes endpoint"  value={wsUrl}  hint="Real-time link for voice + streaming" />
            <J2SettingsRow label="Status"           value="● online" />
            <J2SettingsRow label="Auth token"       value={token.slice(0, 6) + "…"} />
          </div>
        </div>

        <div className="j2-set-section">
          <div className="j2-ws-eyebrow" style={{ marginBottom: 14 }}>Orchestration</div>
          <div className="j2-set-card">
            <J2SettingsRow label="Planner model"       value="Gemma-4"      hint="Decomposes tasks into the DAG" />
            <J2SettingsRow label="Adaptive routing"    value="on"            hint="Pick the best model per agent role" />
            <J2SettingsRow label="Sandbox"             value="Docker · local" />
            <J2SettingsRow label="Auto-heal"           value="on" />
          </div>
        </div>
      </div>
    </div>
  );
}

Object.assign(window, { J2RunsPage, J2MemoryPage, J2StoragePage, J2SettingsPage, J2PageHead });
