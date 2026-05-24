// mc-hud.jsx — Variation 1 · "HUD Cinematic"
// Iron Man / theatrical. Amber primary, teal accents. Corner brackets, scanlines,
// orbiting agent rings around a centered visualizer. Phone-in-frame docked right.

function MCVariantHUD({ width = 1440, height = 920, palette: paletteOverride, density: densityOverride, vizMode: vizModeOverride, live = false }) {
  const mc = useMissionControl({ live });
  const palette = paletteOverride || { accent: '#FFB547', accent2: '#5EEAD4', border: 'rgba(255,181,71,0.15)' };
  const density = densityOverride || 'comfortable';
  const vizMode = vizModeOverride || 'orb';
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

  return (
    <div data-screen-label="V1 · HUD Cinematic" style={{
      width, height, position: 'relative',
      background: 'radial-gradient(ellipse at 50% 30%, #1a1410 0%, #0a0907 50%, #050403 100%)',
      color: '#F5E9D7',
      fontFamily: "'Inter', sans-serif",
      overflow: 'hidden',
    }}>
      {/* Background grid + scanlines */}
      <div style={{
        position: 'absolute', inset: 0,
        backgroundImage: `linear-gradient(${hexA(palette.accent, 0.05)} 1px, transparent 1px), linear-gradient(90deg, ${hexA(palette.accent, 0.05)} 1px, transparent 1px)`,
        backgroundSize: '80px 80px',
        animation: 'mc-grid-shift 32s linear infinite',
        opacity: 0.6,
      }} />
      <div style={{
        position: 'absolute', inset: 0, pointerEvents: 'none',
        backgroundImage: `repeating-linear-gradient(0deg, rgba(255,181,71,0.015) 0px, rgba(255,181,71,0.015) 1px, transparent 1px, transparent 3px)`,
      }} />
      {/* Scan beam */}
      <div style={{
        position: 'absolute', left: 0, right: 0, height: 80, pointerEvents: 'none',
        background: `linear-gradient(180deg, transparent, ${hexA(palette.accent2, 0.04)} 50%, transparent)`,
        animation: 'mc-scan 8s linear infinite',
      }} />

      {/* ── Header ─────────────────────────────────────── */}
      <HudHeader palette={palette} telemetry={mc.telemetry} taskStatus={mc.taskStatus} wsStatus={mc.wsStatus} live={live} />

      {/* ── Corner brackets ─────────────────────────────── */}
      <CornerBrackets palette={palette} />

      {/* ── Center stage: visualizer with orbiting agents ─ */}
      <div style={{
        position: 'absolute', left: 480, top: 88, width: 480, height: 480,
      }}>
        <HudCenterStage mc={mc} palette={palette} vizMode={vizMode} />
      </div>

      {/* ── Left column: command + transcript ──────────── */}
      <div style={{
        position: 'absolute', left: 32, top: 88, width: 420, bottom: 280,
        display: 'flex', flexDirection: 'column', gap: 14,
      }}>
        <HudFramePanel label="01 · COMMAND" palette={palette}>
          <div style={{ padding: 14 }}>
            <textarea
              value={input}
              onChange={(e) => setInput(e.target.value)}
              rows={2}
              style={{
                width: '100%', resize: 'none',
                background: 'transparent', border: 'none', outline: 'none',
                color: '#F5E9D7', fontSize: 14, lineHeight: 1.5,
                fontFamily: "'Inter', sans-serif",
              }}
            />
            <div style={{ display: 'flex', alignItems: 'center', gap: 10, marginTop: 8 }}>
              <button onClick={submit} disabled={mc.running} style={{
                flex: 1, padding: '10px 14px', cursor: mc.running ? 'wait' : 'pointer',
                background: mc.running ? 'transparent' : palette.accent,
                color: mc.running ? palette.accent : '#0a0907',
                border: `1px solid ${palette.accent}`, borderRadius: 2,
                fontFamily: "'JetBrains Mono', monospace", fontSize: 11,
                fontWeight: 700, letterSpacing: 2,
                position: 'relative', overflow: 'hidden',
              }}>
                {mc.running ? `▸ EXECUTING · ${mc.taskStatus}` : '▸ ENGAGE'}
              </button>
              <button onClick={mc.reset} style={{
                padding: '10px 14px', cursor: 'pointer',
                background: 'transparent', color: palette.accent,
                border: `1px solid ${hexA(palette.accent, 0.3)}`, borderRadius: 2,
                fontFamily: "'JetBrains Mono', monospace", fontSize: 11,
                letterSpacing: 1.4,
              }}>
                RESET
              </button>
            </div>
          </div>
        </HudFramePanel>

        <HudFramePanel label="02 · TRANSCRIPT" palette={palette} fillRest>
          <HudTranscript messages={mc.messages} activeVoice={mc.activeVoice} palette={palette} />
        </HudFramePanel>
      </div>

      {/* ── Right column: viewport + phone (full-height) ─ */}
      <div style={{
        position: 'absolute', right: 32, top: 88, width: 420, bottom: 20,
        display: 'flex', flexDirection: 'column', gap: 14,
      }}>
        <HudFramePanel label={live ? "03 · LIVE BROWSER · playwright" : "03 · VIEWPORT · tap to heal"} palette={palette}>
          <div style={{ padding: live ? 0 : 12, height: '100%', position: 'relative' }}>
            {live
              ? <LiveViewport palette={palette} healing={healing} />
              : <MCViewport palette={palette} healing={healing} onCorrect={() => {}} />
            }
          </div>
        </HudFramePanel>

        <HudFramePanel label="04 · HERMES UPLINK · phone PWA" palette={palette} fillRest>
          <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'flex-start', padding: '14px 0', height: '100%' }}>
            <MCPhone messages={mc.messages} voiceLevel={mc.voiceLevel} palette={palette}
              running={mc.running} vizMode={vizMode} width={210} height={418} />
          </div>
        </HudFramePanel>
      </div>

      {/* ── Bottom: DAG + log + storage ─────────────────── */}
      <div style={{
        position: 'absolute', left: 32, right: 470, bottom: 20, height: 240,
        display: 'grid', gridTemplateColumns: '1.2fr 0.8fr 1fr', gap: 14,
      }}>
        <HudFramePanel label="05 · DIRECTED ACYCLIC GRAPH" palette={palette}>
          <div style={{ padding: 12, height: '100%' }}>
            <MCDag nodes={mc.nodes} palette={palette} width={560} height={200} density={density} />
          </div>
        </HudFramePanel>
        <HudFramePanel label="06 · SYSTEM LOG · live" palette={palette}>
          <MCLogStream logs={mc.logs} palette={palette} density={density} />
        </HudFramePanel>
        <HudFramePanel label="07 · STORAGE · disk cleanup" palette={palette}>
          <HudCleanupPanel palette={palette} />
        </HudFramePanel>
      </div>

      {/* ── Auto-heal toast ─────────────────────────────── */}
      {mc.healToast && (
        <div style={{
          position: 'absolute', left: '50%', top: 60,
          transform: 'translateX(-50%)',
          padding: '10px 20px',
          background: 'rgba(255, 181, 71, 0.12)',
          border: `1px solid ${palette.accent}`,
          color: palette.accent,
          fontFamily: "'JetBrains Mono', monospace",
          fontSize: 11, letterSpacing: 1.6,
          animation: 'mc-fade-up 0.4s cubic-bezier(.1,.8,.3,1)',
          boxShadow: `0 0 24px ${hexA(palette.accent, 0.3)}`,
          zIndex: 100,
        }}>
          ⚠ AUTO-HEAL · {mc.healToast.intent} → {mc.healToast.element}
        </div>
      )}
    </div>
  );
}

