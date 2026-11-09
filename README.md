# Lily-Api
### YouTube Fallback API & Stream Resolver

Your live deployed API:
```env
"WORKER_FALLBACK_API_URL" "https://lily-api.nishkarshk46.workers.dev"
"WORKER_FALLBACK_API_KEY" "lily"
```

A drop-in, 100% compatible replacement for:
```env
"WORKER_FALLBACK_API_URL" "https://youtubenewapi.skybotsdeveloper.workers.dev"
"WORKER_FALLBACK_API_KEY" "itsmesid"
```

This API is used by Telegram music bots (such as **VivaanXmusic**, **AnonXMusic**, **YukkiMusic**, and other streaming bots) to bypass YouTube IP bans, rate limits, and 429 errors by offloading audio stream extraction to Cloudflare's globally distributed edge network.

---

## ⚡ What You Get

1. **Cloudflare Worker (`worker.js` & `wrangler.toml`)**:
   - 100% serverless, edge-computed, zero server costs.
   - Deploys instantly to `https://<your-worker-name>.<your-subdomain>.workers.dev`.
   - Free tier includes **100,000 requests per day**.
2. **Python FastAPI Backend (`main.py`, `Dockerfile`)**:
   - Standalone microservice powered by `yt-dlp` and `httpx`.
   - Ready to run locally or host on VPS, Render, Koyeb, Railway, or Docker.
3. **Exact API Compatibility**:
   - Same endpoints (`/`, `/api`, `/api/file/vps/...`).
   - Same authentication header (`x-api-key: itsmesid`).
   - Identical JSON schema output expected by music bots.

---

## 🚀 Option 1: Deploy to Cloudflare Workers (Recommended, 2 Minutes)

You do **not** need to install anything on your computer if you use the Cloudflare Dashboard!

### Method A: Via Cloudflare Web Dashboard (No Code Setup)
1. Go to [Cloudflare Dashboard](https://dash.cloudflare.com/) and sign in (or create a free account).
2. On the left sidebar, click **Compute (Workers & Pages)** -> **Create application** -> **Create Worker**.
3. Name your worker (e.g., `youtubenewapi` or `my-music-resolver`) and click **Deploy**.
4. Click **Edit code** (Quick Edit).
5. Open [`worker.js`](file:///Users/nishkarshkumar/Desktop/fastest%20api/worker.js) from this repository, copy its entire contents, paste it into the Cloudflare code editor, and click **Deploy**.
6. That's it! Your worker URL will be:
   ```
   https://<your-worker-name>.<your-subdomain>.workers.dev
   ```

### Method B: Via Wrangler CLI
Run the following in this folder:
```bash
npm install
npx wrangler login
npx wrangler deploy
```

---

## 🐍 Option 2: Run with Python FastAPI (VPS / Local)

If you prefer running a dedicated server or VPS:

### 1. Local Run
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 main.py
```
The server will start at `http://0.0.0.0:8000`.

### 2. Docker Run
```bash
docker build -t youtube-fallback-api .
docker run -d -p 8000:8000 -e API_KEY="itsmesid" youtube-fallback-api
```

---

## ⚙️ How to Configure in Your Telegram Music Bot

In your bot's `.env` configuration file, replace the old worker URL with your newly deployed worker URL:

```env
WORKER_FALLBACK_API_URL="https://lily-api.nishkarshk46.workers.dev"
WORKER_FALLBACK_API_KEY="lily"
```

*(If you set a custom `API_KEY` in `wrangler.toml` or `.env`, make sure both match!)*

---

## 📖 API Documentation

### 1. Health & Status Check
* **Endpoint:** `GET /`
* **Headers:** None required
* **Response:**
  ```json
  {
    "success": true,
    "service": "elite-cloudflare-resolver",
    "status": "online"
  }
  ```

---

### 2. Resolve YouTube Audio / Video
* **Endpoint:** `GET /api`
* **Headers:**
  - `x-api-key: itsmesid` *(or `Authorization: Bearer itsmesid`)*
* **Query Parameters:**
  - `url` (Required): Full YouTube URL or 11-char Video ID (e.g. `dQw4w9WgXcQ`).
  - `format` (Optional): `mp3` (default) or `mp4`.

#### Example Request:
```bash
curl -H "x-api-key: lily" \
  "https://lily-api.nishkarshk46.workers.dev/api?url=https://www.youtube.com/watch?v=dQw4w9WgXcQ&format=mp3"
```

#### Example Response:
```json
{
  "success": true,
  "title": "Rick Astley - Never Gonna Give You Up (Official Video) (4K Remaster)",
  "fileSize": 3449447,
  "fileSizeText": "3.29 MB",
  "format": "mp3",
  "fullFormat": "mp3",
  "videoId": "dQw4w9WgXcQ",
  "videoUrl": "https://www.youtube.com/watch?v=dQw4w9WgXcQ",
  "downloads": "https://your-worker.workers.dev/api/file/vps/<stream_token>.m4a?videoId=dQw4w9WgXcQ&filename=youtube.m4a",
  "downloadUrl": "https://your-worker.workers.dev/api/file/vps/<stream_token>.m4a?videoId=dQw4w9WgXcQ&filename=youtube.m4a",
  "download_url": "https://your-worker.workers.dev/api/file/vps/<stream_token>.m4a?videoId=dQw4w9WgXcQ&filename=youtube.m4a",
  "rawStreamingUrl": "https://your-worker.workers.dev/api/file/vps/<stream_token>.m4a?videoId=dQw4w9WgXcQ&filename=youtube.m4a",
  "raw_streaming_url": "https://your-worker.workers.dev/api/file/vps/<stream_token>.m4a?videoId=dQw4w9WgXcQ&filename=youtube.m4a",
  "mimeType": "audio/mp4",
  "streamMimeType": "audio/mp4",
  "stream_mime_type": "audio/mp4",
  "downloadMimeType": "audio/mp4",
  "download_mime_type": "audio/mp4",
  "fileExtension": "m4a",
  "file_extension": "m4a",
  "audioIncluded": true,
  "videoIncluded": false,
  "provider": "vps",
  "providerOrigin": "https://your-worker.workers.dev"
}
```

---

### 3. Stream & Proxy Endpoint
* **Endpoint:** `GET /api/file/vps/:token` or `GET /api/stream?url=<raw_stream_url>`
* **Features:**
  - Full HTTP Range requests (`Accept-Ranges: bytes`, `206 Partial Content`).
  - Telegram voice/audio players can seek back and forth instantly without buffering the whole track.

