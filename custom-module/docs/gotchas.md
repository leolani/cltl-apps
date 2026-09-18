# Gotchas

Symptom → cause. Roughly in the order you are likely to hit them.

## Attaching (rungs 1–2)

### The first message never arrives

The commonest one, and it is *intermittent*, which makes it worse.

Subscribing returns before RabbitMQ has actually bound your queue. Anything
published in that window is dropped silently, because a topic exchange has
nowhere to put a message matching no binding.

Sleep before you rely on the subscription — two seconds for one of your own,
five when what has to be bound is somebody else's queue. That is a guess rather
than a check, and [`attaching.md`](attaching.md) says what it does and does not
buy, and what would actually fix it.

**`topic_worker.start().wait()` is not the in-component version of this.** It
is widely assumed to be, and it is not: `TopicWorker.run` sets `_started`
immediately after `subscribe()` returns, which is exactly the moment that is
not yet safe. A component in this position has the same race and the same
non-answer — see `[myorg.tenant] start_delay` below.

### `ModuleNotFoundError: No module named 'cltl.backend'`, but the venv has it

The notebook is not running in the venv you installed into, and nothing says so.

The giveaway is *where* it fails. Every cell up to the image section needs only
`cltl.combot` and `emissor`, which another environment may well also have — so
the notebook works perfectly until the first cell that calls `load_image`, and
then fails on an import you can see is installed. Reinstalling the requirements
changes nothing, because the requirements were never the problem.

Ask the kernel which interpreter it is, from inside the notebook:

```python
import sys; print(sys.executable)
```

If that is not `.../.venv/bin/python`, the cause is almost always the stock
kernelspec. A venv's default kernel is called `python3` and its `kernel.json`
runs a **bare `python`**:

```json
["python", "-m", "ipykernel_launcher", "-f", "{connection_file}"]
```

resolved through `PATH` at kernel-start, *not* pinned to the venv. The notebook
asks for `python3` by name, so whichever Jupyter opens it provides its own.

Fix it by giving the venv a kernel of its own, which records an absolute path:

```bash
source .venv/bin/activate
python -m ipykernel install --user --name cltl-example \
    --display-name "cltl-example (.venv)"
```

then select **cltl-example (.venv)** from the kernel menu and re-run from the
top. `jupyter kernelspec list` shows what is registered and where. In VS Code,
use the kernel picker at the top right and choose `.venv` instead.

As a one-off escape hatch, `%pip install -r ../requirements.notebook.txt` inside
a cell installs into *the running kernel* whatever that turns out to be — which
unblocks you, and leaves you running in an environment you did not choose.

`load_image` catches that `ImportError` and re-raises it with the kernel's
`sys.executable` appended, so the answer is in the traceback itself rather than
on this page.

### Two agents answer every message

By design — see the [README](../README.md). Give `topic_output` a private topic
if you want your module to stop competing with `cltl-eliza`
([`configuration.md`](configuration.md)).

### Only ONE agent answers an image

Also by design, and it is the same fact from the other side. Submitting from the
Image panel publishes an `ImageSignalEvent` on `cltl.topic.image` and **nothing**
on the utterance topic, so `cltl-eliza` — which subscribes only to
`cltl.topic.text_in` — never sees a picture. The single reply is yours.

### You uploaded an image and nothing answered at all

Three causes, in the order they actually occur.

**The Image panel is not there.** `[cltl.chat-ui] image_upload` is `False`, or
`external_input` is `False`. Ask the page what it thinks it has:

```
$ curl -s localhost:8000/chatui/config
{"image_upload":true,"monitoring_url":null}
```

`image_upload: false` means the three image routes 404 and the tab is hidden.
Note that `external_input: True` is *required* alongside it: with it off,
`get_utterances` defaults its speaker filter to the agent's name and filters the
uploaded image's own echo back out of the transcript.

**The picture appears in the chat but no event is published.**
`[cltl.chat-ui.events] topic_image` is empty. The chat UI logs
`No image topic configured; annotations for <id> are not recorded` and echoes the
image anyway — which is why the transcript looks fine and nothing downstream sees
it.

**The event is published and your module declines it.** Read your own log; this
is the one case with a real diagnosis in it:

```
WARNING  Could not load the pixels for image signal <id> from
         cltl-storage:image/<id>: ... Either they were never stored (the
         publisher's upload is best-effort and needs cv2), or the storage
         service is not running, or [myorg.example] image_storage_url points
         somewhere else.
```

`myorg.example` publishes nothing rather than an error bubble — the
`None`-means-say-nothing contract ([`concepts.md`](concepts.md)) — so the log is
the only signal. Check the reference by hand:

```
$ curl -s localhost:8002/storage/image/<id> | head -c 80
{"depth":null,"image":{"__type":"np.ndarray","data":"...
```

### `KeyError: No image with id … found in the storage`, as an HTTP 500

The reference resolved and the pixels are not there. Note the status code: an
unstored id is a **500** with a `KeyError` in the storage container's log, not a
404, so "500" here does not mean the store is broken.

Two ways to arrive:

- **The chat UI could not decode the upload.** Its pixel PUT needs `cv2`, which
  it imports lazily and declares nowhere (two differently-named distributions
  provide it). Without it the PUT is skipped, the signal is published anyway, and
  the reference dangles. `docker logs <chatui> | grep -i cv2`.