// ─── HUD primitives ──────────────────────────────────────
function HudHeader({ palette, telemetry, taskStatus, wsStatus, live }) {
  const wsColor = { online: '#34D399', connecting: '#FFB547', error: '#F87171', offline: 'rgba(255,255,255,0.3)' }[wsStatus] || 'rgba(255,255,255,0.3)';
  const wsLabel = { online: 'LIVE', connecting: 'LINK…', error: 'ERR', offline: 'LOCAL' }[wsStatus] || 'LOCAL';
  return (
    <div style={{
      position: 'absolute', top: 0, left: 0, right: 0, height: 64,
      display: 'flex', alignItems: 'center', padding: '0 32px',
      borderBottom: `1px solid ${hexA(palette.accent, 0.15)}`,
      background: 'rgba(10,9,7,0.6)',
      backdropFilter: 'blur(8px)',
      zIndex: 10,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <HudReticle palette={palette} />
        <div>
          <div style={{
            fontFamily: "'Space Grotesk', sans-serif", fontWeight: 700,
            fontSize: 18, letterSpacing: 6, color: '#F5E9D7',
          }}>J · A · R · V · I · S</div>
          <div style={{ display: 'flex', alignItems: 'center', gap: 8 }}>
            <div style={{
              fontFamily: "'JetBrains Mono', monospace", fontSize: 9, letterSpacing: 2,
              color: hexA(palette.accent, 0.7),
            }}>MISSION CONTROL · HERMES v2.6</div>
            {live && (
              <div style={{ display: 'flex', alignItems: 'center', gap: 4, padding: '1px 6px',
                border: `1px solid ${hexA(wsColor, 0.4)}`, borderRadius: 2,
                fontFamily: "'JetBrains Mono', monospace", fontSize: 8, letterSpacing: 1.4, color: wsColor,
              }}>
                <div style={{ width: 5, height: 5, borderRadius: '50%', background: wsColor,
                  boxShadow: wsStatus === 'online' ? `0 0 6px ${wsColor}` : 'none',
                  animation: wsStatus === 'online' ? 'mc-blink 2s ease-in-out infinite' : 'none',
                }} />
                {wsLabel}
              </div>
            )}
          </div>
        </div>
      </div>
      <div style={{ flex: 1 }} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 24 }}>
        <HudMetric label="STATUS" value={taskStatus} accent={palette.accent} pulse={taskStatus !== 'READY' && taskStatus !== 'DONE'} />
        <HudMetric label="CALLS" value={telemetry.calls} accent={palette.accent2} />
        <HudMetric label="TOKENS" value={telemetry.tokens.toLocaleString()} accent={palette.accent2} />
        <HudMetric label="SPEND" value={'$' + telemetry.cost.toFixed(4)} accent={palette.accent2} />
        <HudMetric label="LATENCY" value={telemetry.latency + 'ms'} accent={palette.accent2} />
      </div>
    </div>
  );
}

