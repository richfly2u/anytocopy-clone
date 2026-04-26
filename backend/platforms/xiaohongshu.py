#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Xiaohongshu (小红书) platform handler — v3
使用 Chrome DevTools Protocol (CDP) 攔截影片/圖片 CDN URL

流程:
1. 用現有分頁或建新空白分頁
2. 啟用 Network + Page
3. Page.navigate 到目標 URL
4. 攔截 Network.responseReceived 找 video/mp4 及 xhscdn 圖片
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

CDP_PORT = int(os.environ.get('CDP_PORT', '9223'))
CDP_API = f"http://127.0.0.1:{CDP_PORT}"
TIMEOUT = 60

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
    'Referer': 'https://www.xiaohongshu.com/',
}


def _is_windows():
    return os.name == 'nt' or sys.platform.startswith('win')


def resolve_short_url(url):
    if 'xhslink.com' in url.lower():
        try:
            resp = requests.get(url, headers=HEADERS, allow_redirects=True, timeout=15)
            return resp.url
        except Exception:
            pass
    return url


def extract_note_id(url):
    """從 URL 提取筆記 ID — 24-32 hex chars"""
    m = re.search(r'/explore/([a-f0-9]{24,32})', url)
    if m:
        return m.group(1)
    m = re.search(r'/discover/item/([a-f0-9]{24,32})', url)
    if m:
        return m.group(1)
    return None


def _cdp_intercept(note_url, timeout=TIMEOUT):
    """CDP 攔截 — 使用現有分頁或建立新分頁"""
    # 確認 CDP 可用
    try:
        resp = requests.get(f"{CDP_API}/json/version", timeout=3)
        if resp.status_code != 200:
            return {'error': 'CDP 服務不可用'}
    except Exception as e:
        return {'error': f'CDP 未啟動: {e}'}

    import websocket as ws_lib
    from websocket import WebSocketTimeoutException

    resolved = resolve_short_url(note_url)

    # 策略：先用既有小紅書分頁 reload，沒有才建新的 navigate
    page_id = None
    use_reload = False
    try:
        pages = requests.get(f"{CDP_API}/json", timeout=5).json()
        print(f"[CDP] 找到 {len(pages)} 個分頁", flush=True)
        # 找已經有小紅書筆記的分頁
        for p in pages:
            pu = p.get('url', '')
            if 'xiaohongshu.com' in pu and extract_note_id(pu):
                page_id = p['id']
                use_reload = True
                print(f"[CDP] 使用既有小紅書分頁: {page_id[:20]} URL: {pu[:80]}", flush=True)
                break
        # 沒有的話找任何非 devtools 分頁
        if not page_id:
            for p in pages:
                if 'devtools://' not in p.get('url', ''):
                    page_id = p['id']
                    use_reload = True
                    print(f"[CDP] 使用空白分頁: {page_id[:20]} URL: {p.get('url','')[:60]}", flush=True)
                    break
    except Exception as e:
        print(f"[CDP] 取分頁列表失敗: {e}")

    # 沒有可用分頁 → 建新的
    if not page_id:
        try:
            resp = requests.put(f"{CDP_API}/json/new", timeout=10)
            page_id = resp.json()['id']
            use_reload = False
            print(f"[CDP] 建立新分頁: {page_id[:20]}")
        except Exception as e:
            return {'error': f'建立CDP分頁失敗: {e}'}

    ws_url = f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{page_id}"

    try:
        ws = ws_lib.create_connection(ws_url, timeout=15)
        msg_id = 0

        def cdp_send(method, params=None):
            nonlocal msg_id
            msg_id += 1
            msg = {'id': msg_id, 'method': method}
            if params:
                msg['params'] = params
            ws.send(json.dumps(msg))

        # 啟用 Network + Page
        cdp_send('Network.enable')
        cdp_send('Page.enable')

        # Drain 事件
        ws.settimeout(0.3)
        for _ in range(20):
            try:
                ws.recv()
            except Exception:
                break

        # Navigate 或 Reload
        ws.settimeout(timeout)
        if use_reload:
            # Reload 會重置 Network domain，需要在 reload 後重新 enable
            cdp_send('Page.reload', {'ignoreCache': True})
            print(f"[CDP] Reload 分頁")
            # Reload 後先等 navigation 開始
            re_enabled = False
        else:
            cdp_send('Page.navigate', {'url': resolved})
            print(f"[CDP] Navigate 到目標")
            re_enabled = True  # navigate 第一次啟用就算

        # 收集資源
        video_urls = []
        image_urls = []
        page_title = '小红书笔记'
        page_author = ''
        page_transcript = ''
        started = time.time()

        while time.time() - started < timeout:
            try:
                ws.settimeout(0.5)
                msg = json.loads(ws.recv())
                method = msg.get('method', '')

                # Reload 後才出現的 Navigation 事件 → 重新啟用 Network
                if use_reload and not re_enabled:
                    if method in ('Page.frameStartedLoading', 'Page.frameNavigated', 'Page.domContentEventFired'):
                        cdp_send('Network.enable')
                        re_enabled = True
                        print(f"[CDP] Reload Navigation 開始，重新啟用 Network")
                        # 短暫等待 network enable 生效
                        time.sleep(0.5)
                        # drain 事件
                        ws.settimeout(0.3)
                        for _ in range(10):
                            try: ws.recv()
                            except: break
                        ws.settimeout(timeout)

                if method == 'Network.responseReceived':
                    r = msg['params']['response']
                    r_url = r.get('url', '')
                    r_mime = r.get('mimeType', '')

                    # 影片 — 放寬條件：xhscdn video 或 video mime
                    if 'video' in r_mime or ('.mp4' in r_url and 'xhscdn' in r_url):
                        if r_url not in [v['url'] for v in video_urls]:
                            video_urls.append({'url': r_url, 'mime': r_mime})

                    # xhscdn 圖片
                    if 'image' in r_mime and 'xhscdn.com' in r_url:
                        if r_url not in [i['url'] for i in image_urls]:
                            image_urls.append({'url': r_url})

                elif method == 'Page.frameStoppedLoading':
                    # 頁面載入完成 → 用 JS 提取作者和文案
                    try:
                        js_author = (
                            "(()=>{"
                            "const el=document.querySelector('.username')||"
                            "document.querySelector('[class*=\"user\"]')||"
                            "document.querySelector('meta[name=\"author\"]');"
                            "return el?el.textContent||el.content||'':''"
                            "})()"
                        )
                        cdp_send('Runtime.evaluate', {'expression': js_author})
                    except Exception:
                        pass

                elif method == 'Runtime.evaluate':
                    try:
                        val = msg.get('result', {}).get('result', {}).get('value', '')
                        if val and val != '小红书':
                            # 已經有 page_title 就當作 author/transcript
                            if page_title and page_title != '小红书笔记':
                                page_author = val
                            else:
                                page_title = val
                    except Exception:
                        pass

            except WebSocketTimeoutException:
                continue
            except Exception:
                break

        ws.close()

        return {
            'video_urls': video_urls,
            'image_urls': image_urls,
            'page_title': page_title,
            'page_author': page_author,
            'note_id': extract_note_id(resolved),
        }

    except Exception as e:
        return {'error': f'CDP攔截失敗: {e}'}


