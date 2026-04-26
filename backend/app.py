#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
VideoText AI Backend API
AnyToCopy clone — video text extraction & watermark removal tool.

Architecture:
  app.py → detect platform → route to platform handler → return result

API Endpoints:
  POST /api/extract          — Extract transcript/metadata from URL
  POST /api/download/video   — Download video from URL
  POST /api/download/audio   — Download audio (MP3) from URL
  POST /api/download/text    — Download transcript as text file
  POST /api/download/zip     — Batch download as ZIP
  GET  /api/health           — Health check
  GET  /api/pages            — SPA page routes
  GET  /api/platforms        — List supported platforms
"""

import json
import os
import sys
import tempfile
import zipfile
from pathlib import Path
from urllib.parse import urlparse

from flask import Flask, request, jsonify, send_file
from flask_cors import CORS

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from utils.platform import (
    detect_platform, get_platform_display, get_platform_icon,
    get_platform_features, extract_youtube_id, extract_bilibili_bvid,
    PLATFORM_NAMES, PLATFORM_ICONS, PLATFORM_FEATURES,
)

app = Flask(__name__)
CORS(app)


# ============================================
# Health Check
# ============================================

@app.route('/api/health', methods=['GET'])
def health_check():
    return jsonify({
        'status': 'ok',
        'message': 'VideoText AI API is running',
        'version': '2.0',
        'platforms': list(PLATFORM_NAMES.values()),
    })


# ============================================
# Platforms List
# ============================================

@app.route('/api/platforms', methods=['GET'])
def list_platforms():
    """Return list of supported platforms with features"""
    result = []
    for key, name in PLATFORM_NAMES.items():
        result.append({
            'id': key,
            'name': name,
            'icon': PLATFORM_ICONS.get(key, 'fa-solid fa-video'),
            'features': get_platform_features(key),
        })
    return jsonify({'platforms': result})


# ============================================
# Main Extract API
# ============================================

@app.route('/api/extract', methods=['POST'])
def extract():
    """
    Main extraction API.
    Accepts: {"url": "https://..."}
    Returns: {"platform", "title", "author", "transcript", ...}
    """
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'error': '请提供URL'}), 400

    url = data['url'].strip()
    platform = detect_platform(url)

    if not platform:
        # Try yt-dlp as fallback
        info = _fallback_extract(url)
        if info.get('error'):
            return jsonify({'error': f'不支援的URL: {info["error"]}'}), 400
        return jsonify(info)

    # Route to platform handler
    if platform == 'youtube':
        result = _handle_youtube(url)
    elif platform == 'xiaohongshu':
        result = _handle_xiaohongshu(url)
    elif platform == 'bilibili':
        result = _handle_bilibili(url)
    elif platform == 'douyin':
        result = _handle_douyin(url)
    elif platform in ('tiktok', 'kuaishou', 'weibo'):
        result = _handle_ytdlp_platform(url, platform)
    else:
        return jsonify({'error': f'平台 {platform} 尚未支援'}), 400

    return jsonify(result)


# ============================================
# Download Endpoints
# ============================================

@app.route('/api/download/video', methods=['POST'])
def download_video_endpoint():
    """
    Download video from URL.
    Accepts: {"url": "...", "platform": "youtube"}
    Returns: video file
    """
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'error': '请提供URL'}), 400

    url = data['url']
    platform = data.get('platform', detect_platform(url))
    output_dir = tempfile.mkdtemp()

    try:
        import yt_dlp
        ydl_opts = {
            'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'format': 'best[ext=mp4]/best',
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filepath = ydl.prepare_filename(info)

        return send_file(
            filepath,
            as_attachment=True,
            download_name=Path(filepath).name,
            mimetype='video/mp4',
        )
    except Exception as e:
        import shutil
        shutil.rmtree(output_dir, ignore_errors=True)
        return jsonify({'error': f'下载失败: {str(e)}'}), 500


@app.route('/api/download/audio', methods=['POST'])
def download_audio_endpoint():
    """
    Extract audio (MP3) from video URL.
    Accepts: {"url": "..."}
    Returns: MP3 file
    """
    data = request.get_json()
    if not data or 'url' not in data:
        return jsonify({'error': '请提供URL'}), 400

    url = data['url']
    output_dir = tempfile.mkdtemp()

    try:
        import yt_dlp
        ydl_opts = {
            'outtmpl': os.path.join(output_dir, '%(title)s.%(ext)s'),
            'quiet': True,
            'no_warnings': True,
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
        }
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=True)
            filename = ydl.prepare_filename(info)
            filepath = Path(filename).with_suffix('.mp3')
            filepath = os.path.join(output_dir, filepath.name)

        return send_file(
            filepath,
            as_attachment=True,
            download_name=Path(filepath).name,
            mimetype='audio/mpeg',
        )
    except Exception as e:
        import shutil
        shutil.rmtree(output_dir, ignore_errors=True)
        return jsonify({'error': f'音频下载失败: {str(e)}'}), 500


@app.route('/api/download/text', methods=['POST'])
def download_text():
    """Download transcript as text file"""
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({'error': '请提供文字内容'}), 400

    text = data['text']
    filename = data.get('filename', 'transcript.txt')

    with tempfile.NamedTemporaryFile(mode='w', suffix='.txt', delete=False, encoding='utf-8') as f:
        f.write(text)
        temp_path = f.name

    return send_file(
        temp_path,
        as_attachment=True,
        download_name=filename,
        mimetype='text/plain; charset=utf-8',
    )


@app.route('/api/download/zip', methods=['POST'])
def download_zip():
    """
    Batch download multiple items as ZIP.
    Accepts: {"urls": ["url1", "url2", ...]}
    Returns: ZIP file
    """
    data = request.get_json()
    if not data or 'urls' not in data:
        return jsonify({'error': '请提供URL列表'}), 400

    urls = data['urls']
    output_dir = tempfile.mkdtemp()
    zip_path = os.path.join(output_dir, 'downloads.zip')

    try:
        import yt_dlp

        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for i, url in enumerate(urls):
                try:
                    sub_dir = os.path.join(output_dir, f'item_{i}')
                    os.makedirs(sub_dir, exist_ok=True)

                    ydl_opts = {
                        'outtmpl': os.path.join(sub_dir, '%(title)s.%(ext)s'),
                        'quiet': True,
                        'no_warnings': True,
                        'format': 'best[ext=mp4]/best',
                    }
                    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                        info = ydl.extract_info(url, download=True)
                        filepath = ydl.prepare_filename(info)

                    if os.path.exists(filepath):
                        zf.write(filepath, arcname=Path(filepath).name)
                except Exception:
                    continue

        if not os.path.exists(zip_path) or os.path.getsize(zip_path) < 100:
            return jsonify({'error': '批量下载失败，请确认URL是否有效'}), 400

        return send_file(
            zip_path,
            as_attachment=True,
            download_name='batch_download.zip',
            mimetype='application/zip',
        )
    except Exception as e:
        import shutil
        shutil.rmtree(output_dir, ignore_errors=True)
        return jsonify({'error': f'批量下载失败: {str(e)}'}), 500


# ============================================
# Platform-specific Handlers
# ============================================

def _handle_youtube(url):
    """Route to YouTube handler"""
    video_id = extract_youtube_id(url)
    if not video_id:
        return {'error': '无法解析YouTube视频ID'}

    from platforms.youtube import extract as youtube_extract
    return youtube_extract(video_id)


def _handle_bilibili(url):
    """Route to Bilibili handler"""
    from platforms.bilibili import extract as bilibili_extract
    return bilibili_extract(url)


def _handle_douyin(url):
    """Route to Douyin handler — 三層降級策略"""
    from platforms.douyin import extract as douyin_extract
    return douyin_extract(url)


def _handle_xiaohongshu(url):
    """Route to Xiaohongshu handler.
    First tries Windows XHS Proxy (port 5001), then falls back to local CDP."""
    # Try Windows XHS Proxy first
    try:
        import urllib.request as _urllib_req
        req = _urllib_req.Request(
            'http://172.22.199.229:5001',
            data=json.dumps({'url': url}).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        resp = _urllib_req.urlopen(req, timeout=120)
        result = json.loads(resp.read().decode('utf-8'))
        return result
    except Exception as proxy_err:
        print(f"[XHS] Proxy unavailable: {proxy_err}")
        pass

    # Fallback: try local CDP method (Windows only)
    try:
        from platforms.xiaohongshu import extract as xhs_extract
        result = xhs_extract(url)
        return result
    except Exception as e:
        return {
            'platform': 'xiaohongshu',
            'platformIcon': 'fa-regular fa-note-sticky',
            'transcript': '小紅書影片下載需要本機輔助。\\n'
                          '請啟動 XHS Proxy: python D:\\\\xhs_downloads\\\\xhs_proxy.py',
            'error': str(e),
        }


def _handle_ytdlp_platform(url, platform):
    """Use yt-dlp to get video info for any platform"""
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
            'transcript': (
                f"[{platform_name}] 视频信息提取成功\n\n"
                f"标题: {info.get('title', 'N/A')}\n"
                f"作者: {info.get('uploader', 'N/A')}\n"
                f"时长: {info.get('duration', 0)}秒\n\n"
                f"⚠️ 文案提取功能开发中\n"
                f"此平台的语音识别需下载视频后进行，将透过Whisper AI支援。"
            ),
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
            'transcript': f'获取信息失败: {str(e)}',
            'error': str(e),
        }


def _fallback_extract(url):
    """Try yt-dlp as fallback for unknown platforms"""
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
            'transcript': '文案提取尚未支援此平台。\n'
                          f'标题: {info.get("title", "N/A")}',
            'video_url': url,
            'can_download_video': True,
        }
    except Exception as e:
        return {'error': str(e)}


# ============================================
# SPA Page Routes (SEO metadata for frontend)
# ============================================

@app.route('/api/pages', methods=['GET'])
def get_pages():
    """Return list of available page routes"""
    return jsonify({
        'pages': [
            {'path': '/', 'title': 'VideoText AI - 视频文案提取 & 去水印工具', 'icon': 'fa-solid fa-house', 'desc': '支援50+平台，一键提取文案、去水印'},
            {'path': '/xiaohongshu', 'title': '小红书视频文案提取 - VideoText AI', 'icon': 'fa-regular fa-note-sticky', 'desc': '小红书视频/图文文案提取、Live图下载'},
            {'path': '/xiaohongshu-image', 'title': '小红书图文提取 - VideoText AI', 'icon': 'fa-regular fa-image', 'desc': '小红书图文笔记图片提取下载'},
            {'path': '/douyin', 'title': '抖音视频文案提取 - VideoText AI', 'icon': 'fa-brands fa-tiktok', 'desc': '抖音视频文案提取、去水印下载'},
            {'path': '/video-extract', 'title': '视频文件文案提取 - VideoText AI', 'icon': 'fa-solid fa-file-video', 'desc': '上传本地视频文件提取文案'},
            {'path': '/audio-extract', 'title': '音频文件转文字 - VideoText AI', 'icon': 'fa-solid fa-file-audio', 'desc': '上传音频文件转文字'},
            {'path': '/batch', 'title': '批量文案提取 - VideoText AI', 'icon': 'fa-solid fa-layer-group', 'desc': '批量处理多链接文案提取'},
            {'path': '/rewrite', 'title': 'AI文案改写 - VideoText AI', 'icon': 'fa-solid fa-wand-magic', 'desc': 'AI智能改写视频文案'},
        ]
    })


# ============================================
# Startup
# ============================================

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', '1').lower() in ('1', 'true', 'yes')

    print(f"🚀 VideoText AI Backend v2.0 starting on port {port}")
    print(f"📡 Supported platforms: YouTube, Bilibili, 小红书 (CDP/Windows), 抖音 (yt-dlp)")
    print(f"📦 Features: Extract, Download Video/Audio/Text, Batch ZIP")

    app.run(host='0.0.0.0', port=port, debug=debug)