function HudMetric({ label, value, accent, pulse }) {
  return (
    <div style={{ minWidth: 80 }}>
      <div style={{
        fontFamily: "'JetBrains Mono', monospace", fontSize: 8,
        color: 'rgba(245,233,215,0.45)', letterSpacing: 1.4,
      }}>{label}</div>
      <div style={{
        fontFamily: "'Space Grotesk', monospace", fontSize: 16, fontWeight: 600,
        color: accent,
        animation: pulse ? 'mc-blink 1.4s ease-in-out infinite' : 'none',
        letterSpacing: 0.5,
      }}>{value}</div>
    </div>
  );
}

function HudReticle({ palette }) {
  return (
    <svg width="40" height="40" viewBox="0 0 40 40" style={{ flexShrink: 0 }}>
      <circle cx="20" cy="20" r="16" stroke={palette.accent} fill="none" strokeWidth="1" />
      <circle cx="20" cy="20" r="10" stroke={hexA(palette.accent, 0.4)} fill="none" strokeWidth="1" />
      <circle cx="20" cy="20" r="3" fill={palette.accent} />
      <line x1="20" y1="0" x2="20" y2="6" stroke={palette.accent} strokeWidth="1" />
      <line x1="20" y1="34" x2="20" y2="40" stroke={palette.accent} strokeWidth="1" />
      <line x1="0" y1="20" x2="6" y2="20" stroke={palette.accent} strokeWidth="1" />
      <line x1="34" y1="20" x2="40" y2="20" stroke={palette.accent} strokeWidth="1" />
      <path d="M 4 4 L 4 12 M 4 4 L 12 4" stroke={palette.accent2} strokeWidth="1.5" fill="none" />
      <path d="M 36 4 L 36 12 M 36 4 L 28 4" stroke={palette.accent2} strokeWidth="1.5" fill="none" />
      <path d="M 4 36 L 4 28 M 4 36 L 12 36" stroke={palette.accent2} strokeWidth="1.5" fill="none" />
      <path d="M 36 36 L 36 28 M 36 36 L 28 36" stroke={palette.accent2} strokeWidth="1.5" fill="none" />
    </svg>
  );
}

