#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Facebook Video Extractor
========================
Uses fdown-api (scrapes fdown.net) to extract Facebook video URLs.
This is more reliable than yt-dlp which has a broken Facebook extractor.

Usage:
  from platforms.facebook import extract, download_video
  info = extract('https://www.facebook.com/watch/?v=...')
  filepath, title = download_video(url, '/output/dir')
"""
import json
import os
import re
import logging
import subprocess
import tempfile

logger = logging.getLogger(__name__)

PLATFORM_NAME = "Facebook"
PLATFORM_ICON = "fa-brands fa-facebook"


def extract(url):
    """Extract Facebook video info"""
    result = _try_fdown_extract(url)
    if result and not result.get('error'):
        return result

    # Fallback: try yt-dlp (typically broken for FB)
    result = _try_ytdlp_extract(url)
    if result and not result.get('error'):
        return result

    return {
        'platform': PLATFORM_NAME,
        'platformIcon': PLATFORM_ICON,
        'title': '提取失敗',
        'author': 'Unknown',
        'transcript': '[Facebook] 影片資訊提取失敗\n\n請確認網址是否正確且為公開影片。',
        'error': 'Facebook extractor failed',
        'can_download_video': False,
        'can_download_audio': False,
    }


def _try_fdown_extract(url):
    """Extract video info using fdown-api"""
    try:
        from fdown_api import Fdown

        fb = Fdown()
        links = fb.get_links(url)

        if not links:
            return None

        # Determine video URL (prefer HD)
        video_src = links.hdlink or links.sdlink
        if not video_src:
            return None

        # Clean up URL
        video_src = video_src.strip()

        return {
            'platform': PLATFORM_NAME,
            'platformIcon': PLATFORM_ICON,
            'title': (links.title or 'Facebook 影片') if links.title != 'No video title' else 'Facebook 影片',
            'author': getattr(links, 'source', 'Facebook') or 'Facebook',
            'transcript': (
                f"[Facebook] 影片資訊提取成功\n\n"
                f"標題: {links.title or 'N/A'}\n"
                f"時長: {links.duration or 'N/A'}\n\n"
                f"⚠️ 文案提取功能開發中\n"
                f"此平台可下載影片。"
            ),
            'video_url': video_src,
            'hd_url': links.hdlink,
            'sd_url': links.sdlink,
            'duration': links.duration or 0,
            'can_download_video': True,
            'can_download_audio': False,
        }
    except AttributeError as e:
        logger.warning(f"[Facebook] fdown-api attr error: {e}")
        return None
    except Exception as e:
        logger.warning(f"[Facebook] fdown-api failed: {e}")
        return None


def _try_ytdlp_extract(url):
    """Fallback: try yt-dlp (typically broken)"""
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
                f"⚠️ 文案提取功能開發中"
            ),
            'video_url': url,
            'duration': info.get('duration', 0),
            'thumbnail': info.get('thumbnail', ''),
            'can_download_video': True,
            'can_download_audio': info.get('duration', 0) < 3600,
        }
    except Exception as e:
        logger.warning(f"[Facebook] yt-dlp failed: {e}")
        return {'error': str(e)}


def download_video(url, output_dir):
    """
    Download Facebook video. Returns (filepath, filename) or raises.
    Uses fdown-api to get video URL, then downloads via subprocess.
    """
    # Get video URL from fdown-api
    from fdown_api import Fdown
    fb = Fdown()
    links = fb.get_links(url)

    if not links:
        raise Exception('fdown-api returned no links')

    video_src = links.hdlink or links.sdlink
    if not video_src:
        raise Exception('No video URL found')

    video_src = video_src.strip()
    title = links.title or 'facebook_video'
    safe_title = re.sub(r'[^\w\s-]', '', title)[:50] or 'facebook_video'
    if safe_title.lower() in ('', 'no video title'):
        safe_title = 'facebook_video'

    output_path = os.path.join(output_dir, f'{safe_title}.mp4')

    # Download via wget (handles redirects, large files well)
    cmd = [
        'wget', '-q', '--show-progress',
        '-O', output_path,
        video_src,
    ]

    result = subprocess.run(cmd, capture_output=True, text=True, timeout=300)
    if result.returncode != 0:
        raise Exception(f'Download failed: {result.stderr[:200]}')

    if not os.path.exists(output_path) or os.path.getsize(output_path) == 0:
        raise Exception('Download produced empty file')

    return output_path, title
