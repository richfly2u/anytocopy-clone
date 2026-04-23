# VideoText AI

A clone of AnyToCopy.com - video text extraction & watermark removal tool.

## Features

- Video text extraction from YouTube, Douyin, Xiaohongshu, Bilibili, etc.
- Image text recognition (OCR)
- Watermark removal
- Video to MP3 conversion
- Batch download (ZIP)

## Tech Stack

### Frontend
- HTML + Tailwind CSS + Vanilla JS
- Deployed on GitHub Pages

### Backend
- Python Flask API
- yt-dlp for video info extraction
- Deployed on Render

## Quick Start

### Local Development

```bash
# Backend
cd backend
pip install -r requirements.txt
python app.py

# Frontend
# Open frontend/index.html in browser
# Or use Live Server
```

### Deploy Backend to Render
1. Push to GitHub
2. Create Web Service on Render
3. Point to `backend/` directory
4. Render auto-detects render.yaml

## API

### POST /api/extract
Extract video transcript

Request:
```json
{"url": "https://www.youtube.com/watch?v=..."}
```

Response:
```json
{
  "platform": "YouTube",
  "platformIcon": "fa-brands fa-youtube",
  "title": "Video Title",
  "author": "Creator",
  "transcript": "Transcript content..."
}
```

## Platform Support

| Platform | Transcript | Watermark | Download |
|----------|-----------|-----------|----------|
| YouTube | Yes | No | Yes |
| Douyin | Dev | Dev | Dev |
| Xiaohongshu | Dev | Dev | Dev |
| Bilibili | Dev | Dev | Dev |
| Kuaishou | Dev | Dev | Dev |
| Weibo | Dev | Dev | Dev |
