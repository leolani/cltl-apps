import logging

from cltl.combot.infra.container import InfraContainer
from cltl.combot.infra.di_container import singleton

from myorg.example.api import Example
from myorg.example.echo import EchoExample
from myorg.example.service import ExampleService

logger = logging.getLogger(__name__)


class ExampleContainer(InfraContainer):
    """Wires an :class:`Example` and its :class:`ExampleService` into a deployment.

    Both accessors are prefixed with `example_` rather than left bare
    (`service`, `impl`). @singleton (cltl.combot.infra.di_container) keys its
    cache by the BARE method name across the whole process, so an unprefixed
    accessor collides the moment this container is mixed into a deployment
    alongside another component that also defines `service`.

    [myorg.example] is mandatory here — this component's only job is running
    it — so there is no `False`-sentinel optionality to guard, unlike e.g.
    cltl-monitoring/src/cltl_service/monitoring/container.py's
    `monitoring_store`, which IS optional and is the pattern to copy if you
    make this component optional in your own deployment.
    """

    @property
    @singleton
    def example(self) -> Example:
        return EchoExample()

    @property
    @singleton
    def example_service(self) -> ExampleService:
        return ExampleService.from_config(self.example, self.event_bus,
                                          self.resource_manager, self.config_manager)

    def start(self):
        logger.info("Start Example")
        super().start()
        self.example_service.start()

    def stop(self):
        logger.info("Stop Example")
        self.example_service.stop()
        super().stop()
