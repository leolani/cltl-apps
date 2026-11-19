"""The checks of tenant-test.sh, run by it in a container on the throwaway
tenant's Docker network, with kombu from the cltl-backend image. Not meant to
be run by hand: tenant-test.sh sets up everything this assumes.

Environment (set by tenant-test.sh):
    TENANT_URL   the tenant's amqps:// URL, its line in tenants.urls
    TENANT_ID    the tenant id, which every routing key here ends in
    CHECKS       comma-separated, from chat, objects, asr
    IMAGE, WAV   paths of the test image and speech, inside this container
    IMAGE_NAME, WAV_NAME  their names, for the output
    TIMEOUT      seconds to wait for a result, per step
    VERBOSE      1 prints every event on the bus as JSON
"""
import bz2
import json
import os
import ssl
import sys
import time
import urllib.error
import urllib.request
import wave

import kombu
from PIL import Image

CHAT = "http://chatui:8000/chatui"
MIC = "http://mic:8000"

URL = os.environ["TENANT_URL"]
TENANT = os.environ["TENANT_ID"]
CHECKS = os.environ.get("CHECKS", "chat,objects,asr").split(",")
IMAGE = os.environ["IMAGE"]
WAV = os.environ["WAV"]
TIMEOUT = float(os.environ.get("TIMEOUT", "120"))
VERBOSE = os.environ.get("VERBOSE") == "1"
IMAGE_NAME = os.environ.get("IMAGE_NAME", os.path.basename(IMAGE))
WAV_NAME = os.environ.get("WAV_NAME", os.path.basename(WAV))

# Topic names as the deployment configs set them (templates/common/config/
# default.config). ELIZA answers on text_out by default, and on eliza_out on a
# server that frees text_out for a tenant's own module (see
# templates/gpu-server/config/custom.config), so a reply counts on either.
TEXT_IN = "cltl.topic.text_in"
REPLY_TOPICS = ("cltl.topic.text_out", "cltl.topic.eliza_out")
OBJECTS = "cltl.topic.object_recognition"
TOPICS = (TEXT_IN, *REPLY_TOPICS, OBJECTS, "cltl.topic.vad")

LINES = ["Hello, I am testing the server.", "I feel a bit tired today."]

# Where to look on the server when a check fails: the services it depends on
# there, as named by scripts/server-compose.sh.
HINTS = {
    "chat": "server-side: eliza (and the event bus); tenant-side: context and chatui, logs below",
    "objects": "server-side: vlm-object and ollama. vlm-object runs on a GPU server only; "
               "against a plain server use --only chat,asr",
    "asr": "server-side: vad and asr (whisper on a GPU server); tenant-side: the backend, logs below",
}


def short(topic):
    return topic.rsplit(".", 1)[-1]


class Bus:
    """One exclusive queue on the tenant's own AMQPS connection, bound to every
    topic above for this tenant. Events are kept in arrival order; the
    checks remember where they started and look only at what came after."""

    def __init__(self):
        ssl_opts = {"cert_reqs": ssl.CERT_REQUIRED, "ca_certs": "/etc/ssl/certs/ca-certificates.crt"}
        self.conn = kombu.Connection(URL, ssl=ssl_opts, connect_timeout=15)
        exchange = kombu.Exchange("cltl.combot", type="topic", passive=True)
        bindings = [kombu.binding(exchange, routing_key=f"{t}.{TENANT}") for t in TOPICS]
        queue = kombu.Queue("", bindings=bindings, exclusive=True, auto_delete=True)
        self.consumer = self.conn.Consumer(queue, callbacks=[self._receive], accept=None)
        self.consumer.consume()
        self.events = []

    def _receive(self, body, message):
        raw = message.body  # kombu has usually undone the bzip2 compression already
        try:
            raw = bz2.decompress(raw)
        except OSError:
            pass
        event = json.loads(raw)
        topic = message.delivery_info["routing_key"].removesuffix(f".{TENANT}")
        self.events.append((topic, event))
        message.ack()
        if VERBOSE:
            print(f"--- event on {topic}\n{json.dumps(event, indent=1)}", flush=True)

    def pump(self, seconds):
        end = time.monotonic() + seconds
        while (left := end - time.monotonic()) > 0:
            try:
                self.conn.drain_events(timeout=min(left, 1))
            except Exception as e:  # socket.timeout between events
                if "timed out" not in str(e).lower():
                    raise

    def mark(self):
        return len(self.events)

    def wait_for(self, since, match, timeout):
        """The first event after `since` that match(topic, payload) accepts, or None."""
        end = time.monotonic() + timeout
        while True:
            for topic, event in self.events[since:]:
                if match(topic, event["payload"]):
                    return topic, event
            since = len(self.events)
            if time.monotonic() >= end:
                return None
            self.pump(min(1, end - time.monotonic()))

    def after(self, since, match):
        return [(t, e) for t, e in self.events[since:] if match(t, e["payload"])]


