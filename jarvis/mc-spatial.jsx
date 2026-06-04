// mc-spatial.jsx — Variation 3 · "Holographic Spatial"
// Floating glass panels in space, depth via parallax/perspective, soft glow.
// Particle visualizer dominant. Phone "hovers" prominently on the right.
// Cyan + violet, restrained amber for anomalies.

function MCVariantSpatial({ width = 1440, height = 920, palette: paletteOverride, density: densityOverride, vizMode: vizModeOverride }) {
  const mc = useMissionControl();
  const palette = paletteOverride || { accent: '#7DD3FC', accent2: '#C4B5FD', anomaly: '#FFB547', border: 'rgba(255,255,255,0.08)' };
  const density = densityOverride || 'comfortable';
  const vizMode = vizModeOverride || 'particles';
  const [input, setInput] = React.useState('Build a REST API for a todo list with frontend');
  const [healing, setHealing] = React.useState(false);
  const [viewMode, setViewMode] = React.useState('3d');

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
    <div data-screen-label="V3 · Holographic Spatial" style={{
      width, height, position: 'relative',
      background: 'radial-gradient(ellipse at 30% 20%, #1e1b3a 0%, #0b0b1a 50%, #050511 100%)',
      color: '#E8ECFF', fontFamily: "'Inter', sans-serif",
      overflow: 'hidden',
    }}>
      {/* Ambient orbs */}
      <Orb size={620} top={-180} left={-180} color={palette.accent2} opacity={0.18} />
      <Orb size={520} bottom={-160} right={-100} color={palette.accent} opacity={0.14} />
      <Orb size={400} top="38%" left="42%" color="#F472B6" opacity={0.08} />

      {/* Background particles full-bleed */}
      <div style={{
        position: 'absolute', inset: 0, opacity: 0.5, pointerEvents: 'none',
      }}>
        <SpatialStarfield />
      </div>

      {/* Soft grid */}
      <div style={{
        position: 'absolute', inset: 0,
        backgroundImage: `linear-gradient(rgba(125,211,252,0.04) 1px, transparent 1px), linear-gradient(90deg, rgba(125,211,252,0.04) 1px, transparent 1px)`,
        backgroundSize: '60px 60px',
        maskImage: 'radial-gradient(ellipse at center, black 30%, transparent 75%)',
        WebkitMaskImage: 'radial-gradient(ellipse at center, black 30%, transparent 75%)',
        pointerEvents: 'none',
      }} />

      {/* ── Header ─────────────────────────────────── */}
      <SpatialHeader palette={palette} mc={mc} />

      {/* ── Big visualizer behind everything ────── */}
      <div style={{
        position: 'absolute', left: 380, top: 180, width: 560, height: 560,
        pointerEvents: 'none',
      }}>
        <MCVisualizer mode={vizMode} level={mc.voiceLevel} size={560} palette={palette} />
      </div>

      {/* ── Left: floating panels ─────────────────── */}
      <SpatialPanel style={{
        position: 'absolute', left: 32, top: 88, width: 360, padding: 0,
      }} palette={palette}>
        <SpatialPanelHeader title="Command" subtitle="natural language → DAG" palette={palette} />
        <div style={{ padding: 16 }}>
          <textarea
            value={input}
            onChange={(e) => setInput(e.target.value)}
            rows={2}
            placeholder="Tell Jarvis what to build…"
            style={{
              width: '100%', resize: 'none',
              background: 'rgba(255,255,255,0.04)',
              border: `1px solid ${palette.border}`,
              borderRadius: 10, padding: 10,
              color: '#E8ECFF', fontSize: 13, lineHeight: 1.5,
              fontFamily: "'Inter', sans-serif", outline: 'none',
            }}
          />
          <div style={{ display: 'flex', gap: 8, marginTop: 10 }}>
            <button onClick={submit} disabled={mc.running} style={{
              flex: 1, padding: '10px 16px', cursor: mc.running ? 'wait' : 'pointer',
              background: `linear-gradient(135deg, ${palette.accent}, ${palette.accent2})`,
              color: '#0b0b1a',
              border: 'none', borderRadius: 10,
              fontWeight: 700, fontSize: 12, letterSpacing: 1.2,
              boxShadow: `0 4px 18px ${hexA(palette.accent, 0.4)}`,
            }}>
              {mc.running ? '◉  Executing' : '▸  Engage'}
            </button>
            <button onClick={mc.reset} style={{
              padding: '10px 14px', cursor: 'pointer',
              background: 'rgba(255,255,255,0.04)',
              color: 'rgba(232,236,255,0.7)',
              border: `1px solid ${palette.border}`, borderRadius: 10,
              fontSize: 12, letterSpacing: 1,
            }}>Reset</button>
          </div>
        </div>
      </SpatialPanel>

      <SpatialPanel style={{
        position: 'absolute', left: 32, top: 280, width: 360, height: 320,
      }} palette={palette}>
        <SpatialPanelHeader title="Transcript" subtitle={mc.activeVoice ? '● speaking' : 'idle'}
          accent={mc.activeVoice ? palette.accent : null} palette={palette} />
        <SpatialTranscript messages={mc.messages} palette={palette} density={density} />
      </SpatialPanel>

      <SpatialPanel style={{
        position: 'absolute', left: 32, top: 620, width: 360, height: 270,
      }} palette={palette}>
        <SpatialPanelHeader title="GBrain memory" subtitle="local knowledge graph" palette={palette} />
        <SpatialMemory mc={mc} palette={palette} />
      </SpatialPanel>

      {/* ── Center: DAG glass panel ─────────────────── */}
      <SpatialPanel style={{
        position: 'absolute', left: 412, top: 88, width: 540, height: 360,
      }} palette={palette}>
        <SpatialPanelHeader title="Execution graph"
          subtitle={mc.running ? `${mc.taskStatus.toLowerCase()} · 6 nodes` : '6 nodes · 7 edges'}
          accent={mc.taskStatus === 'HEALING' ? palette.anomaly : null}
          palette={palette} />
        <div style={{ padding: 16, height: 'calc(100% - 56px)' }}>
          <MCDag nodes={mc.nodes} palette={palette} width={508} height={264} density={density} />
        </div>
      </SpatialPanel>

      {/* Voice readout — floating below DAG */}
      <SpatialPanel style={{
        position: 'absolute', left: 412, top: 468, width: 540, padding: 16,
      }} palette={palette} subtle>
        <div style={{
          display: 'flex', alignItems: 'center', gap: 16, padding: '8px 4px',
        }}>
          <MCVisualizer mode="orb" level={mc.voiceLevel} size={72} palette={palette} />
          <div style={{ flex: 1 }}>
            <div style={{
              fontSize: 9, letterSpacing: 2, color: 'rgba(232,236,255,0.5)',
              fontFamily: "'JetBrains Mono', monospace",
            }}>
              JARVIS · TTS · opus 48k
            </div>
            <div style={{
              marginTop: 6, fontSize: 14, lineHeight: 1.5,
              color: mc.activeVoice ? palette.accent : 'rgba(232,236,255,0.4)',
              fontStyle: mc.activeVoice ? 'normal' : 'italic',
            }}>
              {mc.activeVoice ? `“${mc.activeVoice}”` : 'standing by…'}
            </div>
          </div>
        </div>
      </SpatialPanel>

      {/* Agents — floating chips below voice readout */}
      <div style={{
        position: 'absolute', left: 412, top: 600, width: 540,
      }}>
        <div style={{
          padding: '0 4px 8px', display: 'flex', alignItems: 'baseline', gap: 8,
        }}>
          <span style={{ fontSize: 11, fontWeight: 600, color: '#E8ECFF', letterSpacing: 0.4 }}>Agents</span>
          <span style={{ fontSize: 9, color: 'rgba(232,236,255,0.4)',
            fontFamily: "'JetBrains Mono', monospace", letterSpacing: 1 }}>
            5 SPECIALISTS · ADAPTIVE ROUTER ON
          </span>
        </div>
        <MCAgentRoster agents={mc.agents} palette={palette} density={density} />
      </div>

      {/* Log stream */}
      <SpatialPanel style={{
        position: 'absolute', left: 412, top: 730, width: 540, height: 162,
      }} palette={palette}>
        <SpatialPanelHeader title="Stream" subtitle="hermes · live"
          accent={palette.accent2} palette={palette} />
        <MCLogStream logs={mc.logs} palette={palette} density={density} />
      </SpatialPanel>

      {/* ── Right: viewport + hovering phone ─────────── */}
      <SpatialPanel style={{
        position: 'absolute', right: 32, top: 88, width: 440, height: 290,
      }} palette={palette}>
        <div style={{
          padding: '12px 16px 8px', borderBottom: `1px solid ${palette.border}`,
          display: 'flex', alignItems: 'center', justifyContent: 'space-between'
        }}>
          <div style={{ fontSize: 13, fontWeight: 600, color: '#E8ECFF', letterSpacing: 0.2, display: 'flex', alignItems: 'center', gap: 6 }}>
            Viewport Space
            <span style={{ fontSize: 8, padding: '1px 5px', borderRadius: 3, background: 'rgba(94, 234, 212, 0.15)', border: '1px solid #5eead4', color: '#5eead4', fontFamily: "'JetBrains Mono', monospace", letterSpacing: 0.5 }}>3D ACTIVE</span>
          </div>
          <div style={{ display: 'flex', gap: 6 }}>
            <button 
              onClick={() => setViewMode('2d')} 
              style={{
                background: viewMode === '2d' ? 'rgba(255,255,255,0.08)' : 'transparent',
                border: viewMode === '2d' ? `1px solid ${palette.accent}` : '1px solid transparent',
                borderRadius: 4, color: viewMode === '2d' ? '#E8ECFF' : 'rgba(232,236,255,0.5)',
                fontSize: 9, fontWeight: 700, padding: '2px 8px', cursor: 'pointer',
                fontFamily: "'Space Grotesk', sans-serif"
              }}
            >
              2D VIEW
            </button>
            <button 
              onClick={() => setViewMode('3d')} 
              style={{
                background: viewMode === '3d' ? 'rgba(255,255,255,0.08)' : 'transparent',
                border: viewMode === '3d' ? `1px solid ${palette.accent2}` : '1px solid transparent',
                borderRadius: 4, color: viewMode === '3d' ? '#E8ECFF' : 'rgba(232,236,255,0.5)',
                fontSize: 9, fontWeight: 700, padding: '2px 8px', cursor: 'pointer',
                fontFamily: "'Space Grotesk', sans-serif"
              }}
            >
              3D DEPTH
            </button>
          </div>
        </div>
        <div style={{ padding: 12, height: 'calc(100% - 44px)' }}>
          {viewMode === '2d' ? (
            <MCViewport palette={palette} healing={healing} onCorrect={() => {}} />
          ) : (
            <MCViewport3D palette={palette} />
          )}
        </div>
      </SpatialPanel>

      <div style={{
        position: 'absolute', right: 60, top: 410,
        filter: `drop-shadow(0 30px 60px ${hexA(palette.accent, 0.25)})`,
      }}>
        <div style={{
          transform: 'perspective(1200px) rotateY(-8deg) rotateX(2deg)',
          transformOrigin: 'center center',
        }}>
          <MCPhone messages={mc.messages} voiceLevel={mc.voiceLevel} palette={palette}
            running={mc.running} vizMode={vizMode} />
        </div>
        {/* Floating label */}
        <div style={{
          position: 'absolute', bottom: -10, left: '50%', transform: 'translateX(-50%)',
          padding: '4px 12px',
          background: 'rgba(11,11,26,0.85)',
          backdropFilter: 'blur(8px)',
          border: `1px solid ${hexA(palette.accent, 0.3)}`,
          borderRadius: 100,
          fontSize: 8, letterSpacing: 2, color: palette.accent,
          fontFamily: "'JetBrains Mono', monospace",
          whiteSpace: 'nowrap',
        }}>
          PHONE PWA · WSS-ENCRYPTED
        </div>
      </div>

      {/* ── Auto-heal toast ─────────────────────────── */}
      {mc.healToast && (
        <div style={{
          position: 'absolute', left: '50%', top: 60,
          transform: 'translateX(-50%)',
          padding: '12px 20px',
          background: 'rgba(11,11,26,0.85)',
          backdropFilter: 'blur(16px)',
          border: `1px solid ${palette.anomaly}`,
          borderRadius: 100,
          color: palette.anomaly,
          fontSize: 11, fontWeight: 600, letterSpacing: 1.2,
          fontFamily: "'JetBrains Mono', monospace",
          animation: 'mc-fade-up 0.4s cubic-bezier(.1,.8,.3,1)',
          boxShadow: `0 0 24px ${hexA(palette.anomaly, 0.3)}`,
          zIndex: 100,
          display: 'flex', alignItems: 'center', gap: 10,
        }}>
          <span style={{
            width: 8, height: 8, borderRadius: '50%', background: palette.anomaly,
            animation: 'mc-blink 1.2s infinite',
          }} />
          AUTO-HEAL · {mc.healToast.intent} → {mc.healToast.element}
        </div>
      )}
    </div>
  );
}

