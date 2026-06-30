// Claude Code 用量 — Übersicht 桌面小工具
// 由「安裝桌面小工具.command」自動填入 __PY__ / __REPO__；手動安裝請自行替換。

export const command = `"__PY__" "__REPO__/generate.py" --json`;
export const refreshFrequency = 300000; // 每 5 分鐘更新

export const className = `
  top: 40px;
  right: 30px;
  font-family: -apple-system, "PingFang TC", "Helvetica Neue", sans-serif;
`;

const color = (p) => (p >= 85 ? "#ff6b6b" : p >= 60 ? "#f5c451" : "#3fb68b");
const usd = (n) =>
  "$" + (n >= 1000 ? Math.round(n).toLocaleString("en-US") : n.toFixed(2));

const Bar = ({ pct }) => (
  <div style={{ height: 9, background: "#0e141d", borderRadius: 5, overflow: "hidden" }}>
    <div style={{ height: "100%", width: Math.min(pct, 100) + "%",
                  background: color(pct), borderRadius: 5 }} />
  </div>
);

const Row = ({ label, v }) => (
  <div style={{ marginTop: 12 }}>
    <div style={{ display: "flex", justifyContent: "space-between",
                  fontSize: 12.5, marginBottom: 5 }}>
      <span style={{ color: "#8b98a9" }}>{label}</span>
      <span style={{ color: color(v.pct), fontWeight: 700 }}>{Math.round(v.pct)}%</span>
    </div>
    <Bar pct={v.pct} />
    <div style={{ fontSize: 11, color: "#5b6675", marginTop: 4 }}>
      {usd(v.used)} / {usd(v.limit)} · 還能用 {usd(v.remain)}
    </div>
  </div>
);

export const render = ({ output }) => {
  let d;
  try { d = JSON.parse(output); }
  catch (e) { return <div style={{ color: "#8b98a9", padding: 14 }}>載入中…</div>; }
  return (
    <div style={{
      width: 236, padding: "16px 18px",
      background: "rgba(18,23,33,0.80)",
      WebkitBackdropFilter: "blur(22px)", backdropFilter: "blur(22px)",
      borderRadius: 18, border: "1px solid #222c3a",
      boxShadow: "0 14px 44px rgba(0,0,0,0.5)", color: "#e6edf3",
    }}>
      <div style={{ display: "flex", justifyContent: "space-between",
                    alignItems: "center", fontSize: 13, fontWeight: 700 }}>
        <span>⛁ Claude 用量</span>
        <span style={{ fontSize: 11, color: "#8b98a9", fontWeight: 500 }}>{d.plan}</span>
      </div>
      <Row label="5 小時視窗" v={d.block} />
      <Row label="本週用量" v={d.week} />
      <div style={{ fontSize: 11, color: "#5b6675", marginTop: 12,
                    borderTop: "1px solid #222c3a", paddingTop: 8,
                    display: "flex", justifyContent: "space-between" }}>
        <span>今日 {usd(d.today)}</span>
        <span>更新 {(d.generated_at || "").slice(11)}</span>
      </div>
    </div>
  );
};
