# Module template

`custom-module/` at the repository root is the full worked example for
attaching your own code to a running Leolani deployment — it isn't "a
deployment" the way the server/client templates above are, so there's no
config bundle here to copy into a checkout's `config/`.

See [`../custom-module/README.md`](../custom-module/README.md) to get
started. Its `config/custom.config.example` is the copy-and-edit starting
point for the connection settings (`CLTL_AMQP_URL`, `CLTL_STORAGE_URL`,
`CLTL_TENANT`) needed to attach to an already-running server and client.
