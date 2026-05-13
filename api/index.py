#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VideoText AI Backend — Vercel Serverless Edition
=================================================
Extract video metadata + transcripts from URL.
Returns direct CDN URLs for downloads (Vercel 10s timeout limit).

Supported platforms:
  - YouTube (transcripts + metadata)
  - Bilibili (subtitles + metadata)
  - Facebook (video URL via fdown-api / yt-dlp)
  - Douyin (yt-dlp metadata)
  - Others (yt-dlp fallback)

NOT supported on Vercel (needs local browser/ML):
  - 小红书 / Xiaohongshu
  - Watermark removal
  - OCR
  - Local file upload → whisper
"""

import json
import os
import sys
import re
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

# ── Patch sys.path so api/platforms/ is findable ──
_api_dir = os.path.dirname(os.path.abspath(__file__))
if _api_dir not in sys.path:
    sys.path.insert(0, _api_dir)

from utils.platform import (
    detect_platform, get_platform_display, get_platform_icon,
    get_platform_features, extract_youtube_id, extract_bilibili_bvid,
    PLATFORM_NAMES, PLATFORM_ICONS, PLATFORM_FEATURES,
)

app = Flask(__name__)
CORS(app)

# ═══════════════════════════════════════════
# Health
# ═══════════════════════════════════════════

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'ok',
        'message': 'VideoText AI API (Vercel) is running',
        'version': '2.1-vercel',
        'platforms': list(PLATFORM_NAMES.values()),
    })

@app.route('/api/platforms', methods=['GET'])
def list_platforms():
    result = []
    for key, name in PLATFORM_NAMES.items():
        result.append({
            'id': key,
            'name': name,
            'icon': PLATFORM_ICONS.get(key, 'fa-solid fa-video'),
            'features': get_platform_features(key),
        })
    return jsonify({'platforms': result})

# ═══════════════════════════════════════════
# Extract (main)
# ═══════════════════════════════════════════

@app.route('/api/extract', methods=['POST'])
def extract():
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'error': '請提供 URL'}), 400

    url = data['url'].strip()
    platform = detect_platform(url)

    if not platform:
        info = _fallback_extract(url)
        if info.get('error'):
            return jsonify({'error': f'不支援的 URL: {info["error"]}'}), 400
        return jsonify(info)

    try:
        if platform == 'youtube':
            result = _handle_youtube(url)
        elif platform == 'bilibili':
            result = _handle_bilibili(url)
        elif platform == 'facebook':
            result = _handle_facebook(url)
        elif platform == 'douyin':
            result = _handle_douyin(url)
        elif platform in ('tiktok', 'kuaishou', 'weibo'):
            result = _handle_ytdlp_platform(url, platform)
        elif platform == 'xiaohongshu':
            result = _handle_xiaohongshu(url)
        else:
            return jsonify({'error': f'平台 {platform} 尚未支援'}), 400
    except Exception as e:
        return jsonify({'error': f'提取失敗: {str(e)}'}), 500

    return jsonify(result)

# ═══════════════════════════════════════════
# Platform Handlers
# ═══════════════════════════════════════════

def _handle_youtube(url):
    video_id = extract_youtube_id(url)
    if not video_id:
        return {'error': '無法解析 YouTube 影片 ID'}

    from platforms.youtube import extract as youtube_extract
    return youtube_extract(video_id)

def _handle_bilibili(url):
    from platforms.bilibili import extract as bilibili_extract
    return bilibili_extract(url)

def _handle_facebook(url):
    from platforms.facebook import extract as fb_extract
    return fb_extract(url)

def _handle_douyin(url):
    """Douyin: yt-dlp only (no CDP in cloud)"""
    try:
        import yt_dlp
        ydl_opts = {
            'quiet': True, 'no_warnings': True, 'skip_download': True,
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        # Get direct video URL from formats
        formats = info.get('formats', [])
        video_url = ''
        for f in formats:
            if f.get('vcodec') and f.get('acodec') and f.get('url'):
                video_url = f['url']
                break
        if not video_url:
            for f in formats:
                if f.get('vcodec') and f.get('url'):
                    video_url = f['url']
                    break

        return {
            'platform': '抖音',
            'platformIcon': 'fa-brands fa-tiktok',
            'title': info.get('title', 'Untitled'),
            'author': info.get('uploader', info.get('channel', 'Unknown')),
            'transcript': f"[抖音] 影片資訊提取成功\n\n標題: {info.get('title', 'N/A')}\n作者: {info.get('uploader', 'N/A')}\n時長: {info.get('duration', 0)}秒\n\n⚠️ 文案提取功能開發中\n此平台可下載影片。",
            'video_direct_url': video_url,
            'duration': info.get('duration', 0),
            'thumbnail': info.get('thumbnail', ''),
            'can_download_video': True,
            'can_download_audio': False,
        }
    except Exception as e:
        return {
            'platform': '抖音',
            'platformIcon': 'fa-brands fa-tiktok',
            'title': '提取失敗',
            'author': 'Unknown',
            'transcript': f'[抖音] 提取失敗: {str(e)}',
            'can_download_video': False,
            'error': str(e),
        }

def _handle_xiaohongshu(url):
    """Stub — Xiaohongshu needs local browser"""
    return {
        'platform': '小红书',
        'platformIcon': 'fa-regular fa-note-sticky',
        'title': '需桌面端輔助',
        'author': 'Xiaohongshu',
        'transcript': '⚠️ 小紅書提取需要在桌面端進行。\n\n請前往桌面版 anytocopy 工具或使用本機 Flask 後端。',
        'can_download_video': False,
        'can_download_audio': False,
        'error': 'xiaohongshu_requires_desktop',
    }

def _handle_ytdlp_platform(url, platform):
    import yt_dlp
    platform_name = get_platform_display(platform)
    platform_icon = get_platform_icon(platform)

    try:
        ydl_opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        return {
            'platform': platform_name,
            'platformIcon': platform_icon,
            'title': info.get('title', 'Untitled'),
            'author': info.get('uploader', info.get('channel', 'Unknown')),
            'transcript': f"[{platform_name}] 影片資訊提取成功\n\n標題: {info.get('title', 'N/A')}\n作者: {info.get('uploader', 'N/A')}\n時長: {info.get('duration', 0)}秒\n\n⚠️ 文案提取功能開發中",
            'video_url': url,
            'duration': info.get('duration', 0),
            'thumbnail': info.get('thumbnail', ''),
            'can_download_video': True,
            'can_download_audio': info.get('duration', 0) < 3600,
        }
    except Exception as e:
        return {
            'platform': platform_name,
            'platformIcon': platform_icon,
            'title': 'Unknown',
            'author': 'Unknown',
            'transcript': f'獲取資訊失敗: {str(e)}',
            'error': str(e),
        }

def _fallback_extract(url):
    try:
        import yt_dlp
        ydl_opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        platform_domain = urlparse(url).netloc
        return {
            'platform': platform_domain,
            'platformIcon': 'fa-solid fa-video',
            'title': info.get('title', 'Untitled'),
            'author': info.get('uploader', info.get('channel', 'Unknown')),
            'transcript': f'文案提取尚未支援此平台。\n標題: {info.get("title", "N/A")}',
            'video_url': url,
            'can_download_video': True,
        }
    except Exception as e:
        return {'error': str(e)}

# ═══════════════════════════════════════════
# Download (returns CDN URL, not streaming)
# ═══════════════════════════════════════════

@app.route('/api/download/video', methods=['POST'])
def download_video():
    """Return direct video URL for frontend to download"""
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'error': '請提供 URL'}), 400

    url = data['url'].strip()
    platform = data.get('platform', detect_platform(url))

    # If we already have a direct URL, just return it
    if data.get('video_direct_url'):
        return jsonify({
            'direct_url': data['video_direct_url'],
            'filename': data.get('filename', 'video'),
            'method': 'direct',
        })

    # Try to get direct URL via yt-dlp
    try:
        import yt_dlp
        ydl_opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

        formats = info.get('formats', [])
        # Prefer mp4 with both audio and video
        for f in formats:
            if f.get('vcodec') and f.get('acodec') and f.get('url') and f.get('ext') == 'mp4':
                return jsonify({
                    'direct_url': f['url'],
                    'title': info.get('title', 'video'),
                    'method': 'yt-dlp',
                })

        # Fallback: any format with video
        for f in formats:
            if f.get('vcodec') and f.get('url'):
                return jsonify({
                    'direct_url': f['url'],
                    'title': info.get('title', 'video'),
                    'method': 'yt-dlp-fallback',
                })

        return jsonify({'error': '無法取得直接影片網址'}), 400
    except Exception as e:
        return jsonify({'error': f'取得影片網址失敗: {str(e)}'}), 500

# ═══════════════════════════════════════════
# Pages list
# ═══════════════════════════════════════════

@app.route('/api/pages', methods=['GET'])
def get_pages():
    return jsonify({
        'pages': [
            {'path': '/', 'title': 'VideoText AI - 影片文案提取工具', 'icon': 'fa-solid fa-house', 'desc': '支援多平台，一鍵提取文案'},
            {'path': '/rewrite', 'title': 'AI 文案改寫', 'icon': 'fa-solid fa-wand-magic', 'desc': 'AI 智能改寫影片文案'},
        ]
    })

# ═══════════════════════════════════════════
# Vercel entry point
# ═══════════════════════════════════════════

# Flask `app` is the WSGI handler for Vercel