// ── Spatial primitives ──────────────────────────────────
function Orb({ size, top, left, right, bottom, color, opacity }) {
  return (
    <div style={{
      position: 'absolute', width: size, height: size, top, left, right, bottom,
      background: `radial-gradient(circle, ${hexA(color, opacity)}, transparent 70%)`,
      filter: 'blur(40px)', pointerEvents: 'none',
    }} />
  );
}

function SpatialStarfield() {
  const ref = React.useRef(null);
  React.useEffect(() => {
    const c = ref.current; if (!c) return;
    const dpr = window.devicePixelRatio || 1;
    const W = c.offsetWidth, H = c.offsetHeight;
    c.width = W * dpr; c.height = H * dpr;
    const ctx = c.getContext('2d'); ctx.scale(dpr, dpr);
    const stars = Array.from({ length: 120 }, () => ({
      x: Math.random() * W, y: Math.random() * H, r: Math.random() * 1.2,
      o: 0.1 + Math.random() * 0.5, p: Math.random() * Math.PI * 2,
    }));
    let raf;
    function draw() {
      ctx.clearRect(0, 0, W, H);
      const t = performance.now() / 1000;
      for (const s of stars) {
        const tw = 0.6 + 0.4 * Math.sin(t * 2 + s.p);
        ctx.fillStyle = `rgba(232,236,255,${s.o * tw})`;
        ctx.beginPath(); ctx.arc(s.x, s.y, s.r, 0, Math.PI * 2); ctx.fill();
      }
      raf = requestAnimationFrame(draw);
    }
    draw();
    return () => cancelAnimationFrame(raf);
  }, []);
  return <canvas ref={ref} style={{ width: '100%', height: '100%' }} />;
}

