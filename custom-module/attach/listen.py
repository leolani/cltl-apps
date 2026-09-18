#!/usr/bin/env python
"""Rung 2 — the notebook made durable.

Joins ONE TENANT of a running deployment, subscribes to its text and image
topics, runs the same two transforms this template's installable component runs,
and publishes the results to an output topic. No cltl-example package import, no
meta-repo checkout required — see requirements.notebook.txt.

Start the deployment first:

    docker compose -f deployment/server.compose.yml up -d
    CLTL_TENANT=tenant-a CLTL_CHATUI_PORT=8000 \\
        docker compose -f deployment/tenant.compose.yml up -d

then join that tenant:

    python attach/listen.py --tenant tenant-a \\
        --amqp-url amqp://leolani:leolani@127.0.0.1:5672/

Type in that tenant's chat UI and you get TWO replies — the shared ELIZA's and
this script's. Upload a picture in its Image tab and you get ONE, this
script's: submitting an image publishes only an ImageSignalEvent, never an
utterance, so ELIZA never sees it. The image itself is not in the event; the
signal carries a `cltl-storage:` reference and `--storage-url` is where that
resolves.

This also OPENS the tenant's conversation, and that part is not custom
functionality. The tenant's chat UI renders nothing until it has seen a
ScenarioStarted on its own routing key, this deployment runs no cltl-context,
and a tenant's scenario can only be opened on that tenant's bus — so the custom
side has to do it. `--no-scenario` turns it off when something else already
has. See docs/tenancy.md.

Those are the addresses of the deployment in deployment/ (see
docs/deployment.md). Against the integration harness's demo stacks instead, the
ports are ephemeral and the credentials are eliza/eliza123 — read both out of
what `make -C integration demo-<name> DEMO_FLAGS='--tier compose'` prints under
`broker`.
"""
import argparse
import importlib.util
import logging
import signal
import sys
import threading
import time
from pathlib import Path

from cltl.combot.infra.event.api import Event
from cltl.combot.infra.event.util import extract_scenario_id
from cltl.combot.event.emissor import TextSignalEvent
from cltl.combot.infra.time_util import timestamp_now
from emissor.representation.scenario import TextSignal

# connect.py sits beside this script rather than in an installed package —
# rung 2 has nothing installed — so it is loaded by path. Deliberately not
# `sys.path.insert(...)` + a plain import: the platform's own conventions
# forbid mutating sys.path, and doing it here would also shadow any module
# named `connect` for the rest of the process.
_connect = importlib.util.module_from_spec(
    importlib.util.spec_from_file_location(
        "_cltl_example_connect", Path(__file__).resolve().parent / "connect.py"))
sys.modules[_connect.__name__] = _connect
_connect.__loader__.exec_module(_connect)
event_bus = _connect.event_bus
start_scenario, stop_scenario = _connect.start_scenario, _connect.stop_scenario
load_image, DEFAULT_STORAGE_URL = _connect.load_image, _connect.DEFAULT_STORAGE_URL

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
logger = logging.getLogger("listen")

# Inlined rather than imported from myorg.example.echo, on purpose: rung 2 has
# no package installed at all, and duplicating six lines here is the whole
# lesson of "rung 3 is where this stops being a copy-paste and starts being a
# package". If you change this, cltl.example.echo.EchoExample is unaffected
# and vice versa — see docs/component.md.
MARKER = " (via attach/listen.py)"

# Seconds to wait for a binding nobody confirms. The first is about our own
# consumer thread, the second about the chat UI's container — see main().
SUBSCRIBE_DELAY = 2.0
SCENARIO_DELAY = 5.0


def transform(text: str):
    if not text or not text.strip():
        return None
    text = text.strip()
    if text.endswith(MARKER):
        return None
    return f"YOU SAID: {text.upper()}{MARKER}"


