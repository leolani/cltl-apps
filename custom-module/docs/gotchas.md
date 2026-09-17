# Gotchas

Symptom → cause. Roughly in the order you are likely to hit them.

## Attaching (rungs 1–2)

### The first message never arrives

The commonest one, and it is *intermittent*, which makes it worse.

Subscribing returns before RabbitMQ has actually bound your queue. Anything
published in that window is dropped silently, because a topic exchange has
nowhere to put a message matching no binding.

Use `connect.wait_until_bound()` — the notebook and `listen.py` both do — or,
inside a component, `topic_worker.start().wait()`, which means "subscribed" for
the same reason. See [`attaching.md`](attaching.md).

### `401 Unauthorized` from the management API, then a flat sleep

`wait_until_bound` needs credentials for RabbitMQ's **management API**, which
authenticates separately from AMQP. Pass `amqp_url=` and it takes them from
there.

Without it, it falls back to the platform test harness's credentials, which are
wrong for any other broker. The 401 then degrades to a flat two-second sleep
rather than raising — deliberate, since the management plugin may genuinely be
absent, but it means the binding check quietly stopped checking. The symptom is
the intermittent dropped first message above, not an error.

### Two agents answer every message

By design — see the [README](../README.md). Give `topic_output` a private topic
if you want your module to stop competing with `cltl-eliza`
([`configuration.md`](configuration.md)).

### The chat UI is blank, or says there is no scenario

**Before you have opened one, this is correct.** This deployment runs no
`cltl-context`; nothing in it opens a scenario, and a chat UI renders nothing
until it has seen a `ScenarioStarted` on its own tenant's routing key. Run the
notebook's scenario cell, `attach/listen.py`, or the module container.

If it is *still* blank afterwards, the scenario went somewhere this chat UI is
not listening. In order of likelihood:

- **The tenants do not match.** The `TENANT` in the notebook, or `--tenant` on
  `listen.py`, has to be the same string as the `CLTL_TENANT` the tenant stack
  was started with. Check the bindings screen (below) — you will see the
  scenario on one routing key and the chat UI bound to another.
- **You opened it untenanted.** An untenanted publish lands on the bare
  `cltl.topic.scenario` key, which no tenanted chat UI binds. `listen.py`
  refuses this outright; a hand-written script will not.
- **The publish beat the binding** (rung 4 only). See the next entry.

### The chat UI returns `500 Internal Server Error` when you type

Same cause as the blank UI, surfacing the other way round.
`ChatUiService._create_payload` raises rather than publishing an utterance with
no scenario id, and Flask turns that into a 500 with nothing useful in it. The
real message is in the container log:

```
$ docker logs <tenant's chatui container> 2>&1 | grep -i "no active scenario"
ValueError: No active scenario in chat UI for utterance %hello?
```

Open a scenario first.

### The module container starts, but its tenant's chat UI never wakes up

`[myorg.tenant] start_delay` lost the race. `KombuEventBus.subscribe` returns
before RabbitMQ has bound the queue, so a `ScenarioStarted` published into that
window is dropped by the exchange — silently, on both sides.

Rungs 1–2 close this properly by polling the management API
(`wait_until_bound(..., baseline={})`). **Rung 4 cannot**: `requests` is not in
the base image, and `depends_on` does not reach across compose projects. So the
container waits a flat `start_delay` seconds instead, and that is a guess.

`docker compose -f compose/example.compose.yml restart example` fixes it for
now; raising `start_delay` fixes it for good, and costs only startup latency.

### Two scenarios for one tenant

A listener and a module container both opened one. The chat UI ends up on
whichever `ScenarioStarted` arrived last, and anything created before that
carries the other id — harmless here, but it would split the conversation across
two scenario directories in a deployment with persistence.

