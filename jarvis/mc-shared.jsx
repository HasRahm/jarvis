// mc-shared.jsx — Visualizer (3 modes), DAG graph, viewport, phone-in-frame, log stream.
// Used by all 3 Mission Control variations.

// ─────────────────────────────────────────────────────────────
// Visualizer — orb / waveform / particles, all driven by voiceLevel
// ─────────────────────────────────────────────────────────────
function MCVisualizer({ mode = 'orb', level = 0, size = 200, palette = {} }) {
  const canvasRef = React.useRef(null);
  const stateRef  = React.useRef({ particles: null, t: 0, lastLevel: 0 });

  const accent  = palette.accent  || '#5EEAD4';
  const accent2 = palette.accent2 || '#FFB547';

  // Re-render: use rAF loop so we paint continuously even if level isn't changing.
  React.useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas) return;
    const dpr = window.devicePixelRatio || 1;
    canvas.width = size * dpr;
    canvas.height = size * dpr;
    canvas.style.width = `${size}px`;
    canvas.style.height = `${size}px`;
    const ctx = canvas.getContext('2d');
    ctx.scale(dpr, dpr);

    let raf;
    const draw = () => {
      stateRef.current.t += 1;
      const t = stateRef.current.t;
      ctx.clearRect(0, 0, size, size);
      const cx = size / 2, cy = size / 2;
      // Use the latest "level" via a ref proxy
      const lvl = window.__mcLastLevel?.[mode] ?? 0;
      stateRef.current.lastLevel = stateRef.current.lastLevel * 0.7 + lvl * 0.3;
      const L = stateRef.current.lastLevel;

      if (mode === 'orb') {
        drawOrb(ctx, cx, cy, size, L, t, accent, accent2);
      } else if (mode === 'waveform') {
        drawWaveform(ctx, cx, cy, size, L, t, accent, accent2);
      } else if (mode === 'particles') {
        drawParticles(ctx, cx, cy, size, L, t, accent, accent2, stateRef);
      }
      raf = requestAnimationFrame(draw);
    };
    draw();
    return () => cancelAnimationFrame(raf);
  }, [size, mode, accent, accent2]);

  // Keep latest level in a window-scoped map so the rAF loop reads it without re-effect
  React.useEffect(() => {
    window.__mcLastLevel = window.__mcLastLevel || {};
    window.__mcLastLevel[mode] = level;
  }, [level, mode]);

  return <canvas ref={canvasRef} style={{ display: 'block' }} />;
}

function drawOrb(ctx, cx, cy, size, L, t, accent, accent2) {
  const baseR = size * 0.26;
  const pulse = 1 + L * 0.32;

  // Ambient glow
  const g = ctx.createRadialGradient(cx, cy, 2, cx, cy, baseR * pulse * 1.9);
  g.addColorStop(0, hexA(accent, 0.20));
  g.addColorStop(0.55, hexA(accent2, 0.06));
  g.addColorStop(1, 'transparent');
  ctx.fillStyle = g;
  ctx.beginPath(); ctx.arc(cx, cy, baseR * pulse * 1.9, 0, Math.PI * 2); ctx.fill();

  // Outer ring
  ctx.shadowBlur = 16; ctx.shadowColor = hexA(accent, 0.6);
  ctx.beginPath(); ctx.arc(cx, cy, baseR * pulse, 0, Math.PI * 2);
  ctx.strokeStyle = hexA(accent, 0.8); ctx.lineWidth = 1.4; ctx.stroke();

  // Spectrum spikes
  ctx.shadowBlur = 6; ctx.shadowColor = hexA(accent2, 0.7);
  const rays = 64;
  ctx.beginPath();
  for (let i = 0; i < rays; i++) {
    const angle = (i / rays) * Math.PI * 2;
    const noise = Math.sin(t * 0.08 + i * 1.3) * 0.5 + 0.5;
    const r = baseR * 0.7 + (L * 22 + 4) * noise;
    const x = cx + Math.cos(angle) * r;
    const y = cy + Math.sin(angle) * r;
    i === 0 ? ctx.moveTo(x, y) : ctx.lineTo(x, y);
  }
  ctx.closePath();
  ctx.strokeStyle = hexA(accent2, 0.85); ctx.lineWidth = 1.2; ctx.stroke();

  // Inner pupil
  ctx.shadowBlur = 0;
  ctx.beginPath(); ctx.arc(cx, cy, 3 + L * 5, 0, Math.PI * 2);
  ctx.fillStyle = L > 0.05 ? hexA(accent, 0.95) : hexA('#475569', 0.6);
  ctx.fill();
}

function drawWaveform(ctx, cx, cy, size, L, t, accent, accent2) {
  const bars = 40;
  const padX = 18;
  const w = (size - padX * 2) / bars;
  for (let i = 0; i < bars; i++) {
    const wave = 0.35 + 0.65 * Math.abs(Math.sin(i * 0.4 + t * 0.07));
    const h = (L * 0.85 + 0.05) * size * 0.5 * wave;
    const x = padX + i * w + w * 0.18;
    const y = cy - h / 2;
    const grd = ctx.createLinearGradient(0, y, 0, y + h);
    grd.addColorStop(0, hexA(accent2, 0.95));
    grd.addColorStop(1, hexA(accent, 0.85));
    ctx.fillStyle = grd;
    ctx.shadowBlur = 8; ctx.shadowColor = hexA(accent, 0.5);
    ctx.fillRect(x, y, w * 0.64, h);
  }
  ctx.shadowBlur = 0;
  // baseline
  ctx.strokeStyle = hexA(accent, 0.25);
  ctx.lineWidth = 1;
  ctx.beginPath(); ctx.moveTo(padX, cy); ctx.lineTo(size - padX, cy); ctx.stroke();
}

