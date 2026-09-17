#!/usr/bin/env python
"""Rung 2 — the notebook made durable.

Joins ONE TENANT of a running deployment, subscribes to an input topic, runs the
same transform this template's installable component runs, and publishes the
result to an output topic. No cltl-example package import, no meta-repo
checkout required — see requirements.notebook.txt.

Start the deployment first:

    docker compose -f deployment/server.compose.yml up -d
    CLTL_TENANT=tenant-a CLTL_CHATUI_PORT=8000 \\
        docker compose -f deployment/tenant.compose.yml up -d

then join that tenant:

    python attach/listen.py --tenant tenant-a \\
        --amqp-url amqp://leolani:leolani@127.0.0.1:5672/ \\
        --management-url http://127.0.0.1:15672

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
start_scenario, stop_scenario = _connect.start_scenario, _connect.stop_scenario

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
    # Required, with NO default. There is no untenanted conversation to join
    # any more, and defaulting would pick a tenant on your behalf.
    parser.add_argument("--tenant", required=True,
                        help="the tenant whose conversation to join, e.g. tenant-a. "
                             "'' attaches as a read-only observer of every tenant on "
                             "the exchange and cannot open a scenario (see --no-scenario)")
    parser.add_argument("--topic-input", default="cltl.topic.text_in")
    parser.add_argument("--topic-output", default="cltl.topic.text_out")
    parser.add_argument("--topic-scenario", default="cltl.topic.scenario")
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

    def handler(event: Event):
        # The tenant is logged because it is the thing under demonstration —
        # without it this script would be strictly less informative than the
        # notebook it is derived from.
        logger.info("[%s] %r (tenant=%r)", event.metadata.topic,
                    getattr(event.payload.signal, "text", event.payload),
                    event.metadata.tenant)

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
        bus.subscribe(args.topic_input, handler)
        # Default baseline: "is MY subscription live". The count rises by one
        # when this listener's own queue is bound.
        wait_until_bound(args.management_url, [args.topic_input], tenant=args.tenant,
                         amqp_url=args.amqp_url)

        if not args.no_scenario:
            # baseline={}: a PRESENCE check, not an increment one. The queue
            # that has to exist before this publish is the chat UI's, not ours,
            # so waiting for the count to rise would be answered by our own
            # subscription above.
            wait_until_bound(args.management_url, [args.topic_scenario], tenant=args.tenant,
                             amqp_url=args.amqp_url, baseline={})
            scenario = start_scenario(bus, args.topic_scenario)
            logger.info("Opened scenario %s for tenant %r — the chat UI should come "
                        "alive now.", scenario.id, args.tenant)
        else:
            logger.info("Not opening a scenario (--no-scenario); something else must "
                        "have, or this tenant's chat UI stays blank.")

        logger.info("Listening on %s, publishing to %s, as tenant %r. Ctrl-C to stop.",
                    args.topic_input, args.topic_output, args.tenant)
        logger.info("Type in THIS tenant's chat UI and you get two replies — the "
                    "shared ELIZA's and this script's. Any other tenant's chat UI "
                    "sees nothing at all.")

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
