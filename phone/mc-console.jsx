// mc-console.jsx — Variation 2 · "Operator Console"
// NASA mission-control / Bloomberg terminal. Strict grid, monospace, dense data.
// Teal primary, amber accent reserved for anomalies. No glass, no glow.

function MCVariantConsole({ width = 1440, height = 920, palette: paletteOverride, density: densityOverride, vizMode: vizModeOverride, live = false }) {
  const mc = useMissionControl({ live });
  const palette = paletteOverride || { accent: '#5EEAD4', accent2: '#FFB547', border: 'rgba(255,255,255,0.08)' };
  const density = densityOverride || 'comfortable';
  const vizMode = vizModeOverride || 'waveform';
  const [input, setInput] = React.useState('Build a REST API for a todo list with frontend');
  const [healing, setHealing] = React.useState(false);

  React.useEffect(() => {
    if (mc.healToast) {
      setHealing(true);
      const t = setTimeout(() => setHealing(false), 2400);
      return () => clearTimeout(t);
    }
  }, [mc.healToast]);

  function submit() {
    if (mc.running) return;
    mc.runTask(input);
  }

  // Compute elapsed time on running tasks
  const elapsedRef = React.useRef(0);
  const [elapsed, setElapsed] = React.useState(0);
  React.useEffect(() => {
    if (!mc.running) return;
    const start = Date.now();
    const id = setInterval(() => setElapsed(Date.now() - start), 100);
    return () => clearInterval(id);
  }, [mc.running]);

  return (
    <div data-screen-label="V2 · Operator Console" style={{
      width, height, position: 'relative',
      background: '#0a0c0f', color: '#E6E9EF',
      fontFamily: "'JetBrains Mono', monospace",
      overflow: 'hidden',
    }}>
      {/* ── Top status strip ─────────────────────────── */}
      <ConsoleStatusStrip palette={palette} mc={mc} elapsed={elapsed} />

      {/* ── Main 3-column grid ──────────────────────── */}
      <div style={{
        position: 'absolute', top: 36, left: 0, right: 0, bottom: 200,
        display: 'grid',
        gridTemplateColumns: '320px 1fr 380px',
        gap: 0,
      }}>
        {/* ── Col 1: Command + Transcript + Agents ───── */}
        <div style={{
          display: 'flex', flexDirection: 'column',
          borderRight: `1px solid ${palette.border}`,
        }}>
          <ConsolePane title="COMMAND" id="cmd" palette={palette}>
            <div style={{ padding: 10 }}>
              <textarea
                value={input}
                onChange={(e) => setInput(e.target.value)}
                rows={2}
                style={{
                  width: '100%', resize: 'none',
                  background: 'rgba(255,255,255,0.02)',
                  border: `1px solid ${palette.border}`,
                  padding: 8, color: '#E6E9EF', fontSize: 12,
                  fontFamily: "'JetBrains Mono', monospace", outline: 'none',
                  lineHeight: 1.4,
                }}
              />
              <div style={{ display: 'flex', gap: 6, marginTop: 6 }}>
                <button onClick={submit} disabled={mc.running} style={{
                  flex: 1, padding: '7px 12px', cursor: mc.running ? 'wait' : 'pointer',
                  background: mc.running ? 'transparent' : palette.accent,
                  color: mc.running ? palette.accent : '#0a0c0f',
                  border: `1px solid ${palette.accent}`,
                  borderRadius: 0,
                  fontFamily: "'JetBrains Mono', monospace", fontSize: 10,
                  fontWeight: 700, letterSpacing: 1.6,
                }}>
                  {mc.running ? '◉ RUNNING' : '▶ EXEC'}
                </button>
                <button onClick={mc.reset} style={{
                  padding: '7px 12px', cursor: 'pointer', background: 'transparent',
                  color: 'rgba(230,233,239,0.7)', border: `1px solid ${palette.border}`,
                  fontFamily: "'JetBrains Mono', monospace", fontSize: 10,
                  letterSpacing: 1.4,
                }}>RESET</button>
              </div>
            </div>
          </ConsolePane>

          <ConsolePane title="TRANSCRIPT" id="trn" palette={palette} grow>
            <ConsoleTranscript messages={mc.messages} palette={palette} density={density} />
          </ConsolePane>

          <ConsolePane title="AGENT ROSTER" id="agt" palette={palette}>
            <div style={{ padding: 10 }}>
              <MCAgentRoster agents={mc.agents} palette={palette} density={density} orientation="vertical" />
            </div>
          </ConsolePane>
        </div>

        {/* ── Col 2: Visualizer + DAG ────────────────── */}
        <div style={{ display: 'flex', flexDirection: 'column' }}>
          <ConsolePane title="VOICE BUS · hermes/9000" id="viz" palette={palette}>
            <div style={{
              display: 'flex', alignItems: 'center', gap: 16, padding: 12,
              borderBottom: `1px solid ${palette.border}`,
            }}>
              <MCVisualizer mode={vizMode} level={mc.voiceLevel} size={120} palette={palette} />
              <div style={{ flex: 1 }}>
                <div style={{ fontSize: 9, letterSpacing: 1.4, color: 'rgba(230,233,239,0.5)' }}>
                  CURRENT UTTERANCE
                </div>
                <div style={{
                  marginTop: 4, fontSize: 13, fontFamily: "'Inter', sans-serif",
                  color: mc.activeVoice ? '#E6E9EF' : 'rgba(230,233,239,0.3)',
                  lineHeight: 1.5, minHeight: 60,
                }}>
                  {mc.activeVoice || '— silent —'}
                </div>
                <div style={{ display: 'flex', gap: 16, marginTop: 8, fontSize: 9, letterSpacing: 1 }}>
                  <ConsoleSpark label="VOL" value={Math.round(mc.voiceLevel * 100)} palette={palette} />
                  <ConsoleSpark label="STREAM" value={mc.activeVoice ? 'OPEN' : 'IDLE'} palette={palette} />
                  <ConsoleSpark label="CODEC" value="opus/48k" palette={palette} />
                </div>
              </div>
            </div>
          </ConsolePane>

          <ConsolePane title="EXECUTION GRAPH · 6 nodes · 7 edges" id="dag" palette={palette} grow>
            <div style={{ padding: 16, height: '100%', position: 'relative' }}>
              <MCDag nodes={mc.nodes} palette={palette} width={680} height={300} density={density} />
              <div style={{
                position: 'absolute', bottom: 12, right: 16, display: 'flex', gap: 12,
                fontSize: 9, letterSpacing: 1, color: 'rgba(230,233,239,0.45)',
              }}>
                <ConsoleLegendDot color={palette.accent2} label="ACTIVE" />
                <ConsoleLegendDot color={palette.accent} label="DONE" />
                <ConsoleLegendDot color="rgba(255,255,255,0.15)" label="IDLE" />
              </div>
            </div>
          </ConsolePane>
        </div>

        {/* ── Col 3: Viewport + Phone ────────────────── */}
        <div style={{
          display: 'flex', flexDirection: 'column',
          borderLeft: `1px solid ${palette.border}`,
        }}>
          <ConsolePane title="LIVE VIEWPORT · tap to heal" id="vp" palette={palette}>
            <div style={{ padding: 10 }}>
              <MCViewport palette={palette} healing={healing} onCorrect={() => {}} />
            </div>
          </ConsolePane>
          <ConsolePane title="HERMES UPLINK · phone PWA" id="hm" palette={palette} grow>
            <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'flex-start', padding: '10px 0', height: '100%' }}>
              <MCPhone messages={mc.messages} voiceLevel={mc.voiceLevel} palette={palette}
                running={mc.running} vizMode={vizMode} width={200} height={400} />
            </div>
          </ConsolePane>
        </div>
      </div>

      {/* ── Bottom: log stream (full width) ─────────── */}
      <div style={{
        position: 'absolute', left: 0, right: 0, bottom: 0, height: 200,
        borderTop: `1px solid ${palette.border}`,
        display: 'grid', gridTemplateColumns: '1fr 320px',
      }}>
        <ConsolePane title="SYSTEM LOG · live · last 80 entries" id="log" palette={palette} noBorder>
          <MCLogStream logs={mc.logs} palette={palette} density={density} />
        </ConsolePane>
        <ConsolePane title="GBRAIN MEMORY" id="gb" palette={palette}>
          <ConsoleGBrainPanel mc={mc} palette={palette} />
        </ConsolePane>
      </div>

      {/* ── Auto-heal toast ─────────────────────────── */}
      {mc.healToast && (
        <div style={{
          position: 'absolute', left: '50%', top: 50,
          transform: 'translateX(-50%)',
          padding: '8px 16px',
          background: '#0a0c0f',
          border: `1px solid ${palette.accent2}`,
          color: palette.accent2,
          fontSize: 10, letterSpacing: 1.6, fontWeight: 700,
          animation: 'mc-fade-up 0.3s',
          zIndex: 100,
        }}>
          [ AUTOHEAL ] {mc.healToast.intent} → {mc.healToast.element}
        </div>
      )}
    </div>
  );
}