function drawParticles(ctx, cx, cy, size, L, t, accent, accent2, stateRef) {
  if (!stateRef.current.particles) {
    stateRef.current.particles = Array.from({ length: 90 }, () => ({
      a: Math.random() * Math.PI * 2,
      r: 14 + Math.random() * (size * 0.36),
      s: 0.002 + Math.random() * 0.012,
      v: Math.random() * 0.7 + 0.3,
    }));
  }
  const p = stateRef.current.particles;
  ctx.fillStyle = hexA(accent, 0.04);
  ctx.fillRect(0, 0, size, size);
  for (const q of p) {
    q.a += q.s * (1 + L * 1.4);
    const r = q.r * (1 + L * 0.18);
    const x = cx + Math.cos(q.a) * r;
    const y = cy + Math.sin(q.a) * r;
    const c = q.v > 0.6 ? accent : accent2;
    ctx.fillStyle = hexA(c, 0.4 + L * 0.4);
    ctx.beginPath(); ctx.arc(x, y, 1.3 + q.v * 1.5, 0, Math.PI * 2); ctx.fill();
  }
  // central anchor
  ctx.fillStyle = hexA(accent, 0.7);
  ctx.beginPath(); ctx.arc(cx, cy, 2 + L * 4, 0, Math.PI * 2); ctx.fill();
}

function hexA(hex, a) {
  if (!hex) return `rgba(255,255,255,${a})`;
  if (hex.startsWith('rgb')) return hex;
  const h = hex.replace('#', '');
  const r = parseInt(h.slice(0, 2), 16);
  const g = parseInt(h.slice(2, 4), 16);
  const b = parseInt(h.slice(4, 6), 16);
  return `rgba(${r},${g},${b},${a})`;
}

// ─────────────────────────────────────────────────────────────
// DAG — layered DAG view, nodes positioned on a grid.
// Each node shows role, label, status. Edges animate when active.
// ─────────────────────────────────────────────────────────────
function MCDag({ nodes, palette = {}, width = 720, height = 360, layout = 'flow', density = 'comfortable' }) {
  // Compute layers from deps
  const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
  const layerOf = {};
  function lvl(id, seen = new Set()) {
    if (layerOf[id] != null) return layerOf[id];
    if (seen.has(id)) return 0;
    seen.add(id);
    const n = byId[id];
    if (!n || !n.dep || n.dep.length === 0) { layerOf[id] = 0; return 0; }
    const l = 1 + Math.max(...n.dep.map((d) => lvl(d, seen)));
    layerOf[id] = l; return l;
  }
  nodes.forEach((n) => lvl(n.id));
  const maxLayer = Math.max(...Object.values(layerOf));

  // Group by layer
  const layers = [];
  for (let l = 0; l <= maxLayer; l++) {
    layers.push(nodes.filter((n) => layerOf[n.id] === l));
  }

  // Positions
  const pad = 28;
  const colW = (width - pad * 2) / (maxLayer + 1);
  const positions = {};
  layers.forEach((col, li) => {
    const colH = (height - pad * 2) / col.length;
    col.forEach((n, ni) => {
      positions[n.id] = {
        x: pad + colW * li + colW / 2,
        y: pad + colH * ni + colH / 2,
      };
    });
  });

  // Responsive: shrink node width so the widest layer still fits.
  const baseW = density === 'compact' ? 118 : density === 'spacious' ? 150 : 132;
  const baseH = density === 'compact' ? 44 : density === 'spacious' ? 62 : 52;
  const maxAllowedW = colW - 12; // 6px breathing on each side
  const nodeW = Math.max(96, Math.min(baseW, maxAllowedW));
  const nodeH = baseH;
  const maxLabelChars = nodeW < 120 ? 16 : nodeW < 140 ? 20 : 24;

  const accent  = palette.accent  || '#5EEAD4';
  const accent2 = palette.accent2 || '#FFB547';
  const border  = palette.border  || 'rgba(255,255,255,0.08)';

  return (
    <svg viewBox={`0 0 ${width} ${height}`} width="100%" height="100%" style={{ overflow: 'visible' }}>
      <defs>
        <marker id="mc-arrow" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="6" markerHeight="6" orient="auto">
          <path d="M 0 0 L 10 5 L 0 10 z" fill={hexA(accent, 0.55)} />
        </marker>
        <marker id="mc-arrow-active" viewBox="0 0 10 10" refX="9" refY="5" markerWidth="7" markerHeight="7" orient="auto">
          <path d="M 0 0 L 10 5 L 0 10 z" fill={accent2} />
        </marker>
      </defs>

      {/* Edges */}
      {nodes.map((n) => (n.dep || []).map((d) => {
        const a = positions[d], b = positions[n.id];
        if (!a || !b) return null;
        const fromN = byId[d];
        const flowing = fromN && fromN.status === 'done' && (n.status === 'active' || n.status === 'done');
        const active = flowing || (fromN && fromN.status === 'active');
        const mx = (a.x + b.x) / 2;
        const path = `M ${a.x + nodeW / 2} ${a.y} C ${mx} ${a.y}, ${mx} ${b.y}, ${b.x - nodeW / 2} ${b.y}`;
        return (
          <g key={`${d}-${n.id}`}>
            <path d={path} stroke={hexA(accent, 0.18)} strokeWidth="1.2" fill="none" />
            {active && (
              <path d={path} stroke={accent2} strokeWidth="1.6" fill="none"
                strokeDasharray="6 6" markerEnd="url(#mc-arrow-active)">
                <animate attributeName="stroke-dashoffset" from="12" to="0" dur="0.6s" repeatCount="indefinite" />
              </path>
            )}
            {fromN && fromN.status === 'done' && n.status === 'done' && (
              <path d={path} stroke={hexA(accent, 0.55)} strokeWidth="1.2" fill="none" markerEnd="url(#mc-arrow)" />
            )}
          </g>
        );
      }))}

      {/* Nodes */}
      {nodes.map((n) => {
        const p = positions[n.id];
        if (!p) return null;
        const role = ROLE_META[n.role] || { color: accent, short: '·' };
        const isActive = n.status === 'active';
        const isDone = n.status === 'done';
        const isIdle = n.status === 'idle';
        const fill = isActive ? hexA(role.color, 0.18) : isDone ? hexA(role.color, 0.08) : 'rgba(255,255,255,0.02)';
        const stroke = isActive ? role.color : isDone ? hexA(role.color, 0.5) : border;
        return (
          <g key={n.id} transform={`translate(${p.x - nodeW / 2}, ${p.y - nodeH / 2})`}>
            {isActive && (
              <rect x="-4" y="-4" width={nodeW + 8} height={nodeH + 8} rx="8"
                fill="none" stroke={hexA(role.color, 0.4)} strokeWidth="1"
                strokeDasharray="3 4">
                <animate attributeName="stroke-dashoffset" from="0" to="14" dur="1s" repeatCount="indefinite" />
              </rect>
            )}
            <rect width={nodeW} height={nodeH} rx="6" fill={fill} stroke={stroke} strokeWidth="1" />
            <text x="10" y="18" fontSize="9" fontFamily="'JetBrains Mono', monospace"
              fill={role.color} letterSpacing="1.2">{role.short}</text>
            <text x={nodeW - 10} y="18" fontSize="9" fontFamily="'JetBrains Mono', monospace"
              textAnchor="end" fill={isDone ? hexA(role.color, 0.7) : isActive ? accent2 : 'rgba(255,255,255,0.3)'}
              letterSpacing="1">
              {isDone ? '✓ DONE' : isActive ? '● RUN' : 'IDLE'}
            </text>
            <text x="10" y={nodeH - (density === 'compact' ? 12 : 18)} fontSize={density === 'compact' ? 10 : 11}
              fontFamily="'Inter', sans-serif" fill={isIdle ? 'rgba(255,255,255,0.5)' : '#F1F5F9'}>
              {n.label.length > maxLabelChars ? n.label.slice(0, maxLabelChars) + '…' : n.label}
            </text>
            {density !== 'compact' && nodeW > 120 && (
              <text x="10" y={nodeH - 6} fontSize="9" fontFamily="'JetBrains Mono', monospace"
                fill="rgba(255,255,255,0.35)" letterSpacing="0.5">
                {n.model.length > maxLabelChars ? n.model.slice(0, maxLabelChars) + '…' : n.model}
              </text>
            )}
          </g>
        );
      })}
    </svg>
  );
}

