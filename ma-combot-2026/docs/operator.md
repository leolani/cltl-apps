# Running the course server

For the instructor. A student needs [`student.md`](student.md) instead.

## Before the first `up`

Three things must be true, and none of them is something this stack can check
for you:

1. **A DNS name resolves to this host.** One name, used for both the HTTPS
   endpoint and the broker's TLS listener, so there is one certificate. Caddy
   obtains it over ACME HTTP-01, which means the name must already resolve and
   port 80 must be reachable *before* the first start. A name that is not ready
   yet fails in Caddy's log and nowhere else.
2. **Ports 80, 443, 5671 and SSH are open; nothing else is.** Everything else in
   this stack binds loopback deliberately.
3. **A version tag is chosen.** `CLTL_IMAGE_TAG` must name a real tag, never
   `latest`. It moves under you, and a mid-term pull that changes a payload
   dataclass reaches students as an unmarshal error with no version to point at.

```bash
cd ma-combot-2026
cp .env.example .env && $EDITOR .env      # hostname, ACME email, admin password, image tag
docker compose -f server.compose.yml up -d
```

Watch Caddy get its certificate before going further — everything else depends
on it:

```bash
docker compose -f server.compose.yml logs -f caddy
```

Then give the broker a copy of that certificate and enrol the class:

```bash
bin/sync-certs.sh                          # copies the cert where RabbitMQ can read it
cp roster.example roster.csv && $EDITOR roster.csv
bin/provision.sh roster.csv                # one broker user + one storage credential each
```

`provision.sh` prints the management-UI password once, and writes one connection
sheet per student into `sheets/`. **Hand those out individually.** They contain
two passwords each; a sheet posted to a group channel is a reissue
(`bin/reissue.sh <student>`), which takes a minute and is always the right
answer.

## Verifying it actually works

Before the class does, do the whole exercise yourself as a student, from a
machine that is not this host:

```bash
cd student
cp .env.example .env && $EDITOR .env       # paste your own test sheet
docker compose up -d
```

Then open <http://localhost:8000/chatui/static/chat.html> — **blank is correct**
— and run `custom-module/attach/example.ipynb` against the same credentials. You
should see the chat UI come alive at the scenario cell, two replies to anything
you type, and one reply to an uploaded image.

If you only ever test from the server itself you will not exercise TLS, the
certificate chain, or the storage credential, which are the three things most
likely to be wrong.

## Keeping it running

Two timers. Neither is optional over a term.

**Certificate renewal.** Caddy renews on its own; the broker does not notice
until something copies the new files across and clears the Erlang PEM cache.
`bin/sync-certs.sh` does both and exits quietly when nothing has changed, so a
daily run costs nothing:

```ini
# /etc/systemd/system/combot-certs.service
[Service]
Type=oneshot
WorkingDirectory=/srv/cltl-apps/ma-combot-2026
ExecStart=/srv/cltl-apps/ma-combot-2026/bin/sync-certs.sh

# /etc/systemd/system/combot-certs.timer
[Timer]
OnCalendar=daily
Persistent=true
[Install]
WantedBy=timers.target
```

**Image retention.** `bin/prune-images.sh [days]`, weekly. Nothing in
`cltl-backend` ever deletes an uploaded image — there is no delete path in the
code at all — and the disk it fills is the one RabbitMQ lives on. When the
broker's `disk_free_limit` is crossed it **blocks publishers**, so the whole
class stops at once, with nothing in any log pointing at a photograph from three
weeks ago.

## Watching for trouble

The class cannot report most failures usefully, because every symptom looks like
their own laptop. Watch these yourself:

| Check | Why it matters |
|---|---|
| `df -h` on the storage filesystem | a full disk blocks publishing for everyone |
| `docker compose -f server.compose.yml ps` | `eliza` has a healthcheck now; an unhealthy one means nobody gets a second reply |
| `logs/caddy/access.log` | who reached storage, and with which credential |
| broker log in the `rabbitmq-data` volume | who connected, from where, as whom |

The last two are the audit trail. They are the reason per-student credentials
exist, given that students are *not* prevented from reaching each other's
tenants. Keep them for the term.

## When something is wrong

**A student gets one reply instead of two.** Check `eliza` first — it is the
shared process behind everyone's second reply, and its death looks exactly like
a student's own listener dying. `docker compose -f server.compose.yml ps` and
restart it if unhealthy.

**A student's chat UI shows nothing at all.** Almost always their own scenario,
not the server: see [`known-issues.md`](known-issues.md).

**Everyone stops at once.** Disk, or the broker. `df -h`, then
`docker compose -f server.compose.yml logs rabbitmq | tail`. A disk alarm names
itself clearly in that log; a full disk elsewhere does not.

**Certificate expired.** `bin/sync-certs.sh` by hand, and check why the timer
did not. The broker keeps serving the old certificate until its PEM cache is
cleared, so "Caddy renewed it" and "the broker is using it" are two facts, not
one.

## Tearing down

At the end of the term:

```bash
docker compose -f server.compose.yml down          # keeps the volumes
docker compose -f server.compose.yml down -v       # and the broker's users, and the certs
```

`secrets/`, `sheets/`, `storage/` and `logs/` are gitignored and survive either
way. Delete them deliberately — `sheets/` in particular holds every student's
credentials in plain text.
