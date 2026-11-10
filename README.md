<div align="center">

<!-- Animated Typing Header -->
<a href="https://t.me/advaydev">
  <img src="https://readme-typing-svg.demolab.com?font=Fira+Code&weight=700&size=32&duration=3000&pause=1000&color=FF2E93&center=true&vCenter=true&multiline=true&width=700&height=100&lines=%F0%9F%8C%B8+Lily-Api+%7C+Fastest+Stream+Resolver;Blazing-Fast+Edge+YouTube+Audio+%26+Video+API" alt="Lily-Api Typing Banner" />
</a>

<p align="center">
  <b>Ultra-fast, edge-cached YouTube audio & video extraction API built for Telegram Music Bots, media players, and high-speed downloaders.</b>
</p>

<!-- Colorful Shields.io Badges -->
<p align="center">
  <a href="https://t.me/advaydev">
    <img src="https://img.shields.io/badge/Owner-@advaydev-26A5E4?style=for-the-badge&logo=telegram&logoColor=white" alt="Owner Telegram" />
  </a>
  <img src="https://img.shields.io/badge/Cloudflare-Workers-F38020?style=for-the-badge&logo=cloudflare&logoColor=white" alt="Cloudflare Workers" />
  <img src="https://img.shields.io/badge/FastAPI-009688?style=for-the-badge&logo=fastapi&logoColor=white" alt="FastAPI" />
  <img src="https://img.shields.io/badge/Docker-2496ED?style=for-the-badge&logo=docker&logoColor=white" alt="Docker" />
  <img src="https://img.shields.io/badge/Speed-100%2B%20MB%2Fs-00E676?style=for-the-badge&logo=speedtest&logoColor=black" alt="Speed" />
  <img src="https://img.shields.io/badge/Edge%20Cache-%3C20ms-9D4EDD?style=for-the-badge&logo=lightning&logoColor=white" alt="Latency" />
</p>

<p align="center">
  <a href="#-architecture">Architecture</a> •
  <a href="#-quick-deploy">Quick Deploy</a> •
  <a href="#-speed--performance">Speed Benchmarks</a> •
  <a href="#-api-playground">API Docs</a> •
  <a href="https://t.me/advaydev">Contact Owner</a>
</p>

</div>

---

> [!IMPORTANT]
> **Security First:** Never hardcode real API keys, worker URLs, or personal cookies inside source files. Always configure `API_KEY`, `UPSTREAM_BACKEND`, `UPSTREAM_API_KEY`, and `YOUTUBE_COOKIE` using **Cloudflare Secrets** or environment variables (`.env`).

---

## ✨ Key Highlights

<table>
  <tr>
    <td width="50%">
      <h3>⚡ Sub-20ms Edge Caching</h3>
      Repeated track lookups are served straight from Cloudflare's global edge cache in under <b>20 milliseconds</b> across 300+ locations.
    </td>
    <td width="50%">
      <h3>🚀 100+ MB/s Direct 302 Mode</h3>
      Append <code>&redirect=1</code> (or use <code>directDownloadUrl</code>) to stream directly from CDN servers with <code>ratebypass=yes</code>.
    </td>
  </tr>
  <tr>
    <td width="50%">
      <h3>🔞 Age-Restricted Unlock</h3>
      Supports TV/Android embedded InnerTube clients plus encrypted <code>YOUTUBE_COOKIE</code> / <code>cookies.txt</code> session authentication.
    </td>
    <td width="50%">
      <h3>🎧 HTTP 206 Range Streaming</h3>
      Full byte-range proxy support allows Telegram voice chats and players to start playback in <b>0.2s</b> with instant seeking.
    </td>
  </tr>
</table>

---

## 🧭 Architecture

```mermaid
flowchart LR
    Bot["🤖 Music Bot / Client"] -->|x-api-key| Edge{"⚡ Cloudflare Edge"}
    Edge -->|Cache HIT <20ms| Bot
    Edge -->|Cache MISS| Resolver["🔎 Multi-Engine Resolver"]
    Resolver -->|Option 1| Upstream["🌐 Configured Upstream"]
    Resolver -->|Option 2| EdgeClients["📺 InnerTube / Piped + Cookie"]
    EdgeClients --> Response["📦 Stream & Proxy Links"]
    Response -->|Proxied Mode| Proxy["🛡️ /api/file/vps/... (206 Range)"]
    Response -->|Direct Mode &redirect=1| CDN["🚀 Direct CDN (100+ MB/s)"]
```

---

## ⚡ Speed & Performance

| Delivery Mode | Average Speed | 4 MB Audio Track | 100 MB Video File |
| :--- | :---: | :---: | :---: |
| 🚀 **Direct CDN Redirect** (`&redirect=1`) | **40 – 100+ MB/s** | `~0.2s` | `~1 – 3s` *(on VPS / Fast WiFi)* |
| 🛡️ **Edge Proxied Stream** (`downloads`) | **5 – 10 MB/s** | `~0.6s` | `~12 – 18s` |
| ⚡ **Cached Lookup** (`X-Cache: HIT`) | **< 20ms latency** | Instant metadata | Instant metadata |

