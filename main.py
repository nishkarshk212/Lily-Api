import os
import re
import base64
import urllib.parse
from typing import Optional

from fastapi import FastAPI, Request, Query, Header, HTTPException, status
from fastapi.responses import JSONResponse, StreamingResponse, RedirectResponse
from fastapi.middleware.cors import CORSMiddleware
import httpx

app = FastAPI(title="YouTube Fallback API & Stream Resolver", redirect_slashes=False)

# Enable CORS for all origins with exposure of streaming and cache headers
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=[
        "Content-Range",
        "Content-Length",
        "Accept-Ranges",
        "Content-Type",
        "Content-Disposition",
        "X-Cache"
    ]
)

API_KEY = os.getenv("API_KEY", "")
SERVICE_NAME = os.getenv("SERVICE_NAME", "lily-api-resolver")


def extract_video_id(url_or_id: str) -> Optional[str]:
    """Extract YouTube 11-char video ID from various YouTube URL formats"""
    if not url_or_id or not isinstance(url_or_id, str):
        return None
    url_or_id = url_or_id.strip().strip("<>\"'`")
    
    # 1. Direct 11-char ID
    if re.match(r"^[a-zA-Z0-9_-]{11}$", url_or_id):
        return url_or_id
        
    # 2. Structured URL parsing
    try:
        parsed = None
        if url_or_id.startswith(("http://", "https://")):
            parsed = urllib.parse.urlparse(url_or_id)
        elif "youtube.com" in url_or_id or "youtu.be" in url_or_id:
            parsed = urllib.parse.urlparse("https://" + url_or_id)

        if parsed:
            netloc = parsed.netloc.lower()
            # youtu.be/<id>
            if netloc == "youtu.be" or netloc.endswith(".youtu.be"):
                parts = [p for p in parsed.path.split("/") if p]
                if parts and re.match(r"^[a-zA-Z0-9_-]{11}$", parts[0]):
                    return parts[0]

            # youtube.com, www.youtube.com, m.youtube.com, music.youtube.com, youtube-nocookie.com
            if "youtube.com" in netloc or "youtube-nocookie.com" in netloc:
                qs = urllib.parse.parse_qs(parsed.query)
                if "v" in qs and qs["v"] and re.match(r"^[a-zA-Z0-9_-]{11}$", qs["v"][0]):
                    return qs["v"][0]

                path_match = re.search(r"/(?:shorts|live|embed|v|e)/([a-zA-Z0-9_-]{11})", parsed.path, re.I)
                if path_match:
                    return path_match.group(1)
    except Exception:
        pass

    # 3. Regex fallback
    regex = r"(?:youtu\.be/|youtube(?:-nocookie)?\.com/(?:embed/|v/|e/|shorts/|live/|watch\?(?:.*&)?v=))([a-zA-Z0-9_-]{11})"
    match = re.search(regex, url_or_id, re.I)
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
    """Health check endpoint"""
    return {
        "success": True,
        "service": SERVICE_NAME,
        "status": "online",
    }


