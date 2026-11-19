"""TEST-ONLY stand-in for leoserv, the host's microphone/camera server
(modules/backend/run_host_server.sh): a microphone that plays a WAV file on
request. Run by tenant-test.sh as a container next to the tenant's backend.

    python3 fake_leoserv.py speech.wav [port]

GET /audio      streams 16 kHz mono 16-bit PCM in 30 ms frames, paced in real
                time, as `audio/L16; rate=16000; channels=1; frame_size=480`:
                silence, with the WAV mixed in once per POST /play.
POST /play      plays the WAV once on every open /audio stream.
GET /listeners  how many /audio streams are open, as plain text.
GET /image      404: there is no camera.
Anything else POSTed (text to speak, sounds) is accepted and ignored.
"""
import sys
import threading
import time
import wave
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

RATE, FRAME = 16000, 480
FRAME_BYTES = FRAME * 2
SILENCE = b"\x00" * FRAME_BYTES

with wave.open(sys.argv[1]) as w:
    assert (w.getframerate(), w.getnchannels(), w.getsampwidth()) == (RATE, 1, 2), \
        f"{sys.argv[1]}: need a 16 kHz mono 16-bit WAV"
    SPEECH = w.readframes(w.getnframes())
SPEECH += b"\x00" * (-len(SPEECH) % FRAME_BYTES)

lock = threading.Lock()
streams = {}  # id(handler) -> speech still to play on that stream


def log(msg):
    print(time.strftime("%H:%M:%S"), msg, flush=True)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"

    def do_GET(self):
        path = self.path.split("?")[0]
        if path == "/listeners":
            with lock:
                self.reply(200, str(len(streams)).encode())
        elif path == "/audio":
            self.stream()
        else:
            self.reply(404)

    def do_POST(self):
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        if self.path.split("?")[0] == "/play":
            with lock:
                for key in streams:
                    streams[key] = SPEECH
                count = len(streams)
            log(f"playing {len(SPEECH) / 2 / RATE:.1f}s of speech to {count} listener(s)")
            self.reply(200, str(count).encode())
        else:
            self.reply(200)

    do_PUT = do_DELETE = do_POST

    def reply(self, status, body=b""):
        self.send_response(status)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def stream(self):
        log(f"microphone opened by {self.client_address[0]}")
        self.send_response(200)
        self.send_header("Content-Type", f"audio/L16; rate={RATE}; channels=1; frame_size={FRAME}")
        self.end_headers()
        key = id(self)
        with lock:
            streams[key] = b""
        start, sent = time.monotonic(), 0
        try:
            while True:
                with lock:
                    queue = streams[key]
                    frame, streams[key] = (queue[:FRAME_BYTES], queue[FRAME_BYTES:]) if queue else (SILENCE, b"")
                self.wfile.write(frame)
                sent += 1
                # Real time: frame n is due n x 30 ms after the start.
                delay = start + sent * FRAME / RATE - time.monotonic()
                if delay > 0:
                    time.sleep(delay)
        except (BrokenPipeError, ConnectionResetError):
            log("microphone closed")
        finally:
            with lock:
                streams.pop(key, None)

    def log_message(self, *args):
        pass


port = int(sys.argv[2]) if len(sys.argv) > 2 else 8000
log(f"fake leoserv on :{port}, speech {len(SPEECH) / 2 / RATE:.1f}s")
ThreadingHTTPServer(("0.0.0.0", port), Handler).serve_forever()