---

## 🚀 Quick Deploy

Click any deployment method below to expand interactive step-by-step instructions:

<details>
<summary><b>🟠 Option 1: Deploy to Cloudflare Workers via CLI (Recommended)</b></summary>

1. **Install dependencies & authenticate Wrangler:**
   ```bash
   npm install
   npx wrangler login
   ```
2. **Store your secrets securely on Cloudflare (never committed to Git):**
   ```bash
   npx wrangler secret put API_KEY
   # Optional: Unlock 100% of age-restricted videos
   npx wrangler secret put YOUTUBE_COOKIE
   # Optional: Custom upstream backend relay
   npx wrangler secret put UPSTREAM_BACKEND
   npx wrangler secret put UPSTREAM_API_KEY
   ```
3. **Deploy globally in seconds:**
   ```bash
   npx wrangler deploy
   ```

</details>

<details>
<summary><b>🌐 Option 2: Deploy via Cloudflare Dashboard (No Terminal Needed)</b></summary>

1. Log into the [Cloudflare Dashboard](https://dash.cloudflare.com/) → **Workers & Pages** → **Create Worker**.
2. Name your worker and click **Deploy**, then click **Edit Code**.
3. Copy the code from [`worker.js`](worker.js), paste it in, and click **Deploy**.
4. Go to **Settings** → **Variables and Secrets** and add:
   - `API_KEY`: *Your chosen secret token*
   - `YOUTUBE_COOKIE`: *(Optional) Single-line cookie header string*

</details>

<details>
<summary><b>🐍 Option 3: Self-Host with Python FastAPI or Docker</b></summary>

#### Local Python Setup
```bash
cp .env.example .env
# Edit .env and set your private API_KEY
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
python3 main.py
```

#### Docker Setup
```bash
docker build -t lily-api .
docker run -d -p 8000:8000 -e API_KEY="your_secret_key" lily-api
```

</details>

---

## 🤖 Bot Integration (`.env`)

Configure your Telegram music bot with **your own deployed worker URL** and **secret key**:

```env
WORKER_FALLBACK_API_URL="https://your-worker.your-subdomain.workers.dev"
WORKER_FALLBACK_API_KEY="your_secret_api_key_here"
```

---

## 📖 API Playground

<details open>
<summary><b>1. Health Check — <code>GET /</code></b></summary>

```bash
curl -s "https://your-worker.your-subdomain.workers.dev/"
```

```json
{
  "success": true,
  "service": "lily-api-resolver",
  "status": "online"
}
```

</details>

<details open>
<summary><b>2. Resolve Media — <code>GET /api</code></b></summary>

**Headers:** `x-api-key: your_secret_api_key_here` *(or `Authorization: Bearer your_secret_api_key_here`)*  
**Parameters:**
- `url` *(required)*: YouTube URL or 11-character Video ID
- `format` *(optional)*: `mp3` *(default)* or `mp4`

```bash
curl -s -H "x-api-key: your_secret_api_key_here" \
  "https://your-worker.your-subdomain.workers.dev/api?url=dQw4w9WgXcQ&format=mp3"
```

```json
{
  "success": true,
  "title": "Track Title",
  "fileSize": 3449447,
  "fileSizeText": "3.29 MB",
  "format": "mp3",
  "videoId": "dQw4w9WgXcQ",
  "downloads": "https://your-worker.your-subdomain.workers.dev/api/file/vps/<token>.m4a",
  "directDownloadUrl": "https://your-worker.your-subdomain.workers.dev/api/file/vps/<token>.m4a&redirect=1",
  "directStreamUrl": "https://cdn-url/videoplayback?...",
  "mimeType": "audio/mp4",
  "fileExtension": "m4a",
  "audioIncluded": true,
  "videoIncluded": false
}
```

</details>

<details>
<summary><b>3. Unlocking Age-Restricted Videos</b></summary>

> [!TIP]
> Never upload `cookies.txt` to public repositories! It is already blocked by [`.gitignore`](.gitignore).

- **Cloudflare Worker:** Upload your session cookie string securely via `npx wrangler secret put YOUTUBE_COOKIE`.
- **FastAPI Backend:** Place your Netscape format `cookies.txt` in the project root directory; [`main.py`](main.py) detects and loads it automatically.

</details>

<details>
<summary><b>4. Automated Verification Suite</b></summary>

Run the test script against your deployment without storing credentials in files:

```bash
python3 test_api.py "https://your-worker.your-subdomain.workers.dev" "your_secret_api_key_here"
```

</details>

---

## 👨‍💻 Owner & Support

<div align="center">

Need help setting up, scaling, or customizing **Lily-Api**? Reach out directly on Telegram!

<a href="https://t.me/advaydev">
  <img src="https://img.shields.io/badge/💬%20Chat%20with%20Owner-t.me%2Fadvaydev-26A5E4?style=for-the-badge&logo=telegram&logoColor=white" alt="Contact Owner on Telegram" />
</a>

<br/><br/>

<sub>Built with ⚡ Edge Computing & ❤️ by <a href="https://t.me/advaydev">@advaydev</a></sub>

</div>
