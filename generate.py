#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 用量監控面板 — 專屬版
讀取 ~/.claude/projects 的 JSONL，算出 Claude Code 的 token / 等值 API 成本，
產生一個自帶美感、離線可看的 HTML 儀表板。

用法:
    python3 generate.py            # 產生 index.html 並（可選）開啟
    python3 generate.py --no-open  # 只產生不開啟

設計參考：yanowo/usage-monitor、DeppWang/Claude-Code-Usage-Tracker、khscience/claude-usage-widget
做法（讀 JSONL → 去重 → 計價 → 視覺化），但呈現方式為專屬重做。
"""

import json
import glob
import os
import sys
import html
import webbrowser
from collections import defaultdict
from datetime import datetime, timezone, timedelta

HOME = os.path.expanduser("~")
PROJECTS_DIR = os.path.join(HOME, ".claude", "projects")
OUT_HTML = os.path.join(os.path.dirname(os.path.abspath(__file__)), "index.html")

# ── 計價表（每百萬 token，美元）。來源：claude-api 技能官方計價 ──
#   input / output；cache write(5m)=input×1.25；cache read=input×0.1
PRICING = {
    "opus":   {"in": 5.0,  "out": 25.0},
    "sonnet": {"in": 3.0,  "out": 15.0},
    "haiku":  {"in": 1.0,  "out": 5.0},
}
DEFAULT_PRICE = {"in": 5.0, "out": 25.0}  # 不認得的模型先當 opus 估

# ── 方案用量上限（佔比的「分母」）─────────────────────────────────
#   Anthropic 不會把 5 小時視窗的真實上限寫到本機，所以預設用「自動偵測」：
#   以你歷史上最高的 5 小時 / 單週用量當基準，看「現在用到歷史高點的幾 %」。
#   若你知道自己方案，把下面改成實際等值成本上限（美元），佔比就改用固定分母。
#   None = 自動（歷史最高）。
PLAN_5H_LIMIT_USD = None       # 例：Max 約一個視窗 ~50；自行調整
PLAN_WEEKLY_LIMIT_USD = None   # 例：每週上限的等值成本
PLAN_NAME = ""                 # 方案名稱（顯示用），例 "Max (5x)"
NOTIFY_THRESHOLD = 80          # 用量超過此 % 就提醒（--notify）

# 個人設定檔（gitignore）。由 --calibrate 產生，會覆蓋上面三個值。
_CFG = os.path.join(os.path.dirname(os.path.abspath(__file__)), "config.json")


def _load_config():
    global PLAN_5H_LIMIT_USD, PLAN_WEEKLY_LIMIT_USD, PLAN_NAME
    try:
        with open(_CFG, encoding="utf-8") as fh:
            c = json.load(fh)
        PLAN_5H_LIMIT_USD = c.get("limit_5h_usd") or PLAN_5H_LIMIT_USD
        PLAN_WEEKLY_LIMIT_USD = c.get("limit_weekly_usd") or PLAN_WEEKLY_LIMIT_USD
        PLAN_NAME = c.get("plan", PLAN_NAME)
    except FileNotFoundError:
        pass
    except Exception as e:
        print(f"（config.json 讀取失敗，忽略：{e}）")


def fmt_usd(n):
    return f"${n:,.0f}" if n >= 1000 else f"${n:.2f}"


def price_for(model: str):
    m = (model or "").lower()
    for key, p in PRICING.items():
        if key in m:
            return p
    return DEFAULT_PRICE


def cost_of(model, inp, out, cc, cr):
    """回傳這筆訊息的等值 API 成本（美元）。"""
    p = price_for(model)
    return (
        inp * p["in"]
        + out * p["out"]
        + cc * p["in"] * 1.25   # cache 寫入 ~1.25x input
        + cr * p["in"] * 0.10   # cache 讀取 ~0.1x input
    ) / 1_000_000


def decode_project(dirname: str) -> str:
    """把 -Users-phchen-Desktop-stock-quant 之類解成可讀標籤（取最後一段）。"""
    if not dirname:
        return "unknown"
    parts = [p for p in dirname.split("-") if p]
    return parts[-1] if parts else dirname


def local_dt(ts: str):
    """ISO8601(Z) → 本機時區 datetime。"""
    try:
        if ts.endswith("Z"):
            ts = ts[:-1] + "+00:00"
        return datetime.fromisoformat(ts).astimezone()
    except Exception:
        return None


def model_label(model: str) -> str:
    m = (model or "").lower()
    table = {
        "opus-4-8": "Opus 4.8", "opus-4-7": "Opus 4.7", "opus-4-6": "Opus 4.6",
        "opus-4-5": "Opus 4.5", "sonnet-4-6": "Sonnet 4.6", "sonnet-4-5": "Sonnet 4.5",
        "haiku-4-5": "Haiku 4.5",
    }
    for k, v in table.items():
        if k in m:
            return v
    return model


def collect():
    files = glob.glob(os.path.join(PROJECTS_DIR, "**", "*.jsonl"), recursive=True)

    seen = set()
    totals = defaultdict(float)
    by_day = defaultdict(lambda: defaultdict(float))
    by_model = defaultdict(lambda: defaultdict(float))
    by_project = defaultdict(lambda: defaultdict(float))
    heat = [[0.0] * 24 for _ in range(7)]   # 週(0=Mon)×小時 → 訊息數
    sessions = set()
    all_events = []  # (dt, cost, tokens) 給 5h block 用，量大→只留近 7 天
    blocks = defaultdict(lambda: defaultdict(float))  # 5h 視窗桶 → {cost,tokens,messages}
    weeks = defaultdict(lambda: defaultdict(float))   # ISO 週 → {cost,tokens,messages}

    cutoff_recent = datetime.now().astimezone() - timedelta(days=8)

    for f in files:
        project_dir = os.path.basename(os.path.dirname(f))
        try:
            with open(f, "r", encoding="utf-8", errors="ignore") as fh:
                for line in fh:
                    line = line.strip()
                    if not line or '"usage"' not in line:
                        continue
                    try:
                        d = json.loads(line)
                    except Exception:
                        continue
                    msg = d.get("message")
                    if not isinstance(msg, dict):
                        continue
                    u = msg.get("usage")
                    if not isinstance(u, dict):
                        continue
                    model = msg.get("model", "")
                    if model in ("<synthetic>", None, ""):
                        continue

                    # 去重：message.id + requestId（同 ccusage 做法）
                    uid = f"{msg.get('id')}::{d.get('requestId')}"
                    if uid in seen:
                        continue
                    seen.add(uid)

                    inp = u.get("input_tokens", 0) or 0
                    out = u.get("output_tokens", 0) or 0
                    cc = u.get("cache_creation_input_tokens", 0) or 0
                    cr = u.get("cache_read_input_tokens", 0) or 0
                    tok = inp + out + cc + cr
                    cost = cost_of(model, inp, out, cc, cr)

                    sid = d.get("sessionId")
                    if sid:
                        sessions.add(sid)

                    dt = local_dt(d.get("timestamp", ""))

                    # 總計
                    totals["cost"] += cost
                    totals["input"] += inp
                    totals["output"] += out
                    totals["cache_creation"] += cc
                    totals["cache_read"] += cr
                    totals["tokens"] += tok
                    totals["messages"] += 1

                    # 模型
                    ml = model_label(model)
                    by_model[ml]["cost"] += cost
                    by_model[ml]["tokens"] += tok
                    by_model[ml]["messages"] += 1

                    # 專案
                    pl = decode_project(project_dir)
                    by_project[pl]["cost"] += cost
                    by_project[pl]["tokens"] += tok
                    by_project[pl]["messages"] += 1

                    if dt:
                        day = dt.strftime("%Y-%m-%d")
                        by_day[day]["cost"] += cost
                        by_day[day]["tokens"] += tok
                        by_day[day]["messages"] += 1
                        by_day[day]["output"] += out
                        heat[dt.weekday()][dt.hour] += 1
                        # 固定 5 小時桶（從 epoch 起算，可重現、可比較）
                        bidx = int(dt.timestamp() // (5 * 3600))
                        blocks[bidx]["cost"] += cost
                        blocks[bidx]["tokens"] += tok
                        blocks[bidx]["messages"] += 1
                        wkey = dt.strftime("%G-W%V")  # ISO 年-週
                        weeks[wkey]["cost"] += cost
                        weeks[wkey]["tokens"] += tok
                        weeks[wkey]["messages"] += 1
                        if dt >= cutoff_recent:
                            all_events.append((dt, cost, tok))

        except Exception:
            continue

    return {
        "totals": totals, "by_day": by_day, "by_model": by_model,
        "by_project": by_project, "heat": heat, "sessions": sessions,
        "events": all_events, "blocks": blocks, "weeks": weeks,
    }


def detect_other_tools():
    out = {}
    # Gemini CLI
    gem = os.path.join(HOME, ".gemini")
    if os.path.isdir(gem):
        hist = os.path.join(gem, "history")
        sess = 0
        if os.path.isdir(hist):
            sess = len([x for x in os.listdir(hist) if not x.startswith(".")])
        out["gemini"] = {"installed": True, "sessions": sess,
                         "note": "Gemini CLI 有歷史紀錄，但未保存 token 用量，無法計算成本"}
    else:
        out["gemini"] = {"installed": False}
    # Codex
    out["codex"] = {"installed": os.path.isdir(os.path.join(HOME, ".codex"))}
    return out


def build_data():
    raw = collect()
    t = raw["totals"]

    by_day = []
    for day in sorted(raw["by_day"].keys()):
        v = raw["by_day"][day]
        by_day.append({
            "date": day, "cost": round(v["cost"], 4),
            "tokens": int(v["tokens"]), "messages": int(v["messages"]),
            "output": int(v.get("output", 0)),
        })

    by_model = sorted([
        {"model": k, "cost": round(v["cost"], 2),
         "tokens": int(v["tokens"]), "messages": int(v["messages"])}
        for k, v in raw["by_model"].items()
    ], key=lambda x: -x["cost"])

    by_project = sorted([
        {"project": k, "cost": round(v["cost"], 2),
         "tokens": int(v["tokens"]), "messages": int(v["messages"])}
        for k, v in raw["by_project"].items()
    ], key=lambda x: -x["cost"])

    # 今日 / 本週 / 本月
    now = datetime.now().astimezone()
    today_str = now.strftime("%Y-%m-%d")
    week_start = (now - timedelta(days=now.weekday())).strftime("%Y-%m-%d")
    month_start = now.strftime("%Y-%m-01")

    def sum_since(since):
        c = tk = ms = 0.0
        for d in by_day:
            if d["date"] >= since:
                c += d["cost"]; tk += d["tokens"]; ms += d["messages"]
        return {"cost": round(c, 2), "tokens": int(tk), "messages": int(ms)}

    today = next((d for d in by_day if d["date"] == today_str),
                 {"cost": 0, "tokens": 0, "messages": 0})

    # ── 目前 5 小時視窗（固定桶）+ 佔比 ──
    blocks = raw["blocks"]
    # 基準（分母）：歷史最高 5h 等值成本（排除目前進行中的桶）
    now_bidx = int(now.timestamp() // (5 * 3600))
    past_costs = [v["cost"] for b, v in blocks.items() if b != now_bidx]
    auto_limit = max(past_costs) if past_costs else 0.01
    limit_5h = PLAN_5H_LIMIT_USD if PLAN_5H_LIMIT_USD else auto_limit
    limit_src = "manual" if PLAN_5H_LIMIT_USD else "auto"

    cur = blocks.get(now_bidx, {"cost": 0, "tokens": 0, "messages": 0})
    block_start = datetime.fromtimestamp(now_bidx * 5 * 3600).astimezone()
    block_end = block_start + timedelta(hours=5)
    elapsed = max((now - block_start).total_seconds() / 3600, 0.01)
    reset_in = (block_end - now).total_seconds() / 3600
    used_cost = cur["cost"]
    pct = (used_cost / limit_5h * 100) if limit_5h else 0
    block = {
        "active": cur["messages"] > 0,
        "used_cost": round(used_cost, 2), "tokens": int(cur["tokens"]),
        "messages": int(cur["messages"]),
        "limit": round(limit_5h, 2), "limit_src": limit_src,
        "remain": round(max(limit_5h - used_cost, 0), 2),
        "pct": round(pct, 1),
        "start": block_start.strftime("%H:%M"), "end": block_end.strftime("%H:%M"),
        "reset_in": round(max(reset_in, 0), 1),
        "elapsed_hours": round(elapsed, 1),
        "burn_per_hour": round(used_cost / elapsed, 2) if elapsed > 0 else 0,
    }

    # ── 本週用量 + 佔比 ──
    weeks = raw["weeks"]
    cur_wk = now.strftime("%G-W%V")
    past_wk_costs = [v["cost"] for w, v in weeks.items() if w != cur_wk]
    auto_wk_limit = max(past_wk_costs) if past_wk_costs else 0.01
    wk_limit = PLAN_WEEKLY_LIMIT_USD if PLAN_WEEKLY_LIMIT_USD else auto_wk_limit
    cur_wk_v = weeks.get(cur_wk, {"cost": 0, "tokens": 0, "messages": 0})
    next_monday = (now + timedelta(days=(7 - now.weekday()))).replace(
        hour=0, minute=0, second=0, microsecond=0)
    week_block = {
        "used_cost": round(cur_wk_v["cost"], 2),
        "tokens": int(cur_wk_v["tokens"]),
        "limit": round(wk_limit, 2),
        "limit_src": "manual" if PLAN_WEEKLY_LIMIT_USD else "auto",
        "pct": round((cur_wk_v["cost"] / wk_limit * 100) if wk_limit else 0, 1),
        "remain": round(max(wk_limit - cur_wk_v["cost"], 0), 2),
        "reset_days": round((next_monday - now).total_seconds() / 86400, 1),
    }

    days_active = len(by_day)
    first_day = by_day[0]["date"] if by_day else "-"
    last_day = by_day[-1]["date"] if by_day else "-"

    return {
        "generated_at": now.strftime("%Y-%m-%d %H:%M"),
        "plan_name": PLAN_NAME,
        "totals": {
            "cost": round(t["cost"], 2),
            "input": int(t["input"]), "output": int(t["output"]),
            "cache_creation": int(t["cache_creation"]),
            "cache_read": int(t["cache_read"]),
            "tokens": int(t["tokens"]),
            "messages": int(t["messages"]),
            "sessions": len(raw["sessions"]),
            "projects": len(by_project),
            "active_days": days_active,
            "first_day": first_day, "last_day": last_day,
            "avg_per_day": round(t["cost"] / days_active, 2) if days_active else 0,
        },
        "today": {"cost": round(today["cost"], 2), "tokens": int(today["tokens"]),
                  "messages": int(today["messages"])},
        "week": sum_since(week_start),
        "month": sum_since(month_start),
        "block": block,
        "week_block": week_block,
        "by_day": by_day,
        "by_model": by_model,
        "by_project": by_project,
        "heat": raw["heat"],
        "other_tools": detect_other_tools(),
    }


# ──────────────────────────────────────────────────────────────────────
#  HTML / 前端（自帶 SVG 圖表，無外部相依，離線可看）
# ──────────────────────────────────────────────────────────────────────
def render_html(data: dict) -> str:
    payload = json.dumps(data, ensure_ascii=False)
    # 用 string.Template 風格手動拼，避免 f-string 跟 JS 大括號衝突
    return HTML_TEMPLATE.replace("__DATA__", payload)


HTML_TEMPLATE = r"""<!DOCTYPE html>
<html lang="zh-Hant">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>AI 用量監控 · Claude Code</title>
<style>
  :root{
    --bg:#0b0e14; --bg2:#11161f; --card:#151b26; --card2:#1a2230;
    --line:#222c3a; --txt:#e6edf3; --mut:#8b98a9; --dim:#5b6675;
    --acc:#ff8c42; --acc2:#ffb37a; --grn:#3fb68b; --blu:#5aa9e6;
    --pur:#9b8cff; --pnk:#ff6b9d; --yel:#f5c451;
    --shadow:0 8px 30px rgba(0,0,0,.35);
  }
  *{box-sizing:border-box}
  html,body{margin:0;padding:0}
  body{
    background:radial-gradient(1200px 600px at 80% -10%, #1a2030 0%, var(--bg) 55%) fixed, var(--bg);
    color:var(--txt);
    font-family:-apple-system,"PingFang TC","Noto Sans TC","Helvetica Neue",Arial,sans-serif;
    -webkit-font-smoothing:antialiased; line-height:1.5;
  }
  .wrap{max-width:1180px;margin:0 auto;padding:34px 22px 80px}
  header.top{display:flex;align-items:flex-end;justify-content:space-between;
    flex-wrap:wrap;gap:14px;margin-bottom:26px}
  .brand{display:flex;align-items:center;gap:14px}
  .logo{width:46px;height:46px;border-radius:13px;
    background:linear-gradient(135deg,var(--acc),var(--pnk));
    display:grid;place-items:center;font-size:24px;box-shadow:var(--shadow)}
  h1{font-size:23px;margin:0;letter-spacing:.3px;font-weight:700}
  .sub{color:var(--mut);font-size:13px;margin-top:3px}
  .gen{color:var(--dim);font-size:12px;text-align:right}

  /* KPI 大數字列 */
  .kpis{display:grid;grid-template-columns:repeat(4,1fr);gap:14px;margin-bottom:16px}
  .kpi{background:linear-gradient(160deg,var(--card),var(--bg2));border:1px solid var(--line);
    border-radius:16px;padding:18px 18px 16px;position:relative;overflow:hidden}
  .kpi .lab{color:var(--mut);font-size:12.5px;display:flex;align-items:center;gap:6px}
  .kpi .val{font-size:30px;font-weight:760;margin-top:6px;letter-spacing:.4px;
    font-variant-numeric:tabular-nums}
  .kpi .hint{color:var(--dim);font-size:11.5px;margin-top:5px}
  .kpi .spark{position:absolute;right:0;bottom:0;opacity:.5}
  .kpi.hero{background:linear-gradient(150deg,#2a1c14,#151b26);border-color:#3a2a1e}
  .kpi.hero .val{color:var(--acc2)}

  .row{display:grid;gap:14px;margin-bottom:14px}
  .row.c2{grid-template-columns:1.6fr 1fr}
  .row.c3{grid-template-columns:repeat(3,1fr)}
  .card{background:var(--card);border:1px solid var(--line);border-radius:16px;padding:18px}
  .card h3{margin:0 0 2px;font-size:15px;font-weight:680}
  .card .desc{color:var(--dim);font-size:12px;margin-bottom:14px}
  .card h3 .pill{font-size:11px;color:var(--mut);font-weight:500;margin-left:8px}

  /* 5h block */
  .block-card{background:linear-gradient(155deg,#16212b,#141a24);border-color:#23323e}
  .block-grid{display:grid;grid-template-columns:1fr 1fr;gap:10px 18px;margin-top:6px}
  .blk-item .l{color:var(--mut);font-size:12px}
  .blk-item .v{font-size:20px;font-weight:700;font-variant-numeric:tabular-nums;margin-top:1px}
  .bar-track{height:9px;background:#0e141d;border-radius:6px;overflow:hidden;margin:14px 0 6px}
  .bar-fill{height:100%;border-radius:6px;background:linear-gradient(90deg,var(--grn),var(--blu))}
  /* 本週用量大條 */
  .wk{margin-top:18px;border-top:1px solid var(--line);padding-top:15px}
  .wk-head{display:flex;justify-content:space-between;align-items:baseline;margin-bottom:11px}
  .wk-head .t{font-size:14.5px;font-weight:700}
  .wk-head .r{font-size:12px;color:var(--mut)}
  .wk-mid{display:flex;align-items:center;gap:16px}
  .wk-bar{flex:1;height:20px;background:#0e141d;border-radius:11px;overflow:hidden;position:relative}
  .wk-fill{height:100%;border-radius:11px;transition:width .4s;min-width:8px}
  .wk-pct{font-size:32px;font-weight:780;font-variant-numeric:tabular-nums;line-height:1}
  .wk-foot{display:flex;justify-content:space-between;margin-top:11px;font-size:13.5px;color:var(--mut)}
  .wk-foot b{font-variant-numeric:tabular-nums}
  .gnum{font-size:24px;font-weight:760;margin-top:8px;font-variant-numeric:tabular-nums;letter-spacing:.3px}
  .gnum .now{color:var(--acc2)} .gnum .sep,.gnum .lim{color:var(--mut);font-weight:600;font-size:18px}
  .glab{color:var(--dim);font-size:12px;margin-top:4px} .glab b{color:var(--grn)}
  .status{display:inline-flex;align-items:center;gap:6px;font-size:12px;color:var(--mut)}
  .dot{width:8px;height:8px;border-radius:50%;background:var(--dim)}
  .dot.on{background:var(--grn);box-shadow:0 0 0 4px rgba(63,182,139,.18)}

  /* 圖表通用 */
  svg{display:block;width:100%}
  .legend{display:flex;flex-wrap:wrap;gap:8px 16px;margin-top:12px;font-size:12.5px;color:var(--mut)}
  .legend i{width:10px;height:10px;border-radius:3px;display:inline-block;margin-right:6px;vertical-align:-1px}

  /* 條列排行 */
  .rank{display:flex;flex-direction:column;gap:11px}
  .rank .it{display:grid;grid-template-columns:1fr auto;gap:4px}
  .rank .nm{font-size:13.5px;display:flex;justify-content:space-between}
  .rank .nm b{font-weight:600}
  .rank .nm span{color:var(--mut);font-variant-numeric:tabular-nums}
  .rank .tr{height:7px;background:#0e141d;border-radius:5px;overflow:hidden}
  .rank .fl{height:100%;border-radius:5px}

  /* token 組成 */
  .comp{display:flex;height:30px;border-radius:9px;overflow:hidden;margin:8px 0 4px}
  .comp div{height:100%}
  .comp-leg{display:grid;grid-template-columns:repeat(2,1fr);gap:8px;margin-top:14px}
  .comp-leg .ci{font-size:12.5px;color:var(--mut)}
  .comp-leg .ci b{color:var(--txt);font-variant-numeric:tabular-nums}

  /* heatmap */
  .heat{display:grid;grid-template-columns:auto 1fr;gap:6px;align-items:center}
  .heat .hrow{display:grid;grid-template-columns:repeat(24,1fr);gap:3px}
  .heat .hc{aspect-ratio:1;border-radius:3px;background:#0e141d}
  .heat .wd{font-size:11px;color:var(--dim);width:30px}
  .hint-row{display:flex;justify-content:space-between;color:var(--dim);font-size:11px;margin-top:6px}

  /* other tools */
  .tools{display:grid;grid-template-columns:repeat(3,1fr);gap:12px}
  .tool{background:var(--card2);border:1px solid var(--line);border-radius:13px;padding:15px}
  .tool .tn{font-weight:650;font-size:14px;display:flex;align-items:center;gap:8px}
  .tool .ts{font-size:12px;color:var(--mut);margin-top:8px;line-height:1.55}
  .tag{font-size:10.5px;padding:2px 8px;border-radius:20px;font-weight:600}
  .tag.ok{background:rgba(63,182,139,.16);color:var(--grn)}
  .tag.no{background:rgba(91,102,117,.18);color:var(--dim)}
  .tag.part{background:rgba(245,196,81,.16);color:var(--yel)}

  .foot{color:var(--dim);font-size:11.5px;text-align:center;margin-top:34px;line-height:1.7}
  .tip{cursor:help;border-bottom:1px dashed var(--dim)}
  @media(max-width:820px){
    .kpis{grid-template-columns:repeat(2,1fr)} .row.c2,.row.c3{grid-template-columns:1fr}
    .tools{grid-template-columns:1fr}
  }
</style>
</head>
<body>
<div class="wrap">
  <header class="top">
    <div class="brand">
      <div class="logo">📊</div>
      <div>
        <h1>AI 用量監控面板</h1>
        <div class="sub">Claude Code · 等值 API 成本與 token 解讀</div>
      </div>
    </div>
    <div class="gen">資料更新於 <span id="gen"></span><br><span id="range"></span></div>
  </header>

  <div class="kpis" id="kpis"></div>

  <div class="row c2">
    <div class="card">
      <h3>每日成本趨勢 <span class="pill">近 30 天 · 等值 API（美元）</span></h3>
      <div class="desc">每根 = 當天若用 API 計價的花費。訂閱制下這是你「賺到」的價值。</div>
      <div id="dailyChart"></div>
    </div>
    <div class="card block-card">
      <h3>目前 5 小時用量視窗 <span class="pill">現在用量 / 可用上限</span></h3>
      <div class="desc">基準＝你歷史最高的 5h 用量（自動）。知道方案上限可在 generate.py 設定，佔比就改用實際分母。</div>
      <div id="block"></div>
    </div>
  </div>

  <div class="row c3">
    <div class="card">
      <h3>各模型占比</h3>
      <div class="desc">不同模型計價差很多，Opus 最貴。</div>
      <div id="modelChart"></div>
    </div>
    <div class="card">
      <h3>專案花費排行 <span class="pill">Top 8</span></h3>
      <div class="desc">哪個專案最吃 token。</div>
      <div id="projRank"></div>
    </div>
    <div class="card">
      <h3>Token 組成</h3>
      <div class="desc">快取讀取占比越高，代表越省（只算 0.1× 價）。</div>
      <div id="comp"></div>
    </div>
  </div>

  <div class="row c2">
    <div class="card">
      <h3>活躍時段熱力圖 <span class="pill">星期 × 小時</span></h3>
      <div class="desc">顏色越亮代表你那個時段越常用 Claude Code。</div>
      <div id="heat"></div>
    </div>
    <div class="card">
      <h3>其他 AI 工具 <span class="pill">本機偵測</span></h3>
      <div class="desc">只顯示本機真的找得到資料的工具。</div>
      <div id="tools"></div>
    </div>
  </div>

  <div class="foot" id="foot"></div>
</div>

<script>
const D = __DATA__;
const $ = (id)=>document.getElementById(id);
const fmtN = (n)=> n>=1e9 ? (n/1e9).toFixed(2)+'B' : n>=1e6 ? (n/1e6).toFixed(2)+'M' : n>=1e3 ? (n/1e3).toFixed(1)+'K' : (''+Math.round(n));
const fmtUSD = (n)=> '$'+ (n>=1000 ? n.toLocaleString('en-US',{maximumFractionDigits:0}) : n.toFixed(2));
const esc = (s)=> (''+s).replace(/[&<>]/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;'}[c]));

$('gen').textContent = D.generated_at;
$('range').textContent = D.totals.first_day+' → '+D.totals.last_day+'（'+D.totals.active_days+' 天）';

// ── KPI ──
const T = D.totals;
const kpis = [
  {cls:'hero', lab:'💰 等值 API 總成本', val:fmtUSD(T.cost), hint:'訂閱制下省下的價值 · 平均 '+fmtUSD(T.avg_per_day)+'/天'},
  {lab:'🔢 累計 Token', val:fmtN(T.tokens), hint:T.messages.toLocaleString()+' 則 AI 回應'},
  {lab:'📅 今日花費', val:fmtUSD(D.today.cost), hint:fmtN(D.today.tokens)+' tokens · '+D.today.messages+' 則'},
  {lab:'🗂️ 專案 / Session', val:T.projects+' / '+T.sessions, hint:'本週 '+fmtUSD(D.week.cost)+' · 本月 '+fmtUSD(D.month.cost)},
];
$('kpis').innerHTML = kpis.map(k=>`
  <div class="kpi ${k.cls||''}">
    <div class="lab">${k.lab}</div>
    <div class="val">${k.val}</div>
    <div class="hint">${k.hint}</div>
  </div>`).join('');

// ── 每日趨勢（SVG 長條 + 折線）──
(function(){
  const days = D.by_day.slice(-30);
  const W=720,H=210, pl=40,pr=12,pt=14,pb=26;
  if(!days.length){ $('dailyChart').innerHTML='<div class="desc">尚無資料</div>'; return; }
  const max = Math.max(...days.map(d=>d.cost),0.01);
  const iw=W-pl-pr, ih=H-pt-pb, bw=iw/days.length;
  let bars='', lbls='', grid='';
  for(let g=0;g<=3;g++){ const y=pt+ih*g/3; const v=max*(1-g/3);
    grid+=`<line x1="${pl}" y1="${y}" x2="${W-pr}" y2="${y}" stroke="#1c2632"/>`+
          `<text x="${pl-6}" y="${y+3}" text-anchor="end" fill="#5b6675" font-size="10">$${v.toFixed(v<1?2:0)}</text>`;
  }
  days.forEach((d,i)=>{
    const h=Math.max(d.cost/max*ih,1), x=pl+i*bw, y=pt+ih-h;
    bars+=`<rect x="${x+bw*0.16}" y="${y}" width="${bw*0.68}" height="${h}" rx="2" fill="url(#bg)">
      <title>${d.date}　${fmtUSD(d.cost)}　${fmtN(d.tokens)} tokens　${d.messages} 則</title></rect>`;
    if(i%5===0||i===days.length-1){
      lbls+=`<text x="${x+bw/2}" y="${H-8}" text-anchor="middle" fill="#5b6675" font-size="9.5">${d.date.slice(5)}</text>`;
    }
  });
  $('dailyChart').innerHTML=`<svg viewBox="0 0 ${W} ${H}">
    <defs><linearGradient id="bg" x1="0" y1="0" x2="0" y2="1">
      <stop offset="0" stop-color="#ffb37a"/><stop offset="1" stop-color="#ff8c42"/></linearGradient></defs>
    ${grid}${bars}${lbls}</svg>`;
})();

// ── 5h block 佔比環形儀表 ──
function gaugeColor(p){ return p>=85?'#ff6b6b' : p>=60?'#f5c451' : '#3fb68b'; }
function ringSVG(pct, sizeR){
  const p=Math.min(pct,100), r=sizeR, c=2*Math.PI*r, off=c*(1-p/100);
  const col=gaugeColor(pct), cx=r+11, cy=r+11, d=2*(r+11);
  return `<svg viewBox="0 0 ${d} ${d}" style="width:128px;height:128px;flex:none">
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="#0e141d" stroke-width="13"/>
    <circle cx="${cx}" cy="${cy}" r="${r}" fill="none" stroke="${col}" stroke-width="13"
      stroke-linecap="round" stroke-dasharray="${c}" stroke-dashoffset="${off}"
      transform="rotate(-90 ${cx} ${cy})"/>
    <text x="${cx}" y="${cy-2}" text-anchor="middle" fill="#e6edf3" font-size="26" font-weight="760">${pct.toFixed(0)}%</text>
    <text x="${cx}" y="${cy+16}" text-anchor="middle" fill="#8b98a9" font-size="10.5">已用佔比</text></svg>`;
}
(function(){
  const b=D.block, w=D.week_block, el=$('block');
  if(!b.active && !b.used_cost){
    el.innerHTML='<div class="status"><span class="dot"></span>目前沒有進行中的視窗</div>'; return; }
  const srcTxt = D.plan_name ? (D.plan_name+' 上限') : (b.limit_src==='manual' ? '方案上限' : '歷史最高 5h');
  const wkSrc = D.plan_name ? (D.plan_name+' 週上限') : '上限';
  el.innerHTML=`
    <div style="display:flex;gap:16px;align-items:center">
      ${ringSVG(b.pct, 50)}
      <div style="flex:1;min-width:0">
        <div class="status"><span class="dot ${b.active?'on':''}"></span>${b.active?'進行中':'已結束'}　${b.start} – ${b.end}　·　${b.active?('約 '+b.reset_in+' 小時後重置'):'視窗已滿'}</div>
        <div class="gnum"><span class="now">${fmtUSD(b.used_cost)}</span><span class="sep"> / </span><span class="lim">${fmtUSD(b.limit)}</span></div>
        <div class="glab">現在用量 / ${srcTxt}基準　·　還能用 <b>${fmtUSD(b.remain)}</b></div>
      </div>
    </div>
    <div class="block-grid" style="margin-top:14px">
      <div class="blk-item"><div class="l">消耗速度</div><div class="v">${fmtUSD(b.burn_per_hour)}<span style="font-size:12px;color:var(--mut)">/時</span></div></div>
      <div class="blk-item"><div class="l">本視窗 Token</div><div class="v">${fmtN(b.tokens)}</div></div>
      <div class="blk-item"><div class="l">回應數</div><div class="v">${b.messages}</div></div>
      <div class="blk-item"><div class="l">已過時間</div><div class="v">${b.elapsed_hours}<span style="font-size:12px;color:var(--mut)"> 時</span></div></div>
    </div>
    <div class="wk">
      <div class="wk-head">
        <span class="t">📆 本週用量</span>
        <span class="r">約 ${w.reset_days} 天後重置</span>
      </div>
      <div class="wk-mid">
        <div class="wk-bar"><div class="wk-fill" style="width:${Math.min(w.pct,100)}%;background:linear-gradient(90deg,${gaugeColor(w.pct)},${gaugeColor(w.pct)}cc)"></div></div>
        <div class="wk-pct" style="color:${gaugeColor(w.pct)}">${w.pct.toFixed(0)}%</div>
      </div>
      <div class="wk-foot">
        <span><b style="color:var(--acc2)">${fmtUSD(w.used_cost)}</b> / ${fmtUSD(w.limit)} ${wkSrc}</span>
        <span>還能用 <b style="color:var(--grn)">${fmtUSD(w.remain)}</b></span>
      </div>
    </div>`;
})();

// ── 各模型 donut ──
(function(){
  const m=D.by_model; const total=m.reduce((s,x)=>s+x.cost,0)||1;
  const colors=['#ff8c42','#5aa9e6','#9b8cff','#3fb68b','#ff6b9d','#f5c451'];
  const cx=78,cy=78,r=58,sw=22; let ang=-Math.PI/2, segs='';
  m.forEach((x,i)=>{
    const frac=x.cost/total, a2=ang+frac*Math.PI*2;
    const x1=cx+r*Math.cos(ang), y1=cy+r*Math.sin(ang);
    const x2=cx+r*Math.cos(a2), y2=cy+r*Math.sin(a2);
    const large=frac>0.5?1:0;
    segs+=`<path d="M ${x1} ${y1} A ${r} ${r} 0 ${large} 1 ${x2} ${y2}" stroke="${colors[i%6]}" stroke-width="${sw}" fill="none" stroke-linecap="butt"><title>${x.model}　${fmtUSD(x.cost)}（${(frac*100).toFixed(1)}%）</title></path>`;
    ang=a2;
  });
  const leg=m.map((x,i)=>`<span><i style="background:${colors[i%6]}"></i>${esc(x.model)} ${(x.cost/total*100).toFixed(0)}%</span>`).join('');
  $('modelChart').innerHTML=`
    <div style="display:flex;gap:14px;align-items:center">
      <svg viewBox="0 0 156 156" style="width:150px;flex:none">${segs}
        <text x="78" y="74" text-anchor="middle" fill="#e6edf3" font-size="20" font-weight="700">${fmtUSD(total)}</text>
        <text x="78" y="92" text-anchor="middle" fill="#8b98a9" font-size="10">總等值成本</text></svg>
      <div class="legend" style="flex-direction:column;gap:8px">${leg}</div>
    </div>`;
})();

// ── 專案排行 ──
(function(){
  const p=D.by_project.slice(0,8); const max=Math.max(...p.map(x=>x.cost),0.01);
  const colors=['#ff8c42','#5aa9e6','#9b8cff','#3fb68b','#ff6b9d','#f5c451','#ffb37a','#6fd3b8'];
  $('projRank').innerHTML=`<div class="rank">`+p.map((x,i)=>`
    <div class="it"><div class="nm"><b>${esc(x.project)}</b><span>${fmtUSD(x.cost)} · ${fmtN(x.tokens)}</span></div>
    <div class="tr"><div class="fl" style="width:${Math.max(x.cost/max*100,2)}%;background:${colors[i%8]}"></div></div></div>`).join('')+`</div>`;
})();

// ── token 組成 ──
(function(){
  const t=D.totals; const parts=[
    {k:'快取讀取',v:t.cache_read,c:'#3fb68b',d:'0.1× 計價，最省'},
    {k:'快取寫入',v:t.cache_creation,c:'#5aa9e6',d:'1.25× 計價'},
    {k:'輸出',v:t.output,c:'#ff6b9d',d:'最貴，5× 輸入價'},
    {k:'輸入',v:t.input,c:'#f5c451',d:'一般輸入'},
  ];
  const sum=parts.reduce((s,x)=>s+x.v,0)||1;
  $('comp').innerHTML=`
    <div class="comp">`+parts.map(p=>`<div style="width:${p.v/sum*100}%;background:${p.c}" title="${p.k} ${fmtN(p.v)}"></div>`).join('')+`</div>
    <div class="comp-leg">`+parts.map(p=>`<div class="ci"><i class="legend" style="display:inline-block"></i>
      <span style="display:inline-block;width:9px;height:9px;border-radius:3px;background:${p.c};margin-right:6px"></span>
      ${p.k} <b>${fmtN(p.v)}</b> · ${(p.v/sum*100).toFixed(0)}%<br><span style="color:var(--dim);font-size:11px">${p.d}</span></div>`).join('')+`</div>`;
})();

// ── heatmap ──
(function(){
  const h=D.heat; const wd=['一','二','三','四','五','六','日'];
  let max=0; h.forEach(r=>r.forEach(v=>{if(v>max)max=v}));
  max=max||1;
  let rows='';
  for(let d=0;d<7;d++){
    let cells='';
    for(let hr=0;hr<24;hr++){
      const v=h[d][hr], a=v/max;
      const col = v===0?'#0e141d':`rgba(255,140,66,${0.12+a*0.88})`;
      cells+=`<div class="hc" style="background:${col}" title="週${wd[d]} ${hr}:00　${Math.round(v)} 則"></div>`;
    }
    rows+=`<div class="wd">週${wd[d]}</div><div class="hrow">${cells}</div>`;
  }
  $('heat').innerHTML=`<div class="heat">${rows}</div>
    <div class="hint-row"><span>0 時</span><span>6 時</span><span>12 時</span><span>18 時</span><span>23 時</span></div>`;
})();

// ── other tools ──
(function(){
  const o=D.other_tools; const cards=[];
  cards.push({n:'🤖 Claude Code',tag:'<span class="tag ok">完整資料</span>',
    s:`${T.messages.toLocaleString()} 則回應 · ${fmtN(T.tokens)} tokens · 等值 ${fmtUSD(T.cost)}。本面板主要資料來源。`});
  if(o.gemini && o.gemini.installed){
    cards.push({n:'✨ Gemini CLI',tag:'<span class="tag part">部分</span>',
      s:`偵測到 ${o.gemini.sessions} 個歷史 session。${o.gemini.note}。`});
  } else {
    cards.push({n:'✨ Gemini CLI',tag:'<span class="tag no">未安裝</span>',s:'本機找不到 ~/.gemini 資料。'});
  }
  cards.push({n:'⚡ Codex / ChatGPT',tag:'<span class="tag no">無本機資料</span>',
    s:o.codex.installed?'偵測到 ~/.codex，但未保存可計算的 token 用量。':'未安裝 Codex CLI；ChatGPT/Gemini 網頁版用量需接各家 API key 才能抓取。'});
  $('tools').innerHTML=`<div class="tools">`+cards.map(c=>`
    <div class="tool"><div class="tn">${c.n} ${c.tag}</div><div class="ts">${c.s}</div></div>`).join('')+`</div>`;
})();

$('foot').innerHTML = `成本為「等值 API 計價」估算（Opus $5/$25、Sonnet $3/$15、Haiku $1/$5 每百萬 token；快取寫入 1.25×、讀取 0.1×）。<br>
訂閱制（Max/Pro）實際不照此收費，此數字代表你從訂閱「賺到」的等值價值。<b>想看官方精準佔比：Claude 設定 → Usage。</b><br>
資料來源：~/.claude/projects · 重新整理請再跑一次 generate.py。`;
</script>
</body>
</html>
"""


def demo_data():
    """合成示範資料（給開源 README 截圖用，不含任何個人資料）。"""
    import math
    days = []
    base = datetime(2026, 6, 1)
    for i in range(30):
        d = base + timedelta(days=i)
        c = round(40 + 70 * abs(math.sin(i / 3.0)) + (i % 5) * 6, 2)
        days.append({"date": d.strftime("%Y-%m-%d"), "cost": c,
                     "tokens": int(c * 1.3e6), "messages": int(c * 6), "output": int(c * 3500)})
    total_cost = round(sum(x["cost"] for x in days) + 1800, 2)
    heat = [[max(0, int(8 * abs(math.sin((h - 9) / 4.0)) * (1 if 1 <= h <= 23 else 0)
                        * (0.6 if wd >= 5 else 1))) for h in range(24)] for wd in range(7)]
    return {
        "generated_at": "2026-06-30 22:30",
        "totals": {"cost": total_cost, "input": 1_200_000, "output": 22_000_000,
                   "cache_creation": 240_000_000, "cache_read": 6_900_000_000,
                   "tokens": 7_160_000_000, "messages": 18000, "sessions": 56,
                   "projects": 5, "active_days": 30, "first_day": "2026-06-01",
                   "last_day": "2026-06-30", "avg_per_day": round(total_cost / 30, 2)},
        "today": {"cost": 48.0, "tokens": 62_000_000, "messages": 360},
        "week": {"cost": 312.0, "tokens": 410_000_000, "messages": 2400},
        "month": {"cost": total_cost, "tokens": 7_160_000_000, "messages": 18000},
        "block": {"active": True, "used_cost": 21.4, "tokens": 28_000_000, "messages": 96,
                  "limit": 120.0, "limit_src": "auto", "remain": 98.6, "pct": 17.8,
                  "start": "21:00", "end": "02:00", "reset_in": 3.6,
                  "elapsed_hours": 1.4, "burn_per_hour": 15.3},
        "week_block": {"used_cost": 312.0, "tokens": 410_000_000, "limit": 820.0,
                       "limit_src": "auto", "pct": 38.0, "remain": 508.0},
        "by_day": days,
        "by_model": [{"model": "Opus 4.8", "cost": round(total_cost * 0.62, 2), "tokens": 4_400_000_000, "messages": 11000},
                     {"model": "Opus 4.7", "cost": round(total_cost * 0.30, 2), "tokens": 2_100_000_000, "messages": 5200},
                     {"model": "Sonnet 4.6", "cost": round(total_cost * 0.06, 2), "tokens": 520_000_000, "messages": 1400},
                     {"model": "Haiku 4.5", "cost": round(total_cost * 0.02, 2), "tokens": 140_000_000, "messages": 400}],
        "by_project": [{"project": "my-web-app", "cost": round(total_cost * 0.5, 2), "tokens": 3_500_000_000, "messages": 9000},
                       {"project": "api-service", "cost": round(total_cost * 0.28, 2), "tokens": 1_900_000_000, "messages": 5000},
                       {"project": "data-pipeline", "cost": round(total_cost * 0.14, 2), "tokens": 980_000_000, "messages": 2600},
                       {"project": "docs-site", "cost": round(total_cost * 0.06, 2), "tokens": 410_000_000, "messages": 1000},
                       {"project": "scripts", "cost": round(total_cost * 0.02, 2), "tokens": 120_000_000, "messages": 400}],
        "heat": heat,
        "other_tools": {"gemini": {"installed": True, "sessions": 7,
                                   "note": "Gemini CLI 有歷史紀錄，但未保存 token 用量，無法計算成本"},
                        "codex": {"installed": False}},
    }


def _fmt_tok(n):
    return f"{n/1e9:.2f}B" if n >= 1e9 else f"{n/1e6:.1f}M" if n >= 1e6 else f"{n/1e3:.0f}K"


def print_summary(d):
    """終端機文字摘要（不開瀏覽器）。"""
    b, w, t = d["block"], d["week_block"], d["totals"]
    plan = f"（{d['plan_name']}）" if d.get("plan_name") else ""
    print()
    print(f"  📊 Claude Code 用量摘要{plan}   {d['generated_at']}")
    print("  " + "─" * 46)
    print(f"  5 小時視窗 : {b['pct']:>4.0f}%   {fmt_usd(b['used_cost'])} / {fmt_usd(b['limit'])}"
          f"   約 {b['reset_in']} 小時後重置")
    print(f"  本週用量   : {w['pct']:>4.0f}%   {fmt_usd(w['used_cost'])} / {fmt_usd(w['limit'])}"
          f"   約 {w['reset_days']} 天後重置")
    print(f"  今日花費   : {fmt_usd(d['today']['cost'])}   ·  累計等值 {fmt_usd(t['cost'])}"
          f"  ·  {_fmt_tok(t['tokens'])} tokens")
    print()


def oneline(d):
    """單行（給 Claude Code statusline 或 menu bar 用）。"""
    b, w = d["block"], d["week_block"]
    return f"⛁ 5h {b['pct']:.0f}% · 週 {w['pct']:.0f}% · 今日 {fmt_usd(d['today']['cost'])}"


def do_notify(d, threshold):
    """用量超過門檻就跳桌面通知（mac: osascript / Linux: notify-send）。"""
    import subprocess, platform
    b, w = d["block"], d["week_block"]
    alerts = []
    if b["pct"] >= threshold:
        alerts.append(f"5 小時視窗已用 {b['pct']:.0f}%")
    if w["pct"] >= threshold:
        alerts.append(f"本週已用 {w['pct']:.0f}%")
    if not alerts:
        print(f"用量正常（5h {b['pct']:.0f}% / 週 {w['pct']:.0f}%），未達 {threshold}% 門檻")
        return
    msg, title = " · ".join(alerts), "⚠️ Claude 用量提醒"
    sysname = platform.system()
    try:
        if sysname == "Darwin":
            subprocess.run(["osascript", "-e",
                            f'display notification "{msg}" with title "{title}" sound name "Ping"'])
        elif sysname == "Linux":
            subprocess.run(["notify-send", title, msg])
        else:
            print(f"{title}：{msg}")
    except Exception as e:
        print(f"（通知失敗：{e}）{title}：{msg}")
    print(f"已提醒：{msg}")


def run_calibrate(data):
    """用『官方 設定 → Usage』目前顯示的 % 反推分母，存進 config.json。"""
    b, w = data["block"], data["week_block"]
    print("\n用『Claude 設定 → Usage』目前顯示的 % 來校準（最貼近官方的做法）。")
    print(f"本工具現在量到：5 小時用量 {fmt_usd(b['used_cost'])}、本週用量 {fmt_usd(w['used_cost'])}\n")

    def ask(label, used):
        if used <= 0:
            print(f"（{label}目前用量為 0，跳過）")
            return None
        s = input(f"官方『{label}』現在顯示百分之幾？(只輸數字，Enter 跳過) ").strip()
        if not s:
            return None
        try:
            p = float(s)
        except ValueError:
            print("  輸入無效，跳過")
            return None
        return round(used / (p / 100), 2) if p > 0 else None

    lim5 = ask("5 小時 / current session", b["used_cost"])
    limw = ask("本週 / weekly all models", w["used_cost"])
    plan = input("方案名稱（例 Max (5x)，可留空）：").strip()

    cfg = {}
    if os.path.exists(_CFG):
        try:
            cfg = json.load(open(_CFG, encoding="utf-8"))
        except Exception:
            pass
    if lim5:
        cfg["limit_5h_usd"] = lim5
    if limw:
        cfg["limit_weekly_usd"] = limw
    if plan:
        cfg["plan"] = plan
    with open(_CFG, "w", encoding="utf-8") as fh:
        json.dump(cfg, fh, ensure_ascii=False, indent=2)
    print(f"\n✓ 已存 config.json：{cfg}")
    print("重新產生面板…")
    _load_config()
    with open(OUT_HTML, "w", encoding="utf-8") as fh:
        fh.write(render_html(build_data()))
    webbrowser.open(f"file://{OUT_HTML}")


def main():
    _load_config()
    if "--demo" in sys.argv:
        print("產生示範資料面板（demo）…")
        data = demo_data()
        html_out = render_html(data)
        with open(OUT_HTML, "w", encoding="utf-8") as f:
            f.write(html_out)
        print(f"✓ demo 完成：{OUT_HTML}")
        if "--no-open" not in sys.argv:
            webbrowser.open(f"file://{OUT_HTML}")  # 跨平台開啟（mac/Win/Linux）
        return
    if not os.path.isdir(PROJECTS_DIR):
        print(f"找不到 {PROJECTS_DIR}，這台機器可能沒用過 Claude Code。")
        sys.exit(1)
    quiet = any(f in sys.argv for f in ("--oneline", "--summary", "--notify", "--calibrate"))
    if not quiet:
        print("解析 Claude Code 用量中…")
    data = build_data()
    if "--calibrate" in sys.argv:
        run_calibrate(data); return
    if "--oneline" in sys.argv:
        print(oneline(data)); return
    if "--summary" in sys.argv:
        print_summary(data); return
    if "--notify" in sys.argv:
        thr = NOTIFY_THRESHOLD
        i = sys.argv.index("--notify")
        if i + 1 < len(sys.argv):  # 可選自訂門檻：--notify 50
            try:
                thr = float(sys.argv[i + 1])
            except ValueError:
                pass
        do_notify(data, thr); return
    html_out = render_html(data)
    with open(OUT_HTML, "w", encoding="utf-8") as f:
        f.write(html_out)
    t = data["totals"]
    print(f"✓ 完成：{OUT_HTML}")
    print(f"  等值成本 {t['cost']:,} 美元 · {t['tokens']:,} tokens · "
          f"{t['messages']:,} 則 · {t['active_days']} 天 · {t['projects']} 專案")
    if "--no-open" not in sys.argv:
        webbrowser.open(f"file://{OUT_HTML}")  # 跨平台開啟（mac/Win/Linux）


if __name__ == "__main__":
    main()
