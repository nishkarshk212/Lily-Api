#!/usr/bin/env python3
"""
Test script to verify Lily-Api YouTube Fallback API & Stream Resolver.
Usage:
    python3 test_api.py [API_BASE_URL] [API_KEY]

Example:
    python3 test_api.py https://your-worker.your-subdomain.workers.dev your_secret_key
"""

import os
import sys
import json
import urllib.request
import urllib.error
import urllib.parse

API_BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
API_KEY = sys.argv[2] if len(sys.argv) > 2 else os.getenv("API_KEY", "your_secret_api_key_here")

TEST_VIDEO_ID = "dQw4w9WgXcQ"
TEST_SHORTS_ID = "3AtDnEC4zak"
MASKED_KEY = f"{API_KEY[:2]}***" if len(API_KEY) > 2 else "***"

print("==================================================")
print(f" Testing Lily-Api: {API_BASE_URL}")
print(f" API Key: {MASKED_KEY}")
print("==================================================\n")

DEFAULT_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

passed_tests = 0
total_tests = 0


def make_request(path, headers=None, data=None, method=None):
    url = f"{API_BASE_URL}{path}"
    req_headers = {"User-Agent": DEFAULT_UA, **(headers or {})}
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            resp_bytes = resp.read()
            try:
                json_data = json.loads(resp_bytes.decode("utf-8"))
            except Exception:
                json_data = None
            return resp.status, json_data, resp.headers, resp_bytes
    except urllib.error.HTTPError as e:
        resp_bytes = e.read()
        try:
            json_data = json.loads(resp_bytes.decode("utf-8"))
        except Exception:
            json_data = None
        return e.code, json_data, e.headers, resp_bytes
    except Exception as e:
        return 0, None, {}, str(e).encode()


def run_test(name, passed, detail=""):
    global passed_tests, total_tests
    total_tests += 1
    if passed:
        passed_tests += 1
        print(f"  ✓ {name}" + (f": {detail}" if detail else ""))
    else:
        print(f"  ✗ {name}" + (f": {detail}" if detail else ""))


# 1. Health Check GET /
print("[1/10] Testing GET & HEAD / (Health Check)...")
status, body, _, _ = make_request("/")
run_test("GET / status online", status == 200 and body and body.get("status") == "online", f"service={body.get('service') if body else 'None'}")

status_head, _, _, _ = make_request("/", method="HEAD")
run_test("HEAD / status 200", status_head == 200)

# 2. Authentication Checks
print("\n[2/10] Testing Authentication Enforcement...")
status, body, _, _ = make_request(f"/api?url={TEST_VIDEO_ID}")
run_test("Without API Key (Expected 401)", status == 401 and body and body.get("error", {}).get("code") == "authentication_required")

status, body, _, _ = make_request(f"/api?url={TEST_VIDEO_ID}", headers={"x-api-key": "invalid_wrong_key"})
run_test("With Invalid API Key (Expected 401)", status == 401)

status, body, _, _ = make_request(f"/api?url={TEST_VIDEO_ID}", headers={"Authorization": f"Bearer {API_KEY}"})
run_test("With Authorization: Bearer <key>", status == 200 and body and body.get("success") is True)

status, body, _, _ = make_request(f"/api?url={TEST_VIDEO_ID}&api_key={urllib.parse.quote(API_KEY)}")
run_test("With ?api_key=<key> query parameter", status == 200 and body and body.get("success") is True)

# 3. Input Validation
print("\n[3/10] Testing Input Validation...")
status, body, _, _ = make_request(f"/api?url={TEST_VIDEO_ID}&format=invalid_fmt", headers={"x-api-key": API_KEY})
run_test("Invalid format rejected (Expected 400)", status == 400 and body and body.get("error", {}).get("code") == "invalid_format")

status, body, _, _ = make_request("/api?format=mp3", headers={"x-api-key": API_KEY})
run_test("Missing URL rejected (Expected 400)", status == 400 and body and body.get("error", {}).get("code") == "invalid_input")

# 4. Standard YouTube Watch URL Resolution (MP3)
print("\n[4/10] Testing Standard YouTube Watch URL (MP3)...")
status, body, _, _ = make_request(f"/api?url=https://www.youtube.com/watch?v={TEST_VIDEO_ID}&format=mp3", headers={"x-api-key": API_KEY})
mp3_resolved = status == 200 and body and body.get("success") is True
run_test("Resolve Standard URL (MP3)", mp3_resolved, f"title='{body.get('title')}'" if body else "")
downloads_url = body.get("downloads") if body else None

# 5. YouTube URL Variations (Live, Shorts, youtu.be, Raw ID)
print("\n[5/10] Testing YouTube URL Variations (Live, Shorts, youtu.be, Raw ID)...")
status, body, _, _ = make_request(f"/api?url=https://www.youtube.com/live/{TEST_VIDEO_ID}&format=mp3", headers={"x-api-key": API_KEY})
run_test("Resolve YouTube Live URL (/live/)", status == 200 and body and body.get("videoId") == TEST_VIDEO_ID)

