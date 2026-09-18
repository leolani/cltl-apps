# ma-combot-2026

The course deployment for one term: a permanently running Leolani server that a
class of students attaches to from their own laptops, using the
[`custom-module`](../custom-module) template.

This directory is **the deployment and its operations**, not the teaching
material. The exercise students actually do — the notebook, the script, the
component, the ten documents explaining how any of it works — is `custom-module`,
unchanged. Students copy that repository as they normally would; what this
directory adds is a server for them to point it at, one credential each, and the
handful of documents that say how the two fit together.

## Who runs what

| | Runs | Where |
|---|---|---|
| **Instructor** | `server.compose.yml` — broker, image store, one shared ELIZA, Caddy | one host, permanently |
| **Student** | `student/compose.yml` — their own chat UI | their own laptop |
| **Student** | `custom-module/attach/example.ipynb` or `listen.py` | their own laptop |

Four containers on the server, for any class size. Everything that is per-student
is per-student *on their machine* — which is what keeps the chat UI, which has
neither a login nor a per-browser session, off the public internet.

## Start here

| | |
|---|---|
| [`docs/operator.md`](docs/operator.md) | Standing the server up, and running it for a term |
| [`docs/student.md`](docs/student.md) | What a student does, start to finish |
| [`docs/known-issues.md`](docs/known-issues.md) | Symptoms that are expected here and not in the template |
| [`docs/plans/classroom-deployment.md`](docs/plans/classroom-deployment.md) | Why every part of this is shaped as it is |

## What is deliberately not protected

Students can read each other's conversations, publish into each other's tenants,
and fetch each other's uploaded images. That is not an oversight — it is the
template's own architecture, stated plainly in
[`custom-module/docs/tenancy.md`](../custom-module/docs/tenancy.md): separation
here is *cooperative, not enforced*, and enforcing it would break the notebook
cell that demonstrates how the isolation works at all.

What replaces enforcement is **attribution**. Every student has their own broker
user and their own storage credential, so every connection and every request
carries a name. Tell the class both halves of that.

The class is trusted. The internet is not: nothing here is reachable without a
credential, and the two ports that are open are TLS.

## Naming

Named for the term it serves rather than for what it contains, unlike its
siblings. A later term gets its own directory rather than a migration — the
pinned image tag, the roster and the credentials all belong to one cohort.
