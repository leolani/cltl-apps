import logging.config
import os
import signal

from cltl.combot.event.emissor import SIG, MEN
from cltl.combot.infra.config.k8config import K8LocalConfigurationContainer
from cltl.combot.infra.di_container import singleton
from cltl.combot.infra.event.api import Event, PAYLOAD
from cltl.combot.infra.event.memory import SynchronousEventBus
from myorg.example.container import ExampleContainer
from myorg.tenant.container import TenantContainer
from emissor.representation.util import marshal, unmarshal, register_type_var
from flask import Flask
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.serving import run_simple

# Top-level module, deliberately: find_namespace_packages(include=['myorg.*'])
# in setup.py does not match a bare `main`, so this file is never part of the
# installed distribution. Only the container image (CMD ["python", "src/main.py"])
# and a developer running it directly ever execute it — see docs/component.md.

logging.config.fileConfig(os.environ.get('CLTL_LOGGING_CONFIG', 'config/logging.config'),
                          disable_existing_loggers=False)
logger = logging.getLogger(__name__)

# Must happen before anything marshals an Event, or emissor cannot resolve the
# generic type variables and raises `TypeError: PAYLOAD is not a dataclass`.
register_type_var(PAYLOAD)
register_type_var(SIG)
register_type_var(MEN)


def serializer(obj):
    return marshal(obj, cls=Event)


def deserializer(obj):
    return unmarshal(obj, cls=Event)


class ApplicationContainer(TenantContainer, ExampleContainer):
    """This deployment: the component, plus the scenario a tenant needs.

    `TenantContainer` comes FIRST, and the reason is start ordering rather than
    the event bus. Start order is the reverse of the bases tuple, so:

        TenantContainer.start -> super().start() -> ExampleContainer.start
            -> super().start() (infra) -> example_service.start()
        -> back in TenantContainer: tenant_service.start()

    i.e. `ScenarioStarted` is published LAST, once this process's own subscriber
    is up, and `stop()` mirrors it — `ScenarioStopped` goes out FIRST, while the
    bus is still alive. Swapping the bases would announce the scenario before
    `ExampleService` had subscribed; harmless today, since nothing here consumes
    the scenario topic, but the wrong thing to teach.

    The separate rule that the bus-selecting base must come first applies to a
    container synthesised with an EMPTY class body — see `HarnessInfraContainer`
    in integration/src/cltl_integration/runner/inprocess.py, which explains why
    (`KombuEventBusContainer.event_bus` is a plain, non-@singleton property, so
    whichever base reaches it first through the MRO decides). Here `event_bus`
    is defined in this class's own body, so it wins over every base regardless
    of their order.

    `myorg.tenant` is not part of this component and is meant to be deleted —
    see myorg/tenant/scenario.py and docs/tenancy.md. Deleting it means dropping
    `TenantContainer` from the bases above and nothing else; `ExampleContainer`
    has no knowledge of it.
    """

    @property
    @singleton
    def event_bus_serializer(self):
        return serializer, deserializer

    @property
    @singleton
    def event_bus(self):
        config = self.config_manager.get_config("cltl.event")
        if config.get("implementation") == "internal":
            return SynchronousEventBus()
        return super().event_bus


def main():
    K8LocalConfigurationContainer.load_configuration()
    application = ApplicationContainer()

    # `docker compose down` and `docker stop` send SIGTERM, whose DEFAULT
    # disposition terminates the process outright — so `with application:`
    # would never reach its __exit__, TenantContainer.stop would never run, and
    # ScenarioStopped would never be published. The tenant's chat UI would be
    # left holding a scenario whose owner is gone. (cltl-context/src/main.py has
    # the identical latent bug.) Turning the signal into KeyboardInterrupt makes
    # it unwind through the `with` like a Ctrl-C does.
    def _interrupt(signum, frame):
        logger.info("Received signal %s; shutting down", signum)
        raise KeyboardInterrupt()

    signal.signal(signal.SIGTERM, _interrupt)

    with application:
        flask_app = Flask(__name__)

        @flask_app.route('/health')
        def health():
            return 'OK', 200

        try:
            run_simple('0.0.0.0', 8000, DispatcherMiddleware(flask_app),
                       threaded=True, use_reloader=False, use_debugger=False)
        except KeyboardInterrupt:
            # Caught here rather than relying on werkzeug: its
            # BaseWSGIServer.serve_forever does swallow KeyboardInterrupt, but
            # that is an implementation detail of a pinned version, and the cost
            # of not depending on it is one except clause.
            pass


if __name__ == '__main__':
    main()
