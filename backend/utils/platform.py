#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Platform detection utility
"""
import re

# URL patterns per platform
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
    'youtube': 'YouTube',
    'douyin': '抖音',
    'tiktok': 'TikTok',
    'xiaohongshu': '小红书',
    'bilibili': 'B站',
    'kuaishou': '快手',
    'weibo': '微博',
}

PLATFORM_ICONS = {
    'youtube': 'fa-brands fa-youtube',
    'douyin': 'fa-brands fa-tiktok',
    'tiktok': 'fa-brands fa-tiktok',
    'xiaohongshu': 'fa-regular fa-note-sticky',
    'bilibili': 'fa-brands fa-bilibili',
    'kuaishou': 'fa-solid fa-video',
    'weibo': 'fa-brands fa-weibo',
}

# Which platforms support which features
PLATFORM_FEATURES = {
    'youtube': {'transcript': True, 'video_download': True, 'audio_download': True},
    'douyin': {'transcript': False, 'video_download': True, 'audio_download': False},
    'tiktok': {'transcript': False, 'video_download': True, 'audio_download': False},
    'xiaohongshu': {'transcript': False, 'video_download': True, 'audio_download': True, 'image_download': True},
    'bilibili': {'transcript': True, 'video_download': True, 'audio_download': True},
    'kuaishou': {'transcript': False, 'video_download': True, 'audio_download': False},
    'weibo': {'transcript': False, 'video_download': True, 'audio_download': False},
}


def detect_platform(url):
    """Detect which platform a URL belongs to"""
    url_lower = url.lower()
    for platform, patterns in PLATFORM_PATTERNS.items():
        for pattern in patterns:
            if re.search(pattern, url_lower):
                return platform
    return None


def get_platform_display(platform):
    """Get human-readable platform name"""
    return PLATFORM_NAMES.get(platform, platform)


def get_platform_icon(platform):
    """Get Font Awesome icon class for platform"""
    return PLATFORM_ICONS.get(platform, 'fa-solid fa-video')


def get_platform_features(platform):
    """Get supported features for a platform"""
    return PLATFORM_FEATURES.get(platform, {})


def extract_youtube_id(url):
    """Extract YouTube video ID from various URL formats"""
    video_id = None
    if 'youtu.be/' in url:
        video_id = url.split('youtu.be/')[-1].split('?')[0]
    elif 'watch?v=' in url:
        video_id = url.split('watch?v=')[-1].split('&')[0]
    elif 'shorts/' in url:
        video_id = url.split('shorts/')[-1].split('?')[0]
    elif 'embed/' in url:
        video_id = url.split('embed/')[-1].split('?')[0]
    return video_id


def extract_bilibili_bvid(url):
    """Extract Bilibili BV id from URL"""
    m = re.search(r'(?:video/)(BV[a-zA-Z0-9]+)', url)
    if m:
        return m.group(1)
    m = re.search(r'(BV[a-zA-Z0-9]{10,})', url)
    if m:
        return m.group(1)
    return None


def extract_xhs_note_id(url):
    """Extract Xiaohongshu note ID from URL"""
    # explore/note/xxxxx
    m = re.search(r'/explore/([a-f0-9]{32})', url)
    if m:
        return m.group(1)
    # discover/item/xxxxx
    m = re.search(r'/discover/item/([a-f0-9]{32})', url)
    if m:
        return m.group(1)
    return None