function ConsoleStatusStrip({ palette, mc, elapsed }) {
  const pad = (n) => String(n).padStart(2, '0');
  const secs = Math.floor(elapsed / 1000);
  const t = `T+${pad(Math.floor(secs / 60))}:${pad(secs % 60)}.${pad(Math.floor((elapsed % 1000) / 10))}`;
  return (
    <div style={{
      position: 'absolute', top: 0, left: 0, right: 0, height: 36,
      display: 'flex', alignItems: 'center', padding: '0 12px',
      borderBottom: `1px solid ${palette.border}`,
      background: '#080a0c',
      fontFamily: "'JetBrains Mono', monospace", fontSize: 10, letterSpacing: 1,
    }}>
      <div style={{
        color: palette.accent, fontWeight: 700, letterSpacing: 3, marginRight: 24,
      }}>
        JARVIS // OPS
      </div>
      <div style={{ display: 'flex', gap: 18, color: 'rgba(230,233,239,0.6)' }}>
        <span>SESSION <span style={{ color: '#E6E9EF' }}>hasin@hermes</span></span>
        <span>NODE <span style={{ color: '#E6E9EF' }}>local · 9000</span></span>
        <span>{t}</span>
      </div>
      <div style={{ flex: 1 }} />
      <div style={{ display: 'flex', gap: 14, color: 'rgba(230,233,239,0.55)' }}>
        <span>STATE <span style={{
          color: mc.taskStatus === 'DONE' ? palette.accent : mc.taskStatus === 'HEALING' ? palette.accent2 : '#E6E9EF',
          fontWeight: 700,
          animation: mc.running ? 'mc-blink 1.4s infinite' : 'none',
        }}>{mc.taskStatus}</span></span>
        <span>CALLS <span style={{ color: '#E6E9EF' }}>{mc.telemetry.calls}</span></span>
        <span>TOK <span style={{ color: '#E6E9EF' }}>{mc.telemetry.tokens.toLocaleString()}</span></span>
        <span>$ <span style={{ color: palette.accent }}>{mc.telemetry.cost.toFixed(4)}</span></span>
        <span>↗ <span style={{ color: '#E6E9EF' }}>{mc.telemetry.latency}ms</span></span>
      </div>
    </div>
  );
}

