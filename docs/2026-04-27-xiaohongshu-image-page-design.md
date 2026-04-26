# 設計規格：小紅書圖文頁 + 去水印強化

> AnyToCopy 克隆專案 — Phase 2 功能補完
> 2026-04-27

---

## 1. 架構概覽

```
┌─────────────────────────────────────────────────────┐
│                    前端 (GitHub Pages)                │
│  ┌──────────────┐  ┌──────────────┐  ┌───────────┐  │
│  │ 小紅書影片頁  │  │ 小紅書圖文頁  │  │ 首頁/批次  │  │
│  │  (已有)       │  │  (新增)      │  │  (已有)    │  │
│  └──────┬───────┘  └──────┬───────┘  └─────┬─────┘  │
│         │                  │                │         │
│         └──────────────────┴────────────────┘         │
│                        │                              │
│                   fetch /api/*                        │
└────────────────────────┬──────────────────────────────┘
                         │
┌────────────────────────┴──────────────────────────────┐
│             後端 API (Render / 本地)                    │
│  ┌───────────┐  ┌───────────┐  ┌───────────────────┐  │
│  │ /extract  │  │ /watermark│  │ /download/images  │  │
│  │ (已有)     │  │ /remove   │  │ (已有)            │  │
│  └─────┬─────┘  │ (強化)     │  └───────────────────┘  │
│        │        └─────┬─────┘                          │
│  ┌─────┴──────┐       │                                │
│  │ CDP 攔截   │  ┌────┴─────┐                          │
│  │ (已有)     │  │ Lama AI  │ ← 僅本地模式             │
│  └────────────┘  │ OpenCV   │                          │
│                  │ (fallback)│                          │
│                  └──────────┘                          │
└────────────────────────────────────────────────────────┘
```

---

## 2. 前端 — 小紅書圖文頁

### 2.1 頁面路由

路徑：`/xiaohongshu-image`
導航欄：在「小紅書」旁邊新增「小紅書圖文」入口

### 2.2 UI 佈局

```
┌──────────────────────────────────────────────┐
│  🔖 小紅書圖文提取                            │
│  一鍵下載小紅書圖文筆記中的圖片和文案            │
│                                              │
│  ┌──────────────────────────────────────────┐│
│  │ 📕 貼上小紅書分享連結                      ││
│  │ [___________________________________]    ││
│  │ [📋 貼上]  [📥 提取圖片與文案]            ││
│  └──────────────────────────────────────────┘│
│  支援：xhslink.com / xiaohongshu.com 連結    │
├──────────────────────────────────────────────┤
│             提取結果區域 (成功後顯示)           │
│                                              │
│  ┌──────────────────────────────────────────┐│
│  │ 📌 筆記資訊                              ││
│  │ 標題：XXXXXXXX                            ││
│  │ 作者：@XXXX                              ││
│  │ 共 N 張圖片                               ││
│  │ [📦 打包下載全部]                         ││
│  ├──────────────────────────────────────────┤│
│  │ 🖼️ 圖片畫廊                              ││
│  │ ┌──────┐ ┌──────┐ ┌──────┐              ││
│  │ │ img1 │ │ img2 │ │ img3 │  ...          ││
│  │ └──────┘ └──────┘ └──────┘              ││
│  │ (點擊放大 / 滑鼠懸浮顯示下載按鈕)          ││
│  ├──────────────────────────────────────────┤│
│  │ 📝 文案內容                               ││
│  │ XXXXXXXXXXXXXXXXXXXX                      ││
│  │ XXXXXXXXXXXXXXXXXXXX                      ││
│  │ [📋 複製]  [📄 下載TXT]                  ││
│  ├──────────────────────────────────────────┤│
│  │ 🎨 進階功能                              ││
│  │ [✨ AI去水印]  — 移除圖片浮水印            ││
│  │ (僅本地模式可用，Render 版顯示「本地可用」) ││
│  └──────────────────────────────────────────┘│
└──────────────────────────────────────────────┘
```

### 2.3 互動行為

| 操作 | 行為 |
|------|------|
| 輸入連結 + 按「提取」 | POST `/api/extract` → 顯示 loading → 展示結果 |
| 點擊圖片 | 彈出 lightbox 顯示大圖 |
| 滑鼠懸浮圖片 | 顯示右下角下載按鈕 |
| 「打包下載全部」 | POST `/api/download/images` → 下載 ZIP |
| 「AI 去水印」 | POST `/api/watermark/remove` → 下載去水印版 |
| 「複製」 | 複製文案到剪貼簿 |
| 「下載 TXT」 | 下載文案為 .txt 檔案 |

### 2.4 API 回應格式（小紅書 extract）

