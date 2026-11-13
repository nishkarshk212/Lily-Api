/**
 * Lily-Api: Cloudflare Worker YouTube Fallback API & Stream Resolver
 * Configure sensitive credentials securely via Worker Secrets / Environment Variables.
 */

// Default Configuration (Set real values via Cloudflare Secrets / env)
const DEFAULT_CONFIG = {
  API_KEY: "",
  SERVICE_NAME: "lily-api-resolver",
  UPSTREAM_BACKEND: "",
  UPSTREAM_API_KEY: "",
  YOUTUBE_COOKIE: ""
};

export default {
  async fetch(request, env, ctx) {
    const config = {
      API_KEY: env?.API_KEY || DEFAULT_CONFIG.API_KEY,
      SERVICE_NAME: env?.SERVICE_NAME || DEFAULT_CONFIG.SERVICE_NAME,
      UPSTREAM_BACKEND: env?.UPSTREAM_BACKEND || DEFAULT_CONFIG.UPSTREAM_BACKEND,
      UPSTREAM_API_KEY: env?.UPSTREAM_API_KEY || DEFAULT_CONFIG.UPSTREAM_API_KEY,
      YOUTUBE_COOKIE: env?.YOUTUBE_COOKIE || DEFAULT_CONFIG.YOUTUBE_COOKIE
    };

    const url = new URL(request.url);
    const path = url.pathname;

    // CORS Headers with complete Range and Expose support
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS, HEAD",
      "Access-Control-Allow-Headers": "Content-Type, Authorization, x-api-key, X-API-KEY, api-key, Range",
      "Access-Control-Expose-Headers": "Content-Range, Content-Length, Accept-Ranges, Content-Type, Content-Disposition, X-Cache",
      "Access-Control-Max-Age": "86400"
    };

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders });
    }

    // 1. Health / Status Check Route: GET / or HEAD /
    if (path === "/" || path === "") {
      if (request.method === "HEAD") {
        return new Response(null, {
          status: 200,
          headers: {
            "Content-Type": "application/json; charset=utf-8",
            ...corsHeaders
          }
        });
      }
      return jsonResponse({
        success: true,
        service: config.SERVICE_NAME,
        status: "online"
      }, 200, corsHeaders);
    }

    // 2. Stream Proxy Route: /api/file/... or /api/stream
    if (path.startsWith("/api/file/") || path === "/api/stream") {
      return handleFileStream(request, url, config, corsHeaders);
    }

    // 3. YouTube Resolver API: /api or /api/
    if (path === "/api" || path === "/api/") {
      return handleApiResolve(request, url, config, corsHeaders, ctx);
    }

    // 404 Route Not Found
    return jsonResponse({
      success: false,
      error: {
        code: "not_found",
        message: "Route not found"
      },
      code: "not_found"
    }, 404, corsHeaders);
  }
};

/**
 * Handle YouTube URL resolution (/api)
 */
