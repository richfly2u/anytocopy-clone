#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""快速診斷小紅書 CDP (Windows端，用 127.0.0.1)"""
import json, sys, time, requests

CDP_API = "http://127.0.0.1:9223"

try:
    pages = requests.get(f"{CDP_API}/json", timeout=5).json()
except Exception as e:
    print(f"! 連不上 CDP: {e}")
    print("確認 Chrome/Edge 有開 --remote-debugging-port=9223")
    sys.exit(1)

for p in pages[:5]:
    print(f"  [page] {p['id'][:20]} | {p.get('url','')[:80]}")

# 找 xhs 分頁
xhs_page = None
for p in pages:
    pu = p.get('url', '')
    if 'xiaohongshu.com' in pu and '/explore/' in pu:
        xhs_page = p
        break

if not xhs_page:
    print("! 沒有小紅書分頁，找一個非 devtools 分頁")
    for p in pages:
        if 'devtools://' not in p.get('url', ''):
            xhs_page = p
            break

if not xhs_page:
    print("! 無可用分頁")
    sys.exit(1)

print(f"\n使用分頁: {xhs_page['id'][:20]}")
print(f"URL: {xhs_page.get('url', '')[:100]}")

import websocket as ws_lib
from websocket import WebSocketTimeoutException

ws_url = f"ws://127.0.0.1:9223/devtools/page/{xhs_page['id']}"
ws = ws_lib.create_connection(ws_url, timeout=15)

msg_id = 0
def cdp_send(method, params=None):
    global msg_id
    msg_id += 1
    msg = {'id': msg_id, 'method': method}
    if params: msg['params'] = params
    ws.send(json.dumps(msg))

cdp_send('Network.enable')
cdp_send('Page.enable')

ws.settimeout(0.3)
for _ in range(30):
    try: ws.recv()
    except: break

ws.settimeout(30)
cdp_send('Page.reload', {'ignoreCache': True})
print("[CDP] Reload 發出\n")

start = time.time()
event_count = 0
network_responses = 0
xhscdn_urls = []

while time.time() - start < 15:
    try:
        msg = json.loads(ws.recv())
        event_count += 1
        method = msg.get('method', '')
        
        if method == 'Network.responseReceived':
            network_responses += 1
            r = msg['params']['response']
            url = r.get('url', '')
            mime = r.get('mimeType', '')
            status = r.get('status', 0)
            
            if 'xhscdn' in url:
                xhscdn_urls.append((url[:150], mime, status))
                print(f"  [{status}] {mime[:30]:30s} | {url[:150]}")
            elif url and network_responses <= 3:
                print(f"  [非CDN] {url[:100]}")
        
        elif method in ('Page.frameStoppedLoading', 'Page.domContentEventFired', 'Page.frameStartedLoading'):
            print(f"  [event] {method}")
            
    except WebSocketTimeoutException:
        continue
    except json.JSONDecodeError:
        continue
    except Exception as e:
        print(f"  [error] {e}")
        break

ws.close()

print(f"\n=== 統計 ===")
print(f"總事件: {event_count} | Network.response: {network_responses} | xhscdn: {len(xhscdn_urls)}")
for url, mime, status in xhscdn_urls:
    print(f"  [{status}] {mime} | {url}")
