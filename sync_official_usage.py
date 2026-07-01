#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
同步 Claude Code「官方真實用量」到本機快取。

流程：讀 Keychain 的 OAuth token → 過期才刷新（並寫回 Keychain）→ 打
官方 /api/oauth/usage → 把結果寫進 ~/.claude-usage-official.json。

面板（generate.py）只讀那個快取檔，不碰 token。這支才是唯一會碰憑證的地方。

安全設計：
  • 刷新前 Keychain 內容不變；失敗（含 429 限流）不寫回、保留舊快取
  • 尊重限流：預設 180 秒內不重打（--force 可強制）
  • 只印用量%，永不印出 token

用法：
  python3 sync_official_usage.py           # 需要時才刷新+抓取
  python3 sync_official_usage.py --force    # 忽略快取，強制抓
"""
import json, os, sys, time, subprocess, getpass, urllib.request, urllib.error, re

HOME = os.path.expanduser("~")
CACHE = os.path.join(HOME, ".claude-usage-official.json")
SVC = "Claude Code-credentials"
ACCT = os.environ.get("CLAUDE_KEYCHAIN_ACCT", getpass.getuser())
CLIENT_ID = "9d1c250a-e61b-44d9-88ed-5944d1962f5e"
TOKEN_URL = "https://console.anthropic.com/v1/oauth/token"
USAGE_URL = "https://api.anthropic.com/api/oauth/usage"
MIN_INTERVAL = 175   # 秒；避免打太兇被限流


# User-Agent 版本：寫死即可（端點只在意「claude-code/x.y.z」這個格式，非精確版本）。
# 不呼叫 claude 指令 → LaunchAgent 精簡 PATH 也不會崩。要更新版本改這行就好。
CC_VERSION = "2.1.177"


def sh(a):
    try:
        return subprocess.run(a, capture_output=True, text=True, timeout=15)
    except Exception:
        class _R:  # 找不到執行檔時回傳空結果，不讓整支崩掉
            returncode, stdout, stderr = 1, "", ""
        return _R()


def ua():
    return f"claude-code/{CC_VERSION}"


def read_cred():
    r = sh(["security", "find-generic-password", "-s", SVC, "-a", ACCT, "-w"])
    if r.returncode != 0 or not r.stdout.strip():
        return None, None
    raw = json.loads(r.stdout.strip())
    return raw, raw.get("claudeAiOauth", raw)


def write_cred(raw_shape, o):
    payload = json.dumps({"claudeAiOauth": o}) if "claudeAiOauth" in raw_shape else json.dumps(o)
    return sh(["security", "add-generic-password", "-U", "-s", SVC, "-a", ACCT, "-w", payload]).returncode == 0


def http_json(url, method="GET", data=None, headers=None):
    req = urllib.request.Request(url, data=data, method=method, headers=headers or {})
    try:
        return json.loads(urllib.request.urlopen(req, timeout=20).read()), None
    except urllib.error.HTTPError as e:
        return None, (e.code, e.read().decode()[:160])
    except Exception as e:
        return None, (0, str(e)[:160])


def refresh(o, UA):
    body = json.dumps({"grant_type": "refresh_token", "refresh_token": o["refreshToken"],
                       "client_id": CLIENT_ID}).encode()
    return http_json(TOKEN_URL, "POST", body,
                     {"Content-Type": "application/json", "User-Agent": UA})


def main():
    force = "--force" in sys.argv
    # 尊重最小間隔
    if not force and os.path.exists(CACHE):
        try:
            c = json.load(open(CACHE))
            if time.time() - c.get("fetched_at", 0) < MIN_INTERVAL:
                print("skip: 快取仍新（<%ds）" % MIN_INTERVAL); return
        except Exception:
            pass

    raw, o = read_cred()
    if not o:
        print("no-cred: Keychain 找不到 Claude Code 憑證（沒登入或帳號名不同）"); return

    UA = ua()
    # token 快過期（<2 分）才刷新
    need = o.get("expiresAt", 0) / 1000 - time.time() < 120
    if need:
        tok, err = refresh(o, UA)
        if err:
            print("refresh-fail", *err, "→ 保留舊快取，稍後再試"); return
        o = dict(o)
        o["accessToken"] = tok["access_token"]
        o["refreshToken"] = tok.get("refresh_token", o["refreshToken"])
        o["expiresAt"] = int(time.time() * 1000) + int(tok.get("expires_in", 3600)) * 1000
        if write_cred(raw, o):
            print("refreshed+writeback OK，新到期",
                  time.strftime("%m-%d %H:%M", time.localtime(o["expiresAt"] / 1000)))
        else:
            print("warn: 寫回 Keychain 失敗（仍用新 token 抓一次）")

    usage, err = http_json(USAGE_URL, headers={
        "Authorization": f"Bearer {o['accessToken']}", "anthropic-beta": "oauth-2025-04-20",
        "User-Agent": UA, "Content-Type": "application/json"})
    if err:
        print("usage-fail", *err); return

    out = {"fetched_at": int(time.time()), **usage}
    json.dump(out, open(CACHE, "w"), ensure_ascii=False)
    os.chmod(CACHE, 0o600)
    fh = (usage.get("five_hour") or {}).get("utilization")
    sd = (usage.get("seven_day") or {}).get("utilization")
    print(f"OK 官方用量：5h {fh}% · 週 {sd}%  → 已寫入 {CACHE}")


if __name__ == "__main__":
    main()
