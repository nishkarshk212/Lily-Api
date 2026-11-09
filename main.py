import os
import re
import base64
import urllib.parse
from typing import Optional

from fastapi import FastAPI, Request, Query, Header, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx

app = FastAPI(title="YouTube Fallback API & Stream Resolver")

# Enable CORS for all origins
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

API_KEY = os.getenv("API_KEY", "lily")
SERVICE_NAME = os.getenv("SERVICE_NAME", "elite-cloudflare-resolver")


def extract_video_id(url_or_id: str) -> Optional[str]:
    """Extract YouTube 11-char video ID from input string"""
    if not url_or_id:
        return None
    url_or_id = url_or_id.strip()
    if re.match(r"^[a-zA-Z0-9_-]{11}$", url_or_id):
        return url_or_id
    match = re.search(
        r"(?:youtu\.be/|youtube\.com/(?:embed/|v/|watch\?v=|watch\?.+&v=|shorts/))([a-zA-Z0-9_-]{11})",
        url_or_id,
    )
    return match.group(1) if match else None


def format_file_size(size_bytes: int) -> str:
    """Format bytes into readable string (e.g., 3.29 MB)"""
    if not size_bytes:
        return "3.50 MB"
    if size_bytes < 1024:
        return f"{size_bytes} B"
    if size_bytes < 1024 * 1024:
        return f"{size_bytes / 1024:.2f} KB"
    return f"{size_bytes / (1024 * 1024):.2f} MB"


def encode_b64(text: str) -> str:
    """URL-safe base64 encoding without padding"""
    return base64.urlsafe_b64encode(text.encode()).decode().rstrip("=")


def decode_b64(b64_text: str) -> str:
    """URL-safe base64 decoding with padding restoration"""
    padding = len(b64_text) % 4
    if padding:
        b64_text += "=" * (4 - padding)
    return base64.urlsafe_b64decode(b64_text.encode()).decode()


@app.get("/")
@app.head("/")
async def health_check():
    """Health check endpoint matching elite-cloudflare-resolver"""
    return {
        "success": True,
        "service": SERVICE_NAME,
        "status": "online",
    }


@app.get("/api")
@app.post("/api")
async def resolve_media(
    request: Request,
    url: Optional[str] = Query(None),
    format: str = Query("mp3"),
    x_api_key: Optional[str] = Header(None, alias="x-api-key"),
    authorization: Optional[str] = Header(None),
    api_key: Optional[str] = Query(None),
):
    """Resolve YouTube URL or Video ID to playable direct stream and proxy URLs"""
    # 1. Verify Authentication
    bearer = (
        authorization.replace("Bearer ", "").strip() if authorization else None
    )
    client_key = x_api_key or bearer or api_key

    if not client_key or client_key != API_KEY:
        return JSONResponse(
            status_code=status.HTTP_401_UNAUTHORIZED,
            content={
                "success": False,
                "error": {
                    "code": "authentication_required",
                    "message": "Authentication required",
                },
                "code": "authentication_required",
            },
        )

    # If POST request, check body for parameters
    if request.method == "POST":
        try:
            body = await request.json()
            if not url and "url" in body:
                url = body["url"]
            if "format" in body:
                format = body["format"]
        except Exception:
            pass

    # 2. Validate URL input
    if not url or not url.strip():
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "error": {"code": "invalid_input", "message": "URL is required"},
                "code": "invalid_input",
            },
        )

    # 3. Validate Format
    format = format.lower()
    if format not in ("mp3", "mp4"):
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "error": {
                    "code": "invalid_format",
                    "message": "Format must be mp3 or mp4",
                },
                "code": "invalid_format",
            },
        )

    # 4. Extract YouTube Video ID
    video_id = extract_video_id(url)
    if not video_id:
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "error": {
                    "code": "invalid_input",
                    "message": "Invalid YouTube URL or video ID",
                },
                "code": "invalid_input",
            },
        )

    base_url = str(request.base_url).rstrip("/")
    youtube_url = f"https://www.youtube.com/watch?v={video_id}"

    # 5. Extract video metadata and direct stream URL
    title = "YouTube Track"
    raw_stream_url = None
    file_size = 3500000
    file_ext = "m4a" if format == "mp3" else "mp4"
    mime_type = "audio/mp4" if format == "mp3" else "video/mp4"

    # Extraction Engine 1: yt-dlp (if installed)
    try:
        import yt_dlp

        cookie_file = "cookies.txt" if os.path.exists("cookies.txt") else None

        ydl_opts = {
            "quiet": True,
            "no_warnings": True,
            "skip_download": True,
            "age_limit": None,
            "extractor_args": {
                "youtube": {
                    "player_client": ["android", "ios", "tvhtml5", "web"],
                    "player_skip": ["webpage", "configs"],
                }
            },
            "format": "bestaudio[ext=m4a]/bestaudio/best"
            if format == "mp3"
            else "best[ext=mp4]/best",
        }
        if cookie_file:
            ydl_opts["cookiefile"] = cookie_file
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(youtube_url, download=False)
            title = info.get("title", title)
            raw_stream_url = info.get("url")
            file_size = (
                info.get("filesize")
                or info.get("filesize_approx")
                or (info.get("duration", 200) * 16000)
            )
            if format == "mp3":
                file_ext = info.get("ext", "m4a")
                mime_type = "audio/mp4" if file_ext == "m4a" else "audio/mpeg"
    except ImportError:
        pass
    except Exception as yt_err:
        print(f"yt-dlp extraction warning: {yt_err}")

    # Extraction Engine 2: Piped API Fallback
    if not raw_stream_url:
        piped_hosts = [
            "https://api.piped.private.coffee",
            "https://pipedapi.kavin.rocks",
            "https://piped-api.lunar.icu",
        ]
        async with httpx.AsyncClient(timeout=8.0) as client:
            for host in piped_hosts:
                try:
                    resp = await client.get(
                        f"{host}/streams/{video_id}",
                        headers={"User-Agent": "Mozilla/5.0"},
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        title = data.get("title", title)
                        duration = data.get("duration", 200)
                        if format == "mp4" and data.get("videoStreams"):
                            stream = data["videoStreams"][0]
                            raw_stream_url = stream.get("url")
                            file_ext = "mp4"
                            mime_type = "video/mp4"
                            file_size = stream.get("contentLength") or (
                                duration * 125000
                            )
                            break
                        elif data.get("audioStreams"):
                            streams = data["audioStreams"]
                            m4a = next(
                                (s for s in streams if s.get("format") == "M4A"),
                                streams[0],
                            )
                            raw_stream_url = m4a.get("url")
                            file_ext = "m4a"
                            mime_type = "audio/mp4"
                            file_size = m4a.get("contentLength") or (
                                duration * 16000
                            )
                            break
                except Exception:
                    continue

    if not raw_stream_url:
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "success": False,
                "error": {
                    "code": "upstream_timeout",
                    "message": "Upstream extraction failed or timed out",
                },
                "code": "upstream_timeout",
            },
        )

    # 6. Build response matching exact skybotsdeveloper worker format
    encoded_stream = encode_b64(raw_stream_url)
    proxy_url = f"{base_url}/api/file/vps/{encoded_stream}.{file_ext}?videoId={video_id}&filename=youtube.{file_ext}"

    return {
        "success": True,
        "title": title,
        "fileSize": int(file_size),
        "fileSizeText": format_file_size(int(file_size)),
        "format": format,
        "fullFormat": format,
        "videoId": video_id,
        "videoUrl": youtube_url,
        "downloads": proxy_url,
        "downloadUrl": proxy_url,
        "download_url": proxy_url,
        "rawStreamingUrl": proxy_url,
        "raw_streaming_url": proxy_url,
        "directStreamUrl": raw_stream_url,
        "direct_stream_url": raw_stream_url,
        "directDownloadUrl": f"{proxy_url}&redirect=1",
        "direct_download_url": f"{proxy_url}&redirect=1",
        "mimeType": mime_type,
        "streamMimeType": mime_type,
        "stream_mime_type": mime_type,
        "downloadMimeType": mime_type,
        "download_mime_type": mime_type,
        "fileExtension": file_ext,
        "file_extension": file_ext,
        "audioIncluded": True,
        "videoIncluded": (format == "mp4"),
        "provider": "vps",
        "providerOrigin": base_url,
    }


