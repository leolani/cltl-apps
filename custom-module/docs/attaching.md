# Attaching to a live bus (rungs 1–2)

How the notebook and `attach/listen.py` join a running deployment without
installing anything, and the three things that go wrong the first time.

Read this before modifying `attach/connect.py`, which both rungs share.

## Why this is safe to do

The bus is a single RabbitMQ **topic exchange** named `cltl.combot`. When you
subscribe, you get your **own private queue** — server-named, exclusive,
auto-deleting — bound to the topics you asked for.

That property is what makes rung 1 safe against a live deployment: attaching a
listener is a *fan-out*. Your queue receives copies. You never intercept, delay
or steal a message from the modules already running, and when your notebook
kernel dies the queue disappears with it. You can attach to a deployment
someone else is using and they will not notice.

## A bus without a container

The platform wires components with a dependency-injection container that reads
configuration files. Rungs 1–2 skip all of it: `KombuEventBus` asks its
configuration manager exactly one question — `get_config("cltl.event.kombu")`
— and needs the answer to support `.get(key)` and `in`.

The platform's own `LocalConfigurationManager` already provides that, over a
plain `ConfigParser` — and a `ConfigParser` can be built from a dict without
touching the filesystem. So `attach/connect.py` builds one from four values and
hands it over:

```python
parser = ConfigParser({}, strict=False, interpolation=None)
parser.read_dict({"cltl.event.kombu": {
    "server": server, "exchange": exchange,
    "compression": compression, "tenant": tenant}})

KombuEventBus("cltl-json", LocalConfigurationManager(parser))
```

That is the whole trick, and it is why attaching needs no config files, no
container and no install of this template. Two details in it are not cosmetic:

- **`interpolation=None`.** The default interpolation scans every value on
  read, so a percent-encoded broker password — `amqp://user:p%40ss@host/` —
  parses fine here and then raises `InterpolationSyntaxError` from inside
  `KombuEventBus.__init__`, nowhere near the value that caused it. Nothing here
  wants `$VAR` expansion: this config is composed in Python, which is where a
  caller can interpolate whatever it likes. A `.config` file on disk cannot,
  which is what `EnvInterpolation` exists for.
- **`tenant` is present even when empty.** The bus does `config.get('tenant')
  if 'tenant' in config else None`, so an omitted key yields `None` and an
  empty one yields `''`. The bus behaves identically either way — but writing
  the key is what says the untenanted bus was *meant*.

**Why not `KombuEventBusContainer`?** It registers the serializer for you, and
for a single bus it is the better answer. But `DIContainer._singletons` is
process-global — keyed on the property name, not on the container instance — so
three containers in one kernel hand you one bus with one tenant, and the
isolation section below needs three. The platform's own harness reached the
same conclusion, and wrote it down in `_TenantConfigurationManager`'s docstring.

## Five things that go wrong the first time

**1. `TypeError: PAYLOAD is not a dataclass and cannot be turned into one`**

Emissor's serialisation needs its generic type variables registered before
anything marshals an `Event`. `connect.py` does it at import, as a module-level
`register_type_var(PAYLOAD)` / `(SIG)` / `(MEN)` — the same three lines every
component's `src/main.py` runs before it builds anything. There is no guard on
them and none is needed: `register_type_var` is a single dict assignment, so
running it twice costs nothing. Write your own entry point and you must do the
same.

**2. `SerializerNotInstalled`, deep inside kombu**

`KombuEventBus` takes a serializer *name*, not a function, and looks it up in
kombu's global registry at publish and consume time. If nothing ever registered
that name, the failure surfaces a long way from the cause — inside kombu, from a
bus that constructed perfectly. `connect.py` registers `'cltl-json'` at import,
beside the type vars, so importing it is enough.

The notebook's setup cell writes both of those out again rather than importing
them. That is deliberate: they are two of the five things on this list, and an
import would hide them behind a line that looks like housekeeping. Registering
the same names twice is a no-op.

**3. The chat UI is blank and stays blank**

Nothing has opened a scenario, and in this deployment nothing will: there is no
`cltl-context` in either half. `cltl-chat-ui` renders nothing and refuses to
publish until it has seen a `ScenarioStarted` on its own tenant's routing key.

So `connect.py` carries `start_scenario`/`stop_scenario`, and both the notebook
and `listen.py` call them. **This is not something an attached module normally
does** — it is a chore that falls to the custom side purely because the chat UI
runs inside a tenant and a tenant's scenario can only be opened on that tenant's
own bus. `docs/tenancy.md` is the long version; the short version is that it is
a tenancy tax, not a feature.

Those helpers are a deliberate copy of the platform's
`integration/src/cltl_integration/drivers/scenario.py` and a parallel of this
template's own `src/myorg/tenant/scenario.py`, rather than an import of either —
rung 1 has nothing installed, which is the point of rung 1.

