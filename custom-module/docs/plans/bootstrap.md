# Bootstrapping cltl-example

Status: implemented · Date: 2026-09-09

> **Partly superseded** by [`tenant-isolation.md`](tenant-isolation.md)
> (2026-09-17), which split the deployment into a shared server and one
> stack per tenant. Commands on this page naming
> `deployment/deployment.compose.yml` no longer work — see
> [`../deployment.md`](../deployment.md). Kept as a record of what was
> built and why, not as instructions.

## Why

`cltl-dev`'s `CLAUDE.md` documents how to add a new *platform* component, but
nothing showed a third party how to attach custom processing to an *existing*
deployment without becoming part of the platform itself. This repository is
that entry point: a template a copier clones, renames, and fills in.

## What was built

- The four-file service pattern (`api.py` / `echo.py` / `service.py` /
  `container.py`), in a namespace (`myorg`) the platform does not own, so a
  copy of this template never collides with the platform's own `cltl` /
  `cltl_service` packages.
- Two fixes applied relative to the platform components this was copied from:
  `stop()` returns rather than falling through a `pass` on no worker
  (`cltl-eliza` and `cltl-vad` both have this bug; `cltl-monitoring` doesn't),
  and `_process` always publishes with `source=event` (`cltl-eliza`'s
  greeting branch omits it and silently drops tenant/scenario_id).
- Bus-level-only tenancy: no per-event Python filter, because the bus already
  does the filtering via routing keys; two log-once warnings when a shared
  bus or an incoming event carries no tenant.
- No intention gating, because of `TopicWorker._check_intention`'s
  known cross-tenant gating defect
  (`integration/tests/slices/test_intention_routing.py::TestTenantScopedGating`).
- Four runnable rungs: `attach/example.ipynb` and `attach/listen.py` (attach
  to a live broker, no package install), `attach/inprocess.py` (the
  component composed in one process, no broker), and `compose/
  example.compose.yml` + the `Dockerfile` (join a running deployment as a
  container).
- One meta-repo change: `integration/src/cltl_integration/__main__.py`'s demo
  launcher now prints the broker's AMQP and RabbitMQ management URLs under
  `--tier compose`, since rungs 1–2 need them and nothing printed them
  before. Verified against `integration/tests/test_demo_launcher.py` (no
  regressions — the new lines never match the launcher's own module-key URL
  pattern, and tier 1 prints nothing new since `InProcessRunner` has no
  broker).

## What was found and fixed during implementation

Building for real (`make build`, `make test`/`make pytest-run`, `src/main.py`
standalone) surfaced four real bugs the design pass did not catch:

1. `setup.py`'s build failed outright without a `README.md` present — caught
   the moment `make build` ran, not a paper defect.
2. `artifact_name` needed to be the underscore-normalised form
   (`myorg_example`, not `myorg.example`) — confirmed empirically from the
   sdist filename this venv's setuptools actually produced, exactly as
   flagged as a risk during planning.
3. `flask`/`werkzeug` were missing from `setup.py`'s `service` extra.
   `cltl-eliza` gets them transitively through `cltl.emissor-data`'s own
   `service` extra; this template has no such dependency to piggyback on, so
   `src/main.py`'s `/health` endpoint needed them declared directly.
4. `attach/connect.py`'s `register()` function shadowed the module-level
   `from kombu.serialization import register` import, causing infinite
   self-recursion disguised as a `TypeError` about unexpected keyword
   arguments. Renamed the import to `_register_serializer`.
5. `make docker-ghcr-build` failed outright: the image resolves `--no-index`
   from the first-party sdist registry plus whatever the base image
   preinstalls, and neither `pytest` nor `requests` (both in
   `requirements.txt`, needed only for the dev venv and `attach/`) is
   available that way. Split off `requirements.docker.txt` with just
   `.[service]`, matching `cltl-vad`'s own docker/dev requirements split —
   caught only by actually running the Docker build, not by reasoning about
   it.

Two test races were also found and fixed: `test_a_raising_transform_does_not_
kill_the_worker` published two events back-to-back with no synchronisation,
racing against `TopicWorker`'s default `buffer_size=1` + `OVERWRITE`
strategy, which could silently drop the first event before it was processed;
and `test_reply_carries_the_source_scenario_id` asserted on
`reply.metadata.scenario_id` for an event that only carried a scenario id in
its *payload* (`signal.time.container_id`), not its metadata — correct
platform behaviour (`extract_scenario_id`'s documented fallback), not a
service bug, so the test was split into two.

## Follow-up: published images (2026-09-09)

The docs originally required a `cltl-dev` checkout for everything, because the
only deployment to attach to was `make -C integration demo-text-pipeline`.
With the component images published to `ghcr.io/leolani`, that requirement
splits in two, and only the second half survives:

- **Running a deployment** needs no checkout. `deployment/deployment.compose.yml`
  plus `deployment/config/` is a self-contained four-service stack (RabbitMQ,
  chat UI, ELIZA, context/BDI) pulled from published images. Rungs 1–2 need
  nothing else. Documented in `docs/deployment.md`.
- **Building this template** (rungs 3–4) still needs one, because the
  `Dockerfile` and `make build` resolve `cltl.combot`/`emissor` with
  `pip --no-index` from `cltl-requirements/leolani/` — an sdist registry the
  published *images* do not carry. Left as-is deliberately; the README and
  `docs/docker.md` now state the split rather than implying one rule.

Three bugs found by running the new path rather than reasoning about it:

6. `wait_until_bound` hardcoded `auth=("eliza", "eliza123")` — the integration
   harness's broker credentials. Against any other deployment the management
   API returns 401, and the 401 handler degrades to a flat 2-second sleep, so
   the binding check silently stopped checking and the dropped-first-message
   race it exists to close came back. Now takes them from `amqp_url=`.
7. `attach/listen.py` did `sys.path.insert(0, ...)` to import `connect.py`,
   which `CLAUDE.md` forbids outright. Replaced with an `importlib` load by
   path, which also stops it shadowing any other module named `connect`.
8. The deployment's compose project — and therefore the network name rung 4
   must join — defaulted to `deployment`, after the compose file's *parent
   directory* rather than the repository. Pinned with a `name:` key.

## Verification performed

- `make depend && make build` (twice), `make test`, `make pytest-run` — all
  green, 30/30 tests passing under both runners.
- `venv/bin/pip list` confirmed after every rebuild — never trusted a green
  `make build` alone (its `venv:` recipe chains with `;`, so a genuinely
  broken install still exits 0).
- `attach/inprocess.py` run directly: prints the expected transformed reply
  with no broker or Docker involved (rung 3, headless).
- `src/main.py` run standalone against the default (`internal`) config:
  confirmed `/health` returns 200 and no spurious tenancy warning fires
  (correctly suppressed for `implementation: internal`).
- `integration/tests/test_demo_launcher.py`: 8/8 passing after the
  `__main__.py` change, both via the venv's `pytest` directly.
- **All four rungs verified against a live `demo-text-pipeline --tier
  compose` stack**, using the platform's own `ChatClient` driver to send
  real chat messages and read real replies back:
  - The demo launcher's report printed the new `broker` lines with the
    correct AMQP and management URLs.
  - Rung 2 (`attach/listen.py`) subscribed, bound, and answered a live
    utterance — confirmed **both** eliza's reply and this module's reply
    appear in the same chat, exactly as the README describes. (First attempt
    showed only this module's reply, because eliza was still gated on the
    `init` consent handshake the platform's own BDI flow requires — not a
    template bug; completing consent with "yes" first made both replies
    appear.)
  - Rung 3 (`attach/inprocess.py`) ran headless with no broker, producing the
    expected transformed reply; `src/main.py` run standalone against the
    default `internal` config served `/health` and correctly suppressed the
    tenancy warning (no shared bus).
  - Rung 4: built `ghcr.io/myorg/cltl-example` and joined it to the live
    compose network via `compose/example.compose.yml`. Logs confirmed the
    two-file config split (image's own `[myorg.example]` + the deployment's
    mounted `custom.config`) resolved correctly, the untenanted-bus warning
    fired exactly once with the documented text, `/health` passed, and a
    live chat message drew replies from both eliza and the containerised
    module.
  - Everything was torn down cleanly afterward (compose stack, containers,
    network) — nothing left running.

- **The published-image path, verified end to end against a live stack**
  (2026-09-09): `docker compose -f deployment/deployment.compose.yml up`
  brought all four services healthy; `cltl-context` opened its own scenario
  (`start_scenario: true`) with no external driver; `attach/listen.py`
  attached over the published broker port with the management-API binding
  check authenticating (0.1s, not the 2s fallback); and a chat driven through
  the chat UI's REST API produced the documented behaviour exactly — one reply
  before consent, then both eliza's and this module's on every message after
  "yes". Torn down clean: no containers, no networks, no processes left.
