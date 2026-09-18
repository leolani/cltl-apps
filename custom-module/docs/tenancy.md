# Tenancy

This template's deployment is **multi-tenant**, and that shapes almost
everything else in it. One shared platform serves several isolated groups of
users; your custom code belongs to one of them and must not be able to see the
others.

This page is what a tenant is, how the routing actually works, why this module
opens its own scenario, and — the part worth being clearest about — why opening
a scenario is *not* an example of custom functionality.

## A tenant is one routing-key word

Set at `[cltl.event.kombu] tenant`, and it must match `^[a-z0-9][a-z0-9_-]*$`
— one lowercase word. The bus builds routing keys as `<topic>.<tenant>`, so a
`.`, `*` or `#` in a tenant id would quietly change which keys that pattern
matches.

## Routing, as a table

| Bus tenant | Event tenant | What happens |
|---|---|---|
| set (`X`) | none | the bus stamps the event `X`, routes to `<topic>.X` |
| set (`X`) | `X` | routes to `<topic>.X` |
| set (`X`) | different (`Y`) | **raises `ValueError`** — a tenanted bus refuses another tenant's event |
| unset | none | routes to the **bare** `<topic>` key |
| unset | set (`Y`) | routes to `<topic>.Y` |

A subscriber on a tenanted bus binds exactly `<topic>.<its tenant>`. A
subscriber on an untenanted bus binds `<topic>.#`, which matches zero or more
words — every tenant's traffic *and* the bare topic.

Rows 2 and 5 together are what make a shared server work at all: one untenanted
`cltl-eliza` hears every tenant, and because it replies with `source=event` —
which copies the tenant across — and an untenanted bus routes on the *event's*
tenant rather than its own, the answer lands back in the tenant that asked and
in no other.

**The row that surprises everyone** is the fourth, and this deployment is built
around it. An untenanted bus publishing an untenanted event lands on the bare
`<topic>` key. Untenanted subscribers match it; a tenanted subscriber, bound to
its own specific tenant, does not. That reply reaches **nobody**.