- **The storage directory does not exist.** `CachedImageStorage` creates the
  *parent* of `image_storage_path`, not the path itself, and `cv2.imwrite` into a
  missing directory returns `False` instead of raising — so the PUT answers
  `204 No Content` and the GET fails later. This is why
  `deployment/storage/image/` is committed with a `.gitkeep`; if you moved or
  cleaned it, `mkdir -p` it back.

### Every image fetch 404s, and the URL in the log looks right

Count the slashes. `cltl-storage:image/<id>` is resolved with
`urljoin(storage_url, "image/<id>")`, and `urljoin` **drops the last path
segment** of a base that does not end in `/`:

```python
urljoin("http://storage:8000/storage",  "image/x")  # -> .../image/x      wrong
urljoin("http://storage:8000/storage/", "image/x")  # -> .../storage/image/x
```

`myorg.example` appends the slash for you and logs a warning saying so;
`attach/connect.py` does not, deliberately, and `[cltl.backend] storage_url` for
cltl-monitoring and the chat UI does not either.

### The Monitoring tab is missing, or its iframe will not load

**Missing** is the default. `ghcr.io/leolani/cltl-monitoring` is not a published
package, so the service is behind a compose profile and
`CLTL_MONITORING_URL` is empty — which makes the chat UI leave the tab out
rather than show one that cannot load. See
[`deployment.md`](deployment.md#the-monitoring-tab-is-opt-in).

**Present but empty** is usually `[cltl.monitoring] active_interval`. At the
shipped default of 15 a scenario stops being recorded after fifteen seconds
without a request, and an image submitted during that gap is dropped on arrival
with no replay. This deployment sets it to `0`.

**Present but unreachable** means `CLTL_MONITORING_URL` names something the
*browser* cannot resolve — `monitoring:8000` is a compose service name, not an
address. It has to be `127.0.0.1` and the published port.

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
- **The publish beat the binding.** Every rung guesses at this rather than
  checking it — see the first entry on this page, and the module-container
  entry below.

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

Nothing anywhere closes this properly: rungs 1–2 sleep five seconds before
opening the scenario and the container waits a flat `start_delay`, which is the
same guess with the same number. `depends_on` does not reach across compose
projects, and the bus offers no way to ask whether the other side has bound —
see [`attaching.md`](attaching.md) for what would.

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

### One reply where there used to be two, after a kernel or listener died

Your module is gone and its scenario is not. Nothing in the platform expires
one.

`ChatUiService` holds the scenario id as plain in-memory state and clears it on
exactly one thing, a `ScenarioStopped` — which nothing is going to send now.
So the chat UI keeps working and keeps publishing utterances under a scenario
whose owner is gone, and `cltl-eliza` (which ignores scenario ids entirely)
keeps answering them. **That is why this does not look like a stale scenario:
the page is not blank and nothing errors. You just stopped getting your own
reply**, because the thing that produced it is dead.

Confirm it without touching anything — this route exists precisely because it
has no side effects:

```
$ curl -s localhost:8000/chatui/chat/scenario
{"scenario_id":"d3b3d421-7f4f-4410-8448-7768cb28ec8f"}
```

**The cure is to open a new one, and nothing needs cleaning up first.** Re-run
the notebook's scenario cell, or restart `attach/listen.py`. The chat UI assigns
whatever `ScenarioStarted` arrives, unconditionally, so the new one simply takes
over — the same fact as *Two scenarios for one tenant* above, seen from the
other side.

**Do not restart the chat UI container to fix it.** That clears the id, but the
bus retains nothing: a listener that is still running will never re-announce its
scenario, so you trade a stale scenario for a blank page and still have to open
a new one.

Three things that look like they should have handled this, and do not:

- **`[cltl.chat-ui] timeout`** is the *browser session* timeout, in minutes. On
  expiry it publishes a `quit` desire on `[cltl.chat-ui.events] topic_desire`;
  it never clears the scenario id itself. This deployment sets `timeout: 0` and
  configures no `topic_desire`.
- **`DELETE /chatui/chat/terminate`** is the manual version of that, gated on the
  same two settings. Here it logs `No-op on /chat/terminate`.
- **`cltl-context`** is what would answer such a quit, and it is absent from both
  halves of this deployment on purpose — which is why the custom side opens
  scenarios at all. See [`tenancy.md`](tenancy.md).

Killing the process is the common way to get here, and `kill -9` is sometimes
the only way to stop a listener at all — see *`attach/listen.py` will not die
after the deployment stops* below.

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

### `[myorg.example] image_storage_url is '$CLTL_STORAGE_URL' — an UNEXPANDED variable`

The guard working. `CLTL_STORAGE_URL` is not defined in the container
environment, and `EnvInterpolation` passes an undefined variable through
verbatim with only a warning — so without this refusal the literal string would
have been used as a URL and every fetch would have failed with a confusing
error. `compose/example.compose.yml` defines it; a hand-rolled `docker run` has
to as well. Running `python src/main.py` by hand needs it too — see
`config/custom.config.example`.

The sibling message, `image_storage_url is empty while topic_image is set`, is
the same guard for the other omission. Either set the address, or empty
`[myorg.example] topic_image` to run text-only.

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
