#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
抖音 Douyin platform handler (v2).
Two-tier strategy:
1. yt-dlp --dump-json to extract direct video URL (primary)
2. CDP intercept (fallback, Windows + Chromium port 9333)

Output:
  platform: '抖音'
  note_type: 'video' (douyin is always video)
  video_direct_url: direct CDN video URL
  can_download_video: True
"""

import json
import os
import re
import sys
import time
from pathlib import Path

import requests

CDP_PORT = int(os.environ.get('DOUYIN_CDP_PORT', '9333'))
CDP_API = f"http://127.0.0.1:{CDP_PORT}"
TIMEOUT = 45

HEADERS = {
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
# URL helpers
# ============================================

def get_video_id(url):
    """Extract video ID from douyin URL"""
    # douyin.com/video/xxxxx
    m = re.search(r'/video/(\d+)', url)
    if m:
        return m.group(1)
    # v.douyin.com/xxxxx (short link, needs redirect)
    m = re.search(r'v\.douyin\.com/(\w+)', url)
    if m:
        return {'short': m.group(1)}
    return None


def resolve_short_url(url):
    """Resolve short douyin links to full URL"""
    if 'v.douyin.com' in url.lower() or 'iesdouyin.com' in url.lower():
        try:
            resp = requests.get(url, headers=HEADERS, allow_redirects=True, timeout=15)
            return resp.url
        except Exception:
            pass
    return url


def _is_windows():
    return os.name == 'nt' or sys.platform.startswith('win')


# ============================================
# Strategy 1: yt-dlp (primary)
# ============================================

def extract_via_ytdlp(url):
    """
    Use yt-dlp's Douyin extractor to get the direct video URL.
    Returns dict with 'video_direct_url' on success, or 'error' on failure.
    """
    try:
        import yt_dlp

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        # Extract metadata
        title = info.get('title', info.get('description', '抖音视频')) or '抖音视频'
        author = info.get('uploader', info.get('creator', '')) or ''
        duration = info.get('duration', 0)
        thumbnail = info.get('thumbnail', '')

        # Extract the best direct video URL from formats
        # yt-dlp douyin extractor returns formats with direct CDN URLs
        video_direct_url = None
        formats = info.get('formats', [])

        if formats:
            # Prefer highest quality with video codec
            # Sort by quality (height) descending, prefer those with both video+audio
            best = None
            for f in formats:
                vcodec = f.get('vcodec', 'none')
                acodec = f.get('acodec', 'none')
                if vcodec != 'none':
                    height = f.get('height', 0)
                    if best is None or height > best.get('height', 0):
                        best = f

            if best and best.get('url'):
                video_direct_url = best['url']
            elif not best and formats[0].get('url'):
                video_direct_url = formats[0]['url']

        # Also try direct 'url' key (some extractors put it at top level)
        if not video_direct_url and info.get('url'):
            video_direct_url = info['url']

        if not video_direct_url:
            return {'error': 'yt-dlp未提取到抖音视频URL', '_method': 'yt-dlp'}

        return {
            'platform': '抖音',
            'platformIcon': 'fa-brands fa-tiktok',
            'title': title,
            'author': author,
            'transcript': (
                f'[抖音] 视频提取成功\n\n'
                f'标题: {title}\n'
                f'作者: {author}\n'
                f'时长: {duration}秒\n\n'
                f'⚠️ 文案提取功能开发中\n'
                f'此平台的语音识别需下载视频后透过 Whisper AI 支援。'
            ),
            'video_url': url,
            'video_direct_url': video_direct_url,
            'duration': duration,
            'thumbnail': thumbnail,
            'note_type': 'video',
            'can_download_video': True,
            'can_download_audio': bool(duration) and duration < 3600,
            '_method': 'yt-dlp',
        }
    except Exception as e:
        return {'error': f'yt-dlp抖音提取失败: {str(e)}', '_method': 'yt-dlp'}


# ============================================
# Strategy 2: CDP intercept (fallback, Windows)
# ============================================

def extract_via_cdp(url):
    """
    Use CDP (Chrome DevTools Protocol) to intercept douyin video URLs.
    Opens page → enables Network → navigates → intercepts video responses.
    """
    resolved = resolve_short_url(url)

    # Verify CDP is available
    try:
        resp = requests.get(f"{CDP_API}/json/version", timeout=3)
        if resp.status_code != 200:
            return {'error': 'CDP 服务不可用'}
    except Exception:
        return {'error': 'CDP 服务未启动', 'hint': f'请先启动 Chromium CDP (port {CDP_PORT})'}

    import websocket as ws_lib
    from websocket import WebSocketTimeoutException

    # Create a new page tab
    page_id = None
    try:
        # Try to find an existing usable tab first
        try:
            pages = requests.get(f"{CDP_API}/json", timeout=5).json()
            for p in pages:
                pu = p.get('url', '')
                if 'devtools://' not in pu and 'about:blank' not in pu:
                    page_id = p['id']
                    break
        except Exception:
            pass

        if not page_id:
            resp = requests.put(f"{CDP_API}/json/new", timeout=10)
            page_id = resp.json()['id']
    except Exception as e:
        return {'error': f'建立CDP分页失败: {str(e)}'}

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

        # Enable Network + Page
        cdp_send('Network.enable')
        cdp_send('Page.enable')

        # Drain initial events
        ws.settimeout(0.3)
        for _ in range(15):
            try:
                ws.recv()
            except Exception:
                break

        # Navigate to target URL
        ws.settimeout(TIMEOUT)
        cdp_send('Page.navigate', {'url': resolved})

        # Intercept video responses
        video_url = None
        page_title = '抖音视频'
        page_author = ''
        started = time.time()

        while time.time() - started < TIMEOUT:
            try:
                ws.settimeout(0.5)
                msg = json.loads(ws.recv())
                method = msg.get('method', '')

                if method == 'Network.responseReceived':
                    r = msg['params']['response']
                    r_url = r.get('url', '')
                    r_mime = r.get('mimeType', '')

                    # Douyin video: video mime, .mp4 extension, or aweme/v1/play/
                    if ('video' in r_mime
                            or '.mp4' in r_url
                            or 'aweme/v1/play/' in r_url):
                        if not video_url:
                            video_url = r_url
                        else:
                            video_url = r_url  # later = usually higher quality

                elif method == 'Page.frameStoppedLoading':
                    # 頁面載入完成 → 用 JS 提取作者
                    try:
                        js_author = (
                            "(()=>{"
                            "const el=document.querySelector('.author')||"
                            "document.querySelector('[class*=\"author\"]')||"
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
                        if val:
                            if page_title == '抖音视频':
                                page_title = val
                            else:
                                page_author = val
                    except Exception:
                        pass

            except WebSocketTimeoutException:
                continue
            except Exception:
                break

        ws.close()

        # Close the page tab
        try:
            requests.get(f"{CDP_API}/json/close/{page_id}", timeout=3)
        except Exception:
            pass

        if not video_url:
            return {'error': '未拦截到抖音视频URL', '_method': 'cdp'}

        return {
            'platform': '抖音',
            'platformIcon': 'fa-brands fa-tiktok',
            'title': page_title or '抖音视频',
            'author': page_author or '',
            'video_direct_url': video_url,
            'note_type': 'video',
            'can_download_video': True,
            '_method': 'cdp',
        }
    except Exception as e:
        try:
            requests.get(f"{CDP_API}/json/close/{page_id}", timeout=3)
        except Exception:
            pass
        return {'error': f'CDP拦截失败: {str(e)}', '_method': 'cdp'}


# ============================================
# Main entry point
# ============================================

def extract(url):
    """
    Douyin main extract function.
    Two-tier fallback: CDP → yt-dlp.

    Windows: CDP first (higher chance of watermark-free CDN URL) → yt-dlp
    Non-Windows: yt-dlp only

    Returns dict with:
      platform, note_type, video_direct_url, can_download_video, ...
    """
    # Strategy 1: CDP (Windows only, prefer for watermark-free CDN URLs)
    if _is_windows():
        result = extract_via_cdp(url)
        if 'error' not in result:
            return result

    # Strategy 2: yt-dlp (works cross-platform)
    result = extract_via_ytdlp(url)
    if 'error' not in result:
        return result

    # Both failed
    return {
        'platform': '抖音',
        'platformIcon': 'fa-brands fa-tiktok',
        'title': '抖音视频',
        'note_type': 'video',
        'can_download_video': False,
        'error': '所有抖音提取方式均失败',
        '_method': 'none',
    }


if __name__ == '__main__':
    test_url = sys.argv[1] if len(sys.argv) > 1 else None
    if test_url:
        result = extract(test_url)
        print(json.dumps(result, indent=2, ensure_ascii=False))
