#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""直接調用 API 路由測試"""
import sys, json, os
sys.path.insert(0, 'D:/我的知識庫/anytocopy-clone/backend')
os.environ['CDP_PORT'] = '9223'

from platforms.xiaohongshu import extract

url = "https://www.xiaohongshu.com/explore/69ed5a8a0000000036018e7e?xsec_token=ABSuBlYabW8IF4VOAsAh3F2ERWs6"
result = extract(url)
print(json.dumps(result, indent=2, ensure_ascii=False))