def http(url, data=None, ctype="application/json"):
    if isinstance(data, (dict, list)):
        data = json.dumps(data).encode()
    elif isinstance(data, str):
        data = data.encode()
    req = urllib.request.Request(url, data=data, method="POST" if data is not None else "GET")
    if data is not None:
        req.add_header("Content-Type", ctype)
    with urllib.request.urlopen(req, timeout=30) as resp:
        body = resp.read()
        if body and resp.headers.get_content_type() == "application/json":
            return json.loads(body)
        return body.decode(errors="replace")


def is_reply(topic, payload):
    return topic in REPLY_TOPICS and bool((payload.get("signal") or {}).get("text"))


def text_of(event):
    return event["payload"]["signal"]["text"]


class Failed(Exception):
    pass


def current_chat():
    """The chat context opened for this tenant, once it is there."""
    end = time.monotonic() + TIMEOUT
    while True:
        try:
            chat = http(f"{CHAT}/chat/current")
            if isinstance(chat, dict) and chat.get("id") and chat.get("scenario_id"):
                return chat
            problem = f"no scenario yet: {chat!r}"
        except (urllib.error.URLError, OSError) as e:
            problem = str(e)
        if time.monotonic() > end:
            raise Failed(f"the chat UI has no open chat after {TIMEOUT:.0f}s ({problem})")
        time.sleep(2)


def say(bus, chat, line):
    """Send one chat line as `alice`; (topic, reply text) or None."""
    since = bus.mark()
    http(f"{CHAT}/chat/{chat['id']}?speaker=alice", line, ctype="text/plain")
    found = bus.wait_for(since, is_reply, min(TIMEOUT, 60))
    return found and (found[0], text_of(found[1]))


def check_chat(bus, chat):
    replies = []
    for line in LINES:
        reply = say(bus, chat, line)
        print(f"     alice: {line}")
        if not reply:
            raise Failed(f"no reply on {' or '.join(REPLY_TOPICS)} to {line!r}")
        print(f"  {short(reply[0]):>8}: {reply[1]}")
        replies.append(short(reply[0]))
    return "replies on " + ", ".join(sorted(set(replies)))


def check_objects(bus, chat):
    with Image.open(IMAGE) as img:
        width, height = img.size
        mime = Image.MIME.get(img.format, "image/jpeg")
    with open(IMAGE, "rb") as f:
        data = f.read()
    since = bus.mark()
    uploaded = http(f"{CHAT}/chat/{chat['id']}/image?width={width}&height={height}", data, ctype=mime)
    http(f"{CHAT}/chat/{chat['id']}/image/{uploaded['id']}/annotations",
         {"regions": [{"x0": 0, "y0": 0, "x1": width, "y1": height, "label": "test"}]})
    print(f"  uploaded {IMAGE_NAME} ({width}x{height}) as image {uploaded['id']}")

    found = bus.wait_for(since, lambda t, p: t == OBJECTS, TIMEOUT)
    if not found:
        raise Failed(f"no event on {OBJECTS} within {TIMEOUT:.0f}s")
    objects = []
    for mention in found[1]["payload"].get("mentions", []):
        bounds = (mention.get("segment") or [{}])[0].get("bounds")
        for annotation in mention.get("annotations", []):
            value = annotation.get("value") or {}
            kind, label = value.get("type"), value.get("label")
            if kind in ("scene", "scene_description"):
                print(f"  {kind.replace('_', ' ')}: {label}")
            else:
                print(f"  object: {label}, box {bounds}, confidence {value.get('confidence')}")
                if label and bounds:
                    objects.append(label)
    if not objects:
        raise Failed(f"the event on {OBJECTS} holds no object with a label and a box")
    return ", ".join(objects)