That is precisely what `source=event` prevents. See
[`concepts.md`](concepts.md#the-one-rule-always-pass-source).

## A tenant is not a network

The deployment runs three or more compose projects on **one** Docker network,
sharing one broker, one exchange and one set of credentials. Nothing is
separated by the network.

That is deliberate, and it is the platform's own framing: *"Where the
client/server split cuts one system in two along a network, this cuts it along
a routing key."* Putting each tenant on its own network would work, and would
let a reader walk away believing Docker was doing the isolating. It is not.

The consequence is worth stating plainly: **separation here is cooperative, not
enforced.** Any client that can reach the broker can set `tenant` to anything,
or leave it empty and read every tenant's traffic. The untenanted server half
is exactly such a reader, on purpose. A deployment that needs enforcement needs
per-tenant broker credentials and vhosts, which is a RabbitMQ configuration
problem rather than a Leolani one.

The platform's own harness does use one network per tenant plus
`host.docker.internal:host-gateway`
(`integration/src/cltl_integration/runner/tenants.py`). That is the right shape
when tenants run on different hosts, or when the broker port is ephemeral.

## Anything that reads the bus is tenanted. Storage does not.

That is the whole rule for deciding which half a service belongs to, and the
image feature is what makes it concrete.

`cltl-monitoring` **subscribes** — to the scenario, image and text topics — and
keys its state by scenario id. One shared instance would bind `<topic>.#` and
aggregate every tenant's conversation behind a single URL, so it runs once per
tenant, on the tenant half, with its own `CLTL_TENANT`.

`cltl-backend`'s storage service subscribes to nothing. `StorageContainer` is a
Flask app in front of a directory; it builds an event bus only because
`InfraContainer` does, and never publishes or consumes on it. It has no tenant
dimension to get right, so it is shared infrastructure on the server half,
exactly like the broker.

**What that costs, stated plainly.** Two tenants' pixels sit in one store, and
the only thing between tenant-a and tenant-b's picture is the uuid it is filed
under. `GET /storage/image/<id>` asks for no tenant and checks none. A uuid is
not a capability — it is unguessable, which is not the same as protected, and it
travels in `signal.files` of every event on that tenant's image topic.

This is the same cooperative-not-enforced property as the section above, one
layer down, and it has the same answer: a deployment that needs enforcement
needs per-tenant storage (a `cltl-backend` in `tenant.compose.yml`, each with its
own `image_storage_path` and its own `storage_url`) or an authenticating proxy in
front of the shared one. Neither is a Leolani problem. What this template owes
you is that the limitation is *stated* rather than implied by a diagram.

## The chat UI has to run inside the tenant

Not a preference — a consequence of row 4.

`ChatUiService` publishes what you type with
`Event.for_scenario_payload(scenario_id, payload)` and **no** `source=`. On an
untenanted bus that event carries no tenant, so it routes to the bare
`cltl.topic.text_in` key, which no tenanted module binds. An untenanted chat UI
can talk to the untenanted ELIZA and to nothing else.

So `cltl-chat-ui` is in `deployment/tenant.compose.yml`, one per tenant, and
`cltl-eliza` — which does pass `source=` — is the shared one on the server.

### Seeing it for yourself

`attach/example.ipynb`'s last section does this check from a notebook: it
attaches one observer as `tenant-b` and one untenanted, then tallies what each
receives while you type in tenant-a's chat UI. It needs no second compose stack
— a tenanted subscriber binds `<topic>.tenant-b` whether or not anything is
running for tenant-b — and the untenanted observer is there as a control, since
"the other tenant saw nothing" is also what a dead broker looks like.

The other place to look is RabbitMQ's management UI at
<http://127.0.0.1:15672> → Exchanges → `cltl.combot` → Bindings, where
`cltl.topic.text_in.tenant-a`, `cltl.topic.text_in.tenant-b` and
`cltl.topic.text_in.#` sit side by side. That screen is the entire mechanism,
and there is nothing else behind it.

## Why this module opens a scenario, and why that is not a feature

`cltl-chat-ui` keeps one active scenario id. Until it receives a
`ScenarioStarted` it renders nothing, and `_create_payload` raises
`ValueError: No active scenario` rather than publishing what you type. **A
tenant with no scenario is a blank page.**

In a normal deployment `cltl-context` opens that scenario. Two things follow
from the table above:

1. A `cltl-context` on the **server** half cannot do it. `ContextService._start_scenario`
   publishes with `Event.for_payload(...)` and no source, so from an untenanted
   bus it lands on the bare key — row 4 — and no tenant ever sees it.
2. Therefore the scenario has to be opened on the **tenant's own bus**, by
   something that holds one.

The platform's answer is to deploy a `cltl-context` inside every tenant; its own
multi-tenant topology says so outright — *"context creates the scenario. It is
what makes a tenant a tenant rather than a second copy of a client."* This
template's answer is `myorg.tenant`, which does only the scenario part of that
job, so the template can stay four containers instead of six.

**`myorg.tenant` is not custom functionality, and nothing about it is an
example to follow when writing your own module.** It is a chore that falls to
the custom side purely because tenant separation leaves nobody else who can do
it. The template keeps that visible rather than tidy:

- it is a **separate package**, `myorg/tenant/`, not a feature of
  `myorg/example/`;
- `myorg.example` contains no reference to a scenario, a tenant or
  `myorg.tenant`, and `attach/inprocess.py` composes `ExampleContainer` alone to
  demonstrate that;
- it has **no `api.py`** — there is no choice to abstract, because there is
  nothing here anyone should be swapping out;
- `[myorg.tenant] start_scenario: false` turns it off in one line.

**Delete it** the day your deployment runs a `cltl-context` per tenant: remove
`src/myorg/tenant/`, its `[myorg.tenant]` config section, its tests, and
`TenantContainer` from `src/main.py`'s bases. Nothing else changes.

## Why `myorg.example` only warns where `myorg.tenant` refuses

The two services treat a missing tenant differently, and the asymmetry is the
point.

**Confinement is the bus's job**, via `[cltl.event.kombu] tenant`.
`ExampleService` never compares `event.metadata.tenant` to a configured value
and never filters on it. A Python-side tenant check there could only be dead
code, because the bus already filtered — or false reassurance, because the bus
is misconfigured and the check papers over it. What it *does* do is say out loud
when a shared bus has no tenant, because that failure is otherwise silent. Two
warnings, each logged **once**, never once per event:

- **At startup**, if the implementation is `kombu` and the tenant is empty: a
  warning that this module is bound to every tenant on the exchange.
- **On the first event**, if it carries no tenant: a warning that a reply built
  without `source=` would route to the bare topic key and reach nobody.

`tests/test_tenancy.py` pins both, including the once-only part.

`TenantService` **raises** instead, on an empty tenant, on an unexpanded
`$CLTL_TENANT`, and on anything that is not one lowercase routing-key word. Why
the difference:

- `myorg.example` is **the part you replace**. It has to keep working, quietly,
  on an ordinary single-tenant deployment — still the normal case for a custom
  module. Failing hard there would make the template unusable for its main
  audience.
- `myorg.tenant` exists **only** because of tenant separation. A tenant service
  with no tenant is a contradiction in terms, and the failure it prevents is the
  worst kind: the scenario goes to the bare key, the chat UI stays blank
  forever, and nothing logs an error.

`tests/test_tenant_service.py` pins every branch.

## The `$CLTL_TENANT` trap, now caught twice

Config values interpolate `$VAR` at **read** time, and an unset variable is
passed through as the **literal string** with only a warning.

So an unset `CLTL_TENANT` makes the bus believe the tenant is literally
`"$CLTL_TENANT"`. It binds `cltl.topic.text_in.$CLTL_TENANT` — a real, valid,
permanently empty queue. Nothing errors. Your module simply never receives
anything.

This used to be purely a documentation problem. It is now caught in two places:

- **compose**, at interpolation time. `deployment/tenant.compose.yml` and
  `compose/example.compose.yml` declare
  `name: ...-${CLTL_TENANT:?<message>}`, so an unset variable fails the
  `up` before a container starts.
- **`TenantService.__init__`**, for the cases compose cannot see — an empty
  value, or a literal that came from somewhere else.

The server half still declares `CLTL_TENANT: ""` explicitly rather than leaving
it undefined, for the original reason: there, empty is correct, and only an
*undefined* variable is the bug.

Uppercase is rejected for a reason worth knowing: `docker compose` lowercases an
interpolated project `name:` but **not** the value it passes into the container
environment. `CLTL_TENANT=Tenant_A` gives you a project called `…tenant_a` and a
tenant id of `Tenant_A`, and two halves of a deployment that bind different
keys.

## Single-process runs have no tenants at all

With `[cltl.event] implementation: internal` — one process, no broker, which is
rung 3's default — every event is stamped with the literal string `"local"` and
dispatched to every subscriber regardless. There is no multi-tenant behaviour to
test or demonstrate there, which is why both the tenancy warning in
`ExampleService` and the strict check in `TenantService` are suppressed unless
the implementation is actually `kombu`.

The `start_delay` in `[myorg.tenant]` is skipped there too: a
`SynchronousEventBus` dispatches in the publishing thread, so there is no
binding window to wait out.

## Why there is no intention gating

`TopicWorker` can gate a module so it only processes events during a particular
conversational state — the mechanism that would normally keep `cltl-eliza`
silent until you consent. This template deliberately does not use it, **and
neither does the shared `cltl-eliza` in this deployment**: `deployment/config/server/default.config`
leaves `[cltl.eliza] intentions`, `topic_intention` and `topic_desire` all
empty.

The reason is a known platform defect: the gate keeps a single active flag
**per worker**, shared across every tenant that worker serves, and never reads
the event's tenant. A module shared across tenants and gated on intentions
would therefore be gated by whichever tenant's intention was published last —
tenant A's conversation switching tenant B's module on and off. The platform's
own test suite pins this as a known failure
(`integration/tests/slices/test_intention_routing.py::TestTenantScopedGating`,
`xfail(strict=True)`).

Emptying `topic_intention` as well as `intentions` matters separately:
`ElizaService.start` subscribes to a non-empty intention topic whether or not it
gates on one, and on an untenanted bus that means `cltl.topic.intention.#` —
every tenant's BDI traffic arriving on one queue. It also makes ELIZA's greeting
branch unreachable, which is a small mercy: that branch publishes without
`source=`, so its greeting would be untenanted and delivered to nobody.

The visible cost is that this deployment has **no consent handshake**. There is
no *"Do you want to talk to me?"* and no "say yes first"; ELIZA answers from the
first message, as this template always has.

If you need gating, either run one instance of your module per tenant, so the
shared flag is no longer shared, or wait for the fix upstream.

## Two openers, one tenant

Nothing stops a listener (rung 2) and a module container (rung 4) from both
opening a scenario for the same tenant. The chat UI ends up on whichever
`ScenarioStarted` arrived last, and any signal created before that carries the
other id — invisible here, but it would split the conversation across two
scenario directories in a deployment with persistence.

There is no detection for this, deliberately: the only way to add one would be
to give `TenantService` a `TopicWorker` on the scenario topic, which contradicts
the "this service listens to nothing" property that makes it easy to read.
Avoid it instead — `--no-scenario` on `attach/listen.py`, or
`[myorg.tenant] start_scenario: false` on the container.
