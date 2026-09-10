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

### Only *this* module answers — ELIZA stays silent

You have not answered "yes" to the opening question. `cltl-eliza` is gated on an
intention that only becomes active once the consent handshake completes; this
template has no such gating and answers immediately.

Say "yes" once at the start and both answer from then on. See
[`deployment.md`](deployment.md#say-yes-first).

### Two agents answer every message

By design — see the [README](../README.md). Give `topic_output` a private topic
if you want your module to stop competing with `cltl-eliza`
([`configuration.md`](configuration.md)).

### The chat UI is blank, or says there is no scenario

Nothing renders until a conversation is open. `[cltl.context] start_scenario:
true` makes the context service open one itself at startup. The platform's test
harness leaves it `false` and opens one from the test process instead — a
deployment with neither shows an empty chat UI forever.

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

### `$CLTL_TENANT` (or any variable) reaching the bus as a literal string

An unset variable interpolates to the literal `"$CLTL_TENANT"` with only a
warning. The bus treats that as a real tenant name and binds a queue nothing
will ever route to — no error, no traffic. Declare every interpolated variable
in the environment, even when empty. See [`tenancy.md`](tenancy.md).

### `config/custom.config` left over from a previous run

It is gitignored, and the loader reads it unconditionally if present. A
`custom.config` written to point at a real broker, left behind, makes a later
single-process run silently try to reach a broker that no longer exists.
`rm config/custom.config` when you are done.

### Everything is healthy and nothing is connected

Legacy topic names. See
[`configuration.md`](configuration.md#the-legacy-names-trap).

## Building the component (rungs 3–4)

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
