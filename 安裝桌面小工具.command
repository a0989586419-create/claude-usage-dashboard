#!/bin/bash
# 一鍵把「Claude 用量」卡片貼到 macOS 桌面（用 Übersicht）。雙擊我即可。
set -e
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
PY="$(command -v python3 || echo /usr/bin/python3)"
echo "Repo: $REPO_DIR"

# 1) 確認有 Übersicht
if [ ! -d "/Applications/Übersicht.app" ] && [ ! -d "/Applications/Ubersicht.app" ]; then
  if command -v brew >/dev/null 2>&1; then
    echo "未偵測到 Übersicht，使用 Homebrew 安裝中…"
    brew install --cask ubersicht
  else
    echo "請先安裝 Übersicht：https://tracesof.net/uebersicht/ 後再執行。"
    read -p "按 Enter 結束"; exit 1
  fi
fi

# 2) 找 widgets 資料夾（含 umlaut 的版本優先）
WBASE="$HOME/Library/Application Support/Übersicht/widgets"
[ -d "$HOME/Library/Application Support/Ubersicht/widgets" ] && WBASE="$HOME/Library/Application Support/Ubersicht/widgets"
WDIR="$WBASE/claude-usage.widget"
mkdir -p "$WDIR"

# 3) 填入這台機器的 python / repo 路徑
sed -e "s|__PY__|$PY|g" -e "s|__REPO__|$REPO_DIR|g" \
    "$REPO_DIR/ubersicht/claude-usage.widget/index.jsx" > "$WDIR/index.jsx"
echo "✓ 已安裝 widget：$WDIR/index.jsx"

# 4) 啟動 Übersicht（會自動載入並貼到桌面右上）
open -a "Übersicht" 2>/dev/null || open -a "Ubersicht" 2>/dev/null || true
echo ""
echo "完成！桌面右上角會出現用量卡片（每 5 分鐘自動更新）。"
echo "想搬位置：點 Übersicht 選單列圖示 → 可拖曳 widget。"
read -p "按 Enter 結束"
