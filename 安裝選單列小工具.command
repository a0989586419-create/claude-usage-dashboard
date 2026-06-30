#!/bin/bash
# 一鍵把「Claude 用量」裝到 macOS 選單列（SwiftBar / xbar）。
# 雙擊我即可。會自動填好 repo 路徑、放進外掛資料夾、重新整理。
set -e
REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
echo "Repo: $REPO_DIR"

# 1) 確認有 SwiftBar 或 xbar
have_app() { [ -d "/Applications/SwiftBar.app" ] || [ -d "/Applications/xbar.app" ]; }
if ! have_app; then
  if command -v brew >/dev/null 2>&1; then
    echo "未偵測到 SwiftBar，使用 Homebrew 安裝中…"
    brew install --cask swiftbar
  else
    echo "請先安裝 SwiftBar（https://swiftbar.app）或 xbar（https://xbarapp.com）後再執行。"
    read -p "按 Enter 結束"; exit 1
  fi
fi

# 2) 找外掛資料夾（SwiftBar 優先；沒設就建一個並指定）
PLUGINDIR="$(defaults read com.ambitionsoftware.SwiftBar PluginDirectory 2>/dev/null || true)"
if [ -z "$PLUGINDIR" ]; then
  PLUGINDIR="$(defaults read com.xbarapp.app pluginsDirectory 2>/dev/null || true)"
fi
if [ -z "$PLUGINDIR" ]; then
  PLUGINDIR="$HOME/Library/Application Support/SwiftBar/Plugins"
  mkdir -p "$PLUGINDIR"
  defaults write com.ambitionsoftware.SwiftBar PluginDirectory "$PLUGINDIR"
  echo "已設定 SwiftBar 外掛資料夾：$PLUGINDIR"
fi
mkdir -p "$PLUGINDIR"

# 3) 把外掛複製進去，填入這台機器的 repo 路徑
DEST="$PLUGINDIR/claude-usage.5m.sh"
sed "s|__REPO_DIR__|$REPO_DIR|g" "$REPO_DIR/menubar/claude-usage.5m.sh" > "$DEST"
chmod +x "$DEST"
echo "✓ 已安裝外掛：$DEST"

# 4) 啟動 / 重新整理 SwiftBar
open -a SwiftBar 2>/dev/null || true
sleep 1
open "swiftbar://refreshall" 2>/dev/null || true
echo ""
echo "完成！選單列應該會出現「⛁ 5h% · 週%」。"
echo "第一次若沒看到：開啟 SwiftBar，選外掛資料夾為上面那個路徑即可。"
read -p "按 Enter 結束"