def check_asr(bus, chat):
    with wave.open(WAV) as w:
        seconds = w.getnframes() / w.getframerate()

    # The backend opens the microphone once the scenario runs, i.e. after
    # the consent answer; nothing would hear the speech before that.
    end = time.monotonic() + min(TIMEOUT, 60)
    while http(f"{MIC}/listeners").strip() == "0":
        if time.monotonic() > end:
            raise Failed("the tenant's backend never opened the (fake) microphone")
        bus.pump(1)

    since = bus.mark()
    http(f"{MIC}/play", "")
    print(f"  playing {WAV_NAME} ({seconds:.1f}s) on the microphone")

    def is_asr(topic, payload):
        return topic == TEXT_IN and payload.get("type") == "AsrTextSignalEvent"

    # Listen through the speech, then until transcripts stop coming: 10s
    # without a new one after the speech ended, or the timeout.
    speech_end = time.monotonic() + seconds
    deadline = speech_end + TIMEOUT
    last, count = time.monotonic(), 0
    while time.monotonic() < deadline:
        bus.pump(1)
        heard = bus.after(since, is_asr)
        if len(heard) != count:
            count, last = len(heard), time.monotonic()
        if count and time.monotonic() > max(speech_end, last) + 10:
            break
    bus.pump(3)  # replies to the last transcript

    transcripts = [text_of(e) for _, e in bus.after(since, is_asr)]
    for topic, event in bus.events[since:]:
        payload = event["payload"]
        if is_asr(topic, payload):
            print(f"     heard: {text_of(event)}")
        elif is_reply(topic, payload):
            print(f"  {short(topic):>8}: {text_of(event)}")
    if not any(t.strip() for t in transcripts):
        vad = len(bus.after(since, lambda t, p: t == "cltl.topic.vad"))
        raise Failed(f"no AsrTextSignalEvent with text on {TEXT_IN} ({vad} VAD event(s) seen)")
    return f"{len(transcripts)} transcript(s)"


def main():
    print(f"tenant {TENANT}, checks {','.join(CHECKS)}", flush=True)
    bus = Bus()
    results = {}

    try:
        chat = current_chat()
        print(f"chat {chat['id']}, scenario {chat['scenario_id']}")
        # Answer the agent's opening consent question; nothing responds before.
        reply = say(bus, chat, "yes")
        print(f"     alice: yes\n  {short(reply[0]) if reply else '':>8}: {reply[1] if reply else '(no reply)'}")
    except Failed as e:
        print(f"FAIL setup: {e}")
        return 1

    for name, check in (("chat", check_chat), ("objects", check_objects), ("asr", check_asr)):
        if name not in CHECKS:
            continue
        print(f"\n== {name}", flush=True)
        start = time.monotonic()
        try:
            results[name] = (True, check(bus, chat))
        except Failed as e:
            results[name] = (False, str(e))
        except Exception as e:  # noqa: BLE001 - an HTTP or bus error fails this check only
            results[name] = (False, f"{type(e).__name__}: {e}")
        ok, detail = results[name]
        print(f"{'PASS' if ok else 'FAIL'} {name} ({time.monotonic() - start:.1f}s): {detail}", flush=True)
        if not ok:
            print(f"     look at {HINTS[name]}")

    print("\n" + "  ".join(f"{'PASS' if ok else 'FAIL'} {name}" for name, (ok, _) in results.items()))
    return 0 if all(ok for ok, _ in results.values()) else 1


if __name__ == "__main__":
    sys.exit(main())
