// Claude Code 用量 — Übersicht 桌面小工具（質感版 / 可切主題）
// 可拖曳（記住位置）、環形儀表、迷你走勢、一鍵開啟完整面板。
// 由「安裝桌面小工具.command」自動填入 __PY__ / __REPO__。
//
// ⭐ 換風格：改下面這行 THEME = "aurora" | "terminal" | "mono"
//    aurora=極光(橘粉紫玻璃) / terminal=終端綠(工程感) / mono=極簡白(亮色桌布)

import { run } from "uebersicht";

const THEME = "aurora";

const PY = "__PY__";
const REPO = "__REPO__";
export const command = `"${PY}" "${REPO}/generate.py" --json`;
export const refreshFrequency = 300000; // 每 5 分鐘更新

const openDashboard = () =>
  run(`"${PY}" "${REPO}/generate.py" --no-open && open "${REPO}/index.html"`);

const SANS = '-apple-system, "PingFang TC", "Helvetica Neue", sans-serif';
const MONO = '"SF Mono", "JetBrains Mono", "Menlo", monospace';

const THEMES = {
  aurora: {
    font: SANS,
    cardBg: "linear-gradient(157deg, rgba(30,37,52,0.87), rgba(14,18,27,0.89))",
    blur: "blur(28px) saturate(150%)",
    border: "1px solid rgba(255,255,255,0.09)",
    shadow: "0 24px 64px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.07)",
    accent: "linear-gradient(90deg,#ff8c42,#ff6b9d,#9b8cff)",
    pill: "linear-gradient(135deg,#ff8c42,#ff6b9d)", pillText: "#fff",
    text: "#e6edf3", label: "#cdd6e0", mut: "#8b98a9", dim: "#5b6675", faint: "#48505d",
    track: "#0e141d", spark: "linear-gradient(180deg,#ffb37a,#ff8c42)",
    btnBg: "linear-gradient(135deg, rgba(255,140,66,0.22), rgba(255,107,157,0.22))",
    btnBorder: "1px solid rgba(255,140,66,0.40)", btnText: "#ffb37a",
    divider: "rgba(255,255,255,0.07)",
    gauge: (p) => (p >= 85 ? "#ff6b6b" : p >= 60 ? "#f5c451" : "#3fb68b"),
  },
  terminal: {
    font: MONO,
    cardBg: "linear-gradient(160deg, rgba(8,16,10,0.92), rgba(4,8,5,0.94))",
    blur: "blur(20px) saturate(130%)",
    border: "1px solid rgba(63,230,140,0.24)",
    shadow: "0 24px 64px rgba(0,0,0,0.6), inset 0 0 32px rgba(63,230,140,0.07)",
    accent: "linear-gradient(90deg,#155e3a,#3fe68c,#155e3a)",
    pill: "linear-gradient(135deg,#155e3a,#3fe68c)", pillText: "#04150b",
    text: "#c8f7dc", label: "#9fe7bf", mut: "#5fae84", dim: "#3c7a58", faint: "#2c5a40",
    track: "#06140c", spark: "linear-gradient(180deg,#7dffb6,#2fd47f)",
    btnBg: "rgba(63,230,140,0.12)",
    btnBorder: "1px solid rgba(63,230,140,0.45)", btnText: "#7dffb6",
    divider: "rgba(63,230,140,0.16)",
    gauge: (p) => (p >= 85 ? "#ff7a7a" : p >= 60 ? "#ffe06b" : "#3fe68c"),
  },
  mono: {
    font: SANS,
    cardBg: "linear-gradient(160deg, rgba(252,250,246,0.93), rgba(240,237,230,0.95))",
    blur: "blur(24px) saturate(120%)",
    border: "1px solid rgba(0,0,0,0.08)",
    shadow: "0 18px 50px rgba(60,50,40,0.22), inset 0 1px 0 rgba(255,255,255,0.6)",
    accent: "linear-gradient(90deg,#e08a4a,#d96a8a,#8a7ad0)",
    pill: "linear-gradient(135deg,#e08a4a,#d96a8a)", pillText: "#fff",
    text: "#2a2620", label: "#4a4338", mut: "#8a8174", dim: "#a89f90", faint: "#bcb3a4",
    track: "#e7e1d5", spark: "linear-gradient(180deg,#f0a868,#e08a4a)",
    btnBg: "linear-gradient(135deg, rgba(224,138,74,0.16), rgba(217,106,138,0.16))",
    btnBorder: "1px solid rgba(224,138,74,0.45)", btnText: "#c2683c",
    divider: "rgba(0,0,0,0.08)",
    gauge: (p) => (p >= 85 ? "#e05a5a" : p >= 60 ? "#d9a52a" : "#2fa372"),
  },
};
const T = THEMES[THEME] || THEMES.aurora;

export const className = `
  top: 0; left: 0; width: 100vw; height: 100vh;
  pointer-events: none;
  font-family: ${T.font};
`;

const usd = (n) =>
  "$" + (n >= 1000 ? Math.round(n).toLocaleString("en-US") : (n || 0).toFixed(2));

