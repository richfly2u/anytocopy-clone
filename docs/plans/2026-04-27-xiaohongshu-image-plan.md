# 小紅書圖文頁 + 去水印強化 — 實作計畫

> **For Hermes:** Use tasks sequentially — each task is self-contained.

**目標：** 補完小紅書圖文專屬頁面、強化去水印功能、CDP 提取作者+文案

**檔案變更：**
- Modify: `frontend/index.html` — 新增圖文頁
- Modify: `backend/utils/ai_tools.py` — 強化去水印
- Create: `backend/utils/watermark/__init__.py` — 模組入口
- Create: `backend/utils/watermark/lama.py` — Lama AI
- Create: `backend/utils/watermark/opencv.py` — OpenCV fallback
- Modify: `backend/platforms/xiaohongshu.py` — 加 author + transcript
- Modify: `backend/app.py` — 整合強化版去水印

---

### Task 1: CDP 提取 author + transcript

**Objective:** 小紅書 CDP 攔截後，從頁面提取用戶名和文案內容

**Files:**
- Modify: `backend/platforms/xiaohongshu.py`

**修改內容：**
在 `_cdp_intercept()` 中，當頁面載入完成後（收到 `Page.frameStoppedLoading` 或 timeout 前），用 `Runtime.evaluate` 執行 JS 抓取：

```javascript
// 作者名稱
document.querySelector('.username')?.textContent 
  || document.querySelector('[class*="user"]')?.textContent 
  || document.querySelector('meta[name="author"]')?.content 
  || ''

// 文案內容
document.querySelector('.content')?.textContent 
  || document.querySelector('[class*="desc"]')?.textContent 
  || document.querySelector('meta[name="description"]')?.content 
  || ''
```

將結果存入 cdp response 的 `author` 和 `transcript` 欄位。

---

### Task 2: 建立 watermark 模組

**Objective:** 建立 `backend/utils/watermark/` 目錄，統一去水印入口

**Files:**
- Create: `backend/utils/watermark/__init__.py`
- Create: `backend/utils/watermark/lama.py`
- Create: `backend/utils/watermark/opencv.py`（從 ai_tools.py 搬移）

**`__init__.py` 入口邏輯：**

```python
import os

LAMA_MODEL_PATH = os.path.join(os.path.dirname(__file__), 'models', 'big-lama.pt')

def remove_watermark(image_url, output_path=None, method='auto'):
    """
    自動選擇最佳去水印方法
    - auto: 有 Lama 模型就用，否則 fallback OpenCV
    """
    from .opencv import remove_opencv

    if method == 'auto' and os.path.exists(LAMA_MODEL_PATH):
        try:
            from .lama import remove_lama
            result = remove_lama(image_url, output_path)
            if result.get('success'):
                return result
        except Exception:
            pass
    
    return remove_opencv(image_url, output_path, method='inpaint')
```

**`opencv.py`：** 從 `ai_tools.py` 的 `remove_logo()` 搬過來，保持相同介面。

**`lama.py`：** 使用 `lama-cleaner` 套件（需 pip install）或直接加載 `big-lama.pt`。架構：

```python
def remove_lama(image_url, output_path=None):
    """使用 Lama 模型去除水印"""
    # 下載模型（如不存在）
    # 載入模型
    # 處理圖片
    # 回傳結果
```

---

### Task 3: 強化 ai_tools.py

**Objective:** 將 `remove_logo()` 改為委派到 `watermark` 模組

**Files:**
- Modify: `backend/utils/ai_tools.py`

**修改：** 將 `remove_logo()` 改為：

```python
def remove_logo(image_url, output_path=None, method='auto'):
    from utils.watermark import remove_watermark
    return remove_watermark(image_url, output_path, method)
```

保留向後相容。

---

### Task 4: 強化 app.py 去水印端點

**Objective:** `/api/watermark/remove` 支援 Render 模式提示 + Lama 整合

**Files:**
- Modify: `backend/app.py`

**修改：** 在 `api_remove_watermark()` 中加判斷：

```python
# 如果是在 Render 上 + method=auto，回傳提示
if os.environ.get('RENDER') and method == 'auto':
    return jsonify({
        'success': False, 
        'error': 'AI 去水印僅限本地模式可用，請在本機啟動 Flask 後端使用'
    }), 400
```

---

### Task 5: 前端 — 新增小紅書圖文頁

**Objective:** 在 `index.html` 新增 `page-xiaohongshu-image` 完整頁面

**Files:**
- Modify: `frontend/index.html`

**新增內容：**
1. 導航欄新增「小紅書圖文」連結（介於小紅書和抖音之間）
2. 新增 `page-xiaohongshu-image` div：
   - 輸入區（貼上 xhslink.com 連結）
   - 提取按鈕（呼叫 `/api/extract`）
   - 結果區：
     - 筆記資訊（標題、作者、圖片數）
     - 圖片畫廊（grid 佈局 + lightbox）
     - 文案區（可複製/下載）
     - 去水印按鈕（顯示本地/Render 狀態）
3. SPA 路由加入 `'/xiaohongshu-image': 'page-xiaohongshu-image'`
4. Mobile menu 也加入連結

**關鍵 JS 函數：**
- `startXhsImageExtract()` — 呼叫 `/api/extract`，處理 images 回傳
- `showXhsImageResult(data)` — 渲染圖片畫廊 + 文案
- `openLightbox(imgUrl)` — 點擊圖片放大
- `startWatermarkRemove(imgUrl)` — 呼叫 `/api/watermark/remove`

---

### Task 6: 驗證

**Objective:** 確認所有功能正常

**步驟：**
1. `python backend/app.py` 啟動本地後端
2. 瀏覽器打開 `frontend/index.html`
3. 測試小紅書圖文頁：貼上連結 → 提取 → 圖片顯示 → 打包下載
4. 測試去水印：點擊 AI 去水印 → 下載無水印圖片
5. 確認 Render 模式下去水印顯示提示
6. 確認原有功能（影片頁、批次、改寫）不受影響
