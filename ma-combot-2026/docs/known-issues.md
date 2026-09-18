# Known issues on the course server

Symptom first. These are the things that behave differently here than in
[`custom-module`](../../custom-module) — either because the deployment is shared,
or because it runs for months rather than an afternoon. Everything else is in
[`custom-module/docs/gotchas.md`](../../custom-module/docs/gotchas.md), which is
still the right first stop.

---

### Images fail, but everything else works

`could not load cltl-storage:image/...`, while text replies are fine.

`STORAGE_URL` in notebook cell 12 is still pointing at `127.0.0.1:8002` — your
own laptop — or is missing your credentials, or lost its trailing slash. All
three produce this one symptom. The text half of the notebook never touches
storage, which is why it keeps working and makes this look like a problem with
images rather than with an address.

The value is on your connection sheet. Keep the trailing slash: the reference is
resolved with `urljoin()`, which drops the last path segment of a base without
one.

---

### You type and absolutely nothing happens

No reply, no error, nothing in the notebook, nothing in the chat UI.

Your `TENANT` and your `CLTL_TENANT` disagree. The chat UI publishes on
`cltl.topic.text_in.<its tenant>` and your notebook binds
`cltl.topic.text_in.<its tenant>`; if those are two different words, the message
is delivered to nobody and no part of the system considers that an error.

Check `student/.env` against cell 1. They both come from line 1 of your sheet.

---

### One reply where there used to be two

You get your own module's answer but not ELIZA's.

Two causes, and they are told apart by asking one other person.

- **Only you** — your own listener or kernel died, or the chat UI is publishing
  under a scenario whose owner is gone. See the entry below.
- **Everyone** — the shared `eliza` on the server is down. Tell the instructor;
  there is nothing you can do from your laptop, and nothing you are doing wrong.

---

### Your chat UI stops responding after a crashed notebook

Nothing in the platform expires a scenario. The chat UI holds the id until a
`ScenarioStopped` arrives, and if your kernel died, nothing is going to send one.
It keeps working — publishing under a conversation whose owner is gone — so the
symptom is one reply instead of two rather than a blank page.

Re-run the scenario cell. A new `ScenarioStarted` replaces the dead one; the
assignment is unconditional, so nothing needs cleaning up first. Don't restart
your chat UI container: that clears the id, but the bus retains nothing, so a
listener that is still running never re-announces itself and you trade a stale
scenario for a blank page.

---

### Running the cleanup cell kills a conversation you are using

You abandoned a notebook, started a fresh one, and then went back to the old tab
and ran its cleanup cell — and the *new* conversation went away.

The chat UI clears its scenario on any `ScenarioStopped`, without checking
whether the id matches the one it is holding. An old notebook's cleanup
therefore closes whatever conversation is current.

Re-run the scenario cell in the notebook you actually want to use. Closing old
notebooks without running their cleanup cell is the way to avoid it.

---

### Two browser tabs behave like one conversation

Because they are one. The chat UI keeps a single chat and a single transcript
for the whole process, and this deployment sets `timeout: 0`, which switches off
the cookie check that would otherwise reject a second browser.

It only ever affects your own machine — your chat UI is on `localhost` and
nobody else can reach it. Use one tab.

---

### The isolation cell says another tenant "received traffic it should not"

Expected here, and not a fault. `TENANT_B` in cell 18 is a real classmate on
this server, so of course that observer sees traffic. Set it to an id nobody
owns — `tenant-nobody` — and the cell does what it was written to do.

See [`student.md`](student.md#the-isolation-cells-need-one-change).

---

### The notebook replies twice, then three times

You re-ran the handler cell. A second `subscribe` to a topic the bus is already
consuming *appends* your handler rather than replacing it, so the same message
gets answered once per copy.

Restart the kernel. The cleanup cell closes the buses; re-running from the top
gives you one handler again.

---

### Your connection dies when you close your laptop

Expected, and it recovers by itself: kombu retries, and your queues are
recreated on reconnect. Messages published while you were away are gone — they
were routed to a queue that no longer existed, which a topic exchange discards
without telling anyone.

Keep `?heartbeat=30` in your broker URL. Without it the server keeps your queue
bound long after your laptop has stopped listening.

---

### You can see other people's conversations

Yes. That is how this platform works, and
[`custom-module/docs/tenancy.md`](../../custom-module/docs/tenancy.md) is honest
about it: separation is a routing key, not a wall. It is not enforced here
because enforcing it would break the notebook cell that teaches you the
mechanism.

Everything you do carries your own credential and is logged. See
[`student.md`](student.md#what-you-can-see-and-what-is-expected-of-you).
