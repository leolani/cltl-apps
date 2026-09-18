# Simplifying the attach plumbing

Status: implemented · Date: 2026-09-18

## Why

`attach/connect.py` is the shared plumbing for rungs 1–2, and it had grown
three things it did not need to own.

**A partial `Configuration`.** `_DictConfiguration` implemented `get` and
`__contains__` and left `get_int`, `get_float`, `get_boolean`, `get_enum`,
`__iter__` and `__len__` inherited from the ABC and raising
`NotImplementedError`. That was safe, because `KombuEventBus` asks for nothing
else — but it was a second `Configuration` semantics living beside the
platform's, in a template whose job is to show people the platform's way.

**A registration guard protecting nothing.** `register_event_types()` carried a
`_registered` flag and a `threading.Lock`, and `_serializer`/`_deserializer`
called it on every event — a lock acquire per message on the consumer thread.
`register_type_var` is a single dict assignment and kombu's `register` writes
one registry entry; doing either twice was always a no-op.

**A binding check that had outgrown its value.** `wait_until_bound` and
`binding_key` were ~110 lines that polled RabbitMQ's management API. They
hardcoded the exchange name and the `%2F` vhost, carried the integration
harness's credentials as a fallback, degraded a 401 to a silent two-second
sleep — and, in the `baseline={}` case, could not degrade at all: with a
baseline supplied the pre-loop fallback was skipped, so an unreachable
management API meant polling to the full timeout and then raising. They were
also the only code outside `KombuEventBus` that knew a routing key is
`<topic>.<tenant>`, which should be the bus's business and nobody else's.

A review pass at the same time found four places where the docs described
behaviour the code did not have. One of them resolves itself here; three are
fixed.

## What was built

- **Config from the platform.** `connect.event_bus` builds a `ConfigParser` from
  a dict and hands it to `LocalConfigurationManager`. `_DictConfiguration` and
  `_DictConfigurationManager` are gone. The whole thing is three stdlib lines
  plus one platform import.
- **Serialization at module level**, the shape `src/main.py` already used: three
  `register_type_var` calls, a `serializer`/`deserializer` pair, one
  `kombu.serialization.register`. No flag, no lock, no per-event call.
- **`wait_until_bound` and `binding_key` deleted**, along with `import
  requests`. Callers sleep inline: 2.0s after subscribing, 5.0s before
  `start_scenario`.
- **`--management-url` removed** from `attach/listen.py`.
- **The notebook's setup cell now carries the whole wiring visibly** —
  serialization and the bus factory written out rather than imported — and
  one-liners thereafter. `connect.py` keeps its copy for `listen.py`, which
  imports it as before.
- **`load_image` names the interpreter** it failed on, appending
  `sys.executable` to the `ImportError`, which `gotchas.md` had been promising
  for some time.
- `connect.py`: 418 → 308 lines.

## What was decided, and why

**A sleep rather than a fixed binding check.** The check was correct and it
worked; the reason to drop it anyway is that everywhere it was used, the next
actor is a human. The notebook subscribes and then prints "type something in
the chat UI"; the isolation cell subscribes and then asks for a few more
messages. Against that, a hundred lines of management-API polling — with its
own credentials, its own failure modes, and its own page of documentation —
buys a guarantee nobody was waiting on. The docs now say plainly that this is a
guess, which is a more useful lesson than a mechanism a copier will never
reuse.

**2.0s and 5.0s, not one number.** They are different quantities. The first
waits on our own consumer thread: one AMQP round trip on localhost, tens of
milliseconds. The second waits on the *chat UI's* queue, in another container,
which nothing here can observe — so it uses what `[myorg.tenant] start_delay`
already budgets for the identical problem at rung 4. One number per guess,
consistent across rungs.

**`interpolation=None`.** The platform's `EnvInterpolation` inherits
`BasicInterpolation.before_get`, which scans every value on read — so a
percent-encoded broker password (`amqp://user:p%40ss@host/`) parses fine and
then raises `InterpolationSyntaxError` from inside `KombuEventBus.__init__`.
Nothing in a notebook needs `$VAR` expansion, because the config is composed in
Python. A test pins this.

**No `KombuEventBusContainer`.** It would register the serializer for us, and
for one bus it is the better answer. `DIContainer._singletons` is
process-global, keyed on the property name rather than the container instance,
so three containers in one kernel yield one bus with one tenant — and the
notebook's isolation section needs three, with three different tenants. The
platform's own harness reached this conclusion first and recorded it in
`_TenantConfigurationManager`'s docstring.

**No `parse_configuration` helper in `cltl.combot`.** It was the original shape
of this change, and it dissolved: `LocalConfigurationManager` already takes a
`ConfigParser`, and a `ConfigParser` is buildable from a dict, so there was
nothing left to add. Adding it anyway would have meant a submodule commit and a
pointer commit, and `requirements.notebook.txt` pins `cltl.combot` to a GitHub
branch while the deployment runs published images — so nothing could have been
verified end to end until someone pushed.

