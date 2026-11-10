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

API_BASE_URL = sys.argv[1].rstrip("/") if len(sys.argv) > 1 else os.getenv("API_BASE_URL", "http://127.0.0.1:8000")
API_KEY = sys.argv[2] if len(sys.argv) > 2 else os.getenv("API_KEY", "your_secret_api_key_here")

TEST_VIDEO_ID = "dQw4w9WgXcQ"
MASKED_KEY = f"{API_KEY[:2]}***" if len(API_KEY) > 2 else "***"

print(f"==================================================")
print(f" Testing Lily-Api: {API_BASE_URL}")
print(f" API Key: {MASKED_KEY}")
print(f"==================================================\n")


def make_request(path, headers=None, expect_status=200):
    url = f"{API_BASE_URL}{path}"
    req_headers = {"User-Agent": "Mozilla/5.0", **(headers or {})}
    req = urllib.request.Request(url, headers=req_headers)
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = resp.read()
            try:
                json_data = json.loads(data.decode("utf-8"))
            except Exception:
                json_data = None
            return resp.status, json_data, data
    except urllib.error.HTTPError as e:
        data = e.read()
        try:
            json_data = json.loads(data.decode("utf-8"))
        except Exception:
            json_data = None
        return e.code, json_data, data
    except Exception as e:
        return 0, None, str(e).encode()


# 1. Health Check
print("[1/5] Testing GET / (Health Check)...")
status, body, _ = make_request("/")
if status == 200 and body and body.get("status") == "online":
    print(f"  ✓ SUCCESS: Status is online (service: {body.get('service')})")
else:
    print(f"  ✗ FAILED: Expected 200 online, got {status} ({body})")

# 2. Authentication Check (Without API Key)
print("\n[2/5] Testing GET /api without API key (Should be 401)...")
status, body, _ = make_request(f"/api?url={TEST_VIDEO_ID}")
if status == 401 and body and body.get("error", {}).get("code") == "authentication_required":
    print(f"  ✓ SUCCESS: Correctly rejected with 401 authentication_required")
else:
    print(f"  ✗ FAILED: Expected 401, got {status} ({body})")

# 3. Validation Check (Invalid format)
print("\n[3/5] Testing GET /api with invalid format (Should be 400)...")
status, body, _ = make_request(
    f"/api?url={TEST_VIDEO_ID}&format=invalid_fmt",
    headers={"x-api-key": API_KEY}
)
if status == 400 and body and body.get("error", {}).get("code") == "invalid_format":
    print(f"  ✓ SUCCESS: Correctly rejected with 400 invalid_format")
else:
    print(f"  ✗ FAILED: Expected 400, got {status} ({body})")

# 4. Resolve YouTube Stream (Valid)
print(f"\n[4/5] Testing GET /api with valid video ({TEST_VIDEO_ID})...")
status, body, _ = make_request(
    f"/api?url={TEST_VIDEO_ID}&format=mp3",
    headers={"x-api-key": API_KEY}
)
if status == 200 and body and body.get("success"):
    print(f"  ✓ SUCCESS: Resolved video: '{body.get('title')}'")
    print(f"    - Video ID: {body.get('videoId')}")
    print(f"    - File Size: {body.get('fileSizeText')}")
    print(f"    - Download URL: {body.get('downloads')[:70]}...")

    # 5. Test Audio Streaming & Byte Range
    print("\n[5/5] Testing Stream Proxy with Byte Range (206 Partial Content)...")
    stream_url = body.get("downloads")
    if stream_url:
        req = urllib.request.Request(stream_url, headers={"User-Agent": "Mozilla/5.0", "Range": "bytes=0-1024"})
        try:
            with urllib.request.urlopen(req, timeout=10) as s_resp:
                if s_resp.status in (200, 206):
                    chunk = s_resp.read()
                    print(f"  ✓ SUCCESS: Received {len(chunk)} audio bytes (HTTP {s_resp.status})")
                else:
                    print(f"  ✗ Stream returned unexpected status: {s_resp.status}")
        except Exception as e:
            print(f"  ✗ Stream fetch error: {e}")
    else:
        print("  ✗ No download URL in response to test streaming.")
else:
    print(f"  ✗ FAILED: Resolution returned {status}: {body}")

print("\n==================================================")
print(" Test completed.")
print("==================================================")

