#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Lama (LaMa) AI 去水印模型。

使用 big-lama.pt 模型進行圖片修復（inpainting），
適合移除圖片上的浮水印、文字等人工痕跡。

模型會在首次使用時自動從 GitHub release 下載（約 100MB）。
"""

import os
import logging
import tempfile
from urllib.request import urlretrieve

import cv2
import numpy as np
import requests

from . import LAMA_MODEL_PATH, LAMA_MODEL_URL

logger = logging.getLogger(__name__)


def _download_model():
    """下載 big-lama.pt 模型"""
    os.makedirs(os.path.dirname(LAMA_MODEL_PATH), exist_ok=True)
    logger.info(f"正在下載去水印模型 (約 100MB)...")
    logger.info(f"來源: {LAMA_MODEL_URL}")

    def _report(count, block_size, total_size):
        downloaded = count * block_size
        if total_size > 0:
            pct = min(100, int(downloaded * 100 / total_size))
            if count % 100 == 0:
                logger.info(f"下載進度: {pct}%")

    try:
        urlretrieve(LAMA_MODEL_URL, LAMA_MODEL_PATH, _report)
        size = os.path.getsize(LAMA_MODEL_PATH)
        if size > 1_000_000:
            logger.info(f"模型下載完成 ({size / 1024 / 1024:.1f} MB)")
            return True
        else:
            os.remove(LAMA_MODEL_PATH)
            logger.error("模型檔案過小，下載可能失敗")
            return False
    except Exception as e:
        logger.error(f"模型下載失敗: {e}")
        if os.path.exists(LAMA_MODEL_PATH):
            os.remove(LAMA_MODEL_PATH)
        return False


def _load_model():
    """載入 Lama 模型"""
    if not os.path.exists(LAMA_MODEL_PATH):
        if not _download_model():
            return None

    try:
        import torch
        device = 'cuda' if torch.cuda.is_available() else 'cpu'
        logger.info(f"載入 Lama 模型 (device={device})")

        model = torch.jit.load(LAMA_MODEL_PATH, map_location=device)
        model.eval()
        return model
    except ImportError:
        logger.warning("未安裝 PyTorch，無法使用 Lama 模型")
        return None
    except Exception as e:
        logger.error(f"載入 Lama 模型失敗: {e}")
        return None


def remove_lama(image_url, output_path=None):
    """
    使用 Lama 模型移除圖片水印。

    Args:
        image_url: 圖片 URL 或本地路徑
        output_path: 輸出路徑

    Returns:
        dict
    """
    # 載入模型
    model = _load_model()
    if model is None:
        return {'success': False, 'error': '無法載入 Lama 模型，請確認 PyTorch 已安裝'}

    # 讀取圖片
    if os.path.exists(image_url):
        img_bgr = cv2.imread(image_url)
        if img_bgr is None:
            return {'success': False, 'error': '無法讀取圖片檔案'}
    else:
        try:
            resp = requests.get(image_url, stream=True, timeout=30)
            resp.raise_for_status()
            img_data = np.frombuffer(resp.content, np.uint8)
            img_bgr = cv2.imdecode(img_data, cv2.IMREAD_COLOR)
        except Exception as e:
            return {'success': False, 'error': f'下載圖片失敗: {str(e)}'}

    if img_bgr is None:
        return {'success': False, 'error': '無法解碼圖片'}

    h, w = img_bgr.shape[:2]

    try:
        import torch
        import torch.nn.functional as F

        # 轉 RGB、Padding 到 8 的倍數
        img_rgb = cv2.cvtColor(img_bgr, cv2.COLOR_BGR2RGB)
        orig_h, orig_w = img_rgb.shape[:2]

        # Pad 到 8 的倍數
        pad_h = (8 - orig_h % 8) % 8
        pad_w = (8 - orig_w % 8) % 8
        img_padded = np.pad(img_rgb, ((0, pad_h), (0, pad_w), (0, 0)), mode='reflect')

        # 轉 tensor
        img_tensor = torch.from_numpy(img_padded).float().permute(2, 0, 1).unsqueeze(0) / 255.0
        img_tensor = img_tensor.to(next(model.parameters()).device)

        # 推理
        with torch.no_grad():
            output = model(img_tensor)

        # 裁回原尺寸
        result_tensor = output.squeeze(0).permute(1, 2, 0).cpu().numpy()
        result_tensor = result_tensor[:orig_h, :orig_w]
        result_tensor = np.clip(result_tensor * 255, 0, 255).astype(np.uint8)

        # 轉 BGR
        result_bgr = cv2.cvtColor(result_tensor, cv2.COLOR_RGB2BGR)

    except Exception as e:
        return {'success': False, 'error': f'Lama 推理失敗: {str(e)}'}

    # 輸出
    if output_path is None:
        tmp = tempfile.NamedTemporaryFile(suffix='.png', delete=False)
        output_path = tmp.name
        tmp.close()

    cv2.imwrite(output_path, result_bgr)
    file_size = os.path.getsize(output_path)

    return {
        'success': True,
        'output_path': output_path,
        'file_size': file_size,
        'width': orig_w,
        'height': orig_h,
        'method': 'lama',
    }
