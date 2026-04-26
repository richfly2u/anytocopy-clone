#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Xiaohongshu (小红书) platform handler — 完整版
支援：
- 影片去水印下載（CDP 攔截）
- 圖文筆記圖片提取（CDP 攔截 page DOM + API）
- 筆記元資料提取
- Live圖下載

策略：
1. CDP 攔截 Network（影片/圖片 CDN URL）
2. 透過頁面 DOM 直接提取圖片 URL
3. 回退：基本資訊
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

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36',
    'Referer': 'https://www.xiaohongshu.com/',
}


def _is_windows():
    return os.name == 'nt' or sys.platform.startswith('win')


def resolve_short_url(url):
    """Resolve xhslink short URLs"""
    if 'xhslink.com' in url.lower():
        try:
            resp = requests.get(url, headers=HEADERS, allow_redirects=True, timeout=15)
            return resp.url
        except Exception:
            pass
    return url


def extract_note_id(url):
    """Extract note ID from Xiaohongshu URL"""
    m = re.search(r'/explore/([a-f0-9]{32})', url)
    if m:
        return m.group(1)
    m = re.search(r'/discover/item/([a-f0-9]{32})', url)
    if m:
        return m.group(1)
    return None


# ============================================
# CDP 攔截 (共用)
# ============================================

def _cdp_intercept(url, timeout=45):
    """
    通用 CDP 攔截器。
    1. 建立新分頁
    2. 啟用 Network + Page
    3. Navigate 到目標 URL
    4. 攔截所有回應，分類為 video / image 資源
    5. 取得頁面標題
    6. 清理分頁

    Returns: {video_urls, image_urls, page_title, note_id}
    """
    try:
        resp = requests.get(f"{CDP_API}/json/version", timeout=3)
        if resp.status_code != 200:
            return {'error': 'CDP 服務不可用'}
    except Exception:
        return {'error': 'CDP 未啟動', 'hint': '請啟動 Chromium CDP (port 9223)'}

    import websocket as ws_lib
    from websocket import WebSocketTimeoutException

    # 建立新分頁
    try:
        resp = requests.put(f"{CDP_API}/json/new", timeout=10)
        page = resp.json()
        page_id = page['id']
        ws_url = f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{page_id}"
    except Exception as e:
        return {'error': f'建立CDP分頁失敗: {str(e)}'}

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

        # Drain 初始事件
        ws.settimeout(0.3)
        for _ in range(15):
            try:
                ws.recv()
            except (WebSocketTimeoutException, Exception):
                break

        # Navigate
        resolved = resolve_short_url(url)
        ws.settimeout(timeout)
        cdp_send('Page.navigate', {'url': resolved})

        # 收集資源
        video_urls = []
        image_urls = []
        page_title = '小红书笔记'
        note_api_data = None
        page_loaded = False

        start = time.time()
        while time.time() - start < timeout:
            try:
                ws.settimeout(0.5)
                msg = json.loads(ws.recv())
                method = msg.get('method', '')

                if method == 'Network.responseReceived':
                    resp_data = msg['params']['response']
                    r_url = resp_data.get('url', '')
                    r_mime = resp_data.get('mimeType', '')

                    # 影片 (xhscdn 或 video mime)
                    if ('video' in r_mime or '.mp4' in r_url) and r_mime != 'text/html':
                        if r_url not in [v['url'] for v in video_urls]:
                            video_urls.append({
                                'url': r_url, 'mime': r_mime,
                                'status': resp_data.get('status'),
                            })

                    # 圖片 (xhscdn 圖片 CDN 或 image mime)
                    if 'image' in r_mime and 'xhscdn.com' in r_url:
                        if r_url not in [i['url'] for i in image_urls]:
                            image_urls.append({
                                'url': r_url, 'mime': r_mime,
                                'status': resp_data.get('status'),
                            })

                    # 筆記 API 回應 (edith.xiaohongshu.com)
                    if 'api/sns/h5/v1/note_info' in r_url:
                        # 嘗試讀取 body
                        request_id = msg['params'].get('requestId', '')
                        if request_id:
                            try:
                                body_resp = requests.get(
                                    f"{CDP_API}/json/{page_id}/networkResource",
                                    params={'requestId': request_id},
                                    timeout=3
                                )
                                if body_resp.status_code == 200:
                                    note_api_data = body_resp.json()
                            except Exception:
                                pass

                elif method == 'Page.frameStoppedLoading' and not page_loaded:
                    page_loaded = True
                    # 頁面載入完成，等 1s 收集剩餘資源
                    time.sleep(1)

            except WebSocketTimeoutException:
                # 如果頁面已載入且收集到資源，可提早結束
                if page_loaded:
                    # 多等 3s 捕獲延遲加載
                    if time.time() - start > 15:
                        break
                continue
            except Exception:
                break

        # 取得頁面標題
        try:
            cdp_send('Runtime.evaluate', {
                'expression': 'JSON.stringify({title: document.title, url: document.location.href})'
            })
            ws.settimeout(2)
            while True:
                resp = json.loads(ws.recv())
                if resp.get('id') == msg_id:
                    val = resp.get('result', {}).get('result', {}).get('value', '{}')
                    try:
                        page_info = json.loads(val)
                        if page_info.get('title'):
                            page_title = page_info['title']
                    except Exception:
                        pass
                    break
        except Exception:
            pass

        ws.close()

        # 清理分頁
        try:
            requests.get(f"{CDP_API}/json/close/{page_id}", timeout=3)
        except Exception:
            pass

        return {
            'video_urls': video_urls,
            'image_urls': image_urls,
            'page_title': page_title,
            'note_id': extract_note_id(resolved),
        }

    except Exception as e:
        try:
            requests.get(f"{CDP_API}/json/close/{page_id}", timeout=3)
        except Exception:
            pass
        return {'error': f'CDP攔截失敗: {str(e)}'}