function SpatialPanel({ children, style, palette, subtle }) {
  return (
    <div style={{
      background: subtle ? 'rgba(20,22,40,0.45)' : 'rgba(20,22,40,0.65)',
      backdropFilter: 'blur(20px)',
      WebkitBackdropFilter: 'blur(20px)',
      border: `1px solid ${palette.border}`,
      borderRadius: 16,
      boxShadow: `0 20px 60px rgba(0,0,0,0.4), inset 0 1px 0 rgba(255,255,255,0.06)`,
      overflow: 'hidden',
      ...style,
    }}>
      {children}
    </div>
  );
}

function SpatialPanelHeader({ title, subtitle, accent, palette }) {
  return (
    <div style={{
      padding: '14px 16px 10px',
      borderBottom: `1px solid ${palette.border}`,
      display: 'flex', alignItems: 'baseline', justifyContent: 'space-between',
    }}>
      <div style={{ fontSize: 13, fontWeight: 600, color: '#E8ECFF', letterSpacing: 0.2 }}>
        {title}
      </div>
      <div style={{
        fontSize: 9, letterSpacing: 1.6,
        color: accent || 'rgba(232,236,255,0.4)',
        fontFamily: "'JetBrains Mono', monospace",
        textTransform: 'uppercase',
      }}>
        {subtitle}
      </div>
    </div>
  );
}

