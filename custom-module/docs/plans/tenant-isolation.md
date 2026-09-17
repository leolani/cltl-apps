# Tenant isolation for cltl-example

Status: implemented · Date: 2026-09-17

## Why

The template showed how to attach custom code to a Leolani deployment, but the
deployment it attached to was a single untenanted stack, and `cltl-context`
opened the conversation's scenario inside it. A module in the real world belongs
to **one tenant** of a shared platform, and the template did not show that at
all: the custom side ran with `[cltl.event.kombu] tenant` empty, binding
`<topic>.#` — every tenant on the exchange. Tenancy existed only as prose in
`docs/tenancy.md`, whose closing section said the module did nothing about it
"deliberately".

## What was built

- **The deployment split in two.** `deployment/server.compose.yml` (rabbitmq +
  one untenanted `cltl-eliza`) and `deployment/tenant.compose.yml` (one
  `cltl-chat-ui`, run once per tenant). Two tenants by default, `tenant-a` on
  port 8000 and `tenant-b` on 8001, on one shared Docker network named
  `cltl-example`.
- **`myorg.tenant`** — a second package beside `myorg.example` that publishes
  `ScenarioStarted` on start and `ScenarioStopped` on stop, on the tenant's own
  bus. Three files, no `api.py`, no `TopicWorker`.
- **A strict tenant check** in `TenantService.__init__`: empty, unexpanded
  (`$CLTL_TENANT`), or not-one-routing-key-word all raise. `ExampleService`'s
  two log-once warnings are unchanged.
- **Scenario helpers in `attach/connect.py`**, plus `binding_key` lifted to
  module level and a `baseline=` keyword on `wait_until_bound` that turns the
  increment check into a presence check.
- `attach/listen.py` gained a required `--tenant`, `--topic-scenario`,
  `--no-scenario`, tenant logging, and a `try/finally` that closes the scenario
  before the bus.
- `attach/example.ipynb` lost the consent handshake, gained two cells that open
  and close tenant-a's scenario, and gained a **runnable isolation check**: a
  second observer joined as `tenant-b` plus an untenanted control, tallying what
  each one receives. It needs no second compose stack — a tenanted subscriber
  binds `<topic>.tenant-b` whether or not anything is running for tenant-b — and
  the control is load-bearing, because "the other tenant saw nothing" is also
  what a dead broker looks like.
- `src/main.py` composes `ApplicationContainer(TenantContainer, ExampleContainer)`
  and installs a SIGTERM handler.

## What was decided, and why

- **The custom side publishes `ScenarioStarted` directly** rather than
  publishing an `init` intention for a per-tenant `cltl-context`. The latter is
  what the platform's own multi-tenant topology does and what its demo launcher
  does, and it would have preserved the consent handshake — at the cost of a
  `cltl-context` container in every tenant, and of the scenario still being
  minted by the platform rather than by the custom side. The cost paid instead:
  `[cltl.eliza]` is ungated, and "say yes first" is gone from every document.
- **Scenario creation lives in its own package**, not in `myorg.example` and not
  in a non-packaged `src/` module. The structural separation *is* the statement
  that it is not custom functionality; a comment saying so would have been
  weaker. `attach/inprocess.py` was deliberately left composing
  `ExampleContainer` alone to make the same point a second way.
- **No `api.py` in `myorg.tenant`.** `myorg/example/api.py` exists because
  `EchoExample` is meant to be replaced; nothing here is, and the package is
  meant to be deleted. `tests/test_packaging.py` pins the absence.
- **One Docker network, not one per tenant.** Separate networks would work and
  would let a reader conclude Docker was doing the isolating. It is not — it is
  a routing key, and the deployment is arranged so that is impossible to miss.
- **No scenario watcher and no republish interval.** Both would paper over real
  failure modes (two openers; the binding race) at the cost of the "this service
  listens to nothing" property. Documented as extensions instead.

## What was found during implementation

- **`docker compose` interpolates a top-level `name:` and honours `:?` there**,
  failing before any container starts (verified on v2.40.3). That is what turned
  the `$CLTL_TENANT` trap from a documentation problem into a caught error.
  Compose also **lowercases the interpolated project name but not the container
  environment**, so `CLTL_TENANT=Tenant_A` yields a project named `…tenant_a`
  and a tenant id of `Tenant_A` — which is why the Python-side regex is not
  redundant.