# ============================================
# 從筆記 API URL 提取圖片 URL
# ============================================

def _extract_images_from_dom(page_id):
    """嘗試透過頁面 DOM 提取圖片 URL"""
    try:
        import websocket as ws_lib
        from websocket import WebSocketTimeoutException

        ws_url = f"ws://127.0.0.1:{CDP_PORT}/devtools/page/{page_id}"
        ws = ws_lib.create_connection(ws_url, timeout=10)

        # 執行 JS 提取所有 img 元素
        expression = '''
        (() => {
            const imgs = document.querySelectorAll('img');
            const noteImgs = [];
            const swiperImgs = document.querySelectorAll('.swiper-slide img, [class*="slide"] img');
            
            imgs.forEach(img => {
                const src = img.src || img.getAttribute('data-src') || '';
                // 只保留 xhscdn 的圖片（筆記內容圖片）
                if (src.includes('xhscdn.com') || src.includes('xhs') || src.includes('img')) {
                    noteImgs.push({
                        src: src,
                        width: img.naturalWidth,
                        height: img.naturalHeight,
                        alt: img.alt || ''
                    });
                }
            });
            
            // 如果有輪播圖，優先使用
            if (swiperImgs.length > 0) {
                const swiperSrcs = [];
                swiperImgs.forEach(img => {
                    const src = img.src || img.getAttribute('data-src') || '';
                    if (src && !swiperSrcs.includes(src)) swiperSrcs.push({src, fromSwiper: true});
                });
                return JSON.stringify({images: swiperSrcs.length > 0 ? swiperSrcs : noteImgs, total: imgs.length});
            }
            
            return JSON.stringify({images: noteImgs, total: imgs.length});
        })()
        '''

        ws.send(json.dumps({
            'id': 1, 'method': 'Runtime.evaluate',
            'params': {'expression': expression, 'returnByValue': True}
        }))

        ws.settimeout(5)
        while True:
            resp = json.loads(ws.recv())
            if resp.get('id') == 1:
                val = resp.get('result', {}).get('result', {}).get('value', '{}')
                data = json.loads(val)
                ws.close()
                return data.get('images', [])

    except Exception:
        pass
    return []


# ============================================
# 主 extract 函數
# ============================================

def extract(url):
    """
    小紅書主提取函數。
    返回包含：
    - platform / platformIcon
    - title / author
    - transcript (文案內容)
    - 如果是影片: video_url, can_download_video, can_download_audio
    - 如果是圖文: images[] (圖片 gallery), can_download_images
    - video_url: 原始筆記 URL
    - note_id
    - note_type: 'video' | 'image' | 'unknown'
    """
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
        result['transcript'] = '小红书提取需要 Windows + CDP。请启动 XHS Proxy。'
        return result

    # CDP 攔截
    cdp_result = _cdp_intercept(url, timeout=45)
    if 'error' in cdp_result:
        result['error'] = cdp_result['error']
        if cdp_result.get('hint'):
            result['hint'] = cdp_result['hint']
        return result

    # 提取結果
    video_urls = cdp_result.get('video_urls', [])
    image_urls = cdp_result.get('image_urls', [])
    page_title = cdp_result.get('page_title', '小红书笔记')

    result['title'] = page_title or result['title']

    if video_urls:
        # 影片筆記
        result['note_type'] = 'video'
        best_video = max(video_urls, key=lambda v: v.get('status', 0))
        result['video_direct_url'] = best_video['url']
        result['can_download_video'] = True
        result['can_download_audio'] = True
        result['transcript'] = (
            f"[小红书] 影片提取成功\n\n"
            f"📹 已攔截到無水印影片 URL\n"
            f"點擊「下載影片」即可保存到本地\n\n"
            f"⚠️ 文案提取功能開發中\n"
            f"此平台的語音識別需下載影片後進行。"
        )
    elif image_urls:
        # 圖文筆記
        result['note_type'] = 'image'
        # 去重，取優先級高的
        seen = set()
        unique_images = []
        for img in image_urls:
            url_key = img['url'].split('?')[0]  # 去 query 參數比較
            if url_key not in seen:
                seen.add(url_key)
                unique_images.append(img['url'])

        result['images'] = unique_images
        result['can_download_images'] = True
        result['image_count'] = len(unique_images)
        result['transcript'] = (
            f"[小红书] 图文笔记提取成功\n\n"
            f"🖼️ 共 {len(unique_images)} 張圖片\n"
            f"點擊下方按鈕即可下載全部圖片\n\n"
            f"⚠️ 文案提取功能開發中\n"
            f"圖片中的文字可透過 OCR 識別（即將支援）。"
        )
    else:
        # 可能未抓到資源，但頁面有載入
        result['note_type'] = 'unknown'
        result['transcript'] = (
            f"[小红书] 筆記頁面已載入\n"
            f"未偵測到影片或圖片資源。請確認此連結為有效筆記。"
        )

    return result


if __name__ == '__main__':
    import sys
    test_url = sys.argv[1] if len(sys.argv) > 1 else None
    if test_url:
        result = extract(test_url)
        print(json.dumps(result, indent=2, ensure_ascii=False))