// ─────────────────────────────────────────────────────────────
// MCViewport — fake screenshot with tap-to-heal
// ─────────────────────────────────────────────────────────────
function MCViewport({ palette = {}, onCorrect, healing }) {
  const [coords, setCoords] = React.useState(null);
  const [instr, setInstr] = React.useState('');
  const accent = palette.accent || '#5EEAD4';
  const accent2 = palette.accent2 || '#FFB547';

  function onTap(e) {
    const rect = e.currentTarget.getBoundingClientRect();
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;
    setCoords({ x, y });
  }
  function submit() {
    if (!coords || !instr.trim()) return;
    onCorrect && onCorrect({ coords, instruction: instr });
    setCoords(null); setInstr('');
  }

  return (
    <div style={{ position: 'relative' }}>
      <div onClick={onTap} style={{
        position: 'relative', cursor: 'crosshair', background: '#06070A',
        border: '1px solid rgba(255,255,255,0.06)', borderRadius: 4,
        overflow: 'hidden', aspectRatio: '16/10',
      }}>
        {/* Fake browser preview */}
        <FakeTodoApp palette={palette} healing={healing} />
        {/* Scanline overlay */}
        <div style={{
          position: 'absolute', inset: 0, pointerEvents: 'none',
          backgroundImage: `repeating-linear-gradient(0deg, rgba(255,255,255,0.025) 0px, rgba(255,255,255,0.025) 1px, transparent 1px, transparent 3px)`,
        }} />
        {coords && (
          <div style={{
            position: 'absolute', left: `${coords.x * 100}%`, top: `${coords.y * 100}%`,
            transform: 'translate(-50%,-50%)', pointerEvents: 'none',
          }}>
            <div style={{
              width: 24, height: 24, border: `2px solid ${accent}`, borderRadius: '50%',
              boxShadow: `0 0 16px ${accent}`,
            }} />
            <div style={{ position: 'absolute', left: 30, top: -2, fontSize: 9, color: accent, fontFamily: "'JetBrains Mono', monospace", letterSpacing: 1, whiteSpace: 'nowrap' }}>
              x:{coords.x.toFixed(2)} y:{coords.y.toFixed(2)}
            </div>
          </div>
        )}
      </div>
      {coords && (
        <div style={{
          marginTop: 8, display: 'flex', gap: 6, alignItems: 'center',
          padding: 6, background: 'rgba(255,255,255,0.03)', border: `1px solid ${hexA(accent, 0.3)}`,
          borderRadius: 4,
        }}>
          <input value={instr} onChange={(e) => setInstr(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && submit()}
            placeholder="describe the correction…" style={{
              flex: 1, padding: '6px 8px', background: 'transparent', border: 'none',
              color: '#F1F5F9', fontSize: 11, outline: 'none', fontFamily: "'JetBrains Mono', monospace",
            }} />
          <button onClick={submit} style={{
            padding: '6px 10px', background: accent2, color: '#0a0a0c', border: 'none',
            borderRadius: 3, fontSize: 9, fontWeight: 700, letterSpacing: 1, cursor: 'pointer',
            fontFamily: "'JetBrains Mono', monospace",
          }}>HEAL ↵</button>
        </div>
      )}
    </div>
  );
}

function FakeTodoApp({ palette = {}, healing }) {
  const accent = palette.accent || '#5EEAD4';
  const items = [
    { t: 'Migrate users schema', d: true },
    { t: 'POST /api/todos', d: true },
    { t: 'TodoList composer empty state', d: false },
    { t: 'QA contract assertions', d: false },
  ];
  return (
    <div style={{
      width: '100%', height: '100%', padding: 16,
      background: 'linear-gradient(180deg, #0d1117, #060708)',
      fontFamily: "'Inter', sans-serif",
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 8, marginBottom: 14 }}>
        <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#ff5f57' }} />
        <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#febc2e' }} />
        <div style={{ width: 8, height: 8, borderRadius: '50%', background: '#28c840' }} />
        <div style={{ marginLeft: 14, fontSize: 9, color: 'rgba(255,255,255,0.4)', fontFamily: "'JetBrains Mono', monospace" }}>
          localhost:5173/todos
        </div>
      </div>
      <div style={{ fontSize: 13, fontWeight: 600, color: '#F1F5F9', marginBottom: 10 }}>
        Today
      </div>
      {items.map((it, i) => (
        <div key={i} style={{
          display: 'flex', alignItems: 'center', gap: 8,
          padding: '5px 8px', marginBottom: 4, borderRadius: 4,
          background: healing && i === 2 ? hexA(accent, 0.12) : 'transparent',
          outline: healing && i === 2 ? `1px solid ${accent}` : 'none',
        }}>
          <div style={{
            width: 11, height: 11, borderRadius: 2,
            border: `1px solid ${it.d ? accent : 'rgba(255,255,255,0.3)'}`,
            background: it.d ? accent : 'transparent',
          }} />
          <div style={{ fontSize: 11, color: it.d ? 'rgba(255,255,255,0.5)' : '#F1F5F9',
            textDecoration: it.d ? 'line-through' : 'none' }}>
            {it.t}
          </div>
        </div>
      ))}
      <div style={{ marginTop: 8, padding: '5px 8px', border: '1px dashed rgba(255,255,255,0.15)',
        borderRadius: 4, fontSize: 10, color: 'rgba(255,255,255,0.3)' }}>
        + new todo…
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// LogStream — terminal-style streaming log
// ─────────────────────────────────────────────────────────────
function MCLogStream({ logs, palette = {}, density = 'comfortable' }) {
  const ref = React.useRef(null);
  React.useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [logs]);
  const accent = palette.accent || '#5EEAD4';
  const accent2 = palette.accent2 || '#FFB547';
  const tagColor = {
    HERMES: '#A78BFA', GBRAIN: '#F472B6', ROUTER: accent2,
    QA: '#34D399', BACKEND: '#A78BFA', FRONTEND: '#7DD3FC',
    IAC: '#F472B6', DAG: accent, AUTOHEAL: accent2, ORCHESTR: accent2,
  };
  const rowPad = density === 'compact' ? '2px 8px' : density === 'spacious' ? '5px 10px' : '3px 10px';
  return (
    <div ref={ref} className="mc-pane" style={{
      height: '100%', overflowY: 'auto', fontFamily: "'JetBrains Mono', monospace",
      fontSize: density === 'compact' ? 10 : 11, lineHeight: 1.55,
    }}>
      {logs.map((l, i) => (
        <div key={i} style={{ padding: rowPad, display: 'flex', gap: 8 }}>
          <span style={{ color: 'rgba(255,255,255,0.35)', flexShrink: 0 }}>{l.t}</span>
          <span style={{ color: tagColor[l.tag] || accent, flexShrink: 0, width: 64, letterSpacing: 0.6 }}>
            {l.tag.padEnd(8)}
          </span>
          <span style={{ color: 'rgba(241,245,249,0.85)' }}>{l.text}</span>
        </div>
      ))}
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// Phone-in-frame mini — custom shell, scales to fit
// ─────────────────────────────────────────────────────────────
function MCPhone({ messages, voiceLevel, palette = {}, running, vizMode = 'orb', width = 218, height = 432 }) {
  const ref = React.useRef(null);
  React.useEffect(() => {
    if (ref.current) ref.current.scrollTop = ref.current.scrollHeight;
  }, [messages]);
  const accent = palette.accent || '#5EEAD4';
  const accent2 = palette.accent2 || '#FFB547';
  const vizSize = Math.round(width * 0.46);
  const radius = Math.round(width * 0.13);
  const islandW = Math.round(width * 0.32);
  const islandH = Math.round(width * 0.085);

  return (
    <div style={{
      width, height, position: 'relative',
      borderRadius: radius,
      background: '#000',
      padding: 4,
      boxShadow: '0 30px 60px rgba(0,0,0,0.5), 0 0 0 1px rgba(255,255,255,0.06)',
      flexShrink: 0,
    }}>
      <div style={{
        width: '100%', height: '100%',
        background: 'linear-gradient(180deg, #060A14, #0D1526)',
        borderRadius: radius - 4,
        overflow: 'hidden', position: 'relative',
        display: 'flex', flexDirection: 'column',
        fontFamily: "'Inter', sans-serif",
      }}>
        {/* Dynamic island */}
        <div style={{
          position: 'absolute', top: 8, left: '50%', transform: 'translateX(-50%)',
          width: islandW, height: islandH, borderRadius: islandH / 2, background: '#000',
          zIndex: 5,
        }} />

        {/* Top bar */}
        <div style={{
          padding: '36px 12px 8px',
          display: 'flex', alignItems: 'center', gap: 6,
          borderBottom: '1px solid rgba(255,255,255,0.06)',
          flexShrink: 0,
        }}>
          <div style={{
            fontFamily: "'Space Grotesk', sans-serif", fontWeight: 700, fontSize: 10,
            letterSpacing: 2.5, color: accent2, flex: 1, textAlign: 'center',
          }}>JARVIS</div>
          <div style={{
            position: 'absolute', right: 12, top: 38,
            display: 'flex', alignItems: 'center', gap: 4, padding: '2px 6px',
            border: `1px solid ${hexA(accent, 0.3)}`, borderRadius: 100,
            fontSize: 7, color: accent, letterSpacing: 0.8,
            fontFamily: "'JetBrains Mono', monospace",
          }}>
            <div style={{ width: 4, height: 4, borderRadius: '50%', background: accent,
              boxShadow: `0 0 4px ${accent}` }} />
            LIVE
          </div>
        </div>

        {/* Visualizer */}
        <div style={{
          display: 'flex', justifyContent: 'center', padding: '6px 0', flexShrink: 0,
        }}>
          <MCVisualizer mode={vizMode} level={voiceLevel} size={vizSize} palette={palette} />
        </div>

        {/* Chat */}
        <div ref={ref} className="mc-pane" style={{
          flex: 1, minHeight: 0, overflowY: 'auto', padding: '0 8px 8px',
          display: 'flex', flexDirection: 'column', gap: 5,
        }}>
          {messages.slice(-5).map((m, i) => (
            <div key={i} style={{
              alignSelf: m.role === 'user' ? 'flex-end' : 'flex-start',
              maxWidth: '86%',
              padding: '5px 8px', borderRadius: 9,
              background: m.role === 'user'
                ? `linear-gradient(135deg, ${hexA(accent, 0.22)}, ${hexA(accent, 0.10)})`
                : 'rgba(255,255,255,0.04)',
              border: `1px solid ${m.role === 'user' ? hexA(accent, 0.28) : 'rgba(255,255,255,0.05)'}`,
              fontSize: 9, lineHeight: 1.4, color: '#F1F5F9',
            }}>
              {m.text}
            </div>
          ))}
        </div>

        {/* Input bar */}
        <div style={{
          padding: '6px 8px', borderTop: '1px solid rgba(255,255,255,0.06)',
          display: 'flex', gap: 5, alignItems: 'center', flexShrink: 0,
        }}>
          <div style={{
            width: 24, height: 24, borderRadius: 6, background: 'rgba(255,255,255,0.04)',
            border: '1px solid rgba(255,255,255,0.08)', display: 'flex',
            alignItems: 'center', justifyContent: 'center', fontSize: 10,
          }}>🎤</div>
          <div style={{
            flex: 1, padding: '5px 9px', borderRadius: 7, background: 'rgba(255,255,255,0.04)',
            border: '1px solid rgba(255,255,255,0.08)', fontSize: 9,
            color: 'rgba(255,255,255,0.4)',
            whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
          }}>{running ? 'thinking…' : 'Type a command…'}</div>
          <div style={{
            width: 24, height: 24, borderRadius: 6, background: accent2,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
            fontSize: 10, color: '#0a0a0c',
          }}>➤</div>
        </div>

        {/* Home indicator */}
        <div style={{
          position: 'absolute', bottom: 4, left: '50%', transform: 'translateX(-50%)',
          width: 80, height: 3, borderRadius: 100,
          background: 'rgba(255,255,255,0.4)', zIndex: 10, pointerEvents: 'none',
        }} />
      </div>
    </div>
  );
}

// ─────────────────────────────────────────────────────────────
// AgentRoster — pill per agent with live status
// ─────────────────────────────────────────────────────────────
function MCAgentRoster({ agents, palette = {}, density = 'comfortable', orientation = 'horizontal', columns }) {
  const order = ['orchestrator', 'frontend', 'backend', 'qa', 'iac'];
  const isHoriz = orientation === 'horizontal';
  const cols = columns || order.length;
  return (
    <div style={{
      display: isHoriz ? 'grid' : 'flex',
      gridTemplateColumns: isHoriz ? `repeat(${cols}, minmax(0, 1fr))` : undefined,
      flexDirection: isHoriz ? undefined : 'column',
      gap: density === 'compact' ? 6 : 10,
    }}>
      {order.map((k) => {
        const meta = ROLE_META[k];
        const a = agents[k] || { status: 'idle', step: '—' };
        const isActive = a.status === 'active';
        const isDone   = a.status === 'done';
        return (
          <div key={k} style={{
            minWidth: 0,
            padding: density === 'compact' ? '6px 8px' : '8px 10px',
            background: isActive ? hexA(meta.color, 0.10) : 'rgba(255,255,255,0.02)',
            border: `1px solid ${isActive ? meta.color : isDone ? hexA(meta.color, 0.3) : 'rgba(255,255,255,0.06)'}`,
            borderRadius: 4,
            position: 'relative',
            overflow: 'hidden',
          }}>
            {isActive && (
              <div style={{
                position: 'absolute', bottom: 0, left: 0, height: 1.5, width: '100%',
                background: meta.color, opacity: 0.85,
                animation: 'mc-pulse-bar 1.4s ease-in-out infinite',
              }} />
            )}
            <div style={{ display: 'flex', alignItems: 'center', justifyContent: 'space-between', gap: 6, minWidth: 0 }}>
              <div style={{
                fontFamily: "'JetBrains Mono', monospace", fontSize: 9, letterSpacing: 1,
                color: meta.color,
                whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
              }}>
                {meta.short}{cols <= 3 ? ` · ${meta.name}` : ''}
              </div>
              <div style={{
                fontFamily: "'JetBrains Mono', monospace", fontSize: 7.5, letterSpacing: 0.6,
                color: isActive ? meta.color : isDone ? hexA(meta.color, 0.6) : 'rgba(255,255,255,0.3)',
                flexShrink: 0,
              }}>
                {isActive ? '● RUN' : isDone ? '✓' : 'IDLE'}
              </div>
            </div>
            <div style={{
              marginTop: 4, fontSize: 10, color: 'rgba(241,245,249,0.7)',
              whiteSpace: 'nowrap', overflow: 'hidden', textOverflow: 'ellipsis',
            }}>
              {a.step}
            </div>
          </div>
        );
      })}
    </div>
  );
}

// Animation keyframes injected once
if (!document.getElementById('mc-anim-style')) {
  const s = document.createElement('style');
  s.id = 'mc-anim-style';
  s.textContent = `
    @keyframes mc-pulse-bar { 0%,100%{opacity:.4} 50%{opacity:1} }
    @keyframes mc-scan { 0%{transform:translateY(-100%)} 100%{transform:translateY(2000%)} }
    @keyframes mc-blink { 0%,100%{opacity:1} 50%{opacity:.4} }
    @keyframes mc-spin { to { transform: rotate(360deg); } }
    @keyframes mc-fade-up { from{opacity:0;transform:translateY(8px)} to{opacity:1;transform:translateY(0)} }
    @keyframes mc-grid-shift { from{background-position:0 0} to{background-position:80px 80px} }
  `;
  document.head.appendChild(s);
}

// ─────────────────────────────────────────────────────────────
// MCViewport3D — Interactive 3D Depth Window stack visualizer
// ─────────────────────────────────────────────────────────────
function MCViewport3D({ palette = {} }) {
  const [rotation, setRotation] = React.useState({ x: 22, y: -25 });
  const [isDragging, setIsDragging] = React.useState(false);
  const dragStart = React.useRef({ x: 0, y: 0, rx: 0, ry: 0 });

  const [activeWindow, setActiveWindow] = React.useState('dialog');
  const [dialogVisible, setDialogVisible] = React.useState(true);
  const [chromeDepth, setChromeDepth] = React.useState(1);
  const [vsCodeDepth, setVsCodeDepth] = React.useState(2);
  const [dialogDepth, setDialogDepth] = React.useState(0);

  const [cursorPos, setCursorPos] = React.useState({ x: 190, y: 110, z: 0 });
  const [animating, setAnimating] = React.useState(false);
  const [stepText, setStepText] = React.useState('Click Auto Navigate to start 3D Z-layer tour!');
  const [logItems, setLogItems] = React.useState([]);

  const accent = palette.accent || '#FFB547';
  const accent2 = palette.accent2 || '#5EEAD4';

  function handleMouseDown(e) {
    setIsDragging(true);
    dragStart.current = {
      x: e.clientX,
      y: e.clientY,
      rx: rotation.x,
      ry: rotation.y
    };
  }

  function handleMouseMove(e) {
    if (!isDragging) return;
    const dx = e.clientX - dragStart.current.x;
    const dy = e.clientY - dragStart.current.y;
    setRotation({
      x: Math.max(-45, Math.min(45, dragStart.current.rx - dy * 0.4)),
      y: dragStart.current.ry + dx * 0.4
    });
  }

  function handleMouseUp() {
    setIsDragging(false);
  }

  // Visual Servoing & Auto Navigation Simulation
  async function runAutoNavigate() {
    if (animating) return;
    setAnimating(true);
    setDialogVisible(true);
    setChromeDepth(1);
    setVsCodeDepth(2);
    setDialogDepth(0);
    setLogItems([]);
    
    // Helper to sleep
    const delay = (ms) => new Promise(res => setTimeout(res, ms));
    
    // Step 1: Detect occlusion and move to dismiss button
    setStepText('1. Occlusion Detected! Glide cursor to Blocking Dialog [Dismiss] at Z=0...');
    setCursorPos({ x: 220, y: 115, z: 0 }); // Center of Dialog button
    await delay(1800);

    // Step 2: Click Dismiss
    setStepText('2. Click dialog to dismiss it. Resolving obstacle in depth graph...');
    setLogItems(prev => [...prev, '[Z-NAV] Blocker clicked. Removing Z=0 Dialog.']);
    await delay(1000);
    setDialogVisible(false);
    setDialogDepth(99); // Drop to back
    
    // Step 3: Reshuffle remaining stack
    setStepText('3. Dialog dismissed! Stack reshuffled: Chrome Browser rises to Z=0 foreground!');
    setChromeDepth(0);
    setVsCodeDepth(1);
    setLogItems(prev => [...prev, '[Z-NAV] Reshuffling: Chrome -> Z=0, VS Code -> Z=1.']);
    await delay(1500);

    // Step 4: Glide to Chrome
    setStepText('4. Glide cursor within Chrome (Z=0) to inspect Todo List input field...');
    setCursorPos({ x: 120, y: 90, z: 0 }); // Hover over input field in Chrome
    await delay(1800);

    // Step 5: Focus VS Code
    setStepText('5. VS Code (Z=1) is buried. Trigger Focus Window to bring it to Z=0...');
    setLogItems(prev => [...prev, '[Z-NAV] Focus requested: VS Code.']);
    await delay(1000);
    
    // Step 6: Bring Forward VS Code
    setStepText('6. Bring Forward: VS Code rises to Z=0 foreground! Chrome shifts back to Z=1.');
    setVsCodeDepth(0);
    setChromeDepth(1);
    setLogItems(prev => [...prev, '[Z-NAV] Reshuffling: VS Code -> Z=0, Chrome -> Z=1.']);
    await delay(1500);

    // Step 7: Glide to Deploy button in VS Code
    setStepText('7. Glide cursor to VS Code (Z=0) Deploy button...');
    setCursorPos({ x: 75, y: 100, z: 0 }); // Hover over blue Deploy button
    await delay(1800);

    // Step 8: Click Deploy
    setStepText('8. Click Deploy! Phase 16 3D Spatial depth task completed successfully!');
    setLogItems(prev => [...prev, '[Z-NAV] Deploy successful! System fully operational.']);
    setAnimating(false);
  }

  function handleWindowClick(winId) {
    if (animating) return;
    setActiveWindow(winId);
    if (winId === 'dialog' && dialogVisible) {
      setCursorPos({ x: 220, y: 115, z: 0 });
      setStepText('Clicked Blocking Dialog (Z=0). Focused.');
    } else if (winId === 'chrome') {
      // Bring Chrome forward
      setChromeDepth(0);
      setVsCodeDepth(dialogVisible ? 1 : 1);
      if (dialogVisible) setDialogDepth(2);
      setCursorPos({ x: 120, y: 90, z: 0 });
      setStepText('Clicked Chrome Browser. Brought to Z=0 foreground!');
    } else if (winId === 'vscode') {
      // Bring VS Code forward
      setVsCodeDepth(0);
      setChromeDepth(1);
      if (dialogVisible) setDialogDepth(2);
      setCursorPos({ x: 75, y: 100, z: 0 });
      setStepText('Clicked VS Code. Brought to Z=0 foreground!');
    }
  }

  return (
    <div style={{
      position: 'relative', width: '100%', height: '100%',
      fontFamily: "'Space Grotesk', sans-serif",
      userSelect: 'none', overflow: 'hidden'
    }}>
      {/* Instructions & Console */}
      <div style={{
        position: 'absolute', top: 4, left: 4, right: 4, zIndex: 10,
        background: 'rgba(10, 11, 24, 0.9)',
        border: '1px solid rgba(255,255,255,0.06)', borderRadius: 8,
        padding: '6px 12px', fontSize: 10, lineHeight: 1.45,
        boxShadow: '0 4px 20px rgba(0,0,0,0.5)',
      }}>
        <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: 2 }}>
          <span style={{ color: accent2, fontWeight: 700, letterSpacing: 0.8 }}>3D DEPTH NAVIGATION GRAPH</span>
          <button 
            onClick={runAutoNavigate}
            disabled={animating}
            style={{
              background: `linear-gradient(135deg, ${accent}, ${accent2})`,
              border: 'none', color: '#0b0b1a', fontSize: 9, fontWeight: 700,
              padding: '2px 8px', borderRadius: 4, cursor: animating ? 'wait' : 'pointer',
              boxShadow: `0 0 8px ${hexA(accent2, 0.4)}`, letterSpacing: 0.4
            }}
          >
            {animating ? '● Tour Active' : '⚡ Auto Navigate'}
          </button>
        </div>
        <div style={{ color: '#F1F5F9', fontFamily: "'JetBrains Mono', monospace", fontSize: 9.5 }}>{stepText}</div>
        {logItems.length > 0 && (
          <div style={{
            marginTop: 4, borderTop: '1px dashed rgba(255,255,255,0.1)', paddingTop: 4,
            maxHeight: 38, overflowY: 'auto', color: 'rgba(255,255,255,0.5)', fontSize: 8.5,
            fontFamily: "'JetBrains Mono', monospace"
          }}>
            {logItems.map((log, i) => (
              <div key={i}>{log}</div>
            ))}
          </div>
        )}
      </div>

      {/* Interactive 3D Render Area */}
      <div 
        onMouseDown={handleMouseDown}
        onMouseMove={handleMouseMove}
        onMouseUp={handleMouseUp}
        onMouseLeave={handleMouseUp}
        style={{
          width: '100%', height: '220px', position: 'relative', cursor: isDragging ? 'grabbing' : 'grab',
          background: 'radial-gradient(circle at center, #0f0e26 0%, #050511 100%)',
          borderRadius: 6, display: 'flex', alignItems: 'center', justifyContent: 'center',
          perspective: '800px',
        }}
      >
        <div style={{
          width: '320px', height: '180px', position: 'relative',
          transformStyle: 'preserve-3d',
          transform: `rotateX(${rotation.x}deg) rotateY(${rotation.y}deg)`,
          transition: isDragging ? 'none' : 'transform 0.1s ease-out'
        }}>
          {/* Depth Axis / Grid floor */}
          <div style={{
            position: 'absolute', bottom: -10, left: 10, right: 10, height: 120,
            background: 'radial-gradient(ellipse at center, rgba(94, 234, 212, 0.08) 0%, transparent 70%)',
            borderBottom: '1px solid rgba(94, 234, 212, 0.2)',
            transform: 'rotateX(90deg) translateZ(-40px)',
            transformStyle: 'preserve-3d', pointerEvents: 'none'
          }} />

          {/* Window Node 1: VS Code (Z=2) */}
          <div 
            onClick={(e) => { e.stopPropagation(); handleWindowClick('vscode'); }}
            style={{
              position: 'absolute', left: 20, top: 10, width: 170, height: 110,
              background: 'rgba(10, 15, 30, 0.95)',
              border: `2px solid ${vsCodeDepth === 0 ? accent2 : '#3b82f6'}`,
              borderRadius: 6,
              transform: `translate3d(0, 0, ${-vsCodeDepth * 55}px)`,
              transition: 'transform 0.6s cubic-bezier(0.2, 0.8, 0.2, 1), border-color 0.3s',
              transformStyle: 'preserve-3d',
              boxShadow: vsCodeDepth === 0 ? `0 0 20px ${hexA(accent2, 0.4)}` : '0 10px 30px rgba(0,0,0,0.5)',
              cursor: 'pointer', overflow: 'hidden'
            }}
          >
            {/* Header */}
            <div style={{
              background: '#1e293b', padding: '3px 8px', fontSize: 7.5, color: '#94a3b8',
              display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.05)'
            }}>
              <span>💻 VS Code · deploy.py</span>
              <span style={{ color: accent }}>Z={vsCodeDepth}</span>
            </div>
            {/* Code Content */}
            <div style={{ padding: 6, fontFamily: "'JetBrains Mono', monospace", fontSize: 6.5, color: '#cbd5e1' }}>
              <div style={{ color: '#60a5fa' }}>def deploy_pipeline():</div>
              <div style={{ paddingLeft: 6, color: '#34d399' }}># Spatial Depth active</div>
              <div style={{ paddingLeft: 6, color: '#f472b6' }}>focus_3d_stack()</div>
              <div style={{ paddingLeft: 6, color: '#facc15' }}>win.activate()</div>
              {/* Glowing Deploy Button */}
              <div style={{
                marginTop: 10, background: '#2563eb', color: '#fff', fontSize: 7, fontWeight: 700,
                textAlign: 'center', padding: '3px 0', borderRadius: 3, textTransform: 'uppercase',
                boxShadow: vsCodeDepth === 0 ? '0 0 10px #3b82f6' : 'none', letterSpacing: 0.8
              }}>
                [DEPLOY SYSTEM]
              </div>
            </div>
          </div>

          {/* Window Node 2: Chrome Browser (Z=1) */}
          <div 
            onClick={(e) => { e.stopPropagation(); handleWindowClick('chrome'); }}
            style={{
              position: 'absolute', left: 75, top: 35, width: 170, height: 110,
              background: 'rgba(15, 23, 42, 0.95)',
              border: `2px solid ${chromeDepth === 0 ? accent2 : '#10b981'}`,
              borderRadius: 6,
              transform: `translate3d(0, 0, ${-chromeDepth * 55}px)`,
              transition: 'transform 0.6s cubic-bezier(0.2, 0.8, 0.2, 1), border-color 0.3s',
              transformStyle: 'preserve-3d',
              boxShadow: chromeDepth === 0 ? `0 0 20px ${hexA(accent2, 0.4)}` : '0 10px 30px rgba(0,0,0,0.5)',
              cursor: 'pointer', overflow: 'hidden'
            }}
          >
            {/* Header */}
            <div style={{
              background: '#1e293b', padding: '3px 8px', fontSize: 7.5, color: '#94a3b8',
              display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.05)'
            }}>
              <span>🌐 Chrome · Todo App</span>
              <span style={{ color: accent }}>Z={chromeDepth}</span>
            </div>
            {/* Todo Content */}
            <div style={{ padding: 6, fontSize: 7, color: '#cbd5e1' }}>
              <div style={{ fontWeight: 700, marginBottom: 2 }}>localhost:5173/todos</div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 3, marginBottom: 2, textDecoration: 'line-through', opacity: 0.5 }}>
                <span style={{ color: '#10b981' }}>✓</span> Migrate users schema
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 3, marginBottom: 2, textDecoration: 'line-through', opacity: 0.5 }}>
                <span style={{ color: '#10b981' }}>✓</span> POST /api/todos
              </div>
              <div style={{ display: 'flex', alignItems: 'center', gap: 3, background: 'rgba(16,185,129,0.15)', borderRadius: 2, padding: '1px 3px' }}>
                <span style={{ color: accent2, animation: 'mc-blink 1s infinite' }}>●</span> TodoList empty UX
              </div>
            </div>
          </div>

          {/* Window Node 3: Blocking Dialog (Z=0) */}
          {dialogVisible && (
            <div 
              onClick={(e) => { e.stopPropagation(); handleWindowClick('dialog'); }}
              style={{
                position: 'absolute', left: 130, top: 60, width: 150, height: 90,
                background: 'rgba(30, 16, 20, 0.98)',
                border: `2px solid ${activeWindow === 'dialog' ? accent2 : '#f43f5e'}`,
                borderRadius: 6,
                transform: `translate3d(0, 0, ${-dialogDepth * 55}px)`,
                transition: 'transform 0.6s cubic-bezier(0.2, 0.8, 0.2, 1), opacity 0.5s, border-color 0.3s',
                transformStyle: 'preserve-3d',
                boxShadow: '0 15px 35px rgba(244,63,94,0.15), 0 10px 30px rgba(0,0,0,0.6)',
                cursor: 'pointer', overflow: 'hidden'
              }}
            >
              {/* Header */}
              <div style={{
                background: '#4c0519', padding: '3px 8px', fontSize: 7.5, color: '#fecdd3',
                display: 'flex', justifyContent: 'space-between', borderBottom: '1px solid rgba(255,255,255,0.05)'
              }}>
                <span>⚠️ Blocker · alert.exe</span>
                <span style={{ color: accent }}>Z={dialogDepth}</span>
              </div>
              {/* Alert Content */}
              <div style={{ padding: 6, fontSize: 7.5, color: '#ffe4e6', textAlign: 'center' }}>
                <div style={{ fontWeight: 700, color: '#f43f5e', marginBottom: 2 }}>CONNECTION TIMEOUT</div>
                <div style={{ fontSize: 6.5, opacity: 0.7, marginBottom: 6 }}>Deploy server is occluded or unreachable.</div>
                {/* Red Dismiss Button */}
                <div style={{
                  background: '#e11d48', color: '#fff', fontSize: 7, fontWeight: 700,
                  display: 'inline-block', padding: '2px 8px', borderRadius: 3, border: '1px solid #fda4af'
                }}>
                  DISMISS
                </div>
              </div>
            </div>
          )}

          {/* Glowing Agent Cursor Point */}
          <div style={{
            position: 'absolute',
            left: `${cursorPos.x}px`,
            top: `${cursorPos.y}px`,
            width: 14, height: 14,
            background: 'radial-gradient(circle, #5EEAD4 20%, transparent 70%)',
            borderRadius: '50%',
            transform: `translate3d(0, 0, ${-cursorPos.z * 55 + 10}px)`,
            transition: 'left 1.2s cubic-bezier(0.25, 0.8, 0.25, 1), top 1.2s cubic-bezier(0.25, 0.8, 0.25, 1), transform 1.2s cubic-bezier(0.25, 0.8, 0.25, 1)',
            transformStyle: 'preserve-3d',
            pointerEvents: 'none',
            zIndex: 100
          }}>
            {/* Visual halo/ping ring around the cursor */}
            <div style={{
              position: 'absolute', inset: -6, border: '1.5px solid #5EEAD4', borderRadius: '50%',
              animation: 'mc-blink 1s infinite', opacity: 0.6
            }} />
            {/* Depth Line (connects down to grid floor) */}
            <div style={{
              position: 'absolute', top: 7, left: 6, width: '1.5px', height: '120px',
              background: 'linear-gradient(180deg, #5EEAD4 0%, transparent 100%)',
              transform: 'rotateX(-90deg)', transformOrigin: 'top center', opacity: 0.5
            }} />
          </div>

        </div>
      </div>
      
      {/* 3D rotation hint */}
      <div style={{
        position: 'absolute', bottom: 4, left: '50%', transform: 'translateX(-50%)',
        fontSize: 7.5, fontFamily: "'JetBrains Mono', monospace", color: 'rgba(255,255,255,0.35)',
        letterSpacing: 0.8, pointerEvents: 'none'
      }}>
        ◄ DRAG TO ROTATE 3D SPACE · CLICK ANY WINDOW TO FOCUS ►
      </div>
    </div>
  );
}

Object.assign(window, {
  MCVisualizer, MCDag, MCViewport, MCLogStream, MCPhone, MCAgentRoster,
  FakeTodoApp, hexA, MCViewport3D,
});