現有格式已涵蓋圖文筆記：
```json
{
  "platform": "小红书",
  "platformIcon": "fa-regular fa-note-sticky",
  "title": "筆記標題",
  "author": "用戶名",
  "transcript": "文案內容（從頁面提取）",
  "note_type": "image",
  "images": ["https://xhscdn.com/xxx1", "https://xhscdn.com/xxx2"],
  "image_count": 5,
  "can_download_images": true,
  "note_id": "xxx"
}
```

需要新增欄位：`author` 需從 CDP 頁面抓取用戶名（透過 DOM 或頁面標題解析）。

---

## 3. 後端 — 去水印強化

### 3.1 架構

```
utils/watermark/
├── __init__.py          # 統一入口，自動選擇方法
├── lama.py              # Lama AI 模型（本地模式）
├── opencv.py            # OpenCV inpainting（fallback）
└── models/              # 模型權重目錄（僅本地）
    └── big-lama.pt      # ~100MB，第一次使用時自動下載
```

### 3.2 方法選擇邏輯

```python
def remove_watermark(image_url, output_path=None):
    """自動選擇最佳去水印方法"""
    # 1. 嘗試 Lama（模型存在時）
    if os.path.exists(LAMA_MODEL_PATH):
        return remove_lama(image_url, output_path)
    # 2. Fallback: OpenCV inpainting
    return remove_opencv(image_url, output_path)
```

### 3.3 Lama 整合

- 使用 `lama-cleaner`（已實裝的 open-source 專案）或直接加載 `big-lama.pt`
- 模型路徑：`backend/utils/watermark/models/big-lama.pt`
- 第一次執行 `remove_watermark()` 時自動下載（約 100MB）
- 支援圖片 URL 和本地檔案路徑
- 僅在本地模式啟用（`os.environ.get('RENDER')` 檢查）

### 3.4 API 端點（已存在，需強化）

**`POST /api/watermark/remove`**

請求：
```json
{
  "image_url": "https://xhscdn.com/xxx.jpg",
  "method": "auto"
}
```

回應（成功 — 直接回傳圖片檔案）：
```
Content-Type: image/png
Content-Disposition: attachment; filename="watermark_removed.png"
```

### 3.5 前端的本地/Render 模式區分

- 前端透過 `/api/health` 回傳的 `features` 欄位判斷
- Render 版：`/api/watermark/remove` 回傳 `{"success": false, "error": "去水印功能仅限本地模式"}`，前端顯示提示
- 本地版：正常運作

---

## 4. 小紅書 CDP 強化

### 4.1 提取作者名稱

目前 CDP 攔截不提取作者名稱。需要在 CDP 流程中：
1. 在頁面載入完成後，透過 `Runtime.evaluate` 執行 JS 抓取 DOM 中的用戶名
2. 或解析頁面 URL / meta tag 提取

JS 腳本：
```javascript
document.querySelector('.username')?.textContent 
|| document.querySelector('[class*="user"]')?.textContent 
|| document.querySelector('meta[name="author"]')?.content
|| ''
```

### 4.2 提取文案

類似方式抓取筆記內文文字節點。

---

## 5. 不做的範圍（YAGNI）

- ❌ 影片去水印（小紅書已無水印，抖音留待 Phase 3）
- ❌ 批次去水印（單張處理就好）
- ❌ 去水印歷史記錄
- ❌ WebSocket 即時進度
- ❌ 幫助頁面
- ❌ 本地檔案上傳（video-extract / audio-extract）

---

## 6. 檔案變更清單

| 檔案 | 操作 | 說明 |
|------|------|------|
| `frontend/index.html` | 修改 | 新增 page-xiaohongshu-image、導航欄、lightbox、去水印按鈕 |
| `backend/utils/ai_tools.py` | 修改 | remove_logo 強化，自動選擇 Lama/OpenCV |
| `backend/utils/watermark/__init__.py` | 新增 | 去水印模組入口 |
| `backend/utils/watermark/lama.py` | 新增 | Lama AI 去水印實現 |
| `backend/utils/watermark/opencv.py` | 新增 | 從 ai_tools.py 搬移 OpenCV 實作 |
| `backend/platforms/xiaohongshu.py` | 修改 | CDP 提取 author + transcript |
| `backend/app.py` | 修改 | /api/watermark/remove 整合強化版 |
| `backend/utils/platform.py` | 修改 | 新增 xiaohongshu-image 平台特徵 |

---

## 7. 驗收標準

1. ✅ 貼上 xhslink.com 連結 → 提取圖片 + 文案成功
2. ✅ 圖片畫廊顯示所有圖片，可放大預覽
3. ✅ 打包下載 ZIP 包含所有圖片
4. ✅ 下載單張圖片正常
5. ✅ 本地後端：AI 去水印正常運作
6. ✅ Render 後端：去水印顯示提示訊息
7. ✅ 導航欄切換圖文頁/影片頁正常
8. ✅ 不影響現有功能（影片頁、批次、改寫）
