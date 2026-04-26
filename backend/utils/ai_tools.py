#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI 工具模組 — 文案改寫 + 圖片 OCR + 去水印

API 支援 DeepSeek / OpenAI 自動切換
"""

import base64
import json
import os
import re
import sys as _sys
from io import BytesIO
from pathlib import Path

import requests

# ============================================
# API 配置
# ============================================

DEEPSEEK_API_KEY = os.environ.get('DEEPSEEK_API_KEY', '')
DEEPSEEK_MODEL = os.environ.get('DEEPSEEK_MODEL', 'deepseek-chat')

OPENAI_API_KEY = os.environ.get('OPENAI_API_KEY', '')

# 優先使用 DeepSeek（便宜）
def _call_llm(messages, model=None, temperature=0.7, max_tokens=2048):
    """直接調用 LLM API (無需 openai 套件)"""
    if DEEPSEEK_API_KEY:
        api_key = DEEPSEEK_API_KEY
        base_url = 'https://api.deepseek.com/v1'
        model = model or DEEPSEEK_MODEL
    elif OPENAI_API_KEY:
        api_key = OPENAI_API_KEY
        base_url = 'https://api.openai.com/v1'
        model = model or 'gpt-4o-mini'
    else:
        return {'error': '未配置 API key'}

    headers = {
        'Authorization': f'Bearer {api_key}',
        'Content-Type': 'application/json',
    }

    payload = {
        'model': model,
        'messages': messages,
        'temperature': temperature,
        'max_tokens': max_tokens,
    }

    resp = requests.post(f'{base_url}/chat/completions', json=payload, headers=headers, timeout=60)
    if resp.status_code != 200:
        return {'error': f'API error ({resp.status_code}): {resp.text[:200]}'}

    data = resp.json()
    choices = data.get('choices', [])
    if not choices:
        return {'error': 'API 無回傳內容'}

    content = choices[0].get('message', {}).get('content', '')
    return {'content': content, 'model': data.get('model', model)}


# ============================================
# 1. AI 文案改寫
# ============================================

STYLE_PROMPTS = {
    'formal': '請用正式、專業的風格改寫以下文案。使用正式用語、完整句式，適合商業場合或官方文件使用。',
    'casual': '請用輕鬆、口語化的風格改寫以下文案。像朋友聊天一樣自然，適合社群媒體或日常交流。',
    'persuasive': '請用具有說服力的風格改寫以下文案。使用修辭手法、情感訴求和行動呼籲，適合行銷推廣使用。',
    'concise': '請用精簡、有力的風格改寫以下文案。保留核心資訊，去除冗詞贅字，一句話能說完就不要用兩句。',
}


def rewrite_text(text, style='casual', max_length=2000):
    """
    使用 LLM 改寫文案。
    Returns: {'success': True, 'result': '改寫後的內容', 'style': 'style_name'}
    """
    style_prompt = STYLE_PROMPTS.get(style, STYLE_PROMPTS['casual'])

    system_prompt = (
        "你是一位專業的文案改寫助手。請根據指定的風格改寫使用者提供的文案。\n"
        "要求：\n"
        "1. 保留原文的核心資訊和關鍵訊息\n"
        "2. 不改變原文的語氣和立場\n"
        "3. 如果原文是繁體中文，保持繁體中文輸出\n"
        "4. 直接輸出改寫後的結果，不要加任何前綴說明\n"
        f"\n改寫風格：{style_prompt}"
    )

    result = _call_llm(
        messages=[
            {'role': 'system', 'content': system_prompt},
            {'role': 'user', 'content': f'請改寫以下文案：\n\n{text[:max_length]}'},
        ],
        temperature=0.7,
        max_tokens=2048,
    )

    if 'error' in result:
        return {'success': False, 'error': result['error']}

    return {'success': True, 'result': result['content'].strip(), 'style': style}


# ============================================
# 2. 圖片 OCR (LLM Vision)
# ============================================

def ocr_image(image_url, language='zh'):
    """
    使用 LLM Vision 進行圖片 OCR。
    - image_url: 圖片的 URL 或本地路徑
    - language: zh / en / auto

    Returns: {'success': True, 'text': '識別的文字', 'lines': [...]}
    """
    # 如果是本地檔案，轉 base64
    if os.path.exists(image_url):
        with open(image_url, 'rb') as f:
            img_data = base64.b64encode(f.read()).decode('utf-8')
        ext = Path(image_url).suffix.lower()
        mime_map = {'.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg',
                    '.webp': 'image/webp', '.bmp': 'image/bmp'}
        mime = mime_map.get(ext, 'image/png')
        image_content = f"data:{mime};base64,{img_data}"
    else:
        image_content = image_url

    lang_hint = {
        'zh': '圖片中的文字主要是繁體中文或簡體中文',
        'en': 'The text in the image is primarily English',
        'auto': '圖片中的文字可能是任何語言，請自動識別',
    }.get(language, '請自動識別語言')

    result = _call_llm(
        messages=[{
            'role': 'user',
            'content': [
                {'type': 'text', 'text': (
                    f'請從這張圖片中提取所有文字。{lang_hint}\n\n'
                    '請：\n'
                    '1. 準確提取所有可見文字\n'
                    '2. 保持原文的排列順序\n'
                    '3. 直接輸出提取的文字內容\n'
                    '4. 如果圖片中沒有文字，請回答「圖片中沒有可識別的文字」'
                )},
                {'type': 'image_url', 'image_url': {'url': image_content}},
            ],
        }],
        max_tokens=2048,
    )

    if 'error' in result:
        return {'success': False, 'error': result['error']}

    text = result['content'].strip()
    lines = [l.strip() for l in text.split('\n') if l.strip()]
    return {'success': True, 'text': text, 'lines': lines}


# ============================================
# 3. 去水印 (影像處理)
# ============================================

def remove_logo(image_url, output_path=None, method='inpaint'):
    """
    去水印 — 使用 OpenCV + inpainting。
    對於影片水印，需要 frame-by-frame 處理。

    method:
    - 'inpaint': 用 OpenCV 的 inpainting（需要水印位置遮罩）
    - 'blur': 模糊水印區域
    - 'crop': 裁切掉水印區域
    """
    try:
        import cv2
        import numpy as np
    except ImportError:
        return {'success': False, 'error': '需要安裝 opencv-python: pip install opencv-python-headless'}

    # 下載或讀取圖片
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
        # 需要遮罩 — 假設水印在右下角或底部
        mask = np.zeros((h, w), dtype=np.uint8)

        # 策略 1: 檢測底部亮色/白色區域（常見水印）
        bottom_strip = img[int(h * 0.85):h, :]
        gray = cv2.cvtColor(bottom_strip, cv2.COLOR_BGR2GRAY)
        _, bright_mask = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY)
        mask[int(h * 0.85):h, :] = bright_mask

        # 策略 2: 檢測右下角的半透明水印
        corner = img[h - 80:h, w - 200:w]
        corner_gray = cv2.cvtColor(corner, cv2.COLOR_BGR2GRAY)
        _, corner_mask = cv2.threshold(corner_gray, 180, 255, cv2.THRESH_BINARY)
        mask[h - 80:h, w - 200:w] = np.maximum(mask[h - 80:h, w - 200:w], corner_mask)

        # 執行 inpainting
        result = cv2.inpaint(img, mask, inpaintRadius=5, flags=cv2.INPAINT_TELEA)
    else:
        return {'success': False, 'error': f'不支援的方法: {method}'}

    # 輸出
    if output_path is None:
        from tempfile import NamedTemporaryFile
        tmp = NamedTemporaryFile(suffix='.png', delete=False)
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


# ============================================
# CLI 測試
# ============================================

if __name__ == '__main__':
    import sys
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'help'

    if cmd == 'rewrite' and len(sys.argv) > 2:
        text = sys.argv[2]
        style = sys.argv[3] if len(sys.argv) > 3 else 'casual'
        result = rewrite_text(text, style)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif cmd == 'ocr' and len(sys.argv) > 2:
        url = sys.argv[2]
        result = ocr_image(url)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    elif cmd == 'watermark' and len(sys.argv) > 2:
        url = sys.argv[2]
        method = sys.argv[3] if len(sys.argv) > 3 else 'inpaint'
        result = remove_logo(url, method=method)
        print(json.dumps(result, ensure_ascii=False, indent=2))

    else:
        print("Usage:")
        print("  python ai_tools.py rewrite <text> [style]")
        print("  python ai_tools.py ocr <image_url>")
        print("  python ai_tools.py watermark <image_url> [method]")
        print("Styles: formal, casual, persuasive, concise")
        print("Methods: inpaint, blur, crop")