function ConsolePane({ title, id, children, palette, grow, noBorder }) {
  return (
    <div style={{
      display: 'flex', flexDirection: 'column',
      flex: grow ? 1 : 'none',
      borderBottom: noBorder ? 'none' : `1px solid ${palette.border}`,
      minHeight: 0,
    }}>
      <div style={{
        padding: '5px 10px',
        background: 'rgba(255,255,255,0.015)',
        borderBottom: `1px solid ${palette.border}`,
        display: 'flex', alignItems: 'center', gap: 8,
        fontSize: 9, letterSpacing: 1.6,
      }}>
        <span style={{ color: 'rgba(230,233,239,0.4)' }}>[{id.toUpperCase()}]</span>
        <span style={{ color: palette.accent }}>{title}</span>
      </div>
      <div style={{ flex: 1, position: 'relative', minHeight: 0, overflow: 'hidden' }}>
        {children}
      </div>
    </div>
  );
}

function ConsoleSpark({ label, value, palette }) {
  return (
    <div>
      <span style={{ color: 'rgba(230,233,239,0.4)' }}>{label} </span>
      <span style={{ color: palette.accent }}>{value}</span>
    </div>
  );
}

function ConsoleLegendDot({ color, label }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 4 }}>
      <div style={{ width: 6, height: 6, background: color }} />
      <span>{label}</span>
    </div>
  );
}