async function handleApiResolve(request, url, config, corsHeaders, ctx) {
  // Support POST JSON body
  let body = null;
  if (request.method === "POST") {
    try {
      body = await request.json();
    } catch (_) {}
  }

  // Check Authentication (headers, Bearer token, query params, or POST body)
  const authHeader = request.headers.get("x-api-key") || 
                     request.headers.get("X-API-KEY") || 
                     request.headers.get("api-key");
  const bearerToken = (request.headers.get("Authorization") || "").replace(/^Bearer\s+/i, "");
  const queryKey = url.searchParams.get("api_key") || url.searchParams.get("apiKey") || url.searchParams.get("key");
  const bodyKey = body?.api_key || body?.apiKey || body?.key;

  const providedKey = authHeader || bearerToken || queryKey || bodyKey;

  if (!config.API_KEY || !providedKey || providedKey !== config.API_KEY) {
    return jsonResponse({
      success: false,
      error: {
        code: "authentication_required",
        message: "Authentication required"
      },
      code: "authentication_required"
    }, 401, corsHeaders);
  }

  // Get parameters
  let targetUrl = url.searchParams.get("url") || url.searchParams.get("id") || url.searchParams.get("videoId") || body?.url || body?.id || body?.videoId;
  let format = (url.searchParams.get("format") || body?.format || "mp3").toLowerCase();

  // Validate URL input
  if (!targetUrl || typeof targetUrl !== "string" || targetUrl.trim() === "") {
    return jsonResponse({
      success: false,
      error: {
        code: "invalid_input",
        message: "URL is required"
      },
      code: "invalid_input"
    }, 400, corsHeaders);
  }

  // Validate Format
  if (format !== "mp3" && format !== "mp4") {
    return jsonResponse({
      success: false,
      error: {
        code: "invalid_format",
        message: "Format must be mp3 or mp4"
      },
      code: "invalid_format"
    }, 400, corsHeaders);
  }

  // Extract YouTube Video ID
  const videoId = extractVideoId(targetUrl);
  if (!videoId) {
    return jsonResponse({
      success: false,
      error: {
        code: "invalid_input",
        message: "Invalid YouTube URL or video ID"
      },
      code: "invalid_input"
    }, 400, corsHeaders);
  }

  const origin = `${url.protocol}//${url.host}`;
  const cacheKey = new Request(`${origin}/__cache_api__/${videoId}/${format}`);
  const cache = caches.default;

  // Check Cloudflare Edge Cache for sub-20ms instant responses
  try {
    const cachedResp = await cache.match(cacheKey);
    if (cachedResp) {
      const cachedData = await cachedResp.json();
      return jsonResponse(cachedData, 200, {
        ...corsHeaders,
        "X-Cache": "HIT"
      });
    }
  } catch (_) {}

  try {
    // Strategy 1: Forward to configured Upstream Resolver Backend if set
    if (config.UPSTREAM_BACKEND) {
      try {
        const cleanUpstream = config.UPSTREAM_BACKEND.replace(/\/+$/, "");
        const upstreamOrigin = new URL(cleanUpstream).origin;
        const upstreamKey = config.UPSTREAM_API_KEY || config.API_KEY;

        const upstreamResp = await fetch(
          `${cleanUpstream}/api?url=${encodeURIComponent(targetUrl)}&format=${format}`,
          {
            headers: {
              "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
              "x-api-key": upstreamKey
            },
            redirect: "follow",
            signal: AbortSignal.timeout(8000)
          }
        );
        if (upstreamResp.ok) {
          const upstreamData = await upstreamResp.json();
          if (upstreamData && upstreamData.success) {
            // Rewrite upstream origin to this worker's origin for all streaming/download links
            const fieldsToRewrite = [
              "downloads", "downloadUrl", "download_url",
              "streamUrl", "stream_url", "streamLink", "stream_link",
              "streamingUrl", "streaming_url", "playbackUrl", "playback_url",
              "audioUrl", "audio_url", "directUrl", "direct_url", "directLink", "direct_link",
              "rawDirectLink", "raw_direct_link", "rawStreamingUrl", "raw_streaming_url",
              "directDownloadUrl", "direct_download_url", "providerOrigin"
            ];
            for (const key of fieldsToRewrite) {
              if (upstreamData[key] && typeof upstreamData[key] === "string") {
                upstreamData[key] = upstreamData[key].replaceAll(upstreamOrigin, origin);
              }
            }
            upstreamData.providerOrigin = origin;

            if (upstreamData.downloads && !upstreamData.directDownloadUrl) {
              const sep = upstreamData.downloads.includes("?") ? "&" : "?";
              upstreamData.directDownloadUrl = `${upstreamData.downloads}${sep}redirect=1`;
              upstreamData.direct_download_url = upstreamData.directDownloadUrl;
            }

            // Cache at Edge for 2 hours
            try {
              const responseToCache = new Response(JSON.stringify(upstreamData), {
                status: 200,
                headers: {
                  "Content-Type": "application/json; charset=utf-8",
                  "Cache-Control": "public, max-age=7200"
                }
              });
              if (ctx && ctx.waitUntil) {
                ctx.waitUntil(cache.put(cacheKey, responseToCache));
              }
            } catch (_) {}

            return jsonResponse(upstreamData, 200, {
              ...corsHeaders,
              "X-Cache": "MISS"
            });
          }
        }
      } catch (err) {
        console.warn("Upstream relay failed, trying local edge resolvers:", err);
      }
    }

    // Strategy 2: Multi-resolver fallback on Edge
    const result = await resolveYouTubeMedia(videoId, format, origin, config);

    // Cache at Edge for 2 hours (7200 seconds)
    try {
      const responseToCache = new Response(JSON.stringify(result), {
        status: 200,
        headers: {
          "Content-Type": "application/json; charset=utf-8",
          "Cache-Control": "public, max-age=7200"
        }
      });
      if (ctx && ctx.waitUntil) {
        ctx.waitUntil(cache.put(cacheKey, responseToCache));
      }
    } catch (_) {}

    return jsonResponse(result, 200, {
      ...corsHeaders,
      "X-Cache": "MISS"
    });

  } catch (error) {
    return jsonResponse({
      success: false,
      error: {
        code: "extraction_failed",
        message: error.message || "Failed to extract YouTube stream"
      },
      code: "extraction_failed"
    }, 500, corsHeaders);
  }
}

