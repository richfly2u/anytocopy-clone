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

# Load .env if exists
_env_path = os.path.join(os.path.dirname(os.path.abspath(__file__)), '.env')
if os.path.exists(_env_path):
    with open(_env_path, 'r', encoding='utf-8') as _f:
        for _line in _f:
            _line = _line.strip()
            if _line and not _line.startswith('#') and '=' in _line:
                _k, _v = _line.split('=', 1)
                _k, _v = _k.strip(), _v.strip().strip('"').strip("'")
                if _v and not os.environ.get(_k):
                    os.environ[_k] = _v

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
    Also accepts: {"video_direct_url": "https://..."} for direct CDN downloads
    Returns: video file
    """
    data = request.get_json()
    if not data or ('url' not in data and 'video_direct_url' not in data):
        return jsonify({'error': '请提供URL'}), 400

    url = data.get('url', '')
    output_dir = tempfile.mkdtemp()

    # Handle direct CDN URL download (e.g. douyin video_direct_url passed directly)
    video_direct_url = data.get('video_direct_url')
    if video_direct_url:
        import requests as _req
        try:
            resp = _req.get(video_direct_url, stream=True, timeout=60)
            resp.raise_for_status()
            ext = 'mp4'
            filepath = os.path.join(output_dir, f'video.{ext}')
            with open(filepath, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            filename = data.get('filename', 'video')
            return send_file(filepath, as_attachment=True,
                           download_name=f"{filename[:30]}.{ext}",
                           mimetype='video/mp4')
        except Exception as e:
            import shutil
            shutil.rmtree(output_dir, ignore_errors=True)
            return jsonify({'error': f'直接下載失敗: {str(e)}'}), 500

    platform = data.get('platform', detect_platform(url))

    # 小紅書 / 抖音走 platform handler
    if platform == 'xiaohongshu':
        from platforms.xiaohongshu import extract as xhs_extract
        info = xhs_extract(url)
        if 'video_direct_url' in info:
            # 直接下載 CDN URL
            import requests as _req
            resp = _req.get(info['video_direct_url'], stream=True, timeout=60)
            resp.raise_for_status()
            ext = 'mp4'
            filepath = os.path.join(output_dir, f"xhs_video.{ext}")
            with open(filepath, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return send_file(filepath, as_attachment=True,
                           download_name=f"{info.get('title','xhs')[:30]}.{ext}",
                           mimetype='video/mp4')
        return jsonify({'error': '無法取得小紅書影片 URL'}), 400

    if platform == 'douyin':
        from platforms.douyin import extract as dy_extract
        info = dy_extract(url)
        if 'video_direct_url' in info:
            import requests as _req
            resp = _req.get(info['video_direct_url'], stream=True, timeout=60)
            resp.raise_for_status()
            filepath = os.path.join(output_dir, 'douyin_video.mp4')
            with open(filepath, 'wb') as f:
                for chunk in resp.iter_content(chunk_size=8192):
                    f.write(chunk)
            return send_file(filepath, as_attachment=True,
                           download_name=f"{info.get('title','douyin')[:30]}.mp4",
                           mimetype='video/mp4')
        return jsonify({'error': '無法取得抖音影片 URL'}), 400

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


@app.route('/api/download/images', methods=['POST'])
def download_images_endpoint():
    """
    打包下載小紅書圖文筆記的全部圖片。
    Accepts: {"images": ["url1", "url2", ...], "title": "筆記標題"}
    Returns: ZIP file containing all images
    """
    data = request.get_json()
    if not data or 'images' not in data:
        return jsonify({'error': '请提供圖片列表'}), 400

    images = data['images']
    if not images or len(images) == 0:
        return jsonify({'error': '圖片列表為空'}), 400

    title = data.get('title', 'xiaohongshu_images')[:50]
    output_dir = tempfile.mkdtemp()
    zip_path = os.path.join(output_dir, f'{title}.zip')

    try:
        import requests as _req
        with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
            for i, img_url in enumerate(images):
                try:
                    resp = _req.get(img_url, stream=True, timeout=30)
                    resp.raise_for_status()
                    ext = 'jpg'
                    ct = resp.headers.get('Content-Type', '')
                    if 'png' in ct:
                        ext = 'png'
                    elif 'webp' in ct:
                        ext = 'webp'
                    elif 'gif' in ct:
                        ext = 'gif'
                    temp_path = os.path.join(output_dir, f'image_{i+1}.{ext}')
                    with open(temp_path, 'wb') as f:
                        for chunk in resp.iter_content(chunk_size=8192):
                            f.write(chunk)
                    zf.write(temp_path, arcname=f'image_{i+1}.{ext}')
                except Exception as e:
                    print(f"[DownloadImages] Failed to download image {i}: {e}")
                    continue

        if not os.path.exists(zip_path) or os.path.getsize(zip_path) < 100:
            return jsonify({'error': '圖片打包失败'}), 400

        return send_file(
            zip_path,
            as_attachment=True,
            download_name=f'{title}.zip',
            mimetype='application/zip',
        )
    except Exception as e:
        import shutil
        shutil.rmtree(output_dir, ignore_errors=True)
        return jsonify({'error': f'圖片打包失败: {str(e)}'}), 500


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
    """Route to Xiaohongshu handler — directly uses local CDP extract."""
    try:
        from platforms.xiaohongshu import extract as xhs_extract
        result = xhs_extract(url)
        return result
    except Exception as e:
        return {
            'platform': 'xiaohongshu',
            'platformIcon': 'fa-regular fa-note-sticky',
            'transcript': '小紅書影片下載需要本機輔助。\\n'
                          '請參考 README 啟動相關服務。',
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
# Phase 3: AI Tools (Rewrite, OCR, Watermark)
# ============================================

from utils.ai_tools import rewrite_text, ocr_image, remove_logo


@app.route('/api/rewrite', methods=['POST'])
def api_rewrite():
    """AI 文案改寫。Accepts: {\"text\": \"...\", \"style\": \"casual\"}"""
    data = request.get_json()
    if not data or 'text' not in data:
        return jsonify({'success': False, 'error': '請提供文案內容'}), 400

    text = data['text'].strip()
    style = data.get('style', 'casual')

    if not text:
        return jsonify({'success': False, 'error': '文案內容不能為空'}), 400

    result = rewrite_text(text, style)
    return jsonify(result)


@app.route('/api/ocr', methods=['POST'])
def api_ocr():
    """圖片 OCR。Accepts: {\"image_url\": \"...\", \"language\": \"zh\"} 或 multipart file"""
    if request.content_type and 'multipart' in request.content_type:
        if 'image' not in request.files:
            return jsonify({'success': False, 'error': '請上傳圖片'}), 400
        file = request.files['image']
        if file.filename == '':
            return jsonify({'success': False, 'error': '請選擇圖片'}), 400

        temp_path = os.path.join(tempfile.mkdtemp(), file.filename)
        file.save(temp_path)
        language = request.form.get('language', 'zh')
        result = ocr_image(temp_path, language)
        os.unlink(temp_path)
        return jsonify(result)

    data = request.get_json()
    if not data or 'image_url' not in data:
        return jsonify({'success': False, 'error': '請提供 image_url 或上傳圖片'}), 400

    language = data.get('language', 'zh')
    result = ocr_image(data['image_url'], language)
    return jsonify(result)


@app.route('/api/watermark/remove', methods=['POST'])
def api_remove_watermark():
    """去水印。Accepts: {\"image_url\": \"...\", \"method\": \"auto\"}"""
    data = request.get_json()
    if not data or 'image_url' not in data:
        return jsonify({'success': False, 'error': '請提供 image_url'}), 400

    method = data.get('method', 'auto')

    # Render 環境 — Lama 不可用，提示使用者
    ON_RENDER = os.environ.get('RENDER', '').lower() in ('1', 'true')
    if ON_RENDER and method in ('auto', 'lama'):
        return jsonify({
            'success': False,
            'error': 'AI 去水印僅限本地模式可用，請在本機啟動 Flask 後端使用。',
            'local_methods': ['inpaint', 'blur', 'crop'],
        }), 400

    result = remove_logo(data['image_url'], method=method)
    if not result.get('success'):
        return jsonify(result), 400

    return send_file(
        result['output_path'],
        mimetype='image/png',
        as_attachment=True,
        download_name='watermark_removed.png',
    )


# ============================================
# Phase 4: Local File Extraction (Video/Audio Upload)
# ============================================


@app.route('/api/extract/video', methods=['POST'])
def api_extract_video():
    """上傳本地影片檔案，提取文案（Whisper 語音辨識）"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '請上傳影片檔案'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': '請選擇影片檔案'}), 400

    output_dir = tempfile.mkdtemp()
    try:
        # 保存上傳檔案
        ext = Path(file.filename).suffix.lower()
        allowed_exts = {'.mp4', '.avi', '.mov', '.mkv', '.webm', '.flv', '.wmv', '.m4v'}
        if ext not in allowed_exts:
            return jsonify({'success': False, 'error': f'不支援的影片格式: {ext}'}), 400

        input_path = os.path.join(output_dir, f'input{ext}')
        file.save(input_path)

        # 嘗試 Whisper（如果有安裝）
        transcript = _transcribe_audio(input_path)

        return jsonify({
            'success': True,
            'filename': file.filename,
            'transcript': transcript,
            'method': 'whisper' if transcript else 'unsupported',
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f'影片處理失敗: {str(e)}'}), 500
    finally:
        import shutil
        shutil.rmtree(output_dir, ignore_errors=True)


@app.route('/api/extract/audio', methods=['POST'])
def api_extract_audio():
    """上傳本地音訊檔案，轉文字（Whisper 語音辨識）"""
    if 'file' not in request.files:
        return jsonify({'success': False, 'error': '請上傳音訊檔案'}), 400

    file = request.files['file']
    if file.filename == '':
        return jsonify({'success': False, 'error': '請選擇音訊檔案'}), 400

    output_dir = tempfile.mkdtemp()
    try:
        ext = Path(file.filename).suffix.lower()
        allowed_exts = {'.mp3', '.wav', '.ogg', '.m4a', '.flac', '.aac', '.wma'}
        if ext not in allowed_exts:
            return jsonify({'success': False, 'error': f'不支援的音訊格式: {ext}'}), 400

        input_path = os.path.join(output_dir, f'input{ext}')
        file.save(input_path)

        transcript = _transcribe_audio(input_path)

        return jsonify({
            'success': True,
            'filename': file.filename,
            'transcript': transcript,
            'method': 'whisper' if transcript else 'unsupported',
        })
    except Exception as e:
        return jsonify({'success': False, 'error': f'音訊處理失敗: {str(e)}'}), 500
    finally:
        import shutil
        shutil.rmtree(output_dir, ignore_errors=True)


def _transcribe_audio(audio_path):
    """使用 Whisper 進行語音轉文字（如有安裝）"""
    try:
        import whisper
        model = whisper.load_model('base')
        result = model.transcribe(audio_path, language='zh')
        return result.get('text', '').strip()
    except ImportError:
        # 無 Whisper → 嘗試用 ffmpeg + yt-dlp 的 post-processor
        try:
            import subprocess
            result = subprocess.run(
                ['which', 'whisper', 'faster-whisper'],
                capture_output=True, text=True, timeout=5
            )
            if result.stdout.strip():
                # 有 faster-whisper 或其他 CLI
                proc = subprocess.run(
                    ['faster-whisper', audio_path, '--language', 'zh', '--output_dir', os.path.dirname(audio_path)],
                    capture_output=True, text=True, timeout=300
                )
                return proc.stdout.strip()
        except Exception:
            pass
        return ''
    except Exception as e:
        print(f"[Whisper] 轉寫失敗: {e}")
        return ''

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
    import sys, io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', '1').lower() in ('1', 'true', 'yes')

    print(f"VideoText AI Backend v2.0 starting on port {port}")
    print(f"Supported platforms: YouTube, Bilibili, RedNote (CDP/Windows), Douyin (yt-dlp)")
    print(f"Features: Extract, Download Video/Audio/Text, Batch ZIP")

    app.run(host='0.0.0.0', port=port, debug=debug)