@app.get("/api/file/vps/{encoded_path:path}")
@app.get("/api/stream")
async def stream_media(request: Request, encoded_path: Optional[str] = None):
    """Proxy video or audio stream with HTTP Range support for seamless playback"""
    target_url = None

    if "url" in request.query_params:
        target_url = request.query_params["url"]
    elif encoded_path:
        # Strip extension if present
        clean_path = re.sub(r"\.[a-zA-Z0-9]+$", "", encoded_path)
        try:
            target_url = decode_b64(clean_path)
        except Exception:
            raise HTTPException(
                status_code=400, detail="Invalid encoded stream token"
            )

    if not target_url:
        raise HTTPException(status_code=400, detail="Target stream URL missing")

    # Fast 302 direct redirect for maximum download speeds
    if request.query_params.get("redirect") == "1" or request.query_params.get("direct") == "1":
        from fastapi.responses import RedirectResponse
        redirect_url = target_url
        if "ratebypass=" not in redirect_url:
            redirect_url += ("&" if "?" in redirect_url else "?") + "ratebypass=yes"
        return RedirectResponse(url=redirect_url, status_code=302)

    range_header = request.headers.get("range")
    req_headers = {"User-Agent": "Mozilla/5.0"}
    if range_header:
        req_headers["range"] = range_header

    client = httpx.AsyncClient(follow_redirects=True, timeout=60.0)
    upstream = await client.send(
        client.build_request("GET", target_url, headers=req_headers),
        stream=True,
    )

    resp_headers = {}
    for h in [
        "content-type",
        "content-length",
        "content-range",
        "accept-ranges",
        "cache-control",
    ]:
        if h in upstream.headers:
            resp_headers[h] = upstream.headers[h]

    if "accept-ranges" not in resp_headers:
        resp_headers["accept-ranges"] = "bytes"

    async def stream_generator():
        try:
            async for chunk in upstream.aiter_raw():
                yield chunk
        finally:
            await upstream.aclose()
            await client.aclose()

    return StreamingResponse(
        stream_generator(),
        status_code=upstream.status_code,
        headers=resp_headers,
    )


if __name__ == "__main__":
    import uvicorn

    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)

