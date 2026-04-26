#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
File download helper utilities
"""
import os
import subprocess
import tempfile
import shutil
from pathlib import Path


def download_video_ytdlp(url, output_dir=None, format_type='best'):
    """
    Download video using yt-dlp.
    Returns path to downloaded file.
    """
    if output_dir is None:
        output_dir = tempfile.mkdtemp()

    output_template = os.path.join(output_dir, '%(title)s.%(ext)s')

    ydl_opts = {
        'outtmpl': output_template,
        'quiet': True,
        'no_warnings': True,
    }

    if format_type == 'mp3':
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
    elif format_type == 'best':
        ydl_opts['format'] = 'best[ext=mp4]/best'

    import yt_dlp
    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=True)
        filename = ydl.prepare_filename(info)

        # Adjust extension for audio extraction
        if format_type == 'mp3':
            filename = Path(filename).with_suffix('.mp3').name
            return os.path.join(output_dir, filename)
        else:
            return filename


def download_file(url, output_dir, filename=None):
    """Download a file from URL to local path"""
    import requests

    if filename is None:
        filename = url.split('/')[-1].split('?')[0]

    os.makedirs(output_dir, exist_ok=True)
    output_path = os.path.join(output_dir, filename)

    resp = requests.get(url, stream=True, timeout=30)
    resp.raise_for_status()

    with open(output_path, 'wb') as f:
        for chunk in resp.iter_content(chunk_size=8192):
            f.write(chunk)

    return output_path


def cleanup_temp(dir_path):
    """Remove temporary directory"""
    if dir_path and os.path.exists(dir_path):
        try:
            shutil.rmtree(dir_path)
        except Exception:
            pass
