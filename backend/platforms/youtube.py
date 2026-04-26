#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
YouTube platform handler.
Extracts transcripts, metadata, video/audio downloads.
"""

import os
import tempfile
from pathlib import Path

import yt_dlp
from youtube_transcript_api import YouTubeTranscriptApi


def extract(video_id):
    """
    Extract YouTube video transcript + metadata.
    Returns dict with platform, title, author, transcript, video_url.
    """
    url = f"https://www.youtube.com/watch?v={video_id}"
    title = 'Untitled'
    author = 'Unknown'
    duration = 0
    thumbnail = ''

    # Step 1: Get metadata from yt-dlp
    try:
        ydl_opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            title = info.get('title', 'Untitled')
            author = info.get('uploader', 'Unknown')
            duration = info.get('duration', 0)
            thumbnail = info.get('thumbnail', '')
    except Exception:
        pass

    # Step 2: Get transcript via youtube_transcript_api
    transcript_text = None
    transcript_language = None
    try:
        api = YouTubeTranscriptApi()
        transcript = api.fetch(video_id, languages=['zh-Hant', 'zh-Hans', 'zh', 'en'])
        transcript_text = '\n'.join([item.text for item in transcript])
        transcript_language = 'auto'
    except Exception:
        try:
            api = YouTubeTranscriptApi()
            transcript = api.fetch(video_id)
            transcript_text = '\n'.join([item.text for item in transcript])
            transcript_language = 'auto'
        except Exception:
            pass

    result = {
        'platform': 'YouTube',
        'platformIcon': 'fa-brands fa-youtube',
        'title': title,
        'author': author,
        'transcript': transcript_text or 'No transcript available for this video.',
        'video_url': url,
        'duration': duration,
        'thumbnail': thumbnail,
        'can_download_video': True,
        'can_download_audio': True,
    }

    if not transcript_text:
        # Try description as fallback
        try:
            ydl_opts = {'quiet': True, 'no_warnings': True, 'skip_download': True}
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                desc = (info.get('description') or '')[:2000]
                if desc:
                    result['transcript'] = desc
                    return result
        except Exception:
            pass
        result['error'] = 'No captions'

    return result


def _ensure_output_dir(output_dir):
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    return output_dir


def download_video(video_id, output_dir=None):
    """Download YouTube video as MP4. Returns file path."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    if output_dir is None:
        output_dir = tempfile.mkdtemp()
    _ensure_output_dir(output_dir)

    output_template = os.path.join(output_dir, '%(title)s.%(ext)s')
    ydl_opts = {
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
        'format': 'best[ext=mp4]/best',
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        return ydl.prepare_filename(info)


def download_audio_stream(video_id):
    """Get audio stream URL (for server-side streaming). Returns URL."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'format': 'bestaudio/best',
    }
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)
        # Find best audio format
        formats = info.get('formats', [])
        for f in formats:
            if f.get('acodec') and f.get('acodec') != 'none':
                return f.get('url')
        return None


def download_audio(video_id, output_dir=None):
    """Download YouTube video audio as MP3. Returns file path."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    if output_dir is None:
        output_dir = tempfile.mkdtemp()
    _ensure_output_dir(output_dir)

    output_template = os.path.join(output_dir, '%(title)s.%(ext)s')
    ydl_opts = {
        'outtmpl': output_template,
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
        return os.path.join(output_dir, Path(filename).with_suffix('.mp3').name)