Use `--no-scenario` on `listen.py`, or `[myorg.tenant] start_scenario: false` on
the container. Nothing detects this for you, deliberately — see
[`tenancy.md`](tenancy.md#two-openers-one-tenant).

### One tenant sees another tenant's messages

One of them came up untenanted, so it bound `<topic>.#` and matched everything.

Go to <http://127.0.0.1:15672> → Exchanges → `cltl.combot` → Bindings. You want
to see `cltl.topic.text_in.tenant-a`, `cltl.topic.text_in.tenant-b` and
`cltl.topic.text_in.#` (the shared ELIZA's), and **no** bare
`cltl.topic.text_in`. That screen is the entire isolation mechanism, visible —
it is worth looking at once even when nothing is wrong.

### `attach/listen.py` will not die after the deployment stops

Stop the broker first and the consumer thread is left retrying a connection
that is never coming back — it retries forever by design — so `Ctrl-C` and even
`SIGTERM` hang waiting on it. `kill -9` is the answer; stopping the listener
*before* the deployment avoids it entirely.

The notebook has the same failure mode, which is what its last cell
(`bus.close()`) is for.

### `TypeError: PAYLOAD is not a dataclass and cannot be turned into one`

The serialisation type variables were never registered before something tried
to marshal an `Event`. Every entry point in this repo does this first; a new one
of your own must too. See [`attaching.md`](attaching.md).

## Configuration

### `required variable CLTL_TENANT is missing a value`

Not a bug — the guard working, at the earliest possible moment. The tenant and
module compose files interpolate `CLTL_TENANT` into their project `name:` with
`:?`, so an unset variable fails the `up` before a container starts. Set it to
the tenant's id.

### `$CLTL_TENANT` (or any variable) reaching the bus as a literal string

An unset variable interpolates to the literal `"$CLTL_TENANT"` with only a
warning. The bus treats that as a real tenant name and binds a queue nothing
will ever route to — no error, no traffic. Declare every interpolated variable
in the environment, even when empty.

This is now caught in two places — compose's `:?` above, and
`TenantService.__init__`, which refuses an empty tenant, a literal `$…`, and
anything that is not one lowercase routing-key word. If you hit it anyway, you
are somewhere neither guard reaches: a hand-written script, or a config that
interpolates some *other* variable. See [`tenancy.md`](tenancy.md).

### `CLTL_TENANT=Tenant_A` and the halves do not talk

`docker compose` lowercases an interpolated project `name:` but **not** the
value it puts in the container environment. So the project is called
`…tenant_a` while the tenant id stays `Tenant_A`, and two stacks that look
identical bind different routing keys.

`TenantService` rejects uppercase for exactly this reason. Use one lowercase
word.

### `config/custom.config` left over from a previous run

It is gitignored, and the loader reads it unconditionally if present. A
`custom.config` written to point at a real broker, left behind, makes a later
single-process run silently try to reach a broker that no longer exists.
`rm config/custom.config` when you are done.

### Everything is healthy and nothing is connected

Legacy topic names. See
[`configuration.md`](configuration.md#the-legacy-names-trap).

### `network cltl-example declared as external, but could not be found`

The server half is not up. Tenants and module containers join the network the
server creates; they do not create it themselves. Start
`deployment/server.compose.yml` first, and tear it down last.

## Building the component (rungs 3–4)

### There is no `makefile`

`make build`, `make test` and `make docker-ghcr-build` are referenced throughout
these docs, but this directory ships no `makefile` — those targets come from the
platform's `util/` submodule and from being listed in `project_components` in
`cltl-dev/makefile`. Rungs 3–4 therefore need this template placed inside a
`cltl-dev` checkout, or that machinery added, before they work at all. Rungs 1–2
are unaffected, and the unit tests can be run without any of it:

```bash
python3.10 -m venv .venv && . .venv/bin/activate
pip install -r requirements.notebook.txt pytest
PYTHONPATH=.:src python -m pytest tests
```


### `make build` succeeded but nothing actually built

**A green `make build` is not evidence the build worked.** The build system's
`venv` recipe chains its steps with `;` rather than `&&`, so a failed
`pip install` still exits 0 and the target is marked up to date.

Check that the venv holds more than `pip`/`setuptools`/`wheel`:

```bash
venv/bin/pip list
```

### `make build` needs to run twice

The first pass generates this component's dependency edges for the parent
build; the second is the one that sees them. A property of the platform's build
system, not of this template.

### `ScenarioStopped` never arrives after `docker compose down`

`docker compose down` and `docker stop` send SIGTERM, whose default disposition
kills the process outright — so `with application:` never reaches its `__exit__`
and the scenario is never closed. `src/main.py` installs a SIGTERM handler that
raises `KeyboardInterrupt` so the shutdown unwinds like a `Ctrl-C`; a module
that does not do the same will leave its tenant's chat UI holding a conversation
whose owner is gone. (`cltl-context/src/main.py` has the identical latent bug.)

### `ValueError: could not set <name>`

A `@singleton` property returned `None`, which it treats as "the factory
failed". Use `False` for "intentionally absent" and guard callers with
`if self.thing:`. See [`component.md`](component.md).

### `ModuleNotFoundError: <your-namespace>` after a partial rename

You renamed the directory under `src/` but missed an import, or renamed
`setup.py`'s `name=` but not its `find_namespace_packages(include=...)` pattern
(or the reverse). Rerun `git grep` for the old name — see
[`making-it-yours.md`](making-it-yours.md).

### An edit that points `topic_output` at `topic_input`

Saturates the broker in seconds unless your transform has a loop guard.
`echo.py` has one, matching its own output marker. If you replace the
transform, keep an equivalent guard or do not point output back at input.

### `fatal: transport 'file' not allowed` on a recursive clone

Since git 2.38.1, `protocol.file.allow` defaults to `user`, which forbids the
`file` transport for submodule fetches (a CVE-2022-39253 mitigation). If this
repository is registered as a submodule with a local path, a plain recursive
clone fails. Work around it explicitly:

```bash
git clone <the meta-repo>
cd <the meta-repo>
git -c protocol.file.allow=always submodule update --init --recursive
```

A limitation of local-URL submodules generally, not of this template.
