#!/usr/bin/env python
"""Rung 2 — the notebook made durable.

Attaches to a running deployment's bus, subscribes to an input topic, runs the
same transform this template's installable component runs, and publishes the
result to an output topic. No cltl-example package import, no meta-repo
checkout required — see requirements.notebook.txt.

    python attach/listen.py \\
        --amqp-url amqp://leolani:leolani@127.0.0.1:5672/ \\
        --management-url http://127.0.0.1:15672

Those are the addresses of the deployment in deployment/deployment.compose.yml
(see docs/deployment.md). Against the integration harness's demo stacks
instead, the ports are ephemeral and the credentials are eliza/eliza123 — read
both out of what `make -C integration demo-<name> DEMO_FLAGS='--tier compose'`
prints under `broker`.
"""
import argparse
import importlib.util
import logging
import signal
import sys
import threading
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
event_bus, wait_until_bound = _connect.event_bus, _connect.wait_until_bound

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)-8s %(message)s")
logger = logging.getLogger("listen")

# Inlined rather than imported from myorg.example.echo, on purpose: rung 2 has
# no package installed at all, and duplicating six lines here is the whole
# lesson of "rung 3 is where this stops being a copy-paste and starts being a
# package". If you change this, cltl.example.echo.EchoExample is unaffected
# and vice versa — see docs/component.md.
MARKER = " (via attach/listen.py)"


def transform(text: str):
    if not text or not text.strip():
        return None
    text = text.strip()
    if text.endswith(MARKER):
        return None
    return f"YOU SAID: {text.upper()}{MARKER}"


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--amqp-url", required=True, help="e.g. amqp://leolani:leolani@127.0.0.1:5672/")
    parser.add_argument("--management-url", default=None, help="e.g. http://127.0.0.1:PORT (optional but recommended)")
    parser.add_argument("--tenant", default="", help="empty = every tenant on the exchange")
    parser.add_argument("--topic-input", default="cltl.topic.text_in")
    parser.add_argument("--topic-output", default="cltl.topic.text_out")
    args = parser.parse_args()

    bus = event_bus(args.amqp_url, tenant=args.tenant)

    def handler(event: Event):
        logger.info("[%s] %r", event.metadata.topic, getattr(event.payload.signal, "text", event.payload))

        response = transform(event.payload.signal.text)
        if not response:
            return

        signal = TextSignal.for_scenario(extract_scenario_id(event), timestamp_now(), timestamp_now(), None, response)
        payload = TextSignalEvent.for_agent(signal)
        # source=event: the only thing that copies tenant and scenario_id onto
        # the reply. See docs/tenancy.md.
        bus.publish(args.topic_output, Event.for_payload(payload, source=event))
        logger.info("published: %s", response)

    bus.subscribe(args.topic_input, handler)
    wait_until_bound(args.management_url, [args.topic_input], tenant=args.tenant,
                     amqp_url=args.amqp_url)
    logger.info("Listening on %s, publishing to %s. Ctrl-C to stop.",
               args.topic_input, args.topic_output)

    stop = threading.Event()
    signal.signal(signal.SIGINT, lambda *_: stop.set())
    signal.signal(signal.SIGTERM, lambda *_: stop.set())
    stop.wait()

    logger.info("Stopping.")
    # A bus left open keeps kombu's ConsumerMixin retrying a dead connection
    # forever — always close it.
    bus.close()


if __name__ == "__main__":
    main()