function CornerBrackets({ palette }) {
  const c = palette.accent;
  const sz = 22;
  const offset = 16;
  const Bracket = ({ style, d }) => (
    <svg width={sz} height={sz} style={{ position: 'absolute', ...style, pointerEvents: 'none' }} viewBox={`0 0 ${sz} ${sz}`}>
      <path d={d} stroke={c} strokeWidth="1.5" fill="none" />
    </svg>
  );
  return (
    <>
      <Bracket style={{ left: offset, top: offset + 64 }} d={`M 0 ${sz} L 0 0 L ${sz} 0`} />
      <Bracket style={{ right: offset, top: offset + 64 }} d={`M ${sz} ${sz} L ${sz} 0 L 0 0`} />
      <Bracket style={{ left: offset, bottom: offset }} d={`M 0 0 L 0 ${sz} L ${sz} ${sz}`} />
      <Bracket style={{ right: offset, bottom: offset }} d={`M ${sz} 0 L ${sz} ${sz} L 0 ${sz}`} />
    </>
  );
}

function HudFramePanel({ label, children, palette, fillRest, style }) {
  return (
    <div style={{
      flex: fillRest ? 1 : 'none',
      display: 'flex', flexDirection: 'column',
      background: 'rgba(10,9,7,0.55)',
      border: `1px solid ${hexA(palette.accent, 0.18)}`,
      borderRadius: 2,
      position: 'relative',
      ...style,
    }}>
      <div style={{
        padding: '6px 12px',
        borderBottom: `1px solid ${hexA(palette.accent, 0.12)}`,
        fontFamily: "'JetBrains Mono', monospace", fontSize: 9,
        letterSpacing: 1.8, color: hexA(palette.accent, 0.85),
        display: 'flex', alignItems: 'center', gap: 8,
      }}>
        <div style={{ width: 5, height: 5, background: palette.accent, transform: 'rotate(45deg)' }} />
        {label}
      </div>
      <div style={{ flex: 1, position: 'relative', overflow: 'hidden' }}>
        {children}
      </div>
    </div>
  );
}

