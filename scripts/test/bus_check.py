"""End-to-end check of a server installed by scripts/install-server.sh.

Run by scripts/test/run.sh from outside the "VM", against its AMQPS port:

    python bus_check.py <vm-ip> <hostname> <ca.pem> <tenants.urls>

Needs kombu and cltl.combot importable (run.sh puts cltl-dev/cltl-combot/src
on PYTHONPATH, so the KombuEventBus under test is the source, not a release).
<hostname> is mapped to <vm-ip> inside this process only.
"""
import socket
import ssl
import sys
import threading
import uuid

import kombu
from amqp.exceptions import AccessRefused

vm_ip, hostname, ca_file, urls_file = sys.argv[1:5]

_getaddrinfo = socket.getaddrinfo


def _resolve(host, *args, **kwargs):
    return _getaddrinfo(vm_ip if host == hostname else host, *args, **kwargs)


socket.getaddrinfo = _resolve

urls = {}
with open(urls_file) as f:
    for line in f:
        if line.strip() and not line.startswith("#"):
            tenant, url = line.split()
            urls[tenant] = url

failures = []


def check(name, fn):
    try:
        fn()
        print(f"PASS {name}")
    except Exception as e:  # noqa: BLE001 - report every failure
        print(f"FAIL {name}: {type(e).__name__}: {e}")
        failures.append(name)


def ssl_options():
    return {"server_hostname": None, "cert_reqs": ssl.CERT_REQUIRED, "ca_certs": ca_file}


def event_bus(url, tenant):
    from cltl.combot.infra.event.kombu import KombuEventBus

    values = {"server": url, "exchange": "cltl.combot", "compression": "bzip2",
              "tenant": tenant, "ssl_ca_certs": ca_file}

    class Config:
        def get(self, key):
            return values[key]

        def __contains__(self, key):
            return key in values

    class ConfigManager:
        def get_config(self, name):
            return Config()

    from kombu.serialization import register
    from cltl.combot.infra.event.kombu import _serialize_with_custom_func, _deserialize_with_custom_func
    register("cltl-json", _serialize_with_custom_func, _deserialize_with_custom_func,
             content_type="application/json", content_encoding="utf-8")

    return KombuEventBus("cltl-json", ConfigManager())


def round_trip(tenant, url):
    from cltl.combot.infra.event.api import Event

    def run():
        bus = event_bus(url, tenant)
        received = threading.Event()
        topic = f"cltl.test.ping{uuid.uuid4().hex[:6]}"
        bus.subscribe(topic, lambda event: received.set())
        try:
            for _ in range(20):
                bus.publish(topic, Event.for_payload({"hello": tenant}))
                if received.wait(0.5):
                    return
            raise AssertionError("published event never came back")
        finally:
            bus.close()

    return run


def refused(url, action):
    def run():
        with kombu.Connection(url, ssl=ssl_options()) as conn:
            channel = conn.channel()
            exchange = kombu.Exchange("cltl.combot", type="topic")
            try:
                if action == "publish":
                    kombu.Producer(channel, exchange).publish({}, routing_key="cltl.test.x.someone-else",
                                                              declare=[exchange])
                    # Topic-permission failures close the channel asynchronously.
                    channel.basic_qos(0, 1, False)
                else:
                    queue = kombu.Queue("", exchange, routing_key="#", exclusive=True)
                    queue(channel).declare()
            except AccessRefused:
                return
        raise AssertionError(f"{action} on a foreign routing key was allowed")

    return run


def wrong_hostname(url):
    def run():
        ip_url = url.replace(f"@{hostname}:", f"@{vm_ip}:")
        try:
            with kombu.Connection(ip_url, ssl=ssl_options(), connect_timeout=5) as conn:
                conn.connect()
        except ssl.SSLCertVerificationError:
            return
        raise AssertionError("connected to an IP the certificate does not name")

    return run


def plain_amqp_closed():
    try:
        socket.create_connection((vm_ip, 5672), timeout=3).close()
    except OSError:
        return
    raise AssertionError("plain AMQP 5672 is reachable from outside")


per_tenant = {t: u for t, u in urls.items() if t != "tenant"}
for tenant, url in urls.items():
    bus_tenant = "tenant-x" if tenant == "tenant" else tenant
    check(f"{tenant}: publish and receive over AMQPS", round_trip(bus_tenant, url))
for tenant, url in per_tenant.items():
    check(f"{tenant}: publish on another tenant's key is refused", refused(url, "publish"))
    check(f"{tenant}: binding '#' is refused", refused(url, "bind"))
check("hostname verification rejects a certificate for another name", wrong_hostname(next(iter(urls.values()))))
check("plain AMQP is not reachable", plain_amqp_closed)

sys.exit(1 if failures else 0)
