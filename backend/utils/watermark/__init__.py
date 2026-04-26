#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
去水印模組 — 統一入口。

自動選擇最佳方法：
1. Lama AI 模型（效果最好，需下載 big-lama.pt 約 100MB）
2. OpenCV inpainting（免費 fallback）

模型會在第一次使用 `remove_watermark(method='lama')` 時自動下載。
"""

import os
import logging

logger = logging.getLogger(__name__)

MODEL_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'models')
LAMA_MODEL_PATH = os.path.join(MODEL_DIR, 'big-lama.pt')
LAMA_MODEL_URL = 'https://github.com/Sanster/models/releases/download/add_big_lama/big-lama.pt'


def is_lama_available():
    return os.path.exists(LAMA_MODEL_PATH) and os.path.getsize(LAMA_MODEL_PATH) > 1_000_000


def remove_watermark(image_url, output_path=None, method='auto'):
    """
    移除圖片水印。

    Args:
        image_url: 圖片 URL 或本地路徑
        output_path: 輸出路徑（預設 tempfile）
        method: 'auto' | 'lama' | 'inpaint' | 'blur' | 'crop'

    Returns:
        dict: {'success': True, 'output_path': '...', ...} or {'success': False, 'error': '...'}
    """
    from .opencv import remove_opencv

    if method == 'auto':
        if is_lama_available():
            logger.info("Lama 模型可用，使用 AI 去水印")
            method = 'lama'
        else:
            logger.info("Lama 模型不存在，使用 OpenCV fallback")
            method = 'inpaint'

    if method == 'lama':
        try:
            from .lama import remove_lama
            result = remove_lama(image_url, output_path)
            if result.get('success'):
                return result
            if method != 'auto':
                return result  # 明確要求 lama 但失敗 → 直接回傳錯誤
            logger.warning(f"Lama 去水印失敗: {result.get('error')}，fallback 到 OpenCV")
        except Exception as e:
            if method != 'auto':
                return {'success': False, 'error': f'Lama 去水印失敗: {e}'}
            logger.warning(f"Lama 異常: {e}，fallback 到 OpenCV")

    # OpenCV fallback
    return remove_opencv(image_url, output_path, method=method if method != 'lama' else 'inpaint')