// ── 拖曳 + 記憶位置 ──
let cardEl = null;
const setCard = (el) => {
  if (!el) return;
  cardEl = el;
  try {
    const s = JSON.parse(localStorage.getItem("cuPos") || "null");
    if (s) { el.style.left = s.x + "px"; el.style.top = s.y + "px"; el.style.right = "auto"; }
  } catch (e) {}
};
const startDrag = (e) => {
  const el = cardEl; if (!el) return;
  const r = el.getBoundingClientRect();
  const ox = e.clientX - r.left, oy = e.clientY - r.top;
  const move = (ev) => {
    el.style.left = (ev.clientX - ox) + "px";
    el.style.top = (ev.clientY - oy) + "px";
    el.style.right = "auto";
  };
  const up = () => {
    document.removeEventListener("mousemove", move);
    document.removeEventListener("mouseup", up);
    localStorage.setItem("cuPos", JSON.stringify({
      x: parseInt(el.style.left) || 0, y: parseInt(el.style.top) || 0,
    }));
  };
  document.addEventListener("mousemove", move);
  document.addEventListener("mouseup", up);
  e.preventDefault();
};

const Ring = ({ pct, label, used, limit, sub }) => {
  const r = 32, C = 2 * Math.PI * r, off = C * (1 - Math.min(pct, 100) / 100);
  const col = T.gauge(pct);
  return (
    <div style={{ textAlign: "center", flex: 1 }}>
      <svg width="92" height="92" viewBox="0 0 92 92">
        <circle cx="46" cy="46" r={r} fill="none" stroke={T.track} strokeWidth="8.5" />
        <circle cx="46" cy="46" r={r} fill="none" stroke={col} strokeWidth="8.5"
          strokeLinecap="round" strokeDasharray={C} strokeDashoffset={off}
          transform="rotate(-90 46 46)"
          style={{ filter: `drop-shadow(0 0 6px ${col}aa)`, transition: "stroke-dashoffset .6s ease" }} />
        <text x="46" y="49" textAnchor="middle" fill={T.text} fontSize="21" fontWeight="750">
          {Math.round(pct)}%
        </text>
        <text x="46" y="64" textAnchor="middle" fill={T.mut} fontSize="9.5">{sub}</text>
      </svg>
      <div style={{ fontSize: 13.5, color: T.label, fontWeight: 600, marginTop: 2 }}>{label}</div>
      <div style={{ fontSize: 11, color: T.dim, marginTop: 3 }}>{usd(used)} / {usd(limit)}</div>
    </div>
  );
};

const Spark = ({ data }) => {
  if (!data || !data.length) return null;
  const max = Math.max(...data, 0.01);
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 3, height: 30, marginTop: 14 }}>
      {data.map((v, i) => (
        <div key={i} title={usd(v)} style={{
          flex: 1, height: Math.max((v / max) * 30, 3),
          background: T.spark, borderRadius: 2.5, opacity: 0.55 + 0.45 * (v / max),
        }} />
      ))}
    </div>
  );
};

export const render = ({ output }) => {
  let d;
  try { d = JSON.parse(output); }
  catch (e) { return <div style={{ pointerEvents: "none" }} />; }

  const card = {
    position: "absolute", top: "40px", right: "30px", width: "320px",
    padding: "0 0 18px", overflow: "hidden",
    background: T.cardBg, WebkitBackdropFilter: T.blur,
    borderRadius: "23px", border: T.border, boxShadow: T.shadow,
    color: T.text, pointerEvents: "auto",
  };
  const pad = { padding: "0 23px" };

  return (
    <div ref={setCard} style={card}>
      <div style={{ height: 4, background: T.accent }} />
      <div onMouseDown={startDrag} style={{
        ...pad, paddingTop: 17, paddingBottom: 5, cursor: "move",
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <span style={{ fontSize: 15.5, fontWeight: 750, letterSpacing: 0.2 }}>⛁ Claude 用量</span>
        <span style={{
          fontSize: 11, fontWeight: 700, color: T.pillText, padding: "3px 11px",
          borderRadius: 20, background: T.pill,
        }}>{d.plan || "未校準"}</span>
      </div>
      <div style={{ ...pad, display: "flex", gap: 10, marginTop: 10 }}>
        <Ring pct={d.block.pct} label="5 小時視窗" used={d.block.used} limit={d.block.limit}
          sub={`${d.block.reset_in}h 後重置`} />
        <Ring pct={d.week.pct} label="本週用量" used={d.week.used} limit={d.week.limit}
          sub={`${d.week.reset_days}d 後重置`} />
      </div>
      <div style={pad}><Spark data={d.spark} /></div>
      <div style={{ ...pad, fontSize: 11, color: T.dim, marginTop: 4 }}>近 14 天每日花費</div>
      <div style={{
        ...pad, marginTop: 14, paddingTop: 12, borderTop: `1px solid ${T.divider}`,
        display: "flex", justifyContent: "space-between", fontSize: 12.5, color: T.mut,
      }}>
        <span>今日 <b style={{ color: T.text }}>{usd(d.today)}</b></span>
        <span>累計等值 <b style={{ color: T.text }}>{usd(d.total)}</b></span>
      </div>
      <div style={pad}>
        <div onClick={openDashboard} style={{
          marginTop: 13, textAlign: "center", padding: "11px 0", borderRadius: 13,
          background: T.btnBg, border: T.btnBorder, color: T.btnText,
          fontWeight: 700, fontSize: 13.5, cursor: "pointer", userSelect: "none",
        }}>📊 開啟完整面板</div>
      </div>
      <div style={{ ...pad, textAlign: "right", fontSize: 10, color: T.faint, marginTop: 8 }}>
        更新 {(d.generated_at || "").slice(11)}
      </div>
    </div>
  );
};
