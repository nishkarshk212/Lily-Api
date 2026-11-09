/**
 * Cloudflare Worker: YouTube Fallback API & Stream Resolver
 * Replaces: https://youtubenewapi.skybotsdeveloper.workers.dev
 * Default API Key: itsmesid
 */

// Default Configuration (overridable via Worker Environment Variables)
const DEFAULT_CONFIG = {
  API_KEY: "itsmesid",
  SERVICE_NAME: "elite-cloudflare-resolver",
  UPSTREAM_BACKEND: "" // Optional: URL to your VPS/backend (e.g., https://your-vps.com)
};

export default {
  async fetch(request, env, ctx) {
    const config = {
      API_KEY: env?.API_KEY || DEFAULT_CONFIG.API_KEY,
      SERVICE_NAME: env?.SERVICE_NAME || DEFAULT_CONFIG.SERVICE_NAME,
      UPSTREAM_BACKEND: env?.UPSTREAM_BACKEND || DEFAULT_CONFIG.UPSTREAM_BACKEND
    };

    const url = new URL(request.url);
    const path = url.pathname;

    // CORS Headers
    const corsHeaders = {
      "Access-Control-Allow-Origin": "*",
      "Access-Control-Allow-Methods": "GET, POST, OPTIONS, HEAD",
      "Access-Control-Allow-Headers": "Content-Type, Authorization, x-api-key, X-API-KEY",
      "Access-Control-Max-Age": "86400"
    };

    if (request.method === "OPTIONS") {
      return new Response(null, { status: 204, headers: corsHeaders });
    }

    // 1. Health / Status Check Route: GET /
    if (path === "/" || path === "") {
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

    // 3. YouTube Resolver API: /api
    if (path === "/api" || path === "/api/") {
      return handleApiResolve(request, url, config, corsHeaders);
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
async function handleApiResolve(request, url, config, corsHeaders) {
  // Check Authentication
  const authHeader = request.headers.get("x-api-key") || 
                     request.headers.get("X-API-KEY") || 
                     request.headers.get("api-key");
  const bearerToken = (request.headers.get("Authorization") || "").replace(/^Bearer\s+/i, "");
  const queryKey = url.searchParams.get("api_key") || url.searchParams.get("key");

  const providedKey = authHeader || bearerToken || queryKey;

  if (!providedKey || providedKey !== config.API_KEY) {
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
  let targetUrl = url.searchParams.get("url") || url.searchParams.get("id");
  let format = (url.searchParams.get("format") || "mp3").toLowerCase();

  // Also support POST json body
  if (request.method === "POST") {
    try {
      const body = await request.json();
      if (body.url) targetUrl = body.url;
      if (body.format) format = body.format.toLowerCase();
    } catch (_) {}
  }

  // Validate URL input
  if (!targetUrl || targetUrl.trim() === "") {
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

  try {
    // Strategy 1: Forward to custom Upstream Backend if configured
    if (config.UPSTREAM_BACKEND) {
      try {
        const upstreamResp = await fetch(
          `${config.UPSTREAM_BACKEND.replace(/\/+$/, "")}/api?url=${encodeURIComponent(targetUrl)}&format=${format}`,
          {
            headers: {
              "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)",
              "x-api-key": config.API_KEY
            }
          }
        );
        if (upstreamResp.ok) {
          const upstreamData = await upstreamResp.json();
          if (upstreamData && upstreamData.success) {
            return jsonResponse(upstreamData, 200, corsHeaders);
          }
        }
      } catch (err) {
        console.warn("Upstream backend call failed, falling back to edge resolvers", err);
      }
    }

    // Strategy 2: Multi-resolver fallback on Edge
    const result = await resolveYouTubeMedia(videoId, format, origin);
    return jsonResponse(result, 200, corsHeaders);

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
 * Extract 11-character YouTube video ID
 */
function extractVideoId(input) {
  if (!input) return null;
  input = input.trim();

  if (/^[a-zA-Z0-9_-]{11}$/.test(input)) {
    return input;
  }

  const match = input.match(/(?:youtu\.be\/|youtube\.com\/(?:embed\/|v\/|watch\?v=|watch\?.+&v=|shorts\/))([a-zA-Z0-9_-]{11})/);
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
 * Core Resolver: Queries YouTube InnerTube / Piped / Invidious instances
 */
async function resolveYouTubeMedia(videoId, format, origin) {
  let title = "YouTube Audio Track";
  let duration = 200;
  let rawStreamUrl = null;
  let fileSize = 3500000;
  let mimeType = format === "mp4" ? "video/mp4" : "audio/mp4";
  let fileExtension = format === "mp4" ? "mp4" : "m4a";

  // 1. Fetch metadata & title from YouTube oEmbed
  try {
    const oembedResp = await fetch(`https://www.youtube.com/oembed?url=https://www.youtube.com/watch?v=${videoId}&format=json`, {
      headers: { "User-Agent": "Mozilla/5.0" }
    });
    if (oembedResp.ok) {
      const oembed = await oembedResp.json();
      if (oembed.title) title = oembed.title;
    }
  } catch (_) {}

  // 2. Fetch streams using reliable Piped API instances
  const pipedInstances = [
    "https://api.piped.private.coffee",
    "https://pipedapi.kavin.rocks",
    "https://piped-api.lunar.icu",
    "https://cf.piped.video"
  ];

  for (const host of pipedInstances) {
    try {
      const resp = await fetch(`${host}/streams/${videoId}`, {
        headers: { "User-Agent": "Mozilla/5.0" }
      });
      if (resp.ok) {
        const data = await resp.json();
        if (data.title) title = data.title;
        if (data.duration) duration = data.duration;

        if (format === "mp4" && Array.isArray(data.videoStreams) && data.videoStreams.length > 0) {
          const stream = data.videoStreams.find(s => s.quality === "720p" || s.quality === "1080p") || data.videoStreams[0];
          rawStreamUrl = stream.url;
          mimeType = stream.mimeType || "video/mp4";
          fileExtension = "mp4";
          fileSize = stream.contentLength || (duration * 125000);
          break;
        } else if (Array.isArray(data.audioStreams) && data.audioStreams.length > 0) {
          // Find best audio stream (m4a or opus)
          const stream = data.audioStreams.find(s => s.format === "M4A") || data.audioStreams[0];
          rawStreamUrl = stream.url;
          mimeType = stream.mimeType || "audio/mp4";
          fileExtension = stream.format === "M4A" ? "m4a" : "opus";
          fileSize = stream.contentLength || (duration * 16000);
          break;
        }
      }
    } catch (_) {}
  }

  // 3. Fallback: YouTube InnerTube Android/iOS client
  if (!rawStreamUrl) {
    try {
      const innerTubeResp = await fetch("https://www.youtube.com/youtubei/v1/player?prettyPrint=false", {
        method: "POST",
        headers: {
          "Content-Type": "application/json",
          "User-Agent": "com.google.android.youtube/19.29.37 (Linux; U; Android 11; en_US) gzip",
          "X-YouTube-Client-Name": "3",
          "X-YouTube-Client-Version": "19.29.37"
        },
        body: JSON.stringify({
          context: {
            client: {
              clientName: "ANDROID",
              clientVersion: "19.29.37",
              androidSdkVersion: 30,
              hl: "en",
              gl: "US"
            }
          },
          videoId: videoId
        })
      });

      if (innerTubeResp.ok) {
        const ytData = await innerTubeResp.json();
        if (ytData.videoDetails?.title) title = ytData.videoDetails.title;
        if (ytData.videoDetails?.lengthSeconds) duration = parseInt(ytData.videoDetails.lengthSeconds, 10);

        const formats = ytData.streamingData?.adaptiveFormats || [];
        if (format === "mp4") {
          const videoFmt = formats.find(f => f.mimeType && f.mimeType.includes("video/mp4") && f.url);
          if (videoFmt) {
            rawStreamUrl = videoFmt.url;
            mimeType = "video/mp4";
            fileExtension = "mp4";
            fileSize = parseInt(videoFmt.contentLength || (duration * 120000), 10);
          }
        } else {
          const audioFmt = formats.find(f => f.mimeType && f.mimeType.includes("audio/mp4") && f.url) ||
                           formats.find(f => f.mimeType && f.mimeType.includes("audio") && f.url);
          if (audioFmt) {
            rawStreamUrl = audioFmt.url;
            mimeType = audioFmt.mimeType.split(";")[0];
            fileExtension = "m4a";
            fileSize = parseInt(audioFmt.contentLength || (duration * 16000), 10);
          }
        }
      }
    } catch (_) {}
  }

  // 4. Fallback: Cobalt API instance
  if (!rawStreamUrl) {
    const cobaltInstances = ["https://api.cobalt.tools/api/json", "https://cobalt.kwiatekm.tokyo/api/json"];
    for (const cob of cobaltInstances) {
      try {
        const cResp = await fetch(cob, {
          method: "POST",
          headers: {
            "Accept": "application/json",
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0"
          },
          body: JSON.stringify({
            url: `https://www.youtube.com/watch?v=${videoId}`,
            downloadMode: format === "mp4" ? "auto" : "audio"
          })
        });
        if (cResp.ok) {
          const cData = await cResp.json();
          if (cData.url) {
            rawStreamUrl = cData.url;
            fileSize = duration * 16000;
            break;
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
    rawStreamingUrl: proxyDownloadUrl,
    raw_streaming_url: proxyDownloadUrl,
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
 * Stream Proxy handler: Proxies bytes with HTTP Range support
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
    } catch (e) {
      return jsonResponse({ success: false, error: "Invalid encoded stream URL" }, 400, corsHeaders);
    }
  }

  if (!targetStreamUrl) {
    return jsonResponse({ success: false, error: "Stream URL is required" }, 400, corsHeaders);
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
      method: "GET",
      headers: fetchHeaders
    });

    const responseHeaders = new Headers(corsHeaders);
    const passThroughHeaders = [
      "content-type",
      "content-length",
      "content-range",
      "accept-ranges",
      "cache-control"
    ];

    for (const h of passThroughHeaders) {
      const val = upstreamResponse.headers.get(h);
      if (val) responseHeaders.set(h, val);
    }

    if (!responseHeaders.has("accept-ranges")) {
      responseHeaders.set("accept-ranges", "bytes");
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

