#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VideoText AI Backend API
Video transcript extraction, watermark removal, audio conversion
"""

import os
import json
import re
import subprocess
import tempfile
import shutil
from pathlib import Path
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import yt_dlp
import requests

app = Flask(__name__)
CORS(app)

# ============================================
# Platform URL Detector
# ============================================

PLATFORM_PATTERNS = {
    'youtube': [
        r'(?:https?://)?(?:www\.)?(?:youtube\.com|youtu\.be)/',
        r'(?:https?://)?(?:www\.)?youtube\.com/shorts/',
    ],
    'douyin': [
        r'(?:https?://)?(?:www\.)?douyin\.com/',
        r'(?:https?://)?v\.douyin\.com/',
        r'(?:https?://)?(?:www\.)?iesdouyin\.com/',
    ],
    'tiktok': [
        r'(?:https?://)?(?:www\.)?tiktok\.com/',
        r'(?:https?://)?(?:m\.)?tiktok\.com/',
    ],
    'xiaohongshu': [
        r'(?:https?://)?(?:www\.)?xiaohongshu\.com/',
        r'(?:https?://)?xhslink\.com/',
    ],
    'bilibili': [
        r'(?:https?://)?(?:www\.)?bilibili\.com/',
        r'(?:https?://)?b23\.tv/',
    ],
    'kuaishou': [
        r'(?:https?://)?(?:www\.)?kuaishou\.com/',
        r'(?:https?://)?v\.kuaishou\.com/',
    ],
    'weibo': [
        r'(?:https?://)?(?:www\.)?weibo\.com/',
        r'(?:https?://)?weibo\.(?:tv|video)/',
    ],
}

PLATFORM_NAMES = {
    'youtube': 'YouTube', 'douyin': 'Douyin', 'tiktok': 'TikTok',
    'xiaohongshu': 'Xiaohongshu', 'bilibili': 'Bilibili', 'kuaishou': 'Kuaishou', 'weibo': 'Weibo',
}

PLATFORM_ICONS = {
    'youtube': 'fa-brands fa-youtube', 'douyin': 'fa-brands fa-tiktok',
    'tiktok': 'fa-brands fa-tiktok', 'xiaohongshu': 'fa-regular fa-note-sticky',
    'bilibili': 'fa-brands fa-bilibili', 'kuaishou': 'fa-solid fa-video',
    'weibo': 'fa-brands fa-weibo',
}


def detect_platform(url):
    """Detect which platform a URL belongs to"""
    url_lower = url.lower()
    for platform, patterns in PLATFORM_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, url_lower):
                return platform
    return None


# ============================================
# YouTube Transcript Extractor
# ============================================

# YouTube API Key from environment
YOUTUBE_API_KEY = os.environ.get('YOUTUBE_API_KEY', '')

def extract_youtube_transcript(video_id):
    """Extract YouTube transcript using YouTube Data API + yt-dlp fallback"""
    title = 'Untitled'
    author = 'Unknown'

    # Step 1: Try yt-dlp for metadata + subtitles
    try:
        url = f"https://www.youtube.com/watch?v={video_id}"
        ydl_opts = {
            'writesubtitles': True,
            'writeautomaticsub': True,
            'subtitlesformat': 'vtt',
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
        }

        with tempfile.TemporaryDirectory() as tmpdir:
            ydl_opts['outtmpl'] = os.path.join(tmpdir, '%(id)s.%(ext)s')

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                title = info.get('title', 'Untitled')
                author = info.get('uploader', 'Unknown')

                # Try downloading subtitles
                ydl.download([url])

                sub_files = list(Path(tmpdir).glob('*.vtt'))
                if not sub_files:
                    sub_files = list(Path(tmpdir).glob('*.srt'))

                if sub_files:
                    with open(sub_files[0], 'r', encoding='utf-8') as f:
                        raw = f.read()
                    transcript = parse_vtt(raw)
                    if transcript:
                        return {
                            'platform': 'YouTube',
                            'platformIcon': 'fa-brands fa-youtube',
                            'title': title,
                            'author': author,
                            'transcript': transcript,
                            'video_url': url,
                        }

    except Exception:
        pass  # Fall through to API methods

    # Step 2: Try YouTube Data API for captions
    if YOUTUBE_API_KEY:
        try:
            # Get caption tracks
            captions_url = f"https://www.googleapis.com/youtube/v3/captions?part=snippet&videoId={video_id}&key={YOUTUBE_API_KEY}"
            resp = requests.get(captions_url, timeout=10)
            if resp.status_code == 200:
                items = resp.json().get('items', [])
                if items:
                    # Prefer 'asr' (auto-generated) or first available
                    caption_id = None
                    for item in items:
                        snip = item.get('snippet', {})
                        lang = snip.get('language', '')
                        track_kind = snip.get('trackKind', '')
                        if 'zh' in lang and caption_id is None:
                            caption_id = item['id']
                        if track_kind == 'asr' and caption_id is None:
                            caption_id = item['id']
                    if caption_id is None and items:
                        caption_id = items[0]['id']

                    if caption_id:
                        # Download caption content
                        dl_url = f"https://www.googleapis.com/youtube/v3/captions/{caption_id}?key={YOUTUBE_API_KEY}&tfmt=srt"
                        dl_resp = requests.get(dl_url, timeout=15)
                        if dl_resp.status_code == 200:
                            transcript = parse_vtt(dl_resp.text) if 'WEBVTT' in dl_resp.text else dl_resp.text[:5000]
                            return {
                                'platform': 'YouTube',
                                'platformIcon': 'fa-brands fa-youtube',
                                'title': title,
                                'author': author,
                                'transcript': transcript,
                                'video_url': url,
                            }

            # Get video metadata
            video_url = f"https://www.googleapis.com/youtube/v3/videos?part=snippet&id={video_id}&key={YOUTUBE_API_KEY}"
            vresp = requests.get(video_url, timeout=10)
            if vresp.status_code == 200:
                vitems = vresp.json().get('items', [])
                if vitems:
                    snippet = vitems[0].get('snippet', {})
                    title = snippet.get('title', title)
                    author = snippet.get('channelTitle', author)
                    desc = (snippet.get('description') or '')[:2000]
                    if desc:
                        return {
                            'platform': 'YouTube',
                            'platformIcon': 'fa-brands fa-youtube',
                            'title': title,
                            'author': author,
                            'transcript': desc,
                            'video_url': url,
                        }

        except Exception:
            pass

    return {
        'platform': 'YouTube',
        'platformIcon': 'fa-brands fa-youtube',
        'title': title,
        'author': author,
        'transcript': 'Could not extract transcript. The video may have no captions available.',
        'error': 'No captions available',
    }


def parse_vtt(vtt_content):
    """Parse VTT subtitle format to plain text"""
    lines = vtt_content.split('\n')
    text_lines = []

    for line in lines:
        if line.strip() == '':
            continue
        if line.startswith('WEBVTT'):
            continue
        if line.startswith('Kind:'):
            continue
        if line.startswith('Language:'):
            continue
        if '-->' in line:
            continue
        if re.match(r'^\d+$', line.strip()):
            continue

        clean = re.sub(r'<[^>]+>', '', line).strip()
        if clean:
            text_lines.append(clean)

    return '\n'.join(text_lines)


# ============================================
# General Video Info Extractor
# ============================================

def extract_video_info(url):
    """Extract general video info using yt-dlp"""
    try:
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'skip_download': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)

            return {
                'title': info.get('title', 'Untitled'),
                'author': info.get('uploader', info.get('channel', 'Unknown')),
                'duration': info.get('duration', 0),
                'description': (info.get('description') or '')[:500],
            }

    except Exception as e:
        return {'error': str(e)}


# ============================================
# API Routes
# ============================================

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({'status': 'ok', 'message': 'VideoText AI API is running'})


@app.route('/api/extract', methods=['POST'])
def extract():
    """Main extraction API endpoint"""
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'error': 'Please provide a video URL'}), 400

    url = data['url'].strip()
    platform = detect_platform(url)

    if not platform:
        info = extract_video_info(url)
        if 'error' in info:
            return jsonify({'error': f'Could not parse this URL: {info["error"]}'}), 400
        return jsonify({
            'platform': 'Unknown',
            'platformIcon': 'fa-solid fa-video',
            'title': info.get('title', 'Unknown'),
            'author': info.get('author', 'Unknown'),
            'transcript': 'Transcript extraction not yet supported for this platform',
            'info': info,
        })

    if platform == 'youtube':
        video_id = None
        if 'youtu.be/' in url:
            video_id = url.split('youtu.be/')[-1].split('?')[0]
        elif 'watch?v=' in url:
            video_id = url.split('watch?v=')[-1].split('&')[0]
        elif 'shorts/' in url:
            video_id = url.split('shorts/')[-1].split('?')[0]

        if video_id:
            return jsonify(extract_youtube_transcript(video_id))
        else:
            return jsonify({'error': 'Could not parse YouTube video ID'}), 400

    elif platform in ('douyin', 'tiktok', 'xiaohongshu', 'bilibili', 'kuaishou', 'weibo'):
        info = extract_video_info(url)
        platform_name = PLATFORM_NAMES.get(platform, platform)
        platform_icon = PLATFORM_ICONS.get(platform, 'fa-solid fa-video')

        return jsonify({
            'platform': platform_name,
            'platformIcon': platform_icon,
            'title': info.get('title', 'Untitled'),
            'author': info.get('author', 'Unknown Creator'),
            'transcript': (
                f"[{platform_name}] Transcript extraction in development\n\n"
                f"This feature requires video download + OCR or speech recognition.\n"
                f"Supported extraction methods coming soon:\n"
                f"  - Built-in subtitle extraction\n"
                f"  - OCR text recognition\n"
                f"  - Whisper speech-to-text\n\n"
                f"Video Info:\n"
                f"  Title: {info.get('title', 'Unknown')}\n"
                f"  Author: {info.get('author', 'Unknown')}"
            ),
            'info': info,
        })

    else:
        return jsonify({'error': 'Unsupported platform'}), 400


@app.route('/api/download/transcript', methods=['POST'])
def download_transcript():
    """Download transcript as text file"""
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({'error': 'Please provide transcript text'}), 400

    text = data['text']
    filename = data.get('filename', 'transcript.txt')

    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(text)
        temp_path = f.name

    return send_file(temp_path, as_attachment=True, download_name=filename)


# ============================================
# Startup
# ============================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', '1').lower() in ('1', 'true', 'yes')
    app.run(host='0.0.0.0', port=port, debug=debug)