**The notebook duplicates the wiring rather than importing it.** Rung 1's
subject *is* what it takes to join a bus. An import would have hidden the two
failures the block exists to prevent — the unregistered type vars and the
unregistered serializer name — behind a line that looks like housekeeping.
Registering the same names twice is a no-op, so the duplication costs nothing
at runtime.

## Three documentation claims corrected

1. **`metadata.topic` does not carry the tenant.** `connect.py`,
   `docs/attaching.md` and the notebook all said the delivered event's topic
   ends in the tenant. `KombuEventBus._topic_handler` stamps the **bare** topic
   via `Event.with_topic`; the tenant is in `metadata.tenant` and the suffix
   exists only in the AMQP routing key. The prose offered the false fact as the
   reason dispatch-on-topic works, when in truth it works *because* the topic is
   bare — if the suffix were there, every `event.metadata.topic ==
   self._image_topic` in this repository would stop matching.
2. **`topic_worker.start().wait()` does not mean "bound".** `gotchas.md` offered
   it as the in-component equivalent of the binding check. `TopicWorker.run`
   sets `_started` immediately after `subscribe()` returns, which is precisely
   the moment that is not yet safe. Corrected here; the platform fix is out of
   scope.
3. **`load_image` now does what `gotchas.md:62` said it did** — appends
   `sys.executable` to the `ImportError`, so a notebook on the wrong kernel says
   so in its own traceback.

A fourth — "when it works, it says so", in `attaching.md` and
`getting-started.md` — resolved itself: there is no longer a check to report
success.

## Verification performed

- `PYTHONPATH=.:src .venv/bin/python -m pytest tests` — **92 passed**, 10
  subtests, in a venv built fresh from `requirements.notebook.txt`.
- The new `EventBusConfigTest` asserts through `connect.event_bus` rather than a
  copy of its internals; kombu's `Connection` and `Exchange` are lazy, so
  constructing a bus opens no socket and needs no broker.
- Checked that the empty-tenant assertion is not vacuous: an omitted `tenant`
  key yields `_tenant is None`, a present-but-empty one yields `''`. Both are
  falsy and the bus behaves identically, which is exactly why the distinction
  needed pinning rather than assuming.
- `test_a_percent_encoded_password_survives` fails under the platform's default
  interpolation and passes with `interpolation=None`, which is the whole reason
  that argument is there.

End to end, against `deployment/server.compose.yml` plus one `tenant-a` stack:

| Checked | Result |
|---|---|
| Chat UI before any scenario | `scenario_id: null` — blank, as documented |
| `listen.py`, no `--management-url` | subscribes, sleeps 2s, sleeps 5s, opens the scenario; `scenario_id` set 7s after start |
| Typing into the chat UI | **two** replies — `YOU SAID: HELLO THERE (via attach/listen.py)` and cltl-eliza's `I see.` |
| `metadata.topic` on a delivered event | `'cltl.topic.text_in'` — **bare**, and `metadata.tenant` is `'tenant-a'`. The wire JSON agrees. This is the claim three files had backwards |
| Three buses, three tenants, one process | `tenant-a` saw 3 events, the untenanted control saw 3, `tenant-b` saw **0** — the isolation demonstration, and the thing a DI container could not have done |
| `SIGTERM` to `listen.py` | `Closed scenario …`, chat UI back to `scenario_id: null` with a fresh chat id, process exited without hanging |

The sleeps were sufficient every time: no event was lost in any run, including
the three-bus cell's six fresh consumer threads behind a single two-second wait.

**The image path was not exercised end to end** — it needs a picture uploaded
through the chat UI, and `load_image` is unchanged here apart from the
`ImportError` wrapper, which is unit-tested.

## Not done

- **The real fix for the race.** kombu's `ConsumerMixin` fires
  `on_consume_ready` once a consumer's queues are declared and bound, so
  `_EventBusConsumer` could signal it and `KombuEventBus.subscribe` could wait
  on it. That would remove the guess for every caller — this template's and the
  platform's — and would make `topic_worker.start().wait()` mean what everyone
  assumes it means, which would in turn retire `[myorg.tenant] start_delay`'s
  sibling problem. It is a `cltl.combot` change, and the hook's exact firing
  point was not verified while doing this work.
- **A dict/string `ConfigurationManager` factory in `cltl.combot`**, which could
  also delete the integration harness's `_TenantConfigurationManager` — the same
  partial-`Configuration` wart this change removed from here.
- **Per-instance DI singletons.** `DIContainer._singletons` being process-global
  is why the container route is unavailable to a notebook holding three buses.
  Fixing it properly reaches every component in the platform.
- **The notebook, run cell by cell.** `listen.py` was exercised against a live
  deployment and the notebook's construction path was exercised by a script that
  mimics it (three buses, one process), but nobody opened the `.ipynb` in
  Jupyter and ran it top to bottom.