@app.get("/api")
@app.get("/api/")
@app.post("/api")
@app.post("/api/")
@app.head("/api")
@app.head("/api/")
async def resolve_media(
    request: Request,
    url: Optional[str] = Query(None),
    id: Optional[str] = Query(None),
    videoId: Optional[str] = Query(None),
    format: str = Query("mp3"),
    quality: str = Query("best"),
    x_api_key: Optional[str] = Header(None, alias="x-api-key"),
    authorization: Optional[str] = Header(None),
    api_key: Optional[str] = Query(None),
    apiKey: Optional[str] = Query(None),
    key: Optional[str] = Query(None),
):
    """Resolve YouTube URL or Video ID to playable direct stream and proxy URLs"""
    body_data = {}
    if request.method == "POST":
        try:
            body_data = await request.json()
        except Exception:
            pass

    # 1. Verify Authentication
    bearer = (
        authorization.replace("Bearer ", "").strip() if authorization else None
    )
    body_key = body_data.get("api_key") or body_data.get("apiKey") or body_data.get("key")
    client_key = x_api_key or bearer or api_key or apiKey or key or body_key

    if not API_KEY or not client_key or client_key != API_KEY:
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

    # 2. Extract parameters
    target_url = url or id or videoId or body_data.get("url") or body_data.get("id") or body_data.get("videoId")
    req_format = body_data.get("format", format).lower()
    req_quality = body_data.get("quality", quality).lower()

    if not target_url or not str(target_url).strip():
        return JSONResponse(
            status_code=status.HTTP_400_BAD_REQUEST,
            content={
                "success": False,
                "error": {"code": "invalid_input", "message": "URL is required"},
                "code": "invalid_input",
            },
        )

    # 3. Validate Format
    if req_format not in ("mp3", "mp4"):
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
    video_id = extract_video_id(str(target_url))
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
    file_ext = "m4a" if req_format == "mp3" else "mp4"
    mime_type = "audio/mp4" if req_format == "mp3" else "video/mp4"
    failure_reason = None
    quality_label = None
    resolution = None
    width = None
    height = None
    fps = None
    bitrate = None
    available_qualities = []

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
            if req_format == "mp3"
            else "best[ext=mp4]/bestvideo[ext=mp4]+bestaudio[ext=m4a]/best",
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
            width = info.get("width")
            height = info.get("height")
            fps = info.get("fps")
            bitrate = info.get("tbr") or info.get("vbr") or info.get("abr")
            quality_label = f"{height}p" if height else "HD"
            resolution = f"{width}x{height}" if width and height else None
            if req_format == "mp3":
                file_ext = info.get("ext", "m4a")
                mime_type = "audio/mp4" if file_ext == "m4a" else "audio/mpeg"
    except ImportError:
        pass
    except Exception as yt_err:
        print(f"yt-dlp extraction warning: {yt_err}")

    # Extraction Engine 2: InnerTube Android VR Direct Stream Fallback
    if not raw_stream_url:
        try:
            payload = {
                "context": {
                    "client": {
                        "clientName": "ANDROID_VR",
                        "clientVersion": "1.61.48",
                        "deviceModel": "Quest 3",
                        "hl": "en",
                        "gl": "US"
                    }
                },
                "videoId": video_id,
                "contentCheckOk": True,
                "racyCheckOk": True
            }
            async with httpx.AsyncClient(timeout=6.0) as client:
                resp = await client.post(
                    "https://www.youtube.com/youtubei/v1/player?prettyPrint=false",
                    json=payload,
                    headers={"Content-Type": "application/json", "User-Agent": "Mozilla/5.0"}
                )
                if resp.status_code == 200:
                    yt_data = resp.json()
                    if yt_data.get("videoDetails", {}).get("title"):
                        title = yt_data["videoDetails"]["title"]
                    if yt_data.get("playabilityStatus"):
                        p_status = yt_data["playabilityStatus"].get("status")
                        p_reason = yt_data["playabilityStatus"].get("reason")
                        if p_status and p_status != "OK" and p_reason:
                            failure_reason = p_reason
                    duration = int(yt_data.get("videoDetails", {}).get("lengthSeconds", 200))
                    formats = [
                        *(yt_data.get("streamingData", {}).get("adaptiveFormats", [])),
                        *(yt_data.get("streamingData", {}).get("formats", []))
                    ]
                    if req_format == "mp4":
                        video_fmts = [f for f in formats if "video" in f.get("mimeType", "") and f.get("url")]
                        video_fmts.sort(key=lambda x: (x.get("height", 0), x.get("bitrate", 0)), reverse=True)
                        available_qualities = list(dict.fromkeys([f.get("qualityLabel") or f"{f.get('height')}p" for f in video_fmts if f.get("qualityLabel") or f.get("height")]))
                        chosen_v = None
                        if req_quality and req_quality != "best":
                            q_clean = re.sub(r"[^0-9]", "", req_quality)
                            if q_clean:
                                chosen_v = next((f for f in video_fmts if str(f.get("height")) == q_clean or q_clean in (f.get("qualityLabel") or "")), None)
                        if not chosen_v and video_fmts:
                            chosen_v = video_fmts[0]
                        if chosen_v:
                            raw_stream_url = chosen_v["url"]
                            file_ext = "mp4"
                            mime_type = chosen_v.get("mimeType", "video/mp4").split(";")[0]
                            quality_label = chosen_v.get("qualityLabel") or (f"{chosen_v.get('height')}p" if chosen_v.get("height") else "HD")
                            resolution = f"{chosen_v.get('width')}x{chosen_v.get('height')}" if chosen_v.get("width") and chosen_v.get("height") else None
                            width = chosen_v.get("width")
                            height = chosen_v.get("height")
                            fps = chosen_v.get("fps")
                            bitrate = chosen_v.get("bitrate")
                            file_size = int(chosen_v.get("contentLength") or (duration * (bitrate // 8 if bitrate else 150000)))
                    else:
                        audio_fmts = [f for f in formats if "audio" in f.get("mimeType", "") and f.get("url")]
                        audio_fmts.sort(key=lambda x: (x.get("bitrate", 0), x.get("audioBitrate", 0)), reverse=True)
                        if audio_fmts:
                            chosen_a = audio_fmts[0]
                            raw_stream_url = chosen_a["url"]
                            file_ext = "m4a" if "mp4" in chosen_a.get("mimeType", "") else "opus"
                            mime_type = chosen_a.get("mimeType", "audio/mp4").split(";")[0]
                            bitrate = chosen_a.get("bitrate")
                            quality_label = "high"
                            file_size = int(chosen_a.get("contentLength") or (duration * (bitrate // 8 if bitrate else 16000)))
        except Exception as e:
            print(f"InnerTube extraction error: {e}")

    # Extraction Engine 3: Invidious Instances Fallback
    if not raw_stream_url:
        invidious_hosts = [
            "https://inv.nadeko.net",
            "https://invidious.private.coffee",
            "https://yewtu.be",
            "https://iv.ggtyler.dev"
        ]
        async with httpx.AsyncClient(timeout=5.0) as client:
            for host in invidious_hosts:
                try:
                    resp = await client.get(
                        f"{host}/api/v1/videos/{video_id}",
                        headers={"User-Agent": "Mozilla/5.0"}
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        title = data.get("title", title)
                        duration = data.get("lengthSeconds", 200)
                        adaptive = data.get("adaptiveFormats", [])
                        if req_format == "mp4":
                            v_streams = [s for s in adaptive if "video" in s.get("type", "") and s.get("url")]
                            v_streams.sort(key=lambda x: (x.get("height", 0), x.get("bitrate", 0)), reverse=True)
                            if v_streams:
                                s = v_streams[0]
                                raw_stream_url = s.get("url")
                                file_ext = "mp4"
                                mime_type = "video/mp4"
                                quality_label = s.get("qualityLabel") or (f"{s.get('height')}p" if s.get("height") else "HD")
                                resolution = f"{s.get('width')}x{s.get('height')}" if s.get("width") and s.get("height") else None
                                width = s.get("width")
                                height = s.get("height")
                                file_size = s.get("clen") or (duration * 125000)
                                break
                        else:
                            a_streams = [s for s in adaptive if "audio" in s.get("type", "") and s.get("url")]
                            a_streams.sort(key=lambda x: x.get("bitrate", 0), reverse=True)
                            if a_streams:
                                s = a_streams[0]
                                raw_stream_url = s.get("url")
                                file_ext = "m4a"
                                mime_type = s.get("type", "audio/mp4").split(";")[0]
                                quality_label = "high"
                                file_size = s.get("clen") or (duration * 16000)
                                break
                except Exception:
                    continue

    if not raw_stream_url:
        err_msg = "Upstream extraction failed or timed out"
        if failure_reason:
            if "age" in failure_reason.lower() or "sign in" in failure_reason.lower():
                err_msg = f"Age-restricted content: {failure_reason}. Configure cookies.txt or YOUTUBE_COOKIE to enable playback."
            else:
                err_msg = failure_reason
        return JSONResponse(
            status_code=status.HTTP_502_BAD_GATEWAY,
            content={
                "success": False,
                "error": {
                    "code": "upstream_timeout" if not failure_reason else "extraction_failed",
                    "message": err_msg,
                },
                "code": "upstream_timeout" if not failure_reason else "extraction_failed",
            },
        )

    # 6. Build standardized media stream response
    encoded_stream = encode_b64(raw_stream_url)
    proxy_url = f"{base_url}/api/file/vps/{encoded_stream}.{file_ext}?videoId={video_id}&filename=youtube.{file_ext}"

    return {
        "success": True,
        "title": title,
        "fileSize": int(file_size),
        "fileSizeText": format_file_size(int(file_size)),
        "format": req_format,
        "fullFormat": req_format,
        "videoId": video_id,
        "videoUrl": youtube_url,
        "downloads": proxy_url,
        "downloadUrl": proxy_url,
        "download_url": proxy_url,
        "streamUrl": proxy_url,
        "stream_url": proxy_url,
        "streamLink": proxy_url,
        "streamingUrl": proxy_url,
        "streaming_url": proxy_url,
        "playbackUrl": proxy_url,
        "playback_url": proxy_url,
        "audioUrl": proxy_url,
        "audio_url": proxy_url,
        "directUrl": proxy_url,
        "direct_url": proxy_url,
        "directLink": proxy_url,
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
        "quality": quality_label or ("1080p" if req_format == "mp4" else "high"),
        "qualityLabel": quality_label or ("1080p" if req_format == "mp4" else "high"),
        "resolution": resolution,
        "width": width,
        "height": height,
        "fps": fps,
        "bitrate": bitrate,
        "availableQualities": available_qualities,
        "audioIncluded": True,
        "videoIncluded": (req_format == "mp4"),
        "provider": "vps",
        "providerOrigin": base_url,
    }


@app.get("/api/file/vps/{encoded_path:path}")
@app.head("/api/file/vps/{encoded_path:path}")
@app.get("/api/stream")
@app.head("/api/stream")
async def stream_media(request: Request, encoded_path: Optional[str] = None):
    """Proxy video or audio stream with HTTP Range and HEAD support for seamless playback"""
    target_url = None

    if "url" in request.query_params:
        target_url = request.query_params["url"]
    elif encoded_path:
        clean_path = re.sub(r"\.[a-zA-Z0-9]+$", "", encoded_path)
        try:
            target_url = decode_b64(clean_path)
            # Unwrap nested url parameter if present
            if "url=" in target_url:
                parsed_inner = urllib.parse.parse_qs(urllib.parse.urlparse(target_url).query)
                if "url" in parsed_inner:
                    target_url = parsed_inner["url"][0]
        except Exception:
            raise HTTPException(
                status_code=400, detail="Invalid encoded stream token"
            )

    if not target_url:
        raise HTTPException(status_code=400, detail="Target stream URL missing")

    # Fast 302 direct redirect for maximum download speeds
    if request.query_params.get("redirect") == "1" or request.query_params.get("direct") == "1":
        redirect_url = target_url
        if "ratebypass=" not in redirect_url:
            redirect_url += ("&" if "?" in redirect_url else "?") + "ratebypass=yes"
        return RedirectResponse(url=redirect_url, status_code=302)

    range_header = request.headers.get("range")
    req_headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"}
    if range_header:
        req_headers["range"] = range_header

    client = httpx.AsyncClient(follow_redirects=True, timeout=60.0)
    upstream = await client.send(
        client.build_request(request.method, target_url, headers=req_headers),
        stream=True,
    )

    resp_headers = {}
    for h in [
        "content-type",
        "content-length",
        "content-range",
        "accept-ranges",
        "cache-control",
        "etag",
        "last-modified"
    ]:
        if h in upstream.headers:
            resp_headers[h] = upstream.headers[h]

    if "accept-ranges" not in resp_headers:
        resp_headers["accept-ranges"] = "bytes"

    filename = request.query_params.get("filename")
    if filename:
        resp_headers["content-disposition"] = f'inline; filename="{filename}"'

    if request.method == "HEAD":
        await upstream.aclose()
        await client.aclose()
        return StreamingResponse(
            iter([]),
            status_code=upstream.status_code,
            headers=resp_headers
        )

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
