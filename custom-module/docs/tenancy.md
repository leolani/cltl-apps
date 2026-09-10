# Tenancy

**Skip this page unless you are running one deployment for several isolated
groups of users.** Single-tenant is the default, it is what this template
ships, and everything works without reading further.

What follows is what a tenant is, how routing actually works, and why this
module confines itself to one tenant entirely through configuration rather than
code.

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

**The row that surprises everyone** is the fourth. An untenanted bus publishing
an untenanted event lands on the bare `<topic>` key. Untenanted subscribers
match it; a tenanted subscriber, bound to its own specific tenant, does not.
That reply reaches **nobody** on a multi-tenant deployment.

That is precisely what `source=event` prevents — it copies the incoming event's
tenant onto your reply. See
[`concepts.md`](concepts.md#the-one-rule-always-pass-source).

## The `$CLTL_TENANT` trap

Config values interpolate `$VAR` at **read** time, and an unset variable is
passed through as the **literal string** with only a warning.

So an unset `CLTL_TENANT` makes the bus believe the tenant is literally
`"$CLTL_TENANT"`. It binds `cltl.topic.text_in.$CLTL_TENANT` — a real, valid,
permanently empty queue. Nothing errors. Your module simply never receives
anything.

This is why both compose files here declare `CLTL_TENANT` explicitly even when
it is empty. Never leave it unset and rely on a default.

## Single-process runs have no tenants at all

With `[cltl.event] implementation: internal` — one process, no broker, which is
rung 3's default — every event is stamped with the literal string `"local"` and
dispatched to every subscriber regardless. There is no multi-tenant behaviour to
test or demonstrate there, which is why this module's tenancy warning is
suppressed unless the implementation is actually `kombu`.

## What this module does about it: nothing, deliberately

**Confinement is the bus's job**, via `[cltl.event.kombu] tenant`.
`ExampleService` never compares `event.metadata.tenant` to a configured value
and never filters on it.

A Python-side tenant check here could only be one of two things: dead code,
because the bus already filtered — or false reassurance, because the bus is
misconfigured and the check papers over it. Neither is worth writing.

What the service *does* do is say out loud when a shared bus has no tenant,
because that failure is otherwise silent. Two warnings, each logged **once**,
never once per event:

- **At startup**, if the implementation is `kombu` and the tenant is empty: a
  warning that this module is bound to every tenant on the exchange. Correct on
  a single-tenant deployment; wrong on a shared one.
- **On the first event**, if it carries no tenant: a warning that a reply built
  without `source=` would route to the bare topic key and reach nobody.

`tests/test_tenancy.py` pins both, including the once-only part.

## Why there is no intention gating

`TopicWorker` can gate a module so it only processes events during a particular
conversational state — the mechanism that keeps `cltl-eliza` silent until you
consent. This template deliberately does not use it.

The reason is a known platform defect: the gate keeps a single active flag
**per worker**, shared across every tenant that worker serves, and never reads
the event's tenant. A module shared across tenants and gated on intentions
would therefore be gated by whichever tenant's intention was published last —
tenant A's conversation switching tenant B's module on and off. The platform's
own test suite pins this as a known failure.

If you need gating, either run one instance of your module per tenant, so the
shared flag is no longer shared, or wait for the fix upstream.
