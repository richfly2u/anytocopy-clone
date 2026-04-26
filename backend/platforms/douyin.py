#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音 Douyin platform handler.
三層降級策略:
1. yt-dlp 直接提取（最簡單，但常被抖音 WAF 擋）
2. CDP 攔截影片 URL（需 Windows + Chromium CDP，類似小紅書方案）
3. 第三方 API 回退
"""

import json
import os
import re
import time
from pathlib import Path

import requests

# ============================================
# 抖音 URL 解析
# ============================================

def get_video_id(url):
    """從抖音 URL 提取影片 ID"""
    # douyin.com/video/xxxxx
    m = re.search(r'/video/(\d+)', url)
    if m:
        return m.group(1)
    # v.douyin.com/xxxxx (短連結，需要重定向)
    m = re.search(r'v\.douyin\.com/(\w+)', url)
    if m:
        return {'short': m.group(1)}
    return None


def resolve_short_url(url):
    """解析抖音短鏈接，取得真實 URL"""
    if 'v.douyin.com' in url.lower() or 'iesdouyin.com' in url.lower():
        try:
            resp = requests.get(url, headers=_headers(), allow_redirects=True, timeout=15)
            return resp.url
        except Exception:
            pass
    return url


def _headers():
    return {
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/120.0.0.0 Safari/537.36'
        ),
        'Referer': 'https://www.douyin.com/',
        'Accept': 'application/json, text/plain, */*',
        'Accept-Language': 'zh-CN,zh;q=0.9,en;q=0.8',
    }


# ============================================
# 策略 1: yt-dlp 提取（首選）
# ============================================

def extract_via_ytdlp(url):
    """使用 yt-dlp 嘗試提取抖音影片資訊"""
    try:
        import yt_dlp
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        title = info.get('title', 'Untitled')
        author = info.get('uploader', info.get('creator', 'Unknown'))
        duration = info.get('duration', 0)
        thumbnail = info.get('thumbnail', '')
        description = (info.get('description') or '')[:2000]

        # 構建文案
        transcript_parts = [f"[抖音] 影片資訊提取成功\n"]
        if description:
            transcript_parts.append(f"📝 描述:\n{description}\n")
        transcript_parts.append(
            f"⚠️ 文案提取功能開發中\n"
            f"此平台的語音識別需下載影片後進行，將透過 Whisper AI 支援。"
        )

        return {
            'platform': '抖音',
            'platformIcon': 'fa-brands fa-tiktok',
            'title': title,
            'author': author,
            'transcript': '\n'.join(transcript_parts),
            'video_url': url,
            'duration': duration,
            'thumbnail': thumbnail,
            'can_download_video': True,
            'can_download_audio': duration and duration < 3600,
            '_method': 'yt-dlp',
        }
    except Exception as e:
        return {'error': f'yt-dlp抖音提取失敗: {str(e)}', '_method': 'yt-dlp'}


# ============================================
# 策略 2: CDP 攔截（需 Windows + Chromium）
# ============================================

def _is_windows():
    return os.name == 'nt' or sys.platform.startswith('win')


def extract_via_cdp(url):
    """
    使用 CDP 攔截抖音影片 URL。
    類似小紅書方案：開新分頁 → 啟用 Network → Navigate → 攔截影片
    """
    resolved = resolve_short_url(url)
    video_id = get_video_id(resolved) if resolved != url else None

    CDP_PORT = 9333
    HTTP_API = f"http://127.0.0.1:{CDP_PORT}"
    TIMEOUT = 45

    # 確認 CDP 可用
    try:
        resp = requests.get(f"{HTTP_API}/json/version", timeout=3)
        if resp.status_code != 200:
            return {'error': 'CDP 服務不可用'}
    except Exception:
        return {'error': 'CDP 服務未啟動', 'hint': '請先啟動 Chromium CDP (port 9333)'}

    import websocket as ws_lib
    from websocket import WebSocketTimeoutException

    # 建立新分頁
    try:
        resp = requests.put(f"{HTTP_API}/json/new", timeout=10)
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

        # Navigate 到目標 URL
        ws.settimeout(TIMEOUT)
        cdp_send('Page.navigate', {'url': resolved})

        # 攔截影片
        video_url = None
        mime_type = None
        page_title = '抖音影片'
        start = time.time()

        while time.time() - start < TIMEOUT:
            try:
                ws.settimeout(0.5)
                msg = json.loads(ws.recv())
                method = msg.get('method', '')

                if method == 'Network.responseReceived':
                    resp_data = msg['params']['response']
                    r_url = resp_data.get('url', '')
                    r_mime = resp_data.get('mimeType', '')

                    # 抖音影片特徵：douyin 域名 + video mime 或 .mp4
                    if ('video' in r_mime or '.mp4' in r_url):
                        if not video_url:
                            video_url = r_url
                            mime_type = r_mime
                            # 繼續 collect 更多影片 URL，取最後一個（最高畫質）
                        else:
                            video_url = r_url  # 後面的通常畫質更高

                elif method == 'Page.frameStoppedLoading':
                    # 頁面載入完成後，等 2 秒繼續收集網路請求
                    time.sleep(2)
                    # 嘗試取得頁面標題
                    cdp_send('Runtime.evaluate', {
                        'expression': 'document.title'
                    })
                    # 但不中斷循環，繼續收集

                elif method == 'Runtime.evaluate' and video_url:
                    # 拿到標題後可以結束
                    try:
                        val = msg.get('result', {}).get('result', {}).get('value', '')
                        if val:
                            page_title = val
                    except Exception:
                        pass

            except WebSocketTimeoutException:
                continue
            except Exception:
                break

        ws.close()

        # 清理分頁
        try:
            requests.get(f"{HTTP_API}/json/close/{page_id}", timeout=3)
        except Exception:
            pass

        if not video_url:
            return {'error': '未攔截到抖音影片 URL', '_method': 'cdp'}

        return {
            'platform': '抖音',
            'platformIcon': 'fa-brands fa-tiktok',
            'title': page_title or '抖音影片',
            'author': '',
            'transcript': f'[抖音] 影片 URL 已攔截完成\n可下載無浮水印影片。\n\n⚠️ 文案提取功能開發中\n此平台的語音識別需透過 Whisper AI 支援。',
            'video_url': video_url,
            'can_download_video': True,
            '_method': 'cdp',
            '_video_direct_url': video_url,
        }
    except Exception as e:
        # 確保清理
        try:
            requests.get(f"{HTTP_API}/json/close/{page_id}", timeout=3)
        except Exception:
            pass
        return {'error': f'CDP 攔截失敗: {str(e)}', '_method': 'cdp'}


# ============================================
# 策略 3: 第三方 API 降級
# ============================================

def extract_via_third_party(url):
    """嘗試第三方抖音解析 API"""
    apis = [
        f"https://api.douyin.wtf/api?url={url}",
    ]

    for api_url in apis:
        try:
            resp = requests.get(api_url, headers=_headers(), timeout=15)
            data = resp.json()
            if data.get('video_url') or data.get('url'):
                video_url = data.get('video_url') or data.get('url')
                return {
                    'platform': '抖音',
                    'platformIcon': 'fa-brands fa-tiktok',
                    'title': data.get('title', '抖音影片'),
                    'author': data.get('author', ''),
                    'transcript': f'[抖音] 影片資訊提取成功（第三方API）\n可下載影片。',
                    'video_url': video_url,
                    'can_download_video': True,
                    '_method': 'third-party',
                }
        except Exception:
            continue

    return {'error': '所有抖音提取方式均失敗', '_method': 'none'}


# ============================================
# 主入口
# ============================================

def extract(url):
    """
    抖音主提取函數。
    三層降級：yt-dlp → CDP 攔截 → 第三方 API
    """
    # 策略 1: yt-dlp
    result = extract_via_ytdlp(url)
    if 'error' not in result:
        return result

    # 策略 2: CDP（僅 Windows）
    if _is_windows():
        result = extract_via_cdp(url)
        if 'error' not in result:
            return result

    # 策略 3: 第三方 API
    result = extract_via_third_party(url)
    return result


if __name__ == '__main__':
    import sys
    test_url = sys.argv[1] if len(sys.argv) > 1 else None
    if test_url:
        result = extract(test_url)
        print(json.dumps(result, indent=2, ensure_ascii=False))
