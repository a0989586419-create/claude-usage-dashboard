#!/bin/bash
# <xbar.title>Claude Code Usage</xbar.title>
# <xbar.version>v1.0</xbar.version>
# <xbar.author>phchen</xbar.author>
# <xbar.desc>Claude Code 5-hour / weekly usage % in the menu bar. Auto-refreshes every 5 min.</xbar.desc>
# <xbar.dependencies>python3</xbar.dependencies>
# <swiftbar.refreshOnOpen>true</swiftbar.refreshOnOpen>
#
# 檔名的 ".5m." = 每 5 分鐘自動更新。改間隔就改檔名（.1m. / .10m. …）。
# REPO_DIR 由 install-menubar 安裝時自動填入；手動安裝請改成你的 repo 路徑。

REPO_DIR="__REPO_DIR__"
PY="$(command -v python3 || echo /usr/bin/python3)"
exec "$PY" "$REPO_DIR/generate.py" --swiftbar