function HudCenterStage({ mc, palette, vizMode }) {
  // Visualizer in center, agents around as a ring
  const agentOrder = ['orchestrator', 'frontend', 'backend', 'qa', 'iac'];
  const radius = 200;
  const center = 240;
  return (
    <div style={{ position: 'relative', width: 480, height: 480 }}>
      {/* Concentric rings */}
      <svg width="480" height="480" style={{ position: 'absolute', inset: 0 }}>
        <circle cx={center} cy={center} r="60" stroke={hexA(palette.accent, 0.15)} fill="none" />
        <circle cx={center} cy={center} r="120" stroke={hexA(palette.accent, 0.2)} fill="none" strokeDasharray="4 4" />
        <circle cx={center} cy={center} r="180" stroke={hexA(palette.accent, 0.1)} fill="none" />
        {/* Crosshairs */}
        <line x1={center} y1={20} x2={center} y2={60} stroke={hexA(palette.accent, 0.3)} />
        <line x1={center} y1={420} x2={center} y2={460} stroke={hexA(palette.accent, 0.3)} />
        <line x1={20} y1={center} x2={60} y2={center} stroke={hexA(palette.accent, 0.3)} />
        <line x1={420} y1={center} x2={460} y2={center} stroke={hexA(palette.accent, 0.3)} />
        {/* Tick marks around outer ring */}
        {Array.from({ length: 36 }).map((_, i) => {
          const a = (i / 36) * Math.PI * 2 - Math.PI / 2;
          const r1 = 188, r2 = i % 3 === 0 ? 198 : 193;
          return (
            <line key={i}
              x1={center + Math.cos(a) * r1} y1={center + Math.sin(a) * r1}
              x2={center + Math.cos(a) * r2} y2={center + Math.sin(a) * r2}
              stroke={hexA(palette.accent, 0.4)} strokeWidth="1" />
          );
        })}
      </svg>

      {/* Visualizer center */}
      <div style={{
        position: 'absolute', left: center - 110, top: center - 110,
      }}>
        <MCVisualizer mode={vizMode} level={mc.voiceLevel} size={220} palette={palette} />
      </div>

      {/* Active voice readout */}
      {mc.activeVoice && (
        <div style={{
          position: 'absolute', left: 30, right: 30, bottom: 30, textAlign: 'center',
          fontFamily: "'JetBrains Mono', monospace", fontSize: 11,
          color: palette.accent2, letterSpacing: 0.6, lineHeight: 1.5,
          textShadow: `0 0 12px ${hexA(palette.accent2, 0.6)}`,
        }}>
          “{mc.activeVoice}”
        </div>
      )}

      {/* Orbiting agents */}
      {agentOrder.map((role, i) => {
        const a = (i / agentOrder.length) * Math.PI * 2 - Math.PI / 2;
        const x = center + Math.cos(a) * radius;
        const y = center + Math.sin(a) * radius;
        const agent = mc.agents[role];
        const meta = ROLE_META[role];
        const isActive = agent.status === 'active';
        const isDone = agent.status === 'done';
        return (
          <div key={role} style={{
            position: 'absolute', left: x - 60, top: y - 30,
            width: 120, height: 60,
          }}>
            <svg width="120" height="60" style={{ position: 'absolute', inset: 0 }}>
              <path d={`M 8 0 L 112 0 L 120 8 L 120 52 L 112 60 L 8 60 L 0 52 L 0 8 Z`}
                fill={isActive ? hexA(meta.color, 0.15) : 'rgba(10,9,7,0.85)'}
                stroke={isActive ? meta.color : isDone ? hexA(meta.color, 0.5) : hexA(palette.accent, 0.2)}
                strokeWidth="1" />
              {isActive && (
                <path d={`M 8 0 L 112 0 L 120 8 L 120 52 L 112 60 L 8 60 L 0 52 L 0 8 Z`}
                  fill="none" stroke={meta.color} strokeWidth="1" strokeDasharray="3 3">
                  <animate attributeName="stroke-dashoffset" from="0" to="12" dur="0.8s" repeatCount="indefinite" />
                </path>
              )}
            </svg>
            <div style={{
              position: 'relative', padding: '6px 12px', height: '100%',
              display: 'flex', flexDirection: 'column', justifyContent: 'center',
            }}>
              <div style={{
                fontFamily: "'JetBrains Mono', monospace", fontSize: 9,
                letterSpacing: 1.2, color: meta.color,
                display: 'flex', justifyContent: 'space-between',
              }}>
                <span>{meta.short}</span>
                <span style={{
                  fontSize: 7, opacity: 0.8,
                  animation: isActive ? 'mc-blink 1.2s infinite' : 'none',
                }}>
                  {isActive ? '● RUN' : isDone ? '✓' : '—'}
                </span>
              </div>
              <div style={{
                fontSize: 9, color: '#F5E9D7', marginTop: 2,
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              }}>
                {agent.step}
              </div>
            </div>
          </div>
        );
      })}
    </div>
  );
}

function HudTranscript({ messages, activeVoice, palette }) {
  const ref = React.useRef(null);
  React.useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [messages]);
  return (
    <div ref={ref} className="mc-pane" style={{
      height: '100%', overflowY: 'auto', padding: 12,
      display: 'flex', flexDirection: 'column', gap: 8,
    }}>
      {messages.map((m, i) => (
        <div key={i} style={{
          padding: '8px 10px',
          background: m.role === 'user' ? hexA(palette.accent, 0.08) : 'rgba(255,255,255,0.02)',
          border: `1px solid ${m.role === 'user' ? hexA(palette.accent, 0.25) : 'rgba(255,233,215,0.06)'}`,
          borderLeft: `2px solid ${m.role === 'user' ? palette.accent : palette.accent2}`,
        }}>
          <div style={{
            fontFamily: "'JetBrains Mono', monospace", fontSize: 8,
            letterSpacing: 1.4, color: m.role === 'user' ? palette.accent : palette.accent2,
            marginBottom: 3,
          }}>
            {m.t} · {m.role === 'user' ? 'OPERATOR' : 'JARVIS'}
          </div>
          <div style={{ fontSize: 12, lineHeight: 1.5, color: '#F5E9D7' }}>{m.text}</div>
        </div>
      ))}
    </div>
  );
}

