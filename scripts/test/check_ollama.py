#!/usr/bin/env python3
"""Checks a GPU server's Ollama from outside, through modules/reverse-proxy,
the way an OpenAI client uses it: https://<host>/ollama/v1 with the bearer
token from the server's config/credentials (OLLAMA_TOKEN) as api_key.

    scripts/test/check_ollama.py https://combot.example.org <token>
    scripts/test/check_ollama.py https://combot.example.org <token> --image photo.jpg

Standard library only. Checks, in order: no token and a wrong token are
refused with 401; /v1/models lists the model; a text chat completion; and a
chat completion with an image (a generated red square unless --image is
given). Exits non-zero if any check fails.
"""
import argparse
import base64
import json
import mimetypes
import struct
import sys
import time
import urllib.error
import urllib.request
import zlib

parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
parser.add_argument("url", help="the server, e.g. https://combot.example.org (/ollama is added if missing)")
parser.add_argument("token", help="the bearer token, OLLAMA_TOKEN in the server's config/credentials")
parser.add_argument("--model", default="qwen3-vl:8b-instruct-q4_K_M", help="default: %(default)s")
parser.add_argument("--image", help="an image file for the vision check (default: a generated red square)")
parser.add_argument("--timeout", type=float, default=300, help="seconds per request (default: %(default)s)")
args = parser.parse_args()

base = args.url.rstrip("/").removesuffix("/v1")
if not base.endswith("/ollama"):
    base += "/ollama"

failures = 0


def check(name, fn):
    global failures
    start = time.monotonic()
    try:
        detail = fn()
        print(f"PASS {name} ({time.monotonic() - start:.1f}s){': ' + detail if detail else ''}")
    except Exception as e:  # noqa: BLE001 - report every failure the same way
        failures += 1
        print(f"FAIL {name}: {e}")


def request(path, token=None, body=None):
    """(status, parsed JSON or text) of a GET, or a POST when body is given."""
    req = urllib.request.Request(base + path, data=None if body is None else json.dumps(body).encode())
    if body is not None:
        req.add_header("Content-Type", "application/json")
    if token is not None:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=args.timeout) as resp:
            status, raw = resp.status, resp.read()
    except urllib.error.HTTPError as e:
        status, raw = e.code, e.read()
    try:
        return status, json.loads(raw)
    except ValueError:
        return status, raw.decode(errors="replace")[:200]


def expect_refused(token):
    def run():
        status, _ = request("/v1/models", token)
        if status != 401:
            raise AssertionError(f"HTTP {status}, expected 401")
    return run


def models():
    status, body = request("/v1/models", args.token)
    if status != 200:
        raise AssertionError(f"HTTP {status}: {body}")
    ids = [m["id"] for m in body.get("data", [])]
    if args.model not in ids:
        raise AssertionError(f"{args.model} is not among the pulled models {ids}")
    return ", ".join(ids)


def chat(content):
    status, body = request("/v1/chat/completions", args.token, {
        "model": args.model,
        "messages": [{"role": "user", "content": content}],
        "temperature": 0,
    })
    if status != 200:
        raise AssertionError(f"HTTP {status}: {body}")
    return body["choices"][0]["message"]["content"].strip()


def red_png(size=64):
    row = b"\x00" + b"\xff\x00\x00" * size  # filter byte, then RGB pixels
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data))
    return (b"\x89PNG\r\n\x1a\n"
            + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 2, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(row * size))
            + chunk(b"IEND", b""))


def text():
    reply = chat("Answer with one word: OK")
    if not reply:
        raise AssertionError("empty reply")
    return repr(reply)


def vision():
    if args.image:
        with open(args.image, "rb") as f:
            data = f.read()
        mime = mimetypes.guess_type(args.image)[0] or "image/jpeg"
        question = "Describe this image in one sentence."
    else:
        data, mime = red_png(), "image/png"
        question = "What colour is this image? Answer with one word."
    reply = chat([
        {"type": "image_url", "image_url": {"url": f"data:{mime};base64,{base64.b64encode(data).decode()}"}},
        {"type": "text", "text": question},
    ])
    if not args.image and "red" not in reply.lower():
        raise AssertionError(f"expected 'red', got {reply!r}")
    return repr(reply)


print(f"Ollama at {base}, model {args.model}")
check("no token is refused", expect_refused(None))
check("a wrong token is refused", expect_refused("not-the-token"))
check("/v1/models lists the model", models)
check("text chat completion", text)
check("vision chat completion", vision)
sys.exit(1 if failures else 0)
