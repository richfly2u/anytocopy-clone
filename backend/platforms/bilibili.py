#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Bilibili (B站) platform handler.
Uses free public API + subtitle extraction.

API docs:
- Video info: api.bilibili.com/x/web-interface/view?bvid={bvid}
- Subtitle list: api.bilibili.com/x/player/v2?bvid={bvid}&cid={cid}
"""
import json
import re
import requests


def get_bvid(url):
    """Extract BV id from Bilibili URL"""
    m = re.search(r'(?:video/)(BV[a-zA-Z0-9]+)', url)
    if m:
        return m.group(1)
    m = re.search(r'(BV[a-zA-Z0-9]{10,})', url)
    if m:
        return m.group(1)
    return None


def extract(url):
    """
    Extract Bilibili video info + subtitles.
    Returns: dict with platform, title, author, transcript, video_url, cover_url
    """
    bvid = get_bvid(url)
    if not bvid:
        return {'error': 'Could not extract Bilibili video ID from URL'}

    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        'Referer': 'https://www.bilibili.com/',
    }

    # Step 1: Get video info
    api_url = f'https://api.bilibili.com/x/web-interface/view?bvid={bvid}'
    try:
        resp = requests.get(api_url, headers=headers, timeout=15)
        data = resp.json()
    except Exception as e:
        return {'error': f'Failed to fetch Bilibili API: {str(e)}'}

    if data.get('code') != 0:
        return {'error': f'Bilibili API error: {data.get("message", "unknown")}'}

    vdata = data.get('data', {})
    title = vdata.get('title', 'Untitled')
    author = vdata.get('owner', {}).get('name', 'Unknown')
    desc = vdata.get('desc', '')
    pic = vdata.get('pic', '')
    cid = vdata.get('cid', 0)  # Content ID for subtitles
    duration = vdata.get('duration', 0)
    # View/stat counts
    stat = vdata.get('stat', {})
    view_count = stat.get('view', 0)
    like_count = stat.get('like', 0)

    # Step 2: Try to get subtitles (CC)
    transcript_text = None
    subtitle_info = []

    if cid:
        try:
            sub_url = f'https://api.bilibili.com/x/player/v2?bvid={bvid}&cid={cid}'
            sub_resp = requests.get(sub_url, headers=headers, timeout=10)
            sub_data = sub_resp.json()

            if sub_data.get('code') == 0:
                subtitle_data = sub_data.get('data', {}).get('subtitle', {})
                subtitles = subtitle_data.get('subtitles', [])

                for sub in subtitles:
                    sub_url_full = sub.get('subtitle_url', '')
                    sub_lang = sub.get('lan_doc', 'Unknown')

                    # Fetch subtitle content
                    if sub_url_full:
                        try:
                            sub_content = requests.get(
                                f'https:{sub_url_full}' if sub_url_full.startswith('//') else sub_url_full,
                                headers=headers,
                                timeout=10
                            )
                            sub_json = sub_content.json()
                            bodies = sub_json.get('body', [])
                            sub_text = '\n'.join([b.get('content', '') for b in bodies])
                            subtitle_info.append({
                                'lang': sub_lang,
                                'text': sub_text,
                            })
                        except Exception:
                            pass
        except Exception:
            pass

        # Combine all subtitle texts
        if subtitle_info:
            transcript_text = subtitle_info[0]['text']

    result = {
        'platform': 'B站',
        'platformIcon': 'fa-brands fa-bilibili',
        'title': title,
        'author': author,
        'transcript': transcript_text or desc or 'No description available.',
        'video_url': f'https://www.bilibili.com/video/{bvid}',
        'cover_url': pic,
        'bvid': bvid,
        'duration': duration,
        'stats': {
            'views': view_count,
            'likes': like_count,
        },
        'can_download_video': True,
        'can_download_audio': True,
    }

    if not transcript_text and not result['transcript']:
        result['transcript'] = f'[{author}] {title}\nNo subtitles available for this video.'
        result['error'] = 'No subtitles'

    return result


def download_video(bvid, output_dir):
    """Download Bilibili video via yt-dlp"""
    url = f'https://www.bilibili.com/video/{bvid}'
    import os
    import yt_dlp

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


if __name__ == '__main__':
    import sys
    test = sys.argv[1] if len(sys.argv) > 1 else None
    if test:
        result = extract(test)
        print(json.dumps(result, indent=2, ensure_ascii=False))