function ConsoleTranscript({ messages, palette, density }) {
  const ref = React.useRef(null);
  React.useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [messages]);
  const pad = density === 'compact' ? '5px 8px' : '7px 10px';
  return (
    <div ref={ref} className="mc-pane" style={{
      height: '100%', overflowY: 'auto',
    }}>
      {messages.map((m, i) => (
        <div key={i} style={{
          padding: pad,
          borderBottom: `1px solid ${palette.border}`,
          background: m.role === 'user' ? 'rgba(94,234,212,0.04)' : 'transparent',
        }}>
          <div style={{
            display: 'flex', justifyContent: 'space-between',
            fontSize: 8, letterSpacing: 1.4, marginBottom: 3,
            color: m.role === 'user' ? palette.accent : 'rgba(230,233,239,0.5)',
          }}>
            <span>{m.role === 'user' ? '▶ OPS' : '◀ JARVIS'}</span>
            <span>{m.t}</span>
          </div>
          <div style={{
            fontFamily: "'Inter', sans-serif", fontSize: 12,
            color: '#E6E9EF', lineHeight: 1.5,
          }}>{m.text}</div>
        </div>
      ))}
    </div>
  );
}

function ConsoleGBrainPanel({ mc, palette }) {
  const learnings = [
    { t: '00:01', text: 'email index must be UNIQUE on case-folded value' },
    { t: '00:14', text: 'POST /api/users contract: {id, email, created_at}' },
    { t: '00:42', text: 'gpt-5.4 outperforms claude on assertion-heavy QA (n=42)' },
    { t: '01:08', text: 'todo composer empty state should show 3 example rows' },
  ];
  return (
    <div className="mc-pane" style={{
      height: '100%', overflowY: 'auto', fontSize: 10, lineHeight: 1.5,
    }}>
      <div style={{ padding: 10, borderBottom: `1px solid ${palette.border}` }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline' }}>
          <span style={{ color: 'rgba(230,233,239,0.5)' }}>NODES</span>
          <span style={{ color: palette.accent, fontWeight: 600 }}>12,408</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginTop: 3 }}>
          <span style={{ color: 'rgba(230,233,239,0.5)' }}>EDGES</span>
          <span style={{ color: palette.accent, fontWeight: 600 }}>41,902</span>
        </div>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'baseline', marginTop: 3 }}>
          <span style={{ color: 'rgba(230,233,239,0.5)' }}>+ NEW THIS RUN</span>
          <span style={{ color: palette.accent2, fontWeight: 600 }}>+ {mc.running ? '3' : '0'}</span>
        </div>
      </div>
      <div style={{ padding: 10 }}>
        <div style={{
          fontSize: 8, letterSpacing: 1.4, color: 'rgba(230,233,239,0.4)', marginBottom: 6,
        }}>RECENT LEARNINGS</div>
        {learnings.map((l, i) => (
          <div key={i} style={{ marginBottom: 6 }}>
            <span style={{ color: palette.accent, marginRight: 6 }}>+{l.t}</span>
            <span style={{ color: 'rgba(230,233,239,0.85)', fontFamily: "'Inter', sans-serif" }}>{l.text}</span>
          </div>
        ))}
      </div>
    </div>
  );
}

Object.assign(window, { MCVariantConsole });