status, body, _, _ = make_request(f"/api?url=https://www.youtube.com/shorts/{TEST_SHORTS_ID}&format=mp3", headers={"x-api-key": API_KEY})
run_test("Resolve YouTube Shorts URL (/shorts/)", status == 200 and body and body.get("videoId") == TEST_SHORTS_ID)

status, body, _, _ = make_request(f"/api?url=https://youtu.be/{TEST_VIDEO_ID}&format=mp3", headers={"x-api-key": API_KEY})
run_test("Resolve youtu.be Short URL", status == 200 and body and body.get("videoId") == TEST_VIDEO_ID)

status, body, _, _ = make_request(f"/api?url={TEST_VIDEO_ID}&format=mp3", headers={"x-api-key": API_KEY})
run_test("Resolve Direct 11-char Video ID", status == 200 and body and body.get("videoId") == TEST_VIDEO_ID)

# 6. Video Resolution (MP4)
print("\n[6/10] Testing Video Format Resolution (MP4)...")
status, body, _, _ = make_request(f"/api?url={TEST_VIDEO_ID}&format=mp4", headers={"x-api-key": API_KEY})
mp4_resolved = status == 200 and body and body.get("success") is True and body.get("format") == "mp4"
run_test("Resolve Video (MP4)", mp4_resolved, f"mimeType={body.get('mimeType')}" if body else "")

# 7. POST JSON Request
print("\n[7/10] Testing POST Request with JSON Body...")
payload = json.dumps({"url": TEST_VIDEO_ID, "format": "mp3"}).encode("utf-8")
status, body, _, _ = make_request("/api", headers={"x-api-key": API_KEY, "Content-Type": "application/json"}, data=payload, method="POST")
run_test("POST JSON Body Resolution", status == 200 and body and body.get("success") is True)

# 8. Audio Streaming & Byte Range (Partial Content 206)
print("\n[8/10] Testing Audio Stream Proxy with Byte Range (206 Partial Content)...")
if downloads_url:
    range_headers = {"User-Agent": DEFAULT_UA, "Range": "bytes=0-1024"}
    req = urllib.request.Request(downloads_url, headers=range_headers)
    try:
        with urllib.request.urlopen(req, timeout=12) as s_resp:
            chunk = s_resp.read()
            c_range = s_resp.headers.get("Content-Range")
            c_len = len(chunk)
            run_test("Byte Range Streaming (HTTP 206)", s_resp.status in (200, 206), f"HTTP {s_resp.status}, read {c_len} bytes, Content-Range={c_range}")
    except Exception as e:
        run_test("Byte Range Streaming (HTTP 206)", False, str(e))
else:
    run_test("Byte Range Streaming", False, "No stream URL from previous step")

# 9. Stream Proxy HEAD Request
print("\n[9/10] Testing Stream Proxy HEAD Request...")
if downloads_url:
    req = urllib.request.Request(downloads_url, headers={"User-Agent": DEFAULT_UA}, method="HEAD")
    try:
        with urllib.request.urlopen(req, timeout=12) as h_resp:
            c_len = h_resp.headers.get("Content-Length")
            c_type = h_resp.headers.get("Content-Type")
            acc_ranges = h_resp.headers.get("Accept-Ranges")
            run_test("Stream Proxy HEAD Request", h_resp.status == 200, f"HTTP {h_resp.status}, Content-Length={c_len}, Content-Type={c_type}, Accept-Ranges={acc_ranges}")
    except Exception as e:
        run_test("Stream Proxy HEAD Request", False, str(e))
else:
    run_test("Stream Proxy HEAD Request", False, "No stream URL from previous step")

# 10. Direct Download Redirect (redirect=1)
print("\n[10/10] Testing Direct Download Redirect (redirect=1)...")
if downloads_url:
    sep = "&" if "?" in downloads_url else "?"
    redir_url = f"{downloads_url}{sep}redirect=1"

    class NoRedirect(urllib.request.HTTPRedirectHandler):
        def redirect_request(self, req, fp, code, msg, headers, newurl):
            return None

    opener = urllib.request.build_opener(NoRedirect)
    try:
        opener.open(urllib.request.Request(redir_url, headers={"User-Agent": DEFAULT_UA}))
        run_test("Direct Download 302 Redirect", False, "Expected 302 redirect but got 200")
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 307):
            loc = e.headers.get("Location", "")
            run_test("Direct Download 302 Redirect", True, f"HTTP {e.code} -> {loc[:60]}...")
        else:
            run_test("Direct Download 302 Redirect", False, f"Unexpected HTTP {e.code}")
    except Exception as e:
        run_test("Direct Download 302 Redirect", False, str(e))
else:
    run_test("Direct Download Redirect", False, "No stream URL from previous step")

print("\n==================================================")
print(f" Summary: {passed_tests}/{total_tests} Tests Passed ({(passed_tests/total_tests)*100:.1f}%)")
print("==================================================")
sys.exit(0 if passed_tests == total_tests else 1)