function SpatialHeader({ palette, mc }) {
  return (
    <div style={{
      position: 'absolute', top: 0, left: 0, right: 0, height: 56,
      padding: '0 32px',
      display: 'flex', alignItems: 'center',
      borderBottom: `1px solid ${palette.border}`,
      background: 'rgba(11,11,26,0.4)',
      backdropFilter: 'blur(20px)',
      zIndex: 10,
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <SpatialLogo palette={palette} />
        <div>
          <div style={{
            fontFamily: "'Space Grotesk', sans-serif", fontWeight: 600,
            fontSize: 15, color: '#E8ECFF', letterSpacing: 0.3,
          }}>Jarvis</div>
          <div style={{
            fontSize: 9, letterSpacing: 1.6,
            color: 'rgba(232,236,255,0.5)',
            fontFamily: "'JetBrains Mono', monospace",
          }}>Mission Control · Hermes link active</div>
        </div>
      </div>
      <div style={{ flex: 1 }} />
      <div style={{ display: 'flex', alignItems: 'center', gap: 18, fontSize: 11 }}>
        <SpatialPill label="Task" value={mc.taskStatus} accent={palette.accent} palette={palette}
          pulse={mc.running} />
        <SpatialPill label="Calls" value={mc.telemetry.calls} palette={palette} />
        <SpatialPill label="Tokens" value={mc.telemetry.tokens.toLocaleString()} palette={palette} />
        <SpatialPill label="Spend" value={'$' + mc.telemetry.cost.toFixed(4)} accent={palette.accent2} palette={palette} />
      </div>
    </div>
  );
}

function SpatialPill({ label, value, accent, palette, pulse }) {
  return (
    <div style={{
      display: 'flex', alignItems: 'center', gap: 8,
      padding: '5px 12px',
      background: 'rgba(255,255,255,0.04)',
      border: `1px solid ${palette.border}`,
      borderRadius: 100,
    }}>
      <span style={{ fontSize: 9, letterSpacing: 1.4, color: 'rgba(232,236,255,0.5)',
        fontFamily: "'JetBrains Mono', monospace" }}>{label}</span>
      <span style={{
        fontSize: 12, fontWeight: 600,
        color: accent || '#E8ECFF',
        fontFamily: "'JetBrains Mono', monospace",
        animation: pulse ? 'mc-blink 1.4s infinite' : 'none',
      }}>{value}</span>
    </div>
  );
}

function SpatialLogo({ palette }) {
  return (
    <div style={{ position: 'relative', width: 32, height: 32 }}>
      <div style={{
        position: 'absolute', inset: 0,
        background: `conic-gradient(from 0deg, ${palette.accent}, ${palette.accent2}, ${palette.accent})`,
        borderRadius: '50%',
        animation: 'mc-spin 8s linear infinite',
        opacity: 0.9,
      }} />
      <div style={{
        position: 'absolute', inset: 4, background: '#0b0b1a',
        borderRadius: '50%',
        display: 'flex', alignItems: 'center', justifyContent: 'center',
        fontWeight: 700, fontSize: 11, color: palette.accent,
        fontFamily: "'Space Grotesk', sans-serif", letterSpacing: 1,
      }}>J</div>
    </div>
  );
}

function SpatialTranscript({ messages, palette }) {
  const ref = React.useRef(null);
  React.useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [messages]);
  return (
    <div ref={ref} className="mc-pane" style={{
      height: 'calc(100% - 56px)', overflowY: 'auto', padding: 14,
      display: 'flex', flexDirection: 'column', gap: 10,
    }}>
      {messages.slice(-6).map((m, i) => (
        <div key={i} style={{
          alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
          maxWidth: '88%',
          padding: '8px 12px', borderRadius: 12,
          background: m.role === 'user'
            ? `linear-gradient(135deg, ${hexA(palette.accent, 0.22)}, ${hexA(palette.accent, 0.10)})`
            : 'rgba(255,255,255,0.04)',
          border: `1px solid ${m.role === 'user' ? hexA(palette.accent, 0.3) : palette.border}`,
          borderBottomRightRadius: m.role === 'user' ? 4 : 12,
          borderBottomLeftRadius: m.role === 'user' ? 12 : 4,
        }}>
          <div style={{
            fontSize: 8, letterSpacing: 1.4, marginBottom: 3,
            color: m.role === 'user' ? palette.accent : 'rgba(232,236,255,0.4)',
            fontFamily: "'JetBrains Mono', monospace",
          }}>
            {m.role === 'user' ? 'YOU' : 'JARVIS'} · {m.t}
          </div>
          <div style={{ fontSize: 12, lineHeight: 1.5, color: '#E8ECFF' }}>{m.text}</div>
        </div>
      ))}
    </div>
  );
}

function SpatialMemory({ mc, palette }) {
  const learnings = [
    { tag: 'CONTRACT', text: 'POST /api/users → {id, email, created_at}' },
    { tag: 'INDEX',    text: 'email index UNIQUE on case-folded value' },
    { tag: 'ROUTER',   text: 'qa role → gpt-5.4 wins (n=42, 0.91)' },
    { tag: 'UX',       text: 'todo composer needs empty state' },
  ];
  return (
    <div style={{ padding: 14, height: 'calc(100% - 56px)', overflow: 'hidden' }}>
      <div style={{ display: 'flex', alignItems: 'baseline', gap: 16, marginBottom: 12 }}>
        <SpatialBigNum value="12,408" label="nodes" palette={palette} />
        <SpatialBigNum value="41,902" label="edges" palette={palette} />
        <SpatialBigNum value={mc.running ? '+3' : '+0'} label="this run" accent={palette.accent2} palette={palette} />
      </div>
      <div style={{
        fontSize: 8, letterSpacing: 1.6, color: 'rgba(232,236,255,0.4)',
        fontFamily: "'JetBrains Mono', monospace", marginBottom: 6,
      }}>RECENT LEARNINGS</div>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
        {learnings.map((l, i) => (
          <div key={i} style={{ display: 'flex', gap: 8, alignItems: 'baseline' }}>
            <span style={{
              fontSize: 8, letterSpacing: 1.2, color: palette.accent2,
              fontFamily: "'JetBrains Mono', monospace", flexShrink: 0,
              width: 60,
            }}>{l.tag}</span>
            <span style={{ fontSize: 11, color: 'rgba(232,236,255,0.85)', lineHeight: 1.4 }}>
              {l.text}
            </span>
          </div>
        ))}
      </div>
    </div>
  );
}

function SpatialBigNum({ value, label, accent, palette }) {
  return (
    <div>
      <div style={{
        fontSize: 22, fontWeight: 600, color: accent || '#E8ECFF',
        fontFamily: "'Space Grotesk', monospace", letterSpacing: -0.5,
      }}>{value}</div>
      <div style={{
        fontSize: 9, letterSpacing: 1.4, color: 'rgba(232,236,255,0.5)',
        fontFamily: "'JetBrains Mono', monospace",
      }}>{label}</div>
    </div>
  );
}

Object.assign(window, { MCVariantSpatial });