def extract(url):
    """主提取函數"""
    resolved = resolve_short_url(url)
    note_id = extract_note_id(resolved)

    result = {
        'platform': '小红书',
        'platformIcon': 'fa-regular fa-note-sticky',
        'title': '小红书笔记',
        'author': '',
        'transcript': '',
        'video_url': resolved,
        'note_id': note_id,
        'note_type': 'unknown',
    }

    if not _is_windows():
        result['transcript'] = '小红书提取需要 Windows + CDP'
        return result

    # CDP 攔截
    cdp = _cdp_intercept(url)
    if 'error' in cdp:
        result['error'] = cdp['error']
        return result

    video_urls = cdp.get('video_urls', [])
    image_urls = cdp.get('image_urls', [])
    page_title = cdp.get('page_title', '小红书笔记')
    page_author = cdp.get('page_author', '')
    result['title'] = page_title or result['title']
    result['author'] = page_author or result['author']

    if video_urls:
        result['note_type'] = 'video'
        best = max(video_urls, key=lambda v: v.get('status', 0))
        result['video_direct_url'] = best['url']
        result['can_download_video'] = True
        # 影片筆記不傳 images（避免前端誤判為圖文筆記而隱藏下載按鈕）
        result['images'] = []
        result['image_count'] = 0
        result['transcript'] = (
            f"[小红书] 影片提取成功\n\n"
            f"📹 已攔截到無水印影片 URL\n"
            f"點擊「下載影片」即可保存"
        )
    elif image_urls:
        result['note_type'] = 'image'
        seen = set()
        unique = []
        for img in image_urls:
            key = img['url'].split('?')[0]
            if key not in seen:
                seen.add(key)
                unique.append(img['url'])
        result['images'] = unique
        result['can_download_images'] = True
        result['image_count'] = len(unique)
        result['transcript'] = f"[小红书] 图文笔记提取成功\n共 {len(unique)} 張圖片"
    else:
        result['note_type'] = 'unknown'
        result['transcript'] = (
            f"[小红书] 筆記頁面已載入\n"
            f"未偵測到影片或圖片資源。"
        )

    return result


if __name__ == '__main__':
    import sys
    test_url = sys.argv[1] if len(sys.argv) > 1 else None
    if test_url:
        result = extract(test_url)
        print(json.dumps(result, indent=2, ensure_ascii=False))