- **`DIContainer._singletons` is process-global**, keyed by the bare method
  name. Adding a second container test class silently handed it the first
  class's `example_service`, still bound to the first class's bus; three tests
  failed with empty queues. `DIContainer._reset()` in `setUp` fixes it, and the
  pre-existing container test was passing only by alphabetical luck.
- **Rung 4 cannot close the scenario-start binding race.** `requests` is not in
  `cltl-requirements/requirements.base.txt` and the image installs
  `--no-index`, so a container cannot poll the management API; `depends_on` does
  not reach across compose projects. `[myorg.tenant] start_delay` is a guess,
  and is documented as one.
- **`ScenarioStopped` would never have been published from a container.**
  `run_simple` blocks, and SIGTERM's default disposition kills the process before
  `with application:` unwinds. `cltl-context/src/main.py` has the identical
  latent bug. Fixed here by raising `KeyboardInterrupt` from a SIGTERM handler
  and catching it around `run_simple` rather than relying on werkzeug to swallow
  it.
- Emptying `[cltl.eliza] intentions` is **not enough** to ungate the shared
  ELIZA: `ElizaService.start` still subscribes to a non-empty intention topic,
  which on an untenanted bus means `cltl.topic.intention.#`. `topic_intention`
  and `topic_desire` have to be emptied too.

## Verified against a live deployment

Run on 2026-09-17, aarch64, Docker 29.7.2 / compose v2.40.3. All images are
native arm64; no emulation.

| Check | Result |
|---|---|
| Both chat UIs blank before anything attaches | `GET /chatui/chat/scenario` → `{"scenario_id":null}` on both |
| Bindings after both tenants are up | `text_in.#` (shared ELIZA), `text_in.tenant-a`, `text_in.tenant-b`, `text_out.{a,b}`, `scenario.{a,b}` — and **no bare `cltl.topic.text_in`** |
| `listen.py --tenant tenant-a` opens one scenario | tenant-a → a scenario id; tenant-b → still `null` |
| Two replies, no consent handshake | `YOU SAID: … (via attach/listen.py)` **and** `How do you feel about being feeling anxious about routing keys?` — ELIZA answered the first message, so the ungating works |
| Isolation, with a control | untenanted observer saw 6 events, all `tenant='tenant-a'`; the `tenant-b` observer saw **0** |
| Publishing into a tenant with no scenario | HTTP 500, and `ValueError: No active scenario in chat UI` in the container log |
| `SIGTERM` to `listen.py` | logs `Stopping.` → `Closed scenario …`, and tenant-a's `scenario_id` returns to `null` — the chat UI cleared |
| Compose guards | unset `CLTL_TENANT` and unset `CLTL_CHATUI_PORT` each fail at interpolation before any container starts |
| The strict tenant check | `''`, `$CLTL_TENANT` and `Tenant_A` all refused |

**Two bugs this run caught, both since fixed:**

1. **The notebook's isolation cell hung.** It subscribed both observer buses and
   *then* called `wait_until_bound` twice. That function snapshots the binding
   counts when it is **called**, so the second call's baseline already contained
   its own binding and the count could never rise past it — a 30-second
   `TimeoutError`, and then a process that would not exit because the buses were
   still open. Fixed by interleaving: subscribe one bus, wait for it, then the
   next. The tidier-looking arrangement is the broken one, which is worth a
   comment in the cell and now has one.
2. The same run confirmed why the cleanup cell looks up buses by name through
   `globals()`: when that wait raised, `bus_b` and `bus_all` existed but the
   cells after them had not run, and any teardown holding a direct reference to
   a later name would have raised instead of closing what was open.

## Not done

- **`makefile` still does not exist** in this directory and never has, so rungs
  3–4 remain unrunnable from a standalone checkout and the image could not be
  built or exercised here. Out of scope, recorded in
  [`../gotchas.md`](../gotchas.md#there-is-no-makefile).
- The two-tenant deployment was not brought up end to end during implementation;
  the compose files were validated with `docker compose config` (both the
  success and the required-variable failure paths) and the unit tests were run,
  but the routing-key and isolation checks in the plan's verification section
  are outstanding — **superseded by the section above; they were run.** The
  notebook's cells were exercised as an equivalent headless script rather than
  through Jupyter, since the check needs someone typing in a chat UI; the script
  drove the chat UI's REST API instead.