def describe_image(image):
    # The second modality, and the second local copy — this is
    # myorg.example.imagesize.ImageSizeExample.describe, inlined for the same
    # reason `transform` is. numpy is (rows, cols), so shape[0] is the HEIGHT
    # while every UI says width first; getting that backwards is the only real
    # mistake available in these four lines.
    if image is None or image.size == 0:
        return None
    height, width = image.shape[:2]
    return f"The image you uploaded is {width}x{height}{MARKER}"


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--amqp-url", required=True, help="e.g. amqp://leolani:leolani@127.0.0.1:5672/")
    # Required, with NO default. There is no untenanted conversation to join
    # any more, and defaulting would pick a tenant on your behalf.
    parser.add_argument("--tenant", required=True,
                        help="the tenant whose conversation to join, e.g. tenant-a. "
                             "'' attaches as a read-only observer of every tenant on "
                             "the exchange and cannot open a scenario (see --no-scenario)")
    parser.add_argument("--topic-input", default="cltl.topic.text_in")
    parser.add_argument("--topic-output", default="cltl.topic.text_out")
    parser.add_argument("--topic-scenario", default="cltl.topic.scenario")
    parser.add_argument("--topic-image", default="cltl.topic.image")
    parser.add_argument("--storage-url", default=DEFAULT_STORAGE_URL,
                        help="where cltl-storage:image/<id> resolves — the deployment's "
                             "storage service as seen from OUTSIDE its compose network. "
                             "The trailing slash matters (urljoin)")
    parser.add_argument("--no-images", action="store_true",
                        help="do not subscribe to the image topic — for a deployment "
                             "with no storage service, where every fetch would fail")
    parser.add_argument("--no-scenario", action="store_true",
                        help="do not open a scenario — for when something else already "
                             "did, e.g. this tenant's own myorg.tenant container or "
                             "another listener. Two openers for one tenant leaves the "
                             "chat UI on whichever arrived last")
    args = parser.parse_args()

    if not args.tenant and not args.no_scenario:
        parser.error(
            "--tenant is empty, so this listener cannot open a scenario: an "
            "untenanted bus publishes ScenarioStarted on the bare "
            f"'{args.topic_scenario}' routing key, which no tenanted chat UI binds. "
            "It would reach nobody, silently. Give --tenant a tenant id, or pass "
            "--no-scenario to attach as an observer of every tenant. See "
            "docs/tenancy.md.")

    bus = event_bus(args.amqp_url, tenant=args.tenant)

    def respond_to_image(event: Event):
        signal = event.payload.signal
        if not signal.files:
            logger.warning("Image signal %s carries no file reference.", signal.id)
            return None

        try:
            image = load_image(signal.files[0], args.storage_url)
        except Exception as e:
            # Not fatal, and not rare: the chat UI's upload of the pixels is
            # itself best-effort, so a reference that resolves to nothing is a
            # thing that happens. Either they were never stored, or
            # --storage-url points somewhere else.
            logger.warning("Could not load %s for signal %s: %s. Either the pixels "
                           "were never stored or --storage-url is wrong (note the "
                           "trailing slash).", signal.files[0], signal.id, e)
            return None

        logger.info("fetched pixels for signal %s: shape %s, declared bounds %s",
                    signal.id, image.shape, tuple(signal.ruler.bounds))

        return describe_image(image)

    def handler(event: Event):
        # The tenant is logged because it is the thing under demonstration —
        # without it this script would be strictly less informative than the
        # notebook it is derived from.
        logger.info("[%s] %r (tenant=%r)", event.metadata.topic,
                    getattr(event.payload.signal, "text", event.payload.signal.id),
                    event.metadata.tenant)

        # Dispatch on the topic the BUS stamped on delivery. That is how one
        # subscriber handles several topics, and it is why `topic` is metadata
        # rather than something a publisher sets — see docs/concepts.md.
        if event.metadata.topic == args.topic_image:
            response = respond_to_image(event)
        else:
            response = transform(event.payload.signal.text)

        if not response:
            return

        signal = TextSignal.for_scenario(extract_scenario_id(event), timestamp_now(), timestamp_now(), None, response)
        payload = TextSignalEvent.for_agent(signal)
        # source=event: the only thing that copies tenant and scenario_id onto
        # the reply. See docs/tenancy.md.
        bus.publish(args.topic_output, Event.for_payload(payload, source=event))
        logger.info("published: %s", response)

    scenario = None
    try:
        topics = [args.topic_input] if args.no_images else [args.topic_input, args.topic_image]
        for topic in topics:
            bus.subscribe(topic, handler)
        # `subscribe` returns before RabbitMQ has bound the queue, and a topic
        # exchange drops a message matching no binding — silently, on both
        # sides. This is a guess, not a check: two seconds against a consumer
        # thread that needs one AMQP round trip on localhost. See
        # docs/attaching.md for what that buys and what it does not.
        time.sleep(SUBSCRIBE_DELAY)

        if not args.no_scenario:
            # A longer wait, and a weaker guess: the queue that has to exist
            # before this publish is the CHAT UI's, in another container, not
            # ours. Five seconds is what [myorg.tenant] start_delay budgets for
            # exactly the same problem at rung 4 — one number for one guess.
            time.sleep(SCENARIO_DELAY)
            scenario = start_scenario(bus, args.topic_scenario)
            logger.info("Opened scenario %s for tenant %r — the chat UI should come "
                        "alive now.", scenario.id, args.tenant)
        else:
            logger.info("Not opening a scenario (--no-scenario); something else must "
                        "have, or this tenant's chat UI stays blank.")

        logger.info("Listening on %s, publishing to %s, as tenant %r. Ctrl-C to stop.",
                    ", ".join(topics), args.topic_output, args.tenant)
        logger.info("Type in THIS tenant's chat UI and you get two replies — the "
                    "shared ELIZA's and this script's. Any other tenant's chat UI "
                    "sees nothing at all.")
        if args.no_images:
            logger.info("Not listening for images (--no-images).")
        else:
            logger.info("Upload a picture in the Image tab and Submit, and you get "
                        "ONE reply — this script's. Submitting publishes an image "
                        "signal and no utterance, so ELIZA never sees it. The pixels "
                        "come from %s, not from the event.", args.storage_url)

        stop = threading.Event()
        signal.signal(signal.SIGINT, lambda *_: stop.set())
        signal.signal(signal.SIGTERM, lambda *_: stop.set())
        stop.wait()
        logger.info("Stopping.")
    finally:
        # Order matters and so does the `finally`: the scenario has to close
        # while the bus is still open, and a crash must not leave the tenant's
        # chat UI holding a conversation whose owner is gone.
        if scenario is not None:
            stop_scenario(bus, args.topic_scenario, scenario)
            logger.info("Closed scenario %s.", scenario.id)
        # A bus left open keeps kombu's ConsumerMixin retrying a dead connection
        # forever — always close it.
        bus.close()


if __name__ == "__main__":
    main()
