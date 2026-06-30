#!/bin/bash
# 雙擊啟用「自動盯盤通知」：每 15 分檢查一次，用量 ≥80% 才跳桌面通知。
# 用 macOS LaunchAgent（在你登入的桌面 session 跑，通知才看得到）。
cd "$(dirname "$0")" || exit 1
REPO="$(pwd)"
PY="$(command -v python3)"
[ -z "$PY" ] && { echo "找不到 python3，請先安裝。"; read -n1; exit 1; }

THRESHOLD="${1:-80}"   # 想改門檻：在終端機跑  ./安裝自動通知.command 70
PLIST="$HOME/Library/LaunchAgents/com.cloudmonster.claude-usage-notify.plist"

cat > "$PLIST" <<EOF
<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
  <key>Label</key><string>com.cloudmonster.claude-usage-notify</string>
  <key>ProgramArguments</key>
  <array>
    <string>$PY</string>
    <string>$REPO/generate.py</string>
    <string>--notify</string>
    <string>$THRESHOLD</string>
  </array>
  <key>StartInterval</key><integer>900</integer>
  <key>RunAtLoad</key><true/>
  <key>StandardOutPath</key><string>/tmp/claude-usage-notify.log</string>
  <key>StandardErrorPath</key><string>/tmp/claude-usage-notify.log</string>
</dict>
</plist>
EOF

launchctl unload "$PLIST" 2>/dev/null
launchctl load -w "$PLIST" && echo "✓ 已啟用：每 15 分自動盯盤，用量 ≥${THRESHOLD}% 才通知。"
echo ""
echo "想關閉就跑：  launchctl unload \"$PLIST\""
echo "（若沒收到通知：系統設定 → 通知 → 允許「指令碼編輯程式 / osascript」）"
echo ""
read -n1 -p "按任意鍵關閉視窗…"
