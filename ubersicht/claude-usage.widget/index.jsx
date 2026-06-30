// Claude Code 用量 — Übersicht 桌面小工具（質感版）
// 可拖曳（記住位置）、環形儀表、迷你走勢、一鍵開啟完整面板。
// 由「安裝桌面小工具.command」自動填入 __PY__ / __REPO__。

const PY = "__PY__";
const REPO = "__REPO__";
export const command = `"${PY}" "${REPO}/generate.py" --json`;
export const refreshFrequency = 300000; // 每 5 分鐘更新

// 整個 root 鋪滿桌面但可穿透；只有卡片本身可互動
export const className = `
  top: 0; left: 0; width: 100vw; height: 100vh;
  pointer-events: none;
  font-family: -apple-system, "PingFang TC", "Helvetica Neue", sans-serif;
`;

const color = (p) => (p >= 85 ? "#ff6b6b" : p >= 60 ? "#f5c451" : "#3fb68b");
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

// ── 環形儀表 ──
const Ring = ({ pct, label, used, limit, sub }) => {
  const r = 26, C = 2 * Math.PI * r, off = C * (1 - Math.min(pct, 100) / 100);
  const col = color(pct);
  return (
    <div style={{ textAlign: "center", flex: 1 }}>
      <svg width="74" height="74" viewBox="0 0 74 74">
        <circle cx="37" cy="37" r={r} fill="none" stroke="#0e141d" strokeWidth="7" />
        <circle cx="37" cy="37" r={r} fill="none" stroke={col} strokeWidth="7"
          strokeLinecap="round" strokeDasharray={C} strokeDashoffset={off}
          transform="rotate(-90 37 37)"
          style={{ filter: `drop-shadow(0 0 5px ${col}aa)`, transition: "stroke-dashoffset .6s ease" }} />
        <text x="37" y="40" textAnchor="middle" fill="#e6edf3" fontSize="16" fontWeight="750">
          {Math.round(pct)}%
        </text>
        <text x="37" y="52" textAnchor="middle" fill="#8b98a9" fontSize="8">{sub}</text>
      </svg>
      <div style={{ fontSize: 12, color: "#cdd6e0", fontWeight: 600, marginTop: 1 }}>{label}</div>
      <div style={{ fontSize: 10, color: "#5b6675", marginTop: 2 }}>{usd(used)} / {usd(limit)}</div>
    </div>
  );
};

// ── 迷你走勢（近 14 天）──
const Spark = ({ data }) => {
  if (!data || !data.length) return null;
  const max = Math.max(...data, 0.01);
  return (
    <div style={{ display: "flex", alignItems: "flex-end", gap: 2, height: 22, marginTop: 12 }}>
      {data.map((v, i) => (
        <div key={i} title={usd(v)} style={{
          flex: 1, height: Math.max((v / max) * 22, 2),
          background: "linear-gradient(180deg,#ffb37a,#ff8c42)",
          borderRadius: 2, opacity: 0.55 + 0.45 * (v / max),
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
    position: "absolute", top: "40px", right: "30px", width: "264px",
    padding: "0 0 15px", overflow: "hidden",
    background: "linear-gradient(157deg, rgba(30,37,52,0.86), rgba(14,18,27,0.88))",
    WebkitBackdropFilter: "blur(26px) saturate(150%)",
    borderRadius: "20px", border: "1px solid rgba(255,255,255,0.09)",
    boxShadow: "0 20px 55px rgba(0,0,0,0.55), inset 0 1px 0 rgba(255,255,255,0.07)",
    color: "#e6edf3", pointerEvents: "auto",
  };
  const pad = { padding: "0 19px" };

  return (
    <div ref={setCard} style={card}>
      {/* 頂部漸層光條（氛圍）*/}
      <div style={{ height: 3, background: "linear-gradient(90deg,#ff8c42,#ff6b9d,#9b8cff)" }} />
      {/* 標題列（可拖曳）*/}
      <div onMouseDown={startDrag} style={{
        ...pad, paddingTop: 14, paddingBottom: 4, cursor: "move",
        display: "flex", justifyContent: "space-between", alignItems: "center",
      }}>
        <span style={{ fontSize: 13.5, fontWeight: 750, letterSpacing: 0.2 }}>⛁ Claude 用量</span>
        <span style={{
          fontSize: 10, fontWeight: 700, color: "#fff", padding: "2px 9px", borderRadius: 20,
          background: "linear-gradient(135deg,#ff8c42,#ff6b9d)",
        }}>{d.plan || "未校準"}</span>
      </div>
      {/* 雙環 */}
      <div style={{ ...pad, display: "flex", gap: 8, marginTop: 8 }}>
        <Ring pct={d.block.pct} label="5 小時視窗" used={d.block.used} limit={d.block.limit}
          sub={`${d.block.reset_in}h 後重置`} />
        <Ring pct={d.week.pct} label="本週用量" used={d.week.used} limit={d.week.limit}
          sub={`${d.week.reset_days}d 後重置`} />
      </div>
      {/* 走勢 */}
      <div style={pad}><Spark data={d.spark} /></div>
      <div style={{ ...pad, fontSize: 10, color: "#5b6675", marginTop: 3 }}>近 14 天每日花費</div>
      {/* 頁尾 + 按鈕 */}
      <div style={{
        ...pad, marginTop: 12, paddingTop: 10, borderTop: "1px solid rgba(255,255,255,0.07)",
        display: "flex", justifyContent: "space-between", fontSize: 11, color: "#8b98a9",
      }}>
        <span>今日 <b style={{ color: "#e6edf3" }}>{usd(d.today)}</b></span>
        <span>累計等值 <b style={{ color: "#e6edf3" }}>{usd(d.total)}</b></span>
      </div>
      <div style={pad}>
        <div onClick={() => run(`"${PY}" "${REPO}/generate.py"`)} style={{
          marginTop: 11, textAlign: "center", padding: "9px 0", borderRadius: 11,
          background: "linear-gradient(135deg, rgba(255,140,66,0.20), rgba(255,107,157,0.20))",
          border: "1px solid rgba(255,140,66,0.38)", color: "#ffb37a",
          fontWeight: 700, fontSize: 12.5, cursor: "pointer", userSelect: "none",
        }}>📊 開啟完整面板</div>
      </div>
      <div style={{ ...pad, textAlign: "right", fontSize: 9.5, color: "#48505d", marginTop: 7 }}>
        更新 {(d.generated_at || "").slice(11)}
      </div>
    </div>
  );
};
