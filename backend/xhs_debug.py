#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
小紅書 CDP 攔截測試 — 暴力除錯版
執行方式: python xhs_debug.py
請先確保 Chrome CDP 正在運行 (port 9223)
請先在 Chrome 手動打開目標小紅書筆記
"""

import json
import requests
import websocket
import time
import sys

CDP_API = 'http://127.0.0.1:9223'
NOTE_URL = 'https://www.xiaohongshu.com/discovery/item/69ed5a8a0000000036018e7e'


def log(msg):
    print(f'[{time.strftime("%H:%M:%S")}] {msg}')
    sys.stdout.flush()


# Step 1: 確認 CDP
log('Step 1: 檢查 CDP...')
try:
    r = requests.get(f'{CDP_API}/json/version', timeout=5)
    browser = r.json().get('Browser', '?')
    log(f'  ✅ CDP OK — {browser}')
except Exception as e:
    log(f'  ❌ CDP 不可用: {e}')
    sys.exit(1)

# Step 2: 找小紅書分頁
log('Step 2: 找小紅書分頁...')
try:
    pages = requests.get(f'{CDP_API}/json', timeout=5).json()
    xhs_pages = [p for p in pages if 'xiaohongshu.com' in p.get('url', '')]
    log(f'  共 {len(pages)} 個分頁，小紅書分頁: {len(xhs_pages)}')
    for p in xhs_pages:
        log(f'  - {p["id"][:20]} | {p["url"][:80]}')
except Exception as e:
    log(f'  ❌ 取分頁失敗: {e}')
    sys.exit(1)

if not xhs_pages:
    log('  ⚠️ 沒有小紅書分頁，請在 Chrome 手動打開筆記後重試')
    sys.exit(1)

# Step 3: 選目標分頁
target = None
for p in xhs_pages:
    if '69ed5a8a' in p.get('url', ''):
        target = p
        log(f'  ✅ 找到目標筆記分頁: {p["id"][:20]}')
        break
if not target:
    target = xhs_pages[0]
    log(f'  ⚠️ 沒找到目標筆記，用第一個小紅書分頁: {target["id"][:20]}')

PID = target['id']
WS_URL = f'ws://127.0.0.1:9223/devtools/page/{PID}'

# Step 4: 連 WebSocket
log(f'Step 4: 連 WebSocket...')
try:
    ws = websocket.create_connection(WS_URL, timeout=15)
    log(f'  ✅ WS 連線成功')
except Exception as e:
    log(f'  ❌ WS 連線失敗: {e}')
    sys.exit(1)

# Step 5: 啟用 Network
log('Step 5: 啟用 Network 監聽...')
msg_id = 0
def cdp_send(method, params=None):
    global msg_id
    msg_id += 1
    msg = {'id': msg_id, 'method': method}
    if params: msg['params'] = params
    ws.send(json.dumps(msg))

msg_id = 0
cdp_send('Network.enable')
cdp_send('Page.enable')
time.sleep(0.5)

# Drain events
ws.settimeout(0.3)
drained = 0
for _ in range(20):
    try:
        ws.recv()
        drained += 1
    except: break
log(f'  ✅ Drain 完成 ({drained} events)')

# Step 6: Reload 頁面
log(f'Step 6: Reload 頁面...')
ws.settimeout(45)
cdp_send('Page.reload', {'ignoreCache': True})
log(f'  ⏳ 等待回應 (45s timeout)...')

# Step 7: 監聽
log(f'Step 7: 監聽網路請求...')
videos = []
images = []
all_responses = []
start = time.time()
timeout = 45
page_loaded = False

while time.time() - start < timeout:
    try:
        ws.settimeout(0.5)
        msg = json.loads(ws.recv())
        m = msg.get('method', '')

        if m == 'Network.responseReceived':
            r = msg['params']['response']
            url = r.get('url', '')
            mime = r.get('mimeType', '')
            status = r.get('status', 0)

            # 只記錄有意義的回應
            if status == 200 or status == 206 or 'xhscdn' in url or 'video' in mime:
                all_responses.append({'url': url[:120], 'mime': mime, 'status': status})

            if 'video' in mime:
                videos.append(url)
                log(f'  🎬 VIDEO ({status}): {url[:80]}')

            if 'image' in mime and 'xhscdn.com' in url:
                images.append(url)
                log(f'  🖼️ IMAGE ({status}): {url[:80]}')

        elif m == 'Page.frameStoppedLoading':
            page_loaded = True
            log(f'  📄 頁面載入完成 ({time.time()-start:.1f}s)')
            time.sleep(3)  # 多等 3 秒收集延遲請求

        elif m == 'Page.frameNavigated':
            log(f'  🧭 頁面導航: {msg.get("params",{}).get("frame",{}).get("url","?")[:80]}')

    except websocket.WebSocketTimeoutException:
        if page_loaded:
            log(f'  ⏱️ 頁面已載入，等待 {timeout - (time.time()-start):.0f}s 更多請求...')
            time.sleep(1)
        continue
    except Exception as e:
        log(f'  ⚠️ 接收錯誤: {e}')
        break

ws.close()

# Step 8: 結果
log(f'\n=== 結果 ===')
log(f'🎬 影片: {len(videos)} 個')
for v in videos:
    log(f'   {v[:100]}')

log(f'🖼️  xhscdn 圖片: {len(images)} 個')
for i in images[:5]:
    log(f'   {i[:80]}')

log(f'📊 全部回應: {len(all_responses)} 個')
log(f'   頭 10 個:')
for r in all_responses[:10]:
    log(f'   [{r["status"]}] {r["mime"][:20]} | {r["url"][:60]}')
