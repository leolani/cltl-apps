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

   Port 80 is there for the ACME HTTP-01 challenge alone — the HTTP->HTTPS
   redirect is switched off in `edge/Caddyfile`, so nothing else answers on it.
   You can close 80 too, at the cost of leaving TLS-ALPN-01 over 443 as the only
   route to a renewed certificate; that is a real trade on a host that renews
   unattended for a term, and the reasoning is written out where the setting is.
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

Three things have to survive a reboot, and not one of them is automatic: the
Docker daemon, the containers, and the two timers.

### Start the Docker daemon at boot

`restart: unless-stopped` on every service is worth nothing if `dockerd` itself
never starts. Whether it is enabled depends on how Docker was installed — the
Debian and Ubuntu packages enable it, several other distributions leave it to
you — so check rather than assume:

```bash
systemctl is-enabled docker containerd     # expect: enabled
sudo systemctl enable --now docker.service containerd.service
```

Two things a restart policy does **not** do, both of which have bitten people
who thought a reboot was covered:

- **It cannot resurrect a container that no longer exists.** `unless-stopped`
  restarts containers; it does not create them. After a
  `docker compose down`, a reboot brings back *nothing* — run `up -d` again. The
  named volumes survive, so this costs you uptime rather than data.
- **It does not preserve start order.** `depends_on` is ordering that Compose
  applies when *it* starts things, not something the daemon replays at boot, so
  the four containers come back in whatever order it picks. `storage` and
  `eliza` may fail and be restarted a few times before the broker answers. That
  is expected and self-correcting: judge the stack by its state a minute later,
  not by the first lines in the log.

### Certificate renewal (daily)

Caddy renews on its own; the broker does not notice until something copies the
new files across and clears the Erlang PEM cache. `bin/sync-certs.sh` does both
and exits quietly when nothing has changed, so a daily run costs nothing.

```ini
# /etc/systemd/system/combot-certs.service
[Unit]
Requires=docker.service
After=docker.service

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

### Image retention (weekly)

Nothing in `cltl-backend` ever deletes an uploaded image — there is no delete
path in the code at all — and the disk it fills is the one RabbitMQ lives on.
When the broker's `disk_free_limit` is crossed it **blocks publishers**, so the
whole class stops at once, with nothing in any log pointing at a photograph from
three weeks ago.

```ini
# /etc/systemd/system/combot-prune.service
[Unit]
Requires=docker.service
After=docker.service

[Service]
Type=oneshot
WorkingDirectory=/srv/cltl-apps/ma-combot-2026
ExecStart=/srv/cltl-apps/ma-combot-2026/bin/prune-images.sh 30

# /etc/systemd/system/combot-prune.timer
[Timer]
OnCalendar=weekly
Persistent=true

[Install]
WantedBy=timers.target
```

### Enabling them

Writing the unit files does nothing on its own — this is the same trap as the
daemon, one level up:

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now combot-certs.timer combot-prune.timer
systemctl list-timers 'combot-*'           # both listed, with a NEXT time
```

`Persistent=true` on both means a timer that was missed while the host was down
fires shortly after it comes back, rather than waiting for the next occurrence.

## Rehearsing a reboot

Do this once, deliberately, before the term — not during it, and not for the
first time after an unplanned power cut. A reboot is the single most likely
disturbance over a term and the easiest to get wrong, because everything looks
fine until the machine actually goes down.

```bash
sudo reboot
```

When it comes back, in order:

```bash
cd /srv/cltl-apps/ma-combot-2026

docker compose -f server.compose.yml ps        # four services, all (healthy)
systemctl list-timers 'combot-*'               # both timers, scheduled

# The broker's users came from a named volume, not from a file. If this is
# empty, the volume did not survive and every student needs reissuing — which
# is exactly the failure this rehearsal exists to find early.
docker compose -f server.compose.yml exec rabbitmq rabbitmqctl list_users
```

Then prove the two public surfaces from **another machine**, because testing
from the host itself exercises neither TLS nor the certificate chain:

```bash
# Caddy is up and demanding a credential: expect 401.
curl -s -o /dev/null -w '%{http_code}\n' https://combot.example.org/storage/image/x

# With a real student credential: anything but 401 means auth and the proxy work.
curl -s -o /dev/null -w '%{http_code}\n' -u alice:PASSWORD \
    https://combot.example.org/storage/image/x

# The broker's TLS listener, and the certificate it is actually serving.
openssl s_client -connect combot.example.org:5671 -brief </dev/null
```

That last one is worth reading rather than glancing at. The broker reads its
certificate from `secrets/tls` at start and caches it, so "Caddy renewed the
certificate" and "the broker is serving the new one" are two separate facts —
and a reboot is one of the few moments they are guaranteed to agree.

Finish by doing the student walkthrough from
[Verifying it actually works](#verifying-it-actually-works) again. Four green
healthchecks prove the containers started; only a real conversation proves the
deployment did.

### What a reboot looks like to the class

Reassuring, and worth telling them in advance:

- **Their chat UI keeps working**, because it runs on their own laptop. The
  scenario it is holding is in *its* memory, not the server's, so nothing needs
  reopening afterwards.
- **Their notebooks reconnect by themselves.** kombu retries a lost connection
  and re-declares its queues.
- **Messages published during the outage are gone**, routed to queues that did
  not exist at the time and dropped by the exchange without an error on either
  side. Nothing that was already delivered is lost.

So a reboot costs a few minutes and no state. Schedule it between sessions
anyway — a student mid-exercise cannot tell your reboot apart from their own
code breaking, and will spend the gap debugging something that is not wrong.

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

**Nothing came back after a reboot.** Either `dockerd` is not enabled at boot
(`systemctl is-enabled docker`) or the containers had been removed by an earlier
`docker compose down`, in which case no restart policy can help and `up -d` is
the fix. [Rehearsing a reboot](#rehearsing-a-reboot) is how you find out which
before it matters.

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
