#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
OpenCV inpainting 去水印 — fallback 方案。

支援三種方法：
- inpaint: 檢測底部/右下角亮色區域 → 用 cv2.inpaint 修復
- blur: 模糊水印區域
- crop: 裁切底部 10%
"""

import os
import cv2
import numpy as np
import requests
import tempfile
import logging

logger = logging.getLogger(__name__)


def remove_opencv(image_url, output_path=None, method='inpaint'):
    """
    使用 OpenCV 去水印。

    Args:
        image_url: 圖片 URL 或本地路徑
        output_path: 輸出路徑
        method: 'inpaint' | 'blur' | 'crop'

    Returns:
        dict
    """
    # 讀取圖片
    if os.path.exists(image_url):
        img = cv2.imread(image_url)
        if img is None:
            return {'success': False, 'error': '無法讀取圖片檔案'}
    else:
        try:
            resp = requests.get(image_url, stream=True, timeout=30)
            resp.raise_for_status()
            img_data = np.frombuffer(resp.content, np.uint8)
            img = cv2.imdecode(img_data, cv2.IMREAD_COLOR)
        except Exception as e:
            return {'success': False, 'error': f'下載圖片失敗: {str(e)}'}

    if img is None:
        return {'success': False, 'error': '無法解碼圖片'}

    h, w = img.shape[:2]

    if method == 'crop':
        # 裁切底部 10%（常見水印位置）
        crop_h = int(h * 0.9)
        result = img[:crop_h, :]
    elif method == 'blur':
        # 模糊底部 8%
        mask_h = int(h * 0.08)
        roi = img[h - mask_h:h, :]
        blurred = cv2.GaussianBlur(roi, (51, 51), 0)
        result = img.copy()
        result[h - mask_h:h, :] = blurred
    elif method == 'inpaint':
        # 多策略遮罩檢測
        mask = np.zeros((h, w), dtype=np.uint8)

        # 策略 1: 底部亮色/白色區域
        bottom_strip = img[int(h * 0.85):h, :]
        gray = cv2.cvtColor(bottom_strip, cv2.COLOR_BGR2GRAY)
        _, bright_mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        mask[int(h * 0.85):h, :] = bright_mask

        # 策略 2: 右下角半透明水印
        corner = img[h - 80:h, w - 200:w]
        corner_gray = cv2.cvtColor(corner, cv2.COLOR_BGR2GRAY)
        _, corner_mask = cv2.threshold(corner_gray, 180, 255, cv2.THRESH_BINARY)
        mask[h - 80:h, w - 200:w] = np.maximum(mask[h - 80:h, w - 200:w], corner_mask)

        # 策略 3: 檢測連續的亮色文字區域（邊緣檢測 + 輪廓過濾）
        gray_full = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        edges = cv2.Canny(gray_full, 100, 200)
        # 只關注底部 20% 區域的邊緣
        bottom_edges = edges[int(h * 0.8):h, :]
        kernel = np.ones((3, 3), np.uint8)
        dilated = cv2.dilate(bottom_edges, kernel, iterations=2)
        mask[int(h * 0.8):h, :] = cv2.bitwise_or(mask[int(h * 0.8):h, :], dilated)

        # 執行 inpainting
        result = cv2.inpaint(img, mask, inpaintRadius=5, flags=cv2.INPAINT_TELEA)
    else:
        return {'success': False, 'error': f'不支援的方法: {method}'}

    # 輸出
    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        output_path = tmp.name
        tmp.close()

    cv2.imwrite(output_path, result)
    file_size = os.path.getsize(output_path)

    return {
        'success': True,
        'output_path': output_path,
        'file_size': file_size,
        'width': result.shape[1],
        'height': result.shape[0],
        'method': method,
    }
