# AI 用量監控面板（專屬版）

監控 **Claude Code** 的 token 用量與等值 API 成本，並偵測本機其他 AI 工具。
產出一個自帶美感、離線可看的 HTML 儀表板。

## 怎麼用

- **最簡單**：雙擊 `更新並開啟.command` → 自動重算最新用量並開啟面板
- **或指令**：
  ```bash
  cd ~/Desktop/ai-usage-monitor
  python3 generate.py          # 重新統計 + 開啟
  python3 generate.py --no-open # 只產生 index.html
  ```

每次跑 `generate.py` 會重新掃 `~/.claude/projects`，把 `index.html` 更新到最新。

## 面板看得到什麼

| 區塊 | 解讀 |
|---|---|
| 等值 API 總成本 | 你的用量「若照 API 計價」要多少錢 → 訂閱制下＝賺到的價值 |
| 累計 Token / 今日花費 | 整體規模與當天消耗 |
| 每日成本趨勢 | 近 30 天每天花多少（長條） |
| 目前 5 小時視窗 | Claude Code Max 以 5h 滾動視窗計量，看當前消耗速度 |
| 各模型占比 | Opus／Sonnet／Haiku 各吃多少（Opus 最貴） |
| 專案花費排行 | 哪個專案最吃 token |
| Token 組成 | 快取讀取占比越高＝越省（只算 0.1× 價） |
| 活躍時段熱力圖 | 星期 × 小時，看你什麼時段最常用 |
| 其他 AI 工具 | 本機偵測 Gemini CLI / Codex（有資料才顯示） |

## 計價依據（每百萬 token，美元）

| 模型 | 輸入 | 輸出 | 快取寫入 | 快取讀取 |
|---|---|---|---|---|
| Opus | $5 | $25 | $6.25 | $0.50 |
| Sonnet | $3 | $15 | $3.75 | $0.30 |
| Haiku | $1 | $5 | $1.25 | $0.10 |

> 訂閱制（Max/Pro）實際不照此收費；面板上的成本是「等值估算」，代表訂閱替你省下的價值。

## 檔案

- `generate.py` — 解析 + 計價 + 產生 HTML（核心）
- `index.html` — 產生出來的面板（離線可開）
- `serve.py` — 預覽用多執行緒伺服器（可不理）
- `更新並開啟.command` — 雙擊更新

## 其他 AI 工具的限制

- **Gemini CLI**：有歷史紀錄但未存 token 數，只能顯示 session 數
- **Codex / ChatGPT / Gemini 網頁版**：本機無用量資料，要抓得接各家 API key

## 進階：每天自動更新

想每天自動重算，可加 crontab（早上 9 點）：
```bash
crontab -e
# 加一行：
0 9 * * * /usr/bin/python3 ~/Desktop/ai-usage-monitor/generate.py --no-open
```
