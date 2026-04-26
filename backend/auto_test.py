#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""全自動測試小紅書提取—寫 log 到檔案"""
import sys, subprocess, json, time, os, io

# UTF-8 stdout
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

PYTHON = r'C:\Users\alan\AppData\Local\Programs\Python\Python313\python.exe'
BACKEND = r'D:\我的知識庫\anytocopy-clone\backend'
LOG_FILE = r'D:\我的知識庫\anytocopy-clone\backend\auto_test.log'

log_lines = []
def log(msg):
    log_lines.append(msg)
    print(msg)

def run(cmd, timeout=10):
    return subprocess.run(
        f'cmd /c {cmd}',
        shell=True, capture_output=True, text=True, timeout=timeout,
        cwd=BACKEND
    )

# === Step 1: Kill existing Python processes ===
log("[1] 清除舊 Flask 進程")
r = run('taskkill /F /IM python.exe 2>nul')
log(f"  taskkill exit={r.returncode}")
time.sleep(2)

# === Step 2: Start Flask ===
log("[2] 啟動 Flask (port 5000)")
r = run(f'start /B "" {PYTHON} app.py')
time.sleep(3)

# === Step 3: Check Flask is alive ===
log("[3] 檢查 Flask 是否就緒")
for i in range(5):
    try:
        import urllib.request
        resp = urllib.request.urlopen('http://127.0.0.1:5000/api/health', timeout=3)
        data = json.loads(resp.read())
        log(f"  ✅ Flask running: {data.get('status')}")
        break
    except Exception as e:
        log(f"  ⏳ waiting... ({e})")
        time.sleep(2)
else:
    log("  ❌ Flask did not start")
    with open(LOG_FILE, 'w', encoding='utf-8') as f:
        f.write('\n'.join(log_lines))
    sys.exit(1)

# === Step 4: Test Xiaohongshu extraction ===
log("[4] 測試小紅書提取")
test_url = "https://www.xiaohongshu.com/explore/69ed5a8a0000000036018e7e?xsec_token=ABSuBlYabW8IF4VOAsAh3F2ERWs6"

import urllib.request
req = urllib.request.Request(
    'http://127.0.0.1:5000/api/extract',
    data=json.dumps({"url": test_url}).encode('utf-8'),
    headers={'Content-Type': 'application/json'}
)

try:
    resp = urllib.request.urlopen(req, timeout=90)
    result = json.loads(resp.read())
    log(f"\n=== 提取結果 ===")
    for line in json.dumps(result, indent=2, ensure_ascii=False).split('\n'):
        log(line)
    
    log(f"\n=== 檢查 ===")
    checks = {
        'platform': result.get('platform'),
        'note_type': result.get('note_type'),
        'can_download_video': result.get('can_download_video'),
        'video_direct_url': result.get('video_direct_url', '')[:60] if result.get('video_direct_url') else None,
        'images_length': len(result.get('images', [])),
        'errors': result.get('error'),
    }
    for k, v in checks.items():
        log(f"  {k}: {v}")
    
    images = result.get('images')
    if images and len(images) > 0:
        log(f"\n  ⚠️ images 非空 ({len(images)}張)")
        log(f"  → 前端會顯示「下載圖片」按鈕，隱藏下載影片！")
    else:
        log(f"\n  ✅ images 為空 → 前端會顯示下載影片按鈕")
        
except Exception as e:
    log(f"  ❌ 提取失敗: {e}")

# === Step 5: Cleanup ===
log("[5] 關閉 Flask")
run('taskkill /F /IM python.exe 2>nul')
log("\n=== 完成 ===")

# Save log
with open(LOG_FILE, 'w', encoding='utf-8') as f:
    f.write('\n'.join(log_lines))

