# Configuration

Where settings come from, which ones are yours, and the one trap that makes a
deployment come up healthy and connected to nothing.

## What gets loaded

The platform's loader reads three files, relative to the working directory:

| File | |
|---|---|
| `config/default.config` | Always. Shipped in the repo and in the image. |
| `config/custom.config` | If present. **Gitignored** — your local overrides. |
| `config/credentials.config` | If present. Gitignored — secrets. |

Later files override earlier ones, key by key. That layering is the whole
mechanism: a deployment supplies a `custom.config` with its broker address, and
everything else falls back to the defaults baked in.

Section names are plain strings — nothing scans for a `cltl.` prefix, so
`[myorg.example]` is exactly as valid a section name as `[cltl.eliza]`.

`config/custom.config.example` is a starting point for pointing a local run at
a real broker. Copy it, do not rename it — the real one is gitignored so an
AMQP URL or tenant id cannot be committed by accident.

## Which sections are yours

| Section | Owner | |
|---|---|---|
| `[myorg.example]` | **you** | Your module's settings. Rename it when you rename the module. |
| `[myorg.tenant]` | **neither, really** | Not custom functionality — the scenario a tenant needs. Delete it when your deployment has a `cltl-context`. See [`tenancy.md`](tenancy.md). |
| `[cltl.event]` | the platform | `internal` (one process) or `kombu` (a real broker) |
| `[cltl.event.kombu]` | the platform | `server`, `exchange`, `compression`, `tenant` |

Never add your own keys to the platform's sections, and never read a platform
topic name from anywhere but configuration.

### `[myorg.example]` keys

| Key | Default | |
|---|---|---|
| `topic_input` | `cltl.topic.text_in` | the topic to subscribe to |
| `topic_output` | `cltl.topic.text_out` | the topic to publish on |

Both are mandatory: an empty value raises at construction rather than silently
subscribing to nothing.

**To stop competing with `cltl-eliza`**, point `topic_output` at a topic of your
own — say `myorg.topic.example_out`. Your replies then stop appearing in the
chat UI, because nothing is listening on that topic, which is usually the point:
your module becomes an input to something else you write rather than a second
voice in the conversation.

Do not point `topic_output` at `topic_input`. That is a feedback loop that
saturates the broker in seconds; `echo.py`'s loop guard is what makes it merely
noisy rather than fatal, and your own logic will not have one.

### `[myorg.tenant]` keys

Present only because of tenant separation. `myorg.example` does not read any of
these, and nothing in it knows a scenario exists.

| Key | Default | |
|---|---|---|
| `topic_scenario` | `cltl.topic.scenario` | the topic to announce the conversation on |
| `start_scenario` | `True` | set `False` when something else opens the scenario for this tenant — a real `cltl-context`, or another attached listener |
| `start_delay` | `5.0` | seconds to wait before announcing, so the tenant's chat UI has bound its queue first. Ignored on an in-process bus |
| `agent` | `Leolani` | display name only — the chat UI renders it |
| `speaker` | `Human` | display name only |
| `location` | `unknown` | a free-text label, not a lookup |

`topic_scenario` and `start_scenario` reuse `[cltl.context]`'s own key names on
purpose: swapping this package for a real `cltl-context` is then a section
rename and nothing else.

`agent` and `speaker` are cosmetic. Giving two tenants different agent names
makes the isolation visible on screen, but the agent's **URI** — its actual
identity — is a constant in `src/myorg/tenant/scenario.py` and is the same for
every tenant. The separation is the routing key, not the agent.

`start_delay` is a guess, and it is the weakest part of the design. Rungs 1–2
replace it with a real check against RabbitMQ's management API
(`wait_until_bound(..., baseline={})`); a container cannot, because `requests`
is not in the base image and `depends_on` does not reach across compose
projects. Raising it costs only startup latency. See
[`gotchas.md`](gotchas.md).

## `$VAR` interpolation

`$VAR` and `${VAR}` expand against the process environment when the config is
**read**, not when the file is parsed. `$$` escapes a literal `$`.

**An unset variable passes through as the literal string**, with only a warning
logged. So `server: $CLTL_AMQP_URL` with nothing set becomes the literal
`"$CLTL_AMQP_URL"`, and you get a connection error naming a hostname that is
obviously wrong — annoying but self-explanatory. The same mistake with
`tenant:` is not self-explanatory at all; see [`tenancy.md`](tenancy.md).

The rule that follows: **declare every variable your config interpolates in the
environment, even when empty.** Every compose file here does exactly that — and
for `CLTL_TENANT`, where empty is *not* acceptable on a tenant, they go further
and interpolate it into the project `name:` with `:?`, so an unset variable
fails the `up` outright. `TenantService.__init__` catches the rest.

A `[environment]` section, if present, sets process environment variables at
startup. Other platform components use it; this one does not.

## The legacy-names trap

Most platform components' own `config/default.config` uses **legacy** topic
names — `cltl.chat.utterance`, `cltl.mic` — left over from before the
`cltl.topic.*` convention. They are meant only for running that component
standalone with nothing else attached.

A real deployment mounts its own configuration over that file and supplies the
canonical names. **If it fails to, every service starts, every health check
passes, and no two modules are connected to each other.** Nothing errors,
because a topic nobody publishes on is indistinguishable from a quiet one.

This template's `config/default.config`, and both of the deployment's, already
use the canonical names — they were written after the convention existed — so
there is no gap to fall into here. Keep it in mind if you copy configuration patterns from another
component.

## In the image

This template's image ships its own `config/default.config` — carrying both
`[myorg.example]` and `[myorg.tenant]` — unlike every platform component's. The
reasoning is in
[`docker.md`](docker.md#one-deliberate-deviation-this-image-ships-its-own-config).
A deployment attaching this container therefore only needs to mount a
connection overlay, not a whole directory.
