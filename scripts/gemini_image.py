#!/usr/bin/env python3
"""Generate an image with Google's Gemini API (e.g. gemini-2.5-flash-image / "Nano Banana").

    export GEMINI_API_KEY=...   # get one at https://aistudio.google.com/apikey
                                 # (sign in with the Google account you want this tied to)
    python scripts/gemini_image.py "a flat vector illustration of ..." -o hero.png

The key is read ONLY from the GEMINI_API_KEY environment variable -- never pass
it as a command-line argument, which would leave it sitting in shell history
and visible to anyone who can list processes on this machine.

This talks directly to Google's REST API over HTTPS; there is no OAuth/browser
login involved and none is needed for this endpoint.
"""

from __future__ import annotations

import argparse
import base64
import json
import os
import sys
import urllib.error
import urllib.request

API_BASE = "https://generativelanguage.googleapis.com/v1beta/models"
DEFAULT_MODEL = "gemini-2.5-flash-image"


def generate(prompt: str, model: str, api_key: str) -> list[bytes]:
    url = f"{API_BASE}/{model}:generateContent"
    body = json.dumps({"contents": [{"parts": [{"text": prompt}]}]}).encode()
    req = urllib.request.Request(
        url,
        data=body,
        method="POST",
        headers={"Content-Type": "application/json", "x-goog-api-key": api_key},
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            payload = json.loads(resp.read())
    except urllib.error.HTTPError as e:
        detail = e.read().decode(errors="replace")
        raise SystemExit(f"Gemini API error {e.code}: {detail}")

    images = []
    for cand in payload.get("candidates", []):
        for part in cand.get("content", {}).get("parts", []):
            inline = part.get("inlineData") or part.get("inline_data")
            if inline and inline.get("data"):
                images.append(base64.b64decode(inline["data"]))
    if not images:
        raise SystemExit(
            "No image in the response (the model may have replied with text "
            f"instead). Full response:\n{json.dumps(payload, indent=2)[:2000]}"
        )
    return images


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("prompt", help="Text prompt describing the image")
    ap.add_argument("-o", "--out", default="gemini-image.png",
                     help="Output file path (default: gemini-image.png)")
    ap.add_argument("--model", default=DEFAULT_MODEL,
                     help=f"Gemini model id (default: {DEFAULT_MODEL})")
    args = ap.parse_args()

    api_key = os.environ.get("GEMINI_API_KEY")
    if not api_key:
        print(
            "GEMINI_API_KEY is not set.\n"
            "Get a key at https://aistudio.google.com/apikey (sign in with your "
            "Google account), then run:\n"
            "  export GEMINI_API_KEY=your-key-here",
            file=sys.stderr,
        )
        return 1

    images = generate(args.prompt, args.model, api_key)
    with open(args.out, "wb") as f:
        f.write(images[0])
    print(f"wrote {args.out} ({len(images[0])} bytes)")
    if len(images) > 1:
        print(f"(API returned {len(images)} images; only the first was saved)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
