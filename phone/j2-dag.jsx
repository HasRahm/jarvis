/* j2-dag.jsx — animated agent execution graph */
const { useRef: useDagRef, useState: useDagState, useLayoutEffect: useDagLayout, useEffect: useDagEffect } = React;

function j2StatusOf(node, statuses) {
  return statuses[node.id] || "pending";
}

const J2NodeCard = React.forwardRef(({ node, status }, ref) => {
  const running = status === "running";
  const done    = status === "done";
  const io      = node.kind === "io";
  return (
    <div ref={ref} className={`j2-dag-node ${status} ${io ? "io" : ""}`}>
      <div className="j2-dag-node-top">
        {done
          ? <span className="j2-dag-check"><IconCheck size={11} sw={2.4} /></span>
          : running
            ? <Pulse size={7} />
            : <span className="j2-dag-pend" />}
        <span className="j2-dag-node-label">{node.label}</span>
      </div>
      <div className="j2-dag-node-sub">{node.sub}</div>
    </div>
  );
});

function J2DAG({ statuses }) {
  const wrapRef  = useDagRef(null);
  const nodeRefs = useDagRef({});
  const [paths, setPaths] = useDagState([]);

  const measure = () => {
    const wrap = wrapRef.current;
    if (!wrap) return;
    const wb = wrap.getBoundingClientRect();
    const out = [];
    J2_EDGES.forEach(([from, to], i) => {
      const a = nodeRefs.current[from], b = nodeRefs.current[to];
      if (!a || !b) return;
      const ab = a.getBoundingClientRect(), bb = b.getBoundingClientRect();
      const x1 = ab.right - wb.left,  y1 = ab.top - wb.top + ab.height / 2;
      const x2 = bb.left  - wb.left,  y2 = bb.top - wb.top + bb.height / 2;
      const dx = Math.max(28, (x2 - x1) * 0.5);
      const d  = `M ${x1} ${y1} C ${x1+dx} ${y1}, ${x2-dx} ${y2}, ${x2} ${y2}`;
      const active = statuses[from] === "done" && (statuses[to] === "running" || statuses[to] === "done");
      out.push({ d, active, key: i });
    });
    setPaths(prev => {
      const same = prev.length === out.length && prev.every((p, i) => p.d === out[i].d && p.active === out[i].active);
      return same ? prev : out;
    });
  };

  useDagLayout(() => { measure(); }, [statuses]);
  useDagEffect(() => {
    const ro = new ResizeObserver(measure);
    if (wrapRef.current) ro.observe(wrapRef.current);
    window.addEventListener("resize", measure);
    return () => { ro.disconnect(); window.removeEventListener("resize", measure); };
  }, []);

  const cols = [[], [], [], [], []];
  J2_NODES.forEach(n => cols[n.col].push(n));

  return (
    <div className="j2-dag-wrap" ref={wrapRef}>
      <svg className="j2-dag-edges" preserveAspectRatio="none">
        {paths.map(p => (
          <path key={p.key} d={p.d} className={`j2-dag-edge ${p.active ? "on" : ""}`} />
        ))}
      </svg>
      <div className="j2-dag-cols">
        {cols.map((col, ci) => (
          <div className="j2-dag-col" key={ci}>
            {col.map(n => (
              <J2NodeCard
                key={n.id} node={n} status={j2StatusOf(n, statuses)}
                ref={el => { nodeRefs.current[n.id] = el; }}
              />
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}

window.J2DAG = J2DAG;
