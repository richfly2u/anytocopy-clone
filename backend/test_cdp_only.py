#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""測試 _cdp_intercept 單獨回傳，跳過 proxy 繞路"""
import sys, json, os, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')

sys.path.insert(0, r'D:\我的知識庫\anytocopy-clone\backend')
os.environ['CDP_PORT'] = '9223'

# 直接 import xiaohongshu 模組
from platforms.xiaohongshu import _cdp_intercept, resolve_short_url, extract_note_id

url = "https://www.xiaohongshu.com/explore/69ed5a8a0000000036018e7e?xsec_token=ABSuBlYabW8IF4VOAsAh3F2ERWs6"

print(f"測試 URL: {url}")
print(f"resolved: {resolve_short_url(url)}")
print(f"note_id: {extract_note_id(url)}")
print()

result = _cdp_intercept(url)
print(json.dumps(result, indent=2, ensure_ascii=False))