**4. The first message never arrives**

This one is worth understanding properly, because the symptom is
*intermittent*.

`KombuEventBus.subscribe` starts a background consumer thread and returns
immediately. The queue is declared and bound to the exchange somewhere in that
thread's near future — **not** before `subscribe()` returns. Anything published
in that window is routed to no queue at all and dropped, because that is what a
topic exchange does with a message matching no binding. No error, on either
side.

The notebook and `listen.py` close that window with a flat `time.sleep`. **That
is a guess, not a check**, and it is worth saying so plainly rather than
dressing it up: nothing confirms the binding ever landed.

### Two seconds, and where five is used instead

For a subscription of your own, two seconds. What you are waiting on is one
consumer thread getting scheduled and then one AMQP round trip against a broker
on localhost — tens of milliseconds. In the notebook the next thing to happen
is a person typing into the chat UI, so the real margin is larger again by
orders of magnitude.

**Before `start_scenario`, five.** That wait is a different quantity: the queue
that has to exist is the **chat UI's**, in another container, and nothing in a
notebook can observe it. Five seconds is what `[myorg.tenant] start_delay`
budgets for exactly this problem at rung 4, so there is one number for one
guess across the rungs. [`configuration.md`](configuration.md) calls that number
the weakest part of the design; it is no stronger here.

### What would actually fix it

The bus confirming its own binding. kombu's `ConsumerMixin` fires
`on_consume_ready` once a consumer's queues are declared and bound, so
`KombuEventBus.subscribe` could wait on that and the guess would disappear for
every caller — this template's and the platform's own. It would also make
`topic_worker.start().wait()` mean what it is widely assumed to mean; today it
is set the instant `subscribe()` returns, which is the very moment that is not
yet safe.

That is a change to `cltl.combot`, not to this template, and it is not made
here.

