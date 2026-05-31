/* j2-shared.jsx — icons, small UI atoms, helpers for Jarvis Console 2.0 */

const Icon = ({ d, size = 18, fill = "none", stroke = "currentColor", sw = 1.6, children, vb = 24, style }) => (
  <svg width={size} height={size} viewBox={`0 0 ${vb} ${vb}`} fill={fill} stroke={stroke}
       strokeWidth={sw} strokeLinecap="round" strokeLinejoin="round" style={style}>
    {d ? <path d={d} /> : children}
  </svg>
);

const IconPlus    = (p) => <Icon {...p} children={<><line x1="12" y1="5" x2="12" y2="19"/><line x1="5" y1="12" x2="19" y2="12"/></>} />;
const IconConsole = (p) => <Icon {...p} children={<><rect x="3" y="4.5" width="18" height="15" rx="2.5"/><line x1="13" y1="4.5" x2="13" y2="19.5"/></>} />;
const IconRuns    = (p) => <Icon {...p} children={<><circle cx="12" cy="12" r="8"/><path d="M12 8v4l2.5 1.6"/></>} />;
const IconMemory  = (p) => <Icon {...p} children={<><circle cx="6" cy="7" r="2"/><circle cx="18" cy="7" r="2"/><circle cx="12" cy="17" r="2"/><path d="M7.5 8.4 10.8 15.4M16.5 8.4 13.2 15.4M8 7h8"/></>} />;
const IconGear    = (p) => <Icon {...p} children={<><line x1="4" y1="8" x2="20" y2="8"/><circle cx="9" cy="8" r="2.2" fill="var(--surface)"/><line x1="4" y1="16" x2="20" y2="16"/><circle cx="15" cy="16" r="2.2" fill="var(--surface)"/></>} />;
const IconSend    = (p) => <Icon {...p} children={<><path d="M6 12h12M13 6l6 6-6 6"/></>} />;
const IconArrow   = (p) => <Icon {...p} children={<><path d="M5 12h13M12 6l6 6-6 6"/></>} />;
const IconMic     = (p) => <Icon {...p} children={<><rect x="9" y="3" width="6" height="11" rx="3"/><path d="M5.5 11a6.5 6.5 0 0 0 13 0M12 17.5V21"/></>} />;
const IconCheck   = (p) => <Icon {...p} children={<path d="M5 12.5l4.2 4.2L19 7"/>} />;
const IconSpark   = (p) => <Icon {...p} children={<path d="M12 3c.5 4.2 1.8 5.5 6 6-4.2.5-5.5 1.8-6 6-.5-4.2-1.8-5.5-6-6 4.2-.5 5.5-1.8 6-6z" fill="currentColor" stroke="none"/>} />;
const IconClose   = (p) => <Icon {...p} children={<><line x1="6" y1="6" x2="18" y2="18"/><line x1="18" y1="6" x2="6" y2="18"/></>} />;
const IconFile    = (p) => <Icon {...p} children={<><path d="M7 3h7l5 5v13H7z"/><path d="M14 3v5h5"/></>} />;
const IconDot     = (p) => <Icon {...p} children={<circle cx="12" cy="12" r="4" fill="currentColor" stroke="none"/>} />;
const IconStorage = (p) => <Icon {...p} children={<><ellipse cx="12" cy="7" rx="8" ry="3"/><path d="M4 7v5c0 1.66 3.58 3 8 3s8-1.34 8-3V7"/><path d="M4 12v5c0 1.66 3.58 3 8 3s8-1.34 8-3v-5"/></>} />;
const IconLink    = (p) => <Icon {...p} children={<><path d="M10 13a5 5 0 0 0 7.54.54l3-3a5 5 0 0 0-7.07-7.07l-1.72 1.71"/><path d="M14 11a5 5 0 0 0-7.54-.54l-3 3a5 5 0 0 0 7.07 7.07l1.71-1.71"/></>} />;

const Logo = ({ size = 28 }) => (
  <div style={{
    width: size, height: size, borderRadius: size * 0.32, flexShrink: 0,
    background: "var(--ink)", color: "var(--panel)",
    display: "grid", placeItems: "center",
    fontFamily: "var(--serif)", fontWeight: 500, fontSize: size * 0.56,
    lineHeight: 1, paddingBottom: size * 0.04,
  }}>J</div>
);

const Pulse = ({ color = "var(--clay)", size = 7 }) => (
  <span style={{ position: "relative", width: size, height: size, display: "inline-block", flexShrink: 0 }}>
    <span style={{ position: "absolute", inset: 0, borderRadius: "50%", background: color }} />
    <span className="j2-pulse" style={{ position: "absolute", inset: 0, borderRadius: "50%", boxShadow: `0 0 0 0 ${color}` }} />
  </span>
);

function greeting() {
  const h = new Date().getHours();
  if (h < 5)  return "Still up";
  if (h < 12) return "Good morning";
  if (h < 18) return "Good afternoon";
  return "Good evening";
}

Object.assign(window, {
  j2Icon: Icon, IconPlus, IconConsole, IconRuns, IconMemory, IconGear,
  IconSend, IconArrow, IconMic, IconCheck, IconSpark, IconClose,
  IconFile, IconDot, IconStorage, IconLink, Logo, Pulse, greeting,
});
