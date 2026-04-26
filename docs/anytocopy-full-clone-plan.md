# AnyToCopy 完整功能克隆計畫

> **目標：** 打造一個功能完整的 anytocopy.com 替代品，支援影片文案提取、去水印下載、AI 文案工具、批次操作

## 現有狀態

- ✅ 前端基礎頁面 (dark theme, Tailwind CSS)
- ✅ Flask 後端基礎架構 (API endpoint, yt-dlp 整合)
- ✅ YouTube 文案提取 (youtube-transcript-api)
- ✅ GitHub Pages 前端已部署
- ⬜ **大量功能待實作**

## AnyToCopy 完整功能分析

### 頁面目錄結構
| 頁面 | URL | 功能 |
|------|-----|------|
| 首頁 | / | 主輸入頁，支援 50+ 平台連結 |
| 小紅書 | /xiaohongshu | 小紅書專用：影片/圖文/Live圖 |
| 小紅書圖文 | /xiaohongshu-image | 小紅書圖片提取 |
| 抖音 | /douyin | 抖音專用：影片/圖文 |
| 抖音圖文 | /douyin-image | 抖音圖片提取 |
| 影片檔案提取 | /video-extract | 上傳本地影片提取文案 |
| 音訊檔案提取 | /audio-extract | 上傳本地音訊轉文字 |
| 批次提取 | /batch-extract | 連結/影片/音訊批次任務 |
| 文案改寫 | /rewrite-content | AI 文案改寫工具 |
| 幫助 | /help | 使用說明/常見問題 |

### 核心功能
1. **連結解析** — 從 50+ 平台解析連結，提取影片/圖片
2. **文案提取** — AI 語音辨識轉文字、OCR 圖片文字
3. **去水印下載** — 影片 / 圖片 / Live圖去水印
4. **影片轉音訊** — 下載 MP3
5. **批次下載** — 多連結同時處理 + ZIP 打包
6. **AI 文案工具** — 文案改寫 / 文案素材庫

### 技術障礙
- **小紅書 / 抖音**: WAF 阻擋直接爬取 → 需 CDP 方案 (已有 skill)
- **中國平台通用**: 影片 CDN URL 有時效性 sign/token
- **批次處理**: 需要背景任務隊列

---

## 第一階段：強化後端核心 (2-3 天)

### Task 1: 重構 Flask 後端架構
**Files:**
- `backend/app.py` — 重寫為模組化結構
- `backend/platforms/` — 平台處理器目錄

Create backend structure:
```
backend/
├── app.py                    # Flask entry point
├── requirements.txt
├── render.yaml
├── utils/
│   ├── __init__.py
│   ├── platform.py           # Platform detection
│   └── downloader.py         # File download helpers
├── platforms/
│   ├── __init__.py
│   ├── youtube.py            # YouTube handler
│   ├── xiaohongshu.py        # XHS handler (CDP)
│   ├── douyin.py             # Douyin handler
│   ├── bilibili.py           # Bilibili handler
│   └── weibo.py              # Weibo handler
└── tasks/
    ├── __init__.py
    └── batch.py              # Batch processing
```

### Task 2: 平台識別器
自動識別連結來自哪個平台:
- YouTube: `youtube.com`, `youtu.be`
- Bilibili: `bilibili.com`, `b23.tv`
- 小紅書: `xhslink.com`, `xiaohongshu.com`
- 抖音: `douyin.com`
- 微博: `weibo.com`

### Task 3: YouTube 完全支援
- 文案提取 (已完成)
- 影片下載 (yt-dlp)
- 音訊提取 (yt-dlp -x --audio-format mp3)

### Task 4: 小紅書 CDP 整合
使用現有 `xiaohongshu-cdp-video-downloader` skill:
- 啟動 CentBrowser CDP
- 解析短網址 → 真實 URL
- 攔截影片 CDN URL
- 下載影片

### Task 5: Bilibili 支援
- API: `api.bilibili.com/x/web-interface/view?bvid=`
- 免費 API 無需 cookies
- 提取影片 + 文案 + 封面

### Task 6: 抖音支援
- 需要代理/瀏覽器方案
- 類似小紅書 CDP 方案

---

## 第二階段：前端強化 (2-3 天)

### Task 7: 路由系統 (SPA)
前端實現頁面路由:
- `/` — 首頁
- `/xiaohongshu` — 小紅書專頁
- `/douyin` — 抖音專頁
- `/batch` — 批次提取
- `/rewrite` — 文案改寫

### Task 8: 專用平台頁面
每個平台頁面有:
- 專屬的說明文案
- 特色功能卡片
- SEO meta 標籤

### Task 9: 結果展示增強
- 影片播放器預覽
- 圖片畫廊
- Live 圖動態效果
- 文案編輯器

### Task 10: 批次操作 UI
- 多連結輸入 (textarea)
- 任務進度條
- 結果列表
- ZIP 下載按鈕

---

## 第三階段：進階功能 (3-4 天)

### Task 11: AI 文案改寫工具
- 使用 LLM API 改寫文案
- 支援多種風格 (正式/輕鬆/說服)
- 歷史記錄

### Task 12: 圖片 OCR
- 使用 Tesseract 或 LLM vision API
- 支援繁體中文

### Task 13: 批次背景任務
- Redis/Celery 任務隊列
- WebSocket 即時進度
- 任務歷史

### Task 14: 去水印功能
- 影片水印檢測 + 移除 (AI 或傳統 CV)
- 圖片水印移除

---

## 部署策略

| 服務 | 方案 | 費用 |
|------|------|------|
| 前端 | GitHub Pages | 免費 |
| 後端 API | Render | 免費 |
| 資料庫 | SQLite (dev) / PostgreSQL (prod) | 免費 |
| 背景任務 | Redis Cloud (免費 30MB) | 免費 |
| 文件儲存 | Render 磁碟 / Cloudinary | 免費 |

---

## 優先級路線圖

**Phase 1 (本周):**
1. ✅ 重構 Flask 後端 → 平台識別
2. ✅ 小紅書 CDP 下載 → Flask API 整合
3. ✅ YouTube 強化 (影片下載 + 音訊)
4. ✅ Bilibili 支援

**Phase 2 (下周):**
5. 前端路由 + 專用平台頁面
6. 批次操作 UI
7. 結果展示增強

**Phase 3 (下下周):**
8. AI 文案改寫
9. 圖片 OCR
10. 抖音支援

---

## 技術參考

- **小紅書 CDP**: `xiaohongshu-cdp-video-downloader` skill
- **YouTube**: `youtube-transcript-api` + `yt-dlp`
- **Bilibili API**: `api.bilibili.com/x/web-interface/view?bvid={bvid}`
- **全文搜尋**: `fullstack-mvp-clone` skill