**And only sleep for a topic this bus has not subscribed to before.**
`KombuEventBus` keeps one consumer per topic — one queue, one binding — so a
second `subscribe` to a topic it is already consuming appends your handler to
that consumer's list and creates no new queue
([`kombu.py`](https://github.com/leolani/cltl-combot)'s `subscribe`). The
handler is live the moment `subscribe` returns; there is genuinely nothing to
wait for. That is why the notebook's wire-up cell subscribes `respond` to two
topics that `show` and `show_image` already bound, and then waits for *nothing*.

**5. `ModuleNotFoundError` for a package the venv demonstrably has**

The notebook is running on a different interpreter than the one you installed
into, and nothing says so.

A venv's stock kernel is called `python3` and its `kernel.json` launches a
**bare `python`**, resolved through `PATH` when the kernel starts rather than
pinned to the venv:

```json
["python", "-m", "ipykernel_launcher", "-f", "{connection_file}"]
```

`example.ipynb` asks for that generic `python3` by name, so whichever Jupyter
opens it supplies its own. Ask the kernel what it is — `import sys;
print(sys.executable)` — and give the venv a kernel of its own, which records an
absolute path:

```bash
python -m ipykernel install --user --name cltl-example \
    --display-name "cltl-example (.venv)"
```

In VS Code, the equivalent is the kernel picker at the top right. Full symptom
and cure in [`gotchas.md`](gotchas.md#modulenotfounderror-no-module-named-cltlbackend-but-the-venv-has-it).

## Getting the pixels of an image

`connect.load_image` is the last of the helpers, and it exists because the
surprise is worth meeting once at rung 1: an image signal does not contain an image.

```python
image = load_image(signal.files[0], DEFAULT_STORAGE_URL)
height, width = image.shape[:2]          # numpy is (rows, cols)
```

`signal.files[0]` is `cltl-storage:image/<id>` — a scheme, not a URL.
`ClientImageSource` resolves it against the storage address and decodes what
comes back, which is JSON with the pixels base64-encoded rather than PNG bytes.
Three details it saves you from:

- It must be used as a **context manager**; `capture()` raises outside one.
- `storage_url` **must end in a slash**. The reference is resolved with
  `urljoin()`, which drops the last path segment of a base without one, so
  `…:8002/storage` looks for `…:8002/image/<id>`. The packaged module appends
  the slash and warns; `load_image` does not, on purpose — this is the rung where
  you are meant to see the trap.
- The fetch **can legitimately fail**. The chat UI's upload of the pixels is
  best-effort and needs `cv2`, and it publishes the reference either way — so
  wrap the call and carry on, as `listen.py` does. An unstored id answers HTTP
  500 with a `KeyError`, not 404.

`cltl.backend[impl]` is the third line of `requirements.notebook.txt` and the
only one the text half does not need; the import is inside the function so the
text cells keep working without it.

**Which is also how you learn your notebook is not running in the venv.** See
the fifth item above: `load_image` is usually the first cell that needs anything
the *other* environment does not already have, so a kernel on the wrong
interpreter fails precisely here and nowhere earlier. It therefore reports the
interpreter it failed on — `sys.executable`, in the `ImportError` itself — so
the answer is in the traceback rather than three pages away.

## Seeing what actually crossed the wire

`connect.event_json(event)` returns the JSON the broker carried, pretty-printed
— `marshal(event, cls=Event)`, which *is* the function handed to kombu as the
`cltl-json` serializer. Not a `repr`, and not a reconstruction: what you
read is the publisher's bytes with whitespace added.

Two cells in the notebook show it, one per modality, and both are worth opening
exactly once. The image one settles the claim this page makes twice over:
`"array": null`, a `cltl-storage:` string in `files`, and a `ruler.bounds` that
declares a size nothing has yet checked against the pixels. The text one settles what
`metadata.topic` actually holds: the **bare** topic you subscribed with, with no
tenant on the end. The tenant rides in `metadata.tenant`, and the `.tenant-a`
suffix exists only in the AMQP routing key — `KombuEventBus` stamps the plain
topic on delivery (`_topic_handler`, via `Event.with_topic`). That is precisely
why `_process` can dispatch on it: if the suffix were there, every
`event.metadata.topic == self._image_topic` in this repository would stop
matching.

**Folded, because a payload is sixty lines and a notebook is read top to
bottom.** The notebook wraps the JSON in a plain HTML `<details>` block rather
than setting `jupyter.outputs_hidden` in cell metadata: a collapsed *output* is
each front-end's own notion, honoured by the one that wrote it and ignored by
the next, while `<details>` is collapsed-by-default in JupyterLab, VS Code and
nbviewer alike. The helper is in the setup cell, five lines, and escapes what it
renders — a payload contains whatever somebody typed into the chat.

## Checking the isolation from a notebook

The last section of `attach/example.ipynb` attaches two extra observers and
tallies what each one receives: a tenanted bus for a *different* tenant, and an
untenanted one that binds `<topic>.#` and therefore sees everybody.

Two points of technique there, both reusable:

- **No second stack is needed.** `event_bus(AMQP_URL, tenant="tenant-b")`
  subscribes on `<topic>.tenant-b` whether or not any container is running for
  tenant-b. Bindings do not care whether the tenant "exists"; a tenant is a word
  in a routing key.
- **The untenanted observer is a control, not decoration.** Subscribing as
  another tenant and receiving nothing is exactly what you would also see with
  the broker down, the chat UI unplugged, or nobody typing. The result worth
  reporting is that the untenanted observer *did* see the conversation and the
  other tenant did not. A negative result is worth only as much as the positive
  one beside it.
- **It covers the image topic too**, so the claim is about both modalities. Note
  what it does *not* cover: the pixels themselves. Those live in a shared,
  untenanted store, and the routing key has no say over who can `GET` them —
  see [`tenancy.md`](tenancy.md#anything-that-reads-the-bus-is-tenanted-storage-does-not).

Both extra buses have to be closed along with the main one — see below.

## Closing the bus

Close the scenario **first**, then the bus: closing a scenario is a publish, so
the bus has to still be open for it. `listen.py` does both in a `finally`; the
notebook has a dedicated last cell for both, and closes **every** bus it opened
— the two isolation observers included, since each one holds consumer threads of
its own.

Closing the scenario also clears the chat UI's transcript, which is a convenient
way to see it land rather than taking it on faith.

`KombuEventBus`'s consumer threads retry a lost connection **forever** by
design. A bus left open keeps trying for the life of the process, which is why
a notebook kernel will not shut down cleanly and why stopping the deployment
before the listener leaves you needing `kill -9`. See
[`gotchas.md`](gotchas.md).

## Rung 2: the script

`attach/listen.py` is the notebook made durable — same `connect.py`, same
transform imported from `myorg.example.echo`, so rungs 2 and 3 demonstrably run
identical logic.

```bash
python attach/listen.py --tenant tenant-a \
    --amqp-url amqp://leolani:leolani@127.0.0.1:5672/
```

`--tenant` is **required and has no default**. There is no untenanted
conversation to join, and a default would pick a tenant on your behalf. Passing
`--tenant ''` attaches as a read-only observer of every tenant on the exchange,
and is refused unless you also pass `--no-scenario` — an untenanted
`ScenarioStarted` lands on the bare key and reaches nobody.

`--no-scenario` is for when something else already opened this tenant's
conversation: its own module container, or another listener. Two openers for one
tenant leaves the chat UI on whichever arrived last.

`--help` lists the rest: the input, output, image and scenario topics, and
where `cltl-storage:` resolves. It runs until `Ctrl-C`, then closes the scenario before the bus — in a
`finally`, so a crash does the same.
