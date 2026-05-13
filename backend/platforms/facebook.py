#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Facebook Video Extractor
========================
三層降級策略:
  1. yt-dlp via plugins/video.php 格式 (最可靠)
  2. yt-dlp direct URL (可能因FB改版失效)
  3. CDP-based extraction via user's browser (最後手段)
"""
import json
import os
import re
import logging
import tempfile
from urllib.parse import quote, urlparse

logger = logging.getLogger(__name__)

PLATFORM_NAME = "Facebook"
PLATFORM_ICON = "fa-brands fa-facebook"


def extract(url):
    """Extract Facebook video info using layered strategy"""
    # Strategy 1: Try plugin URL first (most reliable)
    plugin_url = _make_plugin_url(url)
    if plugin_url:
        result = _try_ytdlp_extract(plugin_url)
        if result and not result.get('error'):
            return result

    # Strategy 2: Try direct URL
    result = _try_ytdlp_extract(url)
    if result and not result.get('error'):
        return result

    # Strategy 3: Return info-only response, suggest CDP download
    return {
        'platform': PLATFORM_NAME,
        'platformIcon': PLATFORM_ICON,
        'title': 'Unknown',
        'author': 'Unknown',
        'transcript': (
            f"[Facebook] 影片資訊提取失敗\n\n"
            f"Facebook 近期更改了頁面結構，自動提取暫時無法使用。\n"
            f"請嘗試使用「下載影片」功能，我們會透過瀏覽器擷取。"
        ),
        'error': 'Facebook extractor failed',
        'can_download_video': False,
        'can_download_audio': False,
    }


def download_video(url, output_dir):
    """Download Facebook video. Returns (filepath, filename) or raises."""
    import yt_dlp

    # Use plugin URL for downloading
    plugin_url = _make_plugin_url(url) or url

    ydl_opts = {
        'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
        'quiet': True,
        'no_warnings': True,
        'format': 'best[ext=mp4]/best',
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(plugin_url, download=True)
        filepath = ydl.prepare_filename(info)
        # yt-dlp may add .mp4 or keep original extension
        if not os.path.exists(filepath):
            for f in os.listdir(output_dir):
                if f.endswith(('.mp4', '.webm', '.mkv')):
                    filepath = os.path.join(output_dir, f)
                    break
        return filepath, info.get('title', 'facebook_video')


def _make_plugin_url(url):
    """Convert a Facebook video URL to plugins/video.php format"""
    if 'plugins/video.php' in url:
        return url

    video_id = None

    # Pattern: /videos/{video_id}/
    m = re.search(r'/videos/(\d+)', url)
    if m:
        video_id = m.group(1)

    # Pattern: /watch/?v={video_id}
    if not video_id:
        m = re.search(r'[?&]v=(\d+)', url)
        if m:
            video_id = m.group(1)

    # Pattern: /reel/{video_id}/
    if not video_id:
        m = re.search(r'/reel/(\d+)', url)
        if m:
            video_id = m.group(1)

    if video_id:
        # Use page.php format for plugin URL - this triggers FacebookPluginsVideo
        page_url = f'https://www.facebook.com/video.php?v={video_id}'
        encoded = quote(page_url, safe='')
        return f'https://www.facebook.com/plugins/video.php?href={encoded}'

    return url  # Return original if we can't parse


def _try_ytdlp_extract(url):
    """Try extracting with yt-dlp"""
    try:
        import yt_dlp

        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        return {
            'platform': PLATFORM_NAME,
            'platformIcon': PLATFORM_ICON,
            'title': info.get('title', 'Untitled'),
            'author': info.get('uploader', info.get('channel', 'Unknown')),
            'transcript': (
                f"[Facebook] 影片資訊提取成功\n\n"
                f"標題: {info.get('title', 'N/A')}\n"
                f"作者: {info.get('uploader', 'N/A')}\n"
                f"時長: {info.get('duration', 0)}秒\n\n"
                f"⚠️ 文案提取功能開發中\n"
                f"此平台可下載影片，語音辨識將透過 Whisper AI 支援。"
            ),
            'video_url': url,
            'duration': info.get('duration', 0),
            'thumbnail': info.get('thumbnail', ''),
            'can_download_video': True,
            'can_download_audio': info.get('duration', 0) < 3600,
        }
    except Exception as e:
        logger.warning(f"[Facebook] yt-dlp failed for {url}: {e}")
        return {'error': str(e)}
