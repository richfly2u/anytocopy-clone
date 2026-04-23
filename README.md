# VideoText AI

A clone of [AnyToCopy.com](https://www.anytocopy.com/) - video text extraction & watermark removal tool.

## 🌐 Live Demo

**Frontend (GitHub Pages):** https://richfly2u.github.io/anytocopy-clone/
**Backend API:** Deploy on Render (see below)

## ✨ Features

- 🎬 **Video Text Extraction** - Extract subtitles/transcripts from YouTube, Douyin, Xiaohongshu, Bilibili, etc.
- 🖼️ **Image Text Recognition** - OCR text extraction from images
- 💧 **Watermark Removal** - Intelligent removal from videos and images
- 🎵 **Video to Audio** - Convert video to MP3 audio format
- 📦 **Batch Download** - ZIP package download support

## 🏗️ Architecture

```
anytocopy-clone/
├── frontend/
│   └── index.html          # Main UI (Dark theme, responsive)
├── backend/
│   ├── app.py              # Flask API server
│   ├── requirements.txt    # Python dependencies
│   └── render.yaml         # Render deployment config
├── index.html              # Root for GitHub Pages
└── README.md
```

## 🚀 Deployment

### Frontend (GitHub Pages) ✅
Already deployed at: https://richfly2u.github.io/anytocopy-clone/

### Backend (Render)
1. Go to https://render.com → New Web Service
2. Connect your GitHub repo: `richfly2u/anytocopy-clone`
3. **Root Directory:** `backend`
4. Render will auto-detect `render.yaml`
5. Deploy! API will be at: `https://anytocopy-backend.onrender.com`

## 💻 Local Development

```bash
# Backend
cd backend
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python app.py

# Frontend
# Open frontend/index.html in browser
# Or use: npx serve frontend/
```

## 📡 API

### `POST /api/extract`
Extract video transcript/caption.

**Request:**
```json
{"url": "https://www.youtube.com/watch?v=..."}
```

**Response:**
```json
{
  "platform": "YouTube",
  "platformIcon": "fa-brands fa-youtube",
  "title": "Video Title",
  "author": "Creator Name",
  "transcript": "Extracted transcript content..."
}
```

### `GET /api/health`
Health check endpoint.

## 📋 Platform Support

| Platform | Transcript | Watermark Removal | Download |
|----------|-----------|-------------------|----------|
| YouTube | ✅ Complete | 🔧 Planned | ✅ Via yt-dlp |
| Douyin/TikTok | 🔧 In Development | 🔧 Planned | 🔧 Planned |
| Xiaohongshu | 🔧 In Development | 🔧 Planned | 🔧 Planned |
| Bilibili | 🔧 In Development | 🔧 Planned | 🔧 Planned |
| Kuaishou | 🔧 In Development | 🔧 Planned | 🔧 Planned |
| Weibo | 🔧 In Development | 🔧 Planned | 🔧 Planned |

## 📝 License

MIT
