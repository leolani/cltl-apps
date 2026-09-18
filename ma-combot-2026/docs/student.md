# Attaching to the course server

You have a connection sheet with four values on it. This page is what to do with
them.

The exercise itself is [`custom-module`](../../custom-module) — its
`docs/getting-started.md` is the tutorial, and everything it says is true here
**except the addresses**, because it was written for someone running the whole
deployment on their own laptop. You are not: the server is already running, and
it is shared with everyone else on the course.

## What runs where

The server is already up, and you cannot break it for other people by accident.
Two things run on *your* machine:

- **your chat UI** — `ma-combot-2026/student/`, one container
- **your notebook or script** — `custom-module/attach/`

You need **Docker** and **Python 3.10**.

## 1. Start your chat UI

```bash
cd ma-combot-2026/student
cp .env.example .env
$EDITOR .env          # paste the four values from your sheet
docker compose up -d
```

Then open <http://localhost:8000/chatui/static/chat.html>.

**It is blank, and that is correct.** A chat UI renders nothing until a
conversation — a *scenario* — has been opened for it, and the thing that opens
one is your notebook, a few cells in. Nothing is broken and nothing is missing.
[`custom-module/docs/tenancy.md`](../../custom-module/docs/tenancy.md) explains
why that job falls to you.

## 2. Set up the notebook

Follow `custom-module`'s own instructions to make the virtual environment and
register the kernel. Then change **three** addresses, because the defaults point
at a deployment on your own laptop and yours is on the course server.

In **cell 1**:

```python
AMQP_URL = "amqps://USER:PASSWORD@HOST:5671/?heartbeat=30"   # value 2 on your sheet
MANAGEMENT_URL = ""                                          # not yours to open
TENANT = "tenant-you"                                        # value 1 on your sheet
```

In **cell 12**, the one that starts the image section:

```python
STORAGE_URL = "https://USER:PASSWORD@HOST/storage/"          # value 3 on your sheet
```

That third one is the one people miss, and it fails in a way that looks like
something else entirely: the whole text half of the notebook works perfectly,
and then images fail with `could not load cltl-storage:image/...`. If you see
that, check `STORAGE_URL` before anything else. **Keep the trailing slash** — the
reference is resolved with `urljoin()`, which drops the last segment of a base
that lacks one.

`TENANT` must match `CLTL_TENANT` in your `student/.env`. If they disagree
nothing happens when you type, and nothing anywhere reports an error: your chat
UI publishes on one routing key and your notebook listens on another.

For `attach/listen.py` the same values are command-line flags:

```bash
python attach/listen.py --tenant tenant-you \
    --amqp-url 'amqps://USER:PASSWORD@HOST:5671/?heartbeat=30' \
    --storage-url 'https://USER:PASSWORD@HOST/storage/'
```

## 3. Expect two replies

Type in your chat UI and you get **two** answers: the shared ELIZA's, and your
own notebook's. That is the point of the exercise — your code is taking part in
a conversation that already worked without it. Upload a picture and you get
**one**, yours: ELIZA subscribes to text and never sees an image.

## The isolation cells need one change

Near the end the notebook proves that tenants are separated, by listening as
`tenant-b` and seeing nothing. On your laptop that is a clean experiment. Here,
`tenant-b` may be a classmate.

Set `TENANT_B` to something nobody owns:

```python
TENANT_B = "tenant-nobody"
```

If you leave it pointed at a real classmate's tenant, the cell will report
*"`tenant-b` received traffic it should not be able to see"* and suggest the
deployment is misconfigured. It is not. You are just listening to a real person.

Note also what the *control* in that cell does: it attaches untenanted and
therefore sees **everyone's** conversation. That is genuinely how the platform
works, and it is why the next section exists.

## What you can see, and what is expected of you

You can read every other student's conversation, publish into their chat as
though you were the agent, close their scenario, and fetch images they uploaded.
None of that is blocked.

It is not blocked because the separation in this platform is *cooperative*: a
routing key, not a wall. Making it a wall would break the very cell that shows
you how it works.

**Everything you do carries your name.** Your broker user and your storage
credential are yours alone, and every connection and request is logged against
them. Don't go looking through other people's conversations, and don't publish
into them. If you're curious about what's possible, say so — that is a better
conversation than an incident.

Treat your sheet like a password, because it is two of them. If it leaks, ask
for a reissue; it takes a minute.

## When something looks wrong

[`known-issues.md`](known-issues.md) first — it covers the things that are
expected here and are not in the template's own documentation. Then
[`custom-module/docs/gotchas.md`](../../custom-module/docs/gotchas.md), which is
symptom-first and covers everything else.