// ─── Storage / Disk Cleanup Panel ───────────────────────────
function HudCleanupPanel({ palette }) {
  const scan   = useApi('GET',  '/api/cleanup/scan');
  const safeCl = useApi('POST', '/api/cleanup/safe');
  const judge  = useApi('GET',  '/api/cleanup/judge');
  const del    = useApi('POST', '/api/cleanup/delete');

  const [view,     setView]     = React.useState('overview'); // 'overview' | 'judge'
  const [confirm,  setConfirm]  = React.useState(false);
  const [deleting, setDeleting] = React.useState(null); // path currently being deleted

  // Auto-scan on mount
  React.useEffect(() => { scan.call(); }, []);

  // Re-scan after a safe clean so numbers refresh automatically
  React.useEffect(() => { if (safeCl.data) scan.call(); }, [safeCl.data]);

  async function confirmSafeClean() {
    setConfirm(false);
    await safeCl.call();
  }

  async function handleJudge() {
    setView('judge');
    if (!judge.data) await judge.call();
  }

  async function handleDelete(path) {
    setDeleting(path);
    const r = await del.call({ path });
    setDeleting(null);
    if (r) {
      judge.setData(prev => Array.isArray(prev) ? prev.filter(i => i.path !== path) : prev);
      scan.call(); // refresh totals
    }
  }

  const s = scan.data || {};
  const anyLoading = scan.loading || safeCl.loading || judge.loading;
  const anyError   = scan.error || safeCl.error || judge.error || del.error;

  function fmtMB(bytes) {
    if (bytes == null) return '—';
    const mb = bytes / 1048576;
    return mb >= 1000 ? (mb / 1024).toFixed(1) + ' GB' : mb.toFixed(0) + ' MB';
  }

  const mono = { fontFamily: "'JetBrains Mono', monospace" };
  const dim  = { color: 'rgba(245,233,215,0.45)', fontSize: 8, letterSpacing: 1.2, ...mono };

  return (
    <div style={{ height: '100%', display: 'flex', flexDirection: 'column', padding: '8px 10px', gap: 6, overflow: 'hidden' }}>

      {/* ── Disk summary ─────────────────────────── */}
      <div style={{ display: 'flex', gap: 6, alignItems: 'center' }}>
        {[
          { label: 'TEMP',  val: fmtMB(s.temp_bytes)        },
          { label: 'CACHE', val: fmtMB(s.cache_bytes)       },
          { label: 'SAFE',  val: fmtMB(s.total_safe_bytes)  },
        ].map(({ label, val }) => (
          <div key={label} style={{ flex: 1, background: 'rgba(255,181,71,0.05)', border: `1px solid ${hexA(palette.accent, 0.15)}`, padding: '4px 6px' }}>
            <div style={dim}>{label}</div>
            <div style={{ ...mono, fontSize: 13, fontWeight: 600, color: palette.accent, lineHeight: 1.2 }}>{val}</div>
          </div>
        ))}
        <button onClick={() => scan.call()} disabled={anyLoading} title="Refresh" style={{
          ...mono, fontSize: 11, padding: '4px 7px', cursor: 'pointer', flexShrink: 0,
          background: 'transparent', color: hexA(palette.accent, 0.55),
          border: `1px solid ${hexA(palette.accent, 0.2)}`,
        }}>↻</button>
      </div>

      {/* ── Error strip ──────────────────────────── */}
      {anyError && (
        <div style={{ ...mono, fontSize: 9, color: '#F87171', letterSpacing: 0.8, padding: '3px 6px',
          background: 'rgba(248,113,113,0.08)', border: '1px solid rgba(248,113,113,0.2)',
          whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
          ✕ {anyError}
        </div>
      )}

      {/* ── Safe clean result banner ─────────────── */}
      {safeCl.data && !confirm && (
        <div style={{ ...mono, fontSize: 9, color: '#34D399', letterSpacing: 0.8, padding: '3px 6px',
          background: 'rgba(52,211,153,0.08)', border: '1px solid rgba(52,211,153,0.2)' }}>
          ✓ freed {fmtMB(safeCl.data.freed_bytes)} · {safeCl.data.deleted_files} files
        </div>
      )}

      {/* ── Confirm modal ────────────────────────── */}
      {confirm ? (
        <div style={{ padding: '6px 8px', background: 'rgba(255,181,71,0.08)', border: `1px solid ${palette.accent}` }}>
          <div style={{ ...mono, fontSize: 9, color: palette.accent, marginBottom: 6 }}>
            Delete all temp + cache files?
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button onClick={confirmSafeClean} style={{
              ...mono, fontSize: 9, padding: '4px 10px', cursor: 'pointer',
              background: palette.accent, color: '#0a0907', border: 'none', fontWeight: 700, letterSpacing: 1.2,
            }}>CONFIRM</button>
            <button onClick={() => setConfirm(false)} style={{
              ...mono, fontSize: 9, padding: '4px 10px', cursor: 'pointer',
              background: 'transparent', color: hexA(palette.accent, 0.7), border: `1px solid ${hexA(palette.accent, 0.3)}`,
            }}>CANCEL</button>
          </div>
        </div>
      ) : (
        /* ── Action buttons ───────────────────── */
        <div style={{ display: 'flex', gap: 6 }}>
          <button onClick={() => setConfirm(true)} disabled={anyLoading} style={{
            flex: 1, ...mono, fontSize: 9, letterSpacing: 1.2, fontWeight: 700, padding: '6px 8px', cursor: 'pointer',
            background: safeCl.loading ? 'transparent' : hexA(palette.accent, 0.85),
            color: safeCl.loading ? palette.accent : '#0a0907',
            border: `1px solid ${palette.accent}`,
          }}>
            {safeCl.loading ? '…CLEANING' : '⚡ SAFE CLEAN'}
          </button>
          <button
            onClick={view === 'judge' ? () => { setView('overview'); judge.reset(); } : handleJudge}
            disabled={anyLoading}
            style={{
              flex: 1, ...mono, fontSize: 9, letterSpacing: 1.2, padding: '6px 8px', cursor: 'pointer',
              background: view === 'judge' ? hexA(palette.accent2, 0.15) : 'transparent',
              color: view === 'judge' ? palette.accent2 : hexA(palette.accent, 0.7),
              border: `1px solid ${view === 'judge' ? palette.accent2 : hexA(palette.accent, 0.3)}`,
            }}>
            {judge.loading ? '…SCANNING' : view === 'judge' ? '✕ CLOSE' : '🔍 SCAN ITEMS'}
          </button>
        </div>
      )}

      {/* ── Judgment items list ──────────────────── */}
      {view === 'judge' && (
        <div style={{ flex: 1, overflowY: 'auto', display: 'flex', flexDirection: 'column', gap: 3 }}>
          {judge.loading && <div style={dim}>scanning disk…</div>}
          {!judge.data && !judge.loading && <div style={dim}>Click SCAN ITEMS to find candidates.</div>}
          {Array.isArray(judge.data) && judge.data.length === 0 && (
            <div style={{ ...dim, color: '#34D399' }}>✓ Nothing to remove</div>
          )}
          {Array.isArray(judge.data) && judge.data.map((item, i) => (
            <div key={i} style={{
              display: 'flex', alignItems: 'center', gap: 4,
              padding: '4px 6px', background: 'rgba(255,255,255,0.02)',
              border: `1px solid ${hexA(palette.accent, 0.1)}`,
            }}>
              <div style={{ flex: 1, minWidth: 0 }}>
                <div style={{ ...mono, fontSize: 8, color: '#F5E9D7', whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis' }}>
                  {item.path.split(/[/\\]/).pop()}
                </div>
                <div style={{ ...dim, fontSize: 7 }}>
                  {fmtMB(item.size_bytes)} · {item.reason || item.suggestion || ''}
                </div>
              </div>
              <button
                onClick={() => handleDelete(item.path)}
                disabled={deleting === item.path || del.loading}
                style={{
                  ...mono, fontSize: 8, padding: '2px 6px', cursor: 'pointer', flexShrink: 0,
                  background: 'transparent', color: '#F87171', border: '1px solid rgba(248,113,113,0.4)',
                }}>
                {deleting === item.path ? '…' : 'DEL'}
              </button>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

Object.assign(window, { MCVariantHUD });
