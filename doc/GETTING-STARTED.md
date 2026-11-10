# Getting started

This guide takes you from an empty laptop to a running chat agent, step by
step, on **Windows** or **Linux** (with notes for **macOS** where it differs
from Linux). It assumes no prior knowledge of the platform.

## What you will end up with

The platform runs as two halves:

- a **server**, which does the heavy work (speech recognition, the dialogue
  engine, storing conversations), and
- a **tenant**, your own personal part: the chat window in your browser and
  everything around it.

You can set this up in two ways:

- **A. Everything on your laptop** — a local server *and* a local tenant.
  Works offline, but needs a reasonably strong laptop.
- **B. Only the tenant on your laptop**, connected to the course's server on
  the internet. Lighter, but needs the connection details from your course
  staff.

This guide first sets up **A**, then shows the few changes that turn it into
**B**. If your laptop cannot run A (see [Requirements](#1-requirements)), skip
the server: do the first two steps of [4.2](#42-start-the-tenant) (copy the
configuration, switch to text-only), but instead of starting the tenant there,
go straight on to [scenario B, 5.3](#53-change-the-tenants-configuration).

---

## Contents

1. [Requirements](#1-requirements)
2. [Install the prerequisites](#2-install-the-prerequisites)
3. [Get the code](#3-get-the-code)
4. [Scenario A: local server + local tenant](#4-scenario-a-local-server--local-tenant)
5. [Scenario B: connect your tenant to the course server](#5-scenario-b-connect-your-tenant-to-the-course-server)
6. [Replacing ELIZA with your own module](#6-replacing-eliza-with-your-own-module)
7. [Optional: microphone and camera](#7-optional-microphone-and-camera)
8. [Everyday use: stop, start, update, remove](#8-everyday-use-stop-start-update-remove)
9. [Troubleshooting](#9-troubleshooting)

---

## 1. Requirements

| | **B: tenant only** | **A: server + tenant** |
|---|---|---|
| Operating system | Windows 10/11 (64-bit), Ubuntu 22.04/24.04, or macOS 13+ | same |
| Memory (RAM) | 4 GB (8 GB on Windows/macOS) | **8 GB** minimum, 16 GB recommended |
| Free disk space | 5 GB | **15 GB** |
| CPU | any 64-bit CPU from the last ~8 years | 4 cores or more |
| Internet | during installation, **and** all the time while you use it | during installation only |
| Free ports on your laptop | 8003, 8005, 9001 | additionally 5672, 15672, 8001, 8002 |

For reference, measured on a running installation: the tenant uses about
0.2 GB of memory and 1 GB of disk; the server adds about 1 GB of memory and
4.5 GB of disk. On Windows and macOS, Docker itself runs in a virtual machine
that takes another 1–2 GB of memory on top of that.

**Not sure?** Try A. If the server half fails to start or your laptop becomes
unusably slow, switch to B.

---

## 2. Install the prerequisites

You need two programs: **Docker** (runs the platform) and **Git** (downloads
it). Follow the section for your operating system, and finish with the check
at the end of it.

### Windows 10/11

1. **Turn on virtualisation.** Open *Task Manager* → *Performance* → *CPU* and
   check that *Virtualization* says *Enabled*. If it says *Disabled*, enable it
   in your laptop's BIOS/UEFI settings (search the web for your laptop model
   plus "enable virtualization").
2. **Install WSL2.** Open *PowerShell as Administrator* (right-click the Start
   button → *Terminal (Admin)*) and run:
   ```powershell
   wsl --install
   ```
   Restart your laptop when asked.
3. **Install Docker Desktop** from <https://www.docker.com/products/docker-desktop/>.
   During installation keep *Use WSL 2 instead of Hyper-V* checked. Start
   Docker Desktop afterwards and wait until it says *Engine running*. Docker
   Desktop must be running every time you use the platform.
4. **Install Git for Windows** from <https://git-scm.com/download/win>. The
   default options are fine.
5. **Check.** Open a new, normal *PowerShell* window (not as Administrator)
   and run:
   ```powershell
   docker run --rm hello-world
   git --version
   ```
   You should see *Hello from Docker!* and a Git version number.

All commands in this guide are run in **PowerShell** on Windows itself, not
inside a WSL/Ubuntu window.

### Linux (Ubuntu 22.04 / 24.04)

1. **Install Docker Engine** with the Compose plugin, from Docker's own
   package repository (Ubuntu's own `docker.io` package is often too old):
   ```bash
   sudo apt-get update
   sudo apt-get install -y ca-certificates curl git
   sudo install -m 0755 -d /etc/apt/keyrings
   sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
   echo "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
     https://download.docker.com/linux/ubuntu $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
     | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null
   sudo apt-get update
   sudo apt-get install -y docker-ce docker-ce-cli containerd.io docker-buildx-plugin docker-compose-plugin
   ```
   On another distribution, follow <https://docs.docker.com/engine/install/>
   and install `git` with your package manager.
2. **Allow yourself to use Docker without `sudo`:**
   ```bash
   sudo usermod -aG docker "$USER"
   ```
   Then **log out and log back in** (or restart). This is easy to forget, and
   without it every `docker` command says *permission denied*.
3. **Check:**
   ```bash
   docker run --rm hello-world
   docker compose version
   git --version
   ```
   You should see *Hello from Docker!*, a Compose version (v2.x or newer) and
   a Git version.

### macOS

Follow the Linux steps for everything in this guide, with these differences:

- Install **Docker Desktop** from <https://www.docker.com/products/docker-desktop/>
  (pick *Apple Silicon* or *Intel* to match your Mac) instead of step 1–2
  above, and start it. It must be running whenever you use the platform.
- Git comes with Apple's command-line tools: run `git --version` in
  *Terminal* and accept the offer to install them.
- In Docker Desktop → *Settings* → *Resources*, give Docker at least 8 GB of
  memory if you want to run scenario A.

---

## 3. Get the code

Pick a folder for your work, for example your home folder, and download the
code **twice**: one copy for the server, one for the tenant. They are
configured differently, so they must be separate folders.

**Linux / macOS:**
```bash
cd ~
git clone https://github.com/leolani/cltl-apps.git cltl-apps-server
git clone https://github.com/leolani/cltl-apps.git cltl-apps-tenant
```

**Windows (PowerShell):**
```powershell
cd ~
git clone https://github.com/leolani/cltl-apps.git cltl-apps-server
git clone https://github.com/leolani/cltl-apps.git cltl-apps-tenant
```

If you will only ever use scenario B, you may skip the `cltl-apps-server`
copy.

---

## 4. Scenario A: local server + local tenant

### 4.1 Start the server

Go into the server folder and copy the server configuration into place:

**Linux / macOS:**
```bash
cd ~/cltl-apps-server
cp templates/common/config/* templates/server/config/* config/
```

**Windows (PowerShell):**
```powershell
cd ~\cltl-apps-server
Copy-Item templates\common\config\*, templates\server\config\* config\
```

Then start it. The first start downloads about 5 GB, so expect it to take
5–15 minutes:

**Linux / macOS:**
```bash
docker compose --env-file config/server.env \
    -f modules/event-bus/docker-compose.yml \
    -f modules/backend/docker-compose.yml \
    -f modules/eliza/docker-compose.yml \
    -f modules/vad-asr/docker-compose.yml \
    -f modules/emissor/docker-compose.yml up -d --wait --pull always
```

**Windows (PowerShell, one line):**
```powershell
docker compose --env-file config/server.env -f modules/event-bus/docker-compose.yml -f modules/backend/docker-compose.yml -f modules/eliza/docker-compose.yml -f modules/vad-asr/docker-compose.yml -f modules/emissor/docker-compose.yml up -d --wait --pull always
```

**Expected:** a list of containers ending in *Healthy*.

> **On the very first start** the command may end with
> `container cltl-platform-eliza-asr-1 is unhealthy`. That is the speech
> recogniser still downloading its model (about 140 MB). Wait a minute and run
> **the same command again**; it then finishes with everything *Healthy*. This
> only happens once — the model is kept in `storage/cache/`.

### 4.2 Start the tenant

Go into the tenant folder and copy the tenant configuration into place:

**Linux / macOS:**
```bash
cd ~/cltl-apps-tenant
cp templates/common/config/* templates/tenant/config/* config/
```

**Windows (PowerShell):**
```powershell
cd ~\cltl-apps-tenant
Copy-Item templates\common\config\*, templates\tenant\config\* config\
```

We start **text-only** — typing, no microphone or camera ([section 7](#7-optional-microphone-and-camera)
adds those later). Open `config/custom.config` in a text editor
(Windows: `notepad config\custom.config`; Linux: `nano config/custom.config`
or any editor; macOS: `open -e config/custom.config`). Near the end of the
file, find these lines:

```ini
# [cltl.backend.mic]
# topic:
#
# [cltl.backend.image]
# topic:
# rate: 0
```

and remove the `# ` at the start of each of them, so they read:

```ini
[cltl.backend.mic]
topic:

[cltl.backend.image]
topic:
rate: 0
```

Save the file, then start the tenant:

**Linux / macOS:**
```bash
docker compose --env-file config/tenant.env \
    -f modules/backend/docker-compose.yml \
    -f modules/context/docker-compose.yml \
    -f modules/chat-ui/docker-compose.yml \
    -f modules/monitoring/docker-compose.yml up -d --wait --pull always
```

**Windows (PowerShell, one line):**
```powershell
docker compose --env-file config/tenant.env -f modules/backend/docker-compose.yml -f modules/context/docker-compose.yml -f modules/chat-ui/docker-compose.yml -f modules/monitoring/docker-compose.yml up -d --wait --pull always
```

**Expected:** four containers (`backend`, `context`, `chatui`, `monitoring`),
all *Healthy*.

### 4.3 Open the chat

Open <http://localhost:8003/chatui/static/chat.html> in your browser.

**Expected:** after a few seconds the agent greets you with something like
*"Hello! Do you want to talk to me?"*

If you type an answer now, **you will not get a reply**. That is correct: the
server's dialogue engine, ELIZA, answers on a separate channel (`eliza_out`)
so that it can be replaced by your own module (see [section 6](#6-replacing-eliza-with-your-own-module)).
Your installation works if you see the greeting.

### 4.4 See ELIZA answer

To see ELIZA's replies in the chat, tell the chat window to show them too.
Open the tenant's `config/custom.config` again and add these two lines at the
very end:

```ini
[cltl.chat-ui.events]
topic_response: cltl.topic.text_out, cltl.topic.eliza_out
```

(If the file already contains an *uncommented* `[cltl.chat-ui.events]` line,
add only the `topic_response` line below it instead, to keep the file easy to
read.)

Save, and restart the tenant — the same command as in 4.2, with `restart` in
place of `up -d --wait --pull always`:

**Linux / macOS:**
```bash
docker compose --env-file config/tenant.env \
    -f modules/backend/docker-compose.yml \
    -f modules/context/docker-compose.yml \
    -f modules/chat-ui/docker-compose.yml \
    -f modules/monitoring/docker-compose.yml restart
```

**Windows (PowerShell, one line):**
```powershell
docker compose --env-file config/tenant.env -f modules/backend/docker-compose.yml -f modules/context/docker-compose.yml -f modules/chat-ui/docker-compose.yml -f modules/monitoring/docker-compose.yml restart
```

Wait about 20 seconds and reload the chat page.

**Expected:** the greeting, and then an answer to everything you type. Reply
*yes* to the greeting first; ELIZA then answers, for example *"I feel a bit
tired today"* → *"When you feel a bit tired today, what do you do?"*

You now have a complete working installation. 🎉

---

## 5. Scenario B: connect your tenant to the course server

Scenario B is your tenant from scenario A, pointed at the course server
instead of the server on your laptop. If you skipped scenario A, copy the
tenant configuration and switch it to text-only as in [4.2](#42-start-the-tenant),
then continue at 5.3 — and in 5.4 you only need the second (`up`) command.

### 5.1 What you need from your course staff

| Placeholder in this guide | What it is | Example shape |
|---|---|---|
| `<tenant-id>` | your personal id, lowercase letters, digits, `-` or `_` | `student-17` |
| `<amqps-url>` | your connection to the server's message bus | `amqps://...@<server-host>:5671/` |
| `<server-host>` | the server's name | `combot.example.org` |
| `<storage-user>`, `<storage-password>` | the login for the server's storage | |

Two rules:

- **Your tenant id must be your own.** Two people using the same id see each
  other's conversations.
- **These are passwords.** Don't commit them to git, post them in a chat, or
  share screenshots of your `config/custom.config`. (`config/` is already
  excluded from git in this repository.)

### 5.2 Stop the local server

If you ran scenario A, stop the server first — you do not need it any more,
and it saves memory. In the server folder, run the server command from 4.1
with `down` in place of `up -d --wait --pull always`:

**Linux / macOS:**
```bash
cd ~/cltl-apps-server
docker compose --env-file config/server.env \
    -f modules/event-bus/docker-compose.yml \
    -f modules/backend/docker-compose.yml \
    -f modules/eliza/docker-compose.yml \
    -f modules/vad-asr/docker-compose.yml \
    -f modules/emissor/docker-compose.yml down
```

**Windows (PowerShell, one line):**
```powershell
cd ~\cltl-apps-server
docker compose --env-file config/server.env -f modules/event-bus/docker-compose.yml -f modules/backend/docker-compose.yml -f modules/eliza/docker-compose.yml -f modules/vad-asr/docker-compose.yml -f modules/emissor/docker-compose.yml down
```

### 5.3 Change the tenant's configuration

Open `config/custom.config` in the **tenant** folder. Near the top you will
find the settings that point at your local server. Change **only the
values**, in place, rather than adding new lines elsewhere in the file.

| In section | Change this line | To |
|---|---|---|
| `[cltl.event.kombu]` | `tenant: tenant-a` | `tenant: <tenant-id>` |
| `[cltl.event.kombu]` | `server: amqp://eliza:eliza123@host.docker.internal:5672/` | `server: <amqps-url>` |
| `[cltl.backend]` | `storage_url: http://host.docker.internal:8001/storage/` | `storage_url: https://<storage-user>:<storage-password>@<server-host>/storage/` |
| `[cltl.backend.remote_storage]` | `storage_url: http://host.docker.internal:8001/storage` | `storage_url: https://<storage-user>:<storage-password>@<server-host>/storage` |

Note the two storage lines differ: the first ends in `/storage/`, the second
in `/storage` without the slash. Copy them exactly.

Afterwards the top of the file looks like this (with your own values):

```ini
[cltl.event.kombu]
tenant: student-17
server: amqps://student-17:s3cr3t@combot.example.org:5671/

[cltl.backend]
storage_url: https://storage-user:pa55word@combot.example.org/storage/
audio_storage: remote
image_storage: remote

[cltl.backend.remote_storage]
storage_url: https://storage-user:pa55word@combot.example.org/storage
```

Leave everything else as it is — including the text-only lines and the
`[cltl.chat-ui.events]` lines from scenario A.

### 5.4 Restart the tenant

In the tenant folder, stop and start it again (two commands):

**Linux / macOS:**
```bash
cd ~/cltl-apps-tenant
docker compose --env-file config/tenant.env \
    -f modules/backend/docker-compose.yml \
    -f modules/context/docker-compose.yml \
    -f modules/chat-ui/docker-compose.yml \
    -f modules/monitoring/docker-compose.yml down
docker compose --env-file config/tenant.env \
    -f modules/backend/docker-compose.yml \
    -f modules/context/docker-compose.yml \
    -f modules/chat-ui/docker-compose.yml \
    -f modules/monitoring/docker-compose.yml up -d --wait --pull always
```

**Windows (PowerShell, two lines):**
```powershell
cd ~\cltl-apps-tenant
docker compose --env-file config/tenant.env -f modules/backend/docker-compose.yml -f modules/context/docker-compose.yml -f modules/chat-ui/docker-compose.yml -f modules/monitoring/docker-compose.yml down
docker compose --env-file config/tenant.env -f modules/backend/docker-compose.yml -f modules/context/docker-compose.yml -f modules/chat-ui/docker-compose.yml -f modules/monitoring/docker-compose.yml up -d --wait --pull always
```

**Expected:** all four containers *Healthy*. Open
<http://localhost:8003/chatui/static/chat.html>: you get the greeting, and —
because you kept the `[cltl.chat-ui.events]` lines from 4.4 — ELIZA's answers
from the course server. Without those lines you get the greeting only, exactly
as in 4.3.

If a container is *unhealthy*, see [Troubleshooting](#9-troubleshooting).

**Going back to scenario A** is the same change in reverse: put the four
original values back (they are also in `templates/tenant/config/custom.config`),
start the local server, and restart the tenant.

---

## 6. Replacing ELIZA with your own module

ELIZA is a stand-in. The platform is built so that you can replace the
agent's replies with your own code:

- The chat window shows whatever is sent on the **`cltl.topic.text_out`**
  channel. Your module listens to what the user says, on
  **`cltl.topic.text_in`**, and sends its reply on `cltl.topic.text_out`.
- ELIZA's own reply keeps arriving on **`cltl.topic.eliza_out`**. Your module
  may listen to it too, for example to use, rewrite or ignore ELIZA's
  suggestion.
- When your module answers, **remove** the `[cltl.chat-ui.events]` lines you
  added in 4.4 and restart the tenant, so that the chat window shows your
  module's reply only, not ELIZA's as well.
- In **scenario A** you can also turn ELIZA off entirely: leave the line
  `-f modules/eliza/docker-compose.yml` out of the server command in 4.1
  (stop the server with `down` first, using the full command *with* that
  line). In scenario B ELIZA keeps running on the course server; it simply
  goes unseen once you removed the lines from 4.4.

How to write such a module — in a Jupyter notebook, as a Python script or as
a container — is explained in [`custom-module/`](../custom-module/README.md).
It connects to a running installation from this guide, scenario A or B.

---

## 7. Optional: microphone and camera

To talk instead of type, you run one extra program on your laptop itself
(not in Docker): a small server that gives the platform access to your
microphone, camera and speakers.

### 7.1 Undo the text-only switch

In the tenant's `config/custom.config`, put the `# ` back in front of the six
lines you uncommented in 4.2 (or delete those lines). Leave the file otherwise
as it is.

### 7.2 Install what the microphone server needs

**Windows:**

1. Install **Python 3.10, 3.11, 3.12 or 3.13** from <https://www.python.org/downloads/windows/>
   (not 3.14 — the audio library has no ready-made version for it yet). Keep
   the option *py launcher* checked.
2. Git for Windows is already installed (section 2) — it is needed here too.
3. Settings → *Privacy & security* → *Microphone*, and again → *Camera*: turn
   on **Let desktop apps access your microphone / camera**.
4. Check that port 8000 is not reserved by Windows:
   ```powershell
   netsh int ipv4 show excludedportrange protocol=tcp
   ```
   If any range listed includes 8000, see [Troubleshooting](#9-troubleshooting).

**Linux (Ubuntu):**
```bash
sudo apt-get install -y python3-venv python3-dev portaudio19-dev build-essential
```

**macOS:**
Install [Homebrew](https://brew.sh/) if you do not have it, then:
```bash
brew install python portaudio
```

### 7.3 Start the microphone server

From the **tenant** folder. The first start installs its software into
`modules/backend/venv/` and takes a few minutes; later starts are quick.

**Linux / macOS** (in a terminal you keep open):
```bash
cd ~/cltl-apps-tenant
./modules/backend/run_host_server.sh
```

**Windows (PowerShell)** — opens it in its own window:
```powershell
cd ~\cltl-apps-tenant
start "leoserv" modules\backend\run_host_server.cmd
```

On **Windows**, allow it when the firewall asks. On **macOS**, allow
*Terminal* to use the microphone and camera when asked (or later in System
Settings → *Privacy & Security*). On a laptop without a camera, the
microphone server stops right away — the camera is required.

Keep this program running whenever you use voice. Stop it with *Ctrl+C* (or
by closing its window on Windows).

### 7.4 Restart the tenant

Run the `restart` command from 4.4 in the tenant folder. Reload the chat page
and speak: what you say appears in the chat as text, and the replies are read
out loud.

**ELIZA's spoken replies.** The chat window can show several channels, but the
speaker can only follow one. To hear ELIZA's answers (instead of only reading
them), add this to the tenant's `config/custom.config` and restart the tenant
again:

```ini
[cltl.backend.tts]
topic: cltl.topic.eliza_out
```

Remove it again once your own module replies on `cltl.topic.text_out`.

---

## 8. Everyday use: stop, start, update, remove

All commands below use the long `docker compose …` command for the folder you
are in: the server command from 4.1 in the server folder, the tenant command
from 4.2 in the tenant folder. Only the last words change. In scenario A, start
the server before the tenant, and stop the tenant before the server.

| To | End the command with |
|---|---|
| **Stop** (keeps your data) | `down` |
| **Start** again | `up -d --wait` |
| **Restart** after a configuration change | `restart` |
| See what is running | `ps` |
| See the log of one part, e.g. the chat | `logs chatui` (or `backend`, `context`, `monitoring`; on the server `rabbitmq`, `eliza-eliza`, `eliza-asr`, `eliza-vad`, `eliza-emissor`) |

Your Docker installation keeps running in the background; on Windows and
macOS you can quit Docker Desktop when you are done to free memory.

**Update** to the latest version, in each folder:

```bash
git pull
```

then start with `up -d --wait --pull always`. `git pull` never touches your
`config/` folder, so your settings stay. If the update notes tell you a
setting changed, compare your `config/custom.config` with the matching
`templates/<server|tenant>/config/custom.config`.

**Remove everything:** in each folder run the command with `down -v`, then
delete both folders. On **Linux**, the platform's files in `storage/` belong to
the system administrator, so delete the folders with
`sudo rm -rf ~/cltl-apps-server ~/cltl-apps-tenant`. Finally, free Docker's
disk space with:

```bash
docker image prune -a
```

(That removes *all* Docker images not in use, also ones from other projects.)

---

## 9. Troubleshooting

| What you see | Why | What to do |
|---|---|---|
| `container cltl-platform-eliza-asr-1 is unhealthy` on the first server start | The speech model is still downloading | Wait a minute and run the same `up` command again |
| The chat page loads but no greeting appears | The tenant is not connected to a server, or the server is not running | Check `ps` in both folders (A) or your settings in 5.3 (B). Then `restart` the tenant |
| Greeting appears, but no answers | ELIZA answers on `eliza_out`, which the chat window does not show by default | See [4.4](#44-see-eliza-answer) |
| Answers stop after a while | The conversation was ended (typing *Bye* ends it) | Reload the chat page |
| `permission denied ... /var/run/docker.sock` (Linux) | You are not in the `docker` group yet | Do step 2 of the Linux prerequisites, then log out and in |
| `Cannot connect to the Docker daemon` / `docker: command not found` | Docker (Desktop) is not running | Start Docker Desktop and wait for *Engine running* |
| Docker Desktop: *WSL 2 installation is incomplete* or *virtualization not enabled* | WSL2 or virtualisation is missing | Steps 1–2 of the Windows prerequisites |
| `Bind for 0.0.0.0:8003 failed: port is already allocated` (or another port) | Another program, or a second copy of the platform, uses that port | Stop the other program, or check `docker ps` for old containers and stop them |
| **B:** `context` stays *unhealthy*; `logs chatui` says `ACCESS_REFUSED` | Wrong `<amqps-url>`: a typo in the password, or your tenant id does not match it | Copy the URL and tenant id again from what the staff gave you; then `down` and `up` |
| **B:** log says `certificate verify failed` or `hostname mismatch` | The URL uses an IP address instead of the server's name | Use `<server-host>` as given, never an IP |
| **B:** image upload fails, or a log mentions `401` | Wrong storage user or password in the two `storage_url` lines | Check both lines in 5.3 |
| **Windows, voice:** *An attempt was made to access a socket in a way forbidden by its access permissions* | Windows reserved port 8000 | In *PowerShell as Administrator*: `net stop winnat`, start the microphone server, then `net start winnat` |
| **Voice:** the microphone server exits right after starting | No camera found, or no permission for the camera/microphone | Check the privacy settings in 7.2/7.3; a camera is required |
| `no space left on device` | Docker's disk is full | Free space with `docker system prune`, or (Windows/macOS) increase the disk in Docker Desktop → *Settings* → *Resources* |

Still stuck? Collect the output of `ps` and `logs <part>` for the folder that
misbehaves, and ask your course staff — leave your passwords out.

Want to know more about how the platform is put together? See
[`DEPLOYMENT.md`](DEPLOYMENT.md) and [`LEOLANI.md`](LEOLANI.md).