/**
 * Extract 11-character YouTube video ID from various YouTube URL formats
 */
function extractVideoId(input) {
  if (!input || typeof input !== "string") return null;
  input = input.trim();

  // Strip wrapping markdown, quotes, angle brackets
  input = input.replace(/^[<"'`]+|[>"'`]+$/g, "").trim();

  // Direct 11-char ID check
  if (/^[a-zA-Z0-9_-]{11}$/.test(input)) {
    return input;
  }

  // Parse structured URL
  try {
    let urlObj = null;
    if (input.startsWith("http://") || input.startsWith("https://")) {
      urlObj = new URL(input);
    } else if (input.includes("youtube.com") || input.includes("youtu.be")) {
      urlObj = new URL(`https://${input}`);
    }

    if (urlObj) {
      const hostname = urlObj.hostname.toLowerCase();

      // youtu.be/<id>
      if (hostname === "youtu.be" || hostname.endsWith(".youtu.be")) {
        const pathParts = urlObj.pathname.split("/").filter(Boolean);
        if (pathParts.length > 0 && /^[a-zA-Z0-9_-]{11}$/.test(pathParts[0])) {
          return pathParts[0];
        }
      }

      // youtube.com, www.youtube.com, m.youtube.com, music.youtube.com, youtube-nocookie.com
      if (hostname.includes("youtube.com") || hostname.includes("youtube-nocookie.com")) {
        // 1. ?v=...
        const v = urlObj.searchParams.get("v");
        if (v && /^[a-zA-Z0-9_-]{11}$/.test(v)) {
          return v;
        }

        // 2. /shorts/<id>, /live/<id>, /embed/<id>, /v/<id>, /e/<id>
        const pathMatch = urlObj.pathname.match(/\/(?:shorts|live|embed|v|e)\/([a-zA-Z0-9_-]{11})/i);
        if (pathMatch && pathMatch[1]) {
          return pathMatch[1];
        }
      }
    }
  } catch (_) {}

  // Regex fallback
  const regex = /(?:youtu\.be\/|youtube(?:-nocookie)?\.com\/(?:embed\/|v\/|e\/|shorts\/|live\/|watch\?(?:.*&)?v=))([a-zA-Z0-9_-]{11})/i;
  const match = input.match(regex);
  return match ? match[1] : null;
}

/**
 * Format bytes into human-readable string (e.g. "3.29 MB")
 */
function formatFileSize(bytes) {
  if (!bytes || isNaN(bytes)) return "3.50 MB";
  const num = parseInt(bytes, 10);
  if (num < 1024) return `${num} B`;
  if (num < 1024 * 1024) return `${(num / 1024).toFixed(2)} KB`;
  return `${(num / (1024 * 1024)).toFixed(2)} MB`;
}

/**
 * Encode URL into Base64 (URL-safe)
 */
function encodeBase64Url(str) {
  const bytes = new TextEncoder().encode(str);
  let binary = "";
  for (let i = 0; i < bytes.byteLength; i++) {
    binary += String.fromCharCode(bytes[i]);
  }
  return btoa(binary)
    .replace(/\+/g, "-")
    .replace(/\//g, "_")
    .replace(/=+$/, "");
}

/**
 * Decode Base64 (URL-safe) into string
 */
function decodeBase64Url(base64) {
  base64 = base64.replace(/-/g, "+").replace(/_/g, "/");
  while (base64.length % 4) {
    base64 += "=";
  }
  const binary = atob(base64);
  const bytes = new Uint8Array(binary.length);
  for (let i = 0; i < binary.length; i++) {
    bytes[i] = binary.charCodeAt(i);
  }
  return new TextDecoder().decode(bytes);
}

/**
 * Core Resolver: Queries YouTube InnerTube / Invidious fallback instances
 */
async function resolveYouTubeMedia(videoId, format, origin, config) {
  let title = "YouTube Audio Track";
  let duration = 200;
  let rawStreamUrl = null;
  let fileSize = 3500000;
  let mimeType = format === "mp4" ? "video/mp4" : "audio/mp4";
  let fileExtension = format === "mp4" ? "mp4" : "m4a";

  // 1. Fetch metadata & title from YouTube oEmbed
  try {
    const oembedResp = await fetch(`https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=${videoId}&format=json`, {
      headers: { "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36" },
      signal: AbortSignal.timeout(3500)
    });
    if (oembedResp.ok) {
      const oembed = await oembedResp.json();
      if (oembed.title) title = oembed.title;
    }
  } catch (_) {}

  // 2. Query YouTube InnerTube with Android VR & Mobile clients (Direct cipher-free formats)
  const innerTubeClients = [
    {
      name: "ANDROID_VR",
      version: "1.61.48",
      deviceModel: "Quest 3"
    },
    {
      name: "ANDROID",
      version: "19.44.38",
      sdk: 34
    },
    {
      name: "IOS",
      version: "19.45.4"
    }
  ];

  for (const c of innerTubeClients) {
    try {
      const bodyPayload = {
        context: {
          client: {
            clientName: c.name,
            clientVersion: c.version,
            hl: "en",
            gl: "US",
            ...(c.deviceModel ? { deviceModel: c.deviceModel } : {}),
            ...(c.sdk ? { androidSdkVersion: c.sdk } : {})
          }
        },
        videoId: videoId,
        contentCheckOk: true,
        racyCheckOk: true
      };

      const reqHeaders = {
        "Content-Type": "application/json",
        "User-Agent": c.sdk
          ? "com.google.android.youtube/19.44.38 (Linux; U; Android 14; en_US) gzip"
          : "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        ...(config?.YOUTUBE_COOKIE ? { "Cookie": config.YOUTUBE_COOKIE } : {})
      };

      const innerTubeResp = await fetch("https://www.youtube.com/youtubei/v1/player?prettyPrint=false", {
        method: "POST",
        headers: reqHeaders,
        body: JSON.stringify(bodyPayload),
        signal: AbortSignal.timeout(5000)
      });

      if (innerTubeResp.ok) {
        const ytData = await innerTubeResp.json();
        if (ytData.videoDetails?.title) title = ytData.videoDetails.title;
        if (ytData.videoDetails?.lengthSeconds) duration = parseInt(ytData.videoDetails.lengthSeconds, 10);

        const formats = ytData.streamingData?.adaptiveFormats || ytData.streamingData?.formats || [];
        if (format === "mp4") {
          const videoFmt = formats.find(f => f.mimeType && f.mimeType.includes("video/mp4") && f.url);
          if (videoFmt) {
            rawStreamUrl = videoFmt.url;
            mimeType = "video/mp4";
            fileExtension = "mp4";
            fileSize = parseInt(videoFmt.contentLength || (duration * 125000), 10);
            break;
          }
        } else {
          const audioFmt = formats.find(f => f.mimeType && f.mimeType.includes("audio/mp4") && f.url) ||
                           formats.find(f => f.mimeType && f.mimeType.includes("audio") && f.url);
          if (audioFmt) {
            rawStreamUrl = audioFmt.url;
            mimeType = audioFmt.mimeType.split(";")[0];
            fileExtension = "m4a";
            fileSize = parseInt(audioFmt.contentLength || (duration * 16000), 10);
            break;
          }
        }
      }
    } catch (_) {}
  }

  // 3. Fallback: Invidious Public Instances
  if (!rawStreamUrl) {
    const invidiousHosts = [
      "https://inv.nadeko.net",
      "https://invidious.private.coffee",
      "https://yewtu.be",
      "https://iv.ggtyler.dev"
    ];
    for (const host of invidiousHosts) {
      try {
        const resp = await fetch(`${host}/api/v1/videos/${videoId}`, {
          headers: { "User-Agent": "Mozilla/5.0" },
          signal: AbortSignal.timeout(3500)
        });
        if (resp.ok) {
          const data = await resp.json();
          if (data.title) title = data.title;
          if (data.lengthSeconds) duration = data.lengthSeconds;
          const adaptive = data.adaptiveFormats || [];
          if (format === "mp4") {
            const vStream = adaptive.find(s => s.type && s.type.includes("video/mp4") && s.url);
            if (vStream) {
              rawStreamUrl = vStream.url;
              mimeType = "video/mp4";
              fileExtension = "mp4";
              fileSize = parseInt(vStream.clen || (duration * 125000), 10);
              break;
            }
          } else {
            const aStream = adaptive.find(s => s.type && s.type.includes("audio/mp4") && s.url) ||
                            adaptive.find(s => s.type && s.type.includes("audio") && s.url);
            if (aStream) {
              rawStreamUrl = aStream.url;
              mimeType = aStream.type.split(";")[0];
              fileExtension = "m4a";
              fileSize = parseInt(aStream.clen || (duration * 16000), 10);
              break;
            }
          }
        }
      } catch (_) {}
    }
  }

  if (!rawStreamUrl) {
    throw new Error("Unable to extract playback stream for this video. Please try again.");
  }

  // Build the proxied download & streaming URL
  const encodedStream = encodeBase64Url(rawStreamUrl);
  const proxyDownloadUrl = `${origin}/api/file/vps/${encodedStream}.${fileExtension}?videoId=${videoId}&filename=youtube.${fileExtension}`;

  const fileSizeText = formatFileSize(fileSize);

  return {
    success: true,
    title: title,
    fileSize: fileSize,
    fileSizeText: fileSizeText,
    format: format,
    fullFormat: format,
    videoId: videoId,
    videoUrl: `https://www.youtube.com/watch?v=${videoId}`,
    downloads: proxyDownloadUrl,
    downloadUrl: proxyDownloadUrl,
    download_url: proxyDownloadUrl,
    streamUrl: proxyDownloadUrl,
    stream_url: proxyDownloadUrl,
    streamLink: proxyDownloadUrl,
    streamingUrl: proxyDownloadUrl,
    streaming_url: proxyDownloadUrl,
    playbackUrl: proxyDownloadUrl,
    playback_url: proxyDownloadUrl,
    audioUrl: proxyDownloadUrl,
    audio_url: proxyDownloadUrl,
    directUrl: proxyDownloadUrl,
    direct_url: proxyDownloadUrl,
    directLink: proxyDownloadUrl,
    rawStreamingUrl: proxyDownloadUrl,
    raw_streaming_url: proxyDownloadUrl,
    directStreamUrl: rawStreamUrl,
    direct_stream_url: rawStreamUrl,
    directDownloadUrl: `${proxyDownloadUrl}&redirect=1`,
    direct_download_url: `${proxyDownloadUrl}&redirect=1`,
    mimeType: mimeType,
    streamMimeType: mimeType,
    stream_mime_type: mimeType,
    downloadMimeType: mimeType,
    download_mime_type: mimeType,
    fileExtension: fileExtension,
    file_extension: fileExtension,
    audioIncluded: true,
    videoIncluded: (format === "mp4"),
    provider: "vps",
    providerOrigin: origin
  };
}

/**
 * Stream Proxy handler: Proxies bytes with HTTP Range and HEAD support
 */
async function handleFileStream(request, url, config, corsHeaders) {
  let targetStreamUrl = null;

  // Support /api/stream?url=...
  if (url.searchParams.has("url")) {
    targetStreamUrl = url.searchParams.get("url");
  } else {
    // Support /api/file/:provider/:encoded.<ext>
    const parts = url.pathname.replace(/^\/api\/file\/[^\/]+\//, "");
    const base64Part = parts.split("?")[0].replace(/\.[a-zA-Z0-9]+$/, "");
    try {
      targetStreamUrl = decodeBase64Url(base64Part);
      // If target wraps a googlevideo.com URL, unwrap it directly
      if (targetStreamUrl && targetStreamUrl.includes("url=")) {
        const queryParams = new URL(targetStreamUrl).searchParams;
        if (queryParams.has("url")) {
          targetStreamUrl = queryParams.get("url");
        }
      }
    } catch (e) {
      return jsonResponse({ success: false, error: "Invalid encoded stream URL" }, 400, corsHeaders);
    }
  }

  if (!targetStreamUrl) {
    return jsonResponse({ success: false, error: "Stream URL is required" }, 400, corsHeaders);
  }

  // 302 Direct Redirect bypasses proxy latency entirely when redirect=1 or direct=1
  if (url.searchParams.get("redirect") === "1" || url.searchParams.get("direct") === "1") {
    let redirectUrl = targetStreamUrl;
    if (!redirectUrl.includes("ratebypass=")) {
      redirectUrl += (redirectUrl.includes("?") ? "&" : "?") + "ratebypass=yes";
    }
    return Response.redirect(redirectUrl, 302);
  }

  // Forward Range header if requested by client (crucial for music streaming seeking)
  const rangeHeader = request.headers.get("Range");
  const fetchHeaders = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
  };
  if (rangeHeader) {
    fetchHeaders["Range"] = rangeHeader;
  }

  try {
    const upstreamResponse = await fetch(targetStreamUrl, {
      method: request.method === "HEAD" ? "HEAD" : "GET",
      headers: fetchHeaders,
      signal: AbortSignal.timeout(30000)
    });

    const responseHeaders = new Headers(corsHeaders);
    const passThroughHeaders = [
      "content-type",
      "content-length",
      "content-range",
      "accept-ranges",
      "cache-control",
      "etag",
      "last-modified"
    ];

    for (const h of passThroughHeaders) {
      const val = upstreamResponse.headers.get(h);
      if (val) responseHeaders.set(h, val);
    }

    if (!responseHeaders.has("accept-ranges")) {
      responseHeaders.set("accept-ranges", "bytes");
    }

    const filename = url.searchParams.get("filename");
    if (filename) {
      responseHeaders.set("Content-Disposition", `inline; filename="${filename}"`);
    }

    if (request.method === "HEAD") {
      return new Response(null, {
        status: upstreamResponse.status,
        headers: responseHeaders
      });
    }

    return new Response(upstreamResponse.body, {
      status: upstreamResponse.status,
      headers: responseHeaders
    });
  } catch (error) {
    return jsonResponse({
      success: false,
      error: `Failed to stream media: ${error.message}`
    }, 502, corsHeaders);
  }
}

/**
 * Helper to build JSON responses
 */
function jsonResponse(data, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(data), {
    status: status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      ...extraHeaders
    }
  });
}
