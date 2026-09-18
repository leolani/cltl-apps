import logging

from cltl.combot.infra.container import InfraContainer
from cltl.combot.infra.di_container import singleton

from myorg.example.api import Example, ImageExample
from myorg.example.echo import EchoExample
from myorg.example.imagesize import ImageSizeExample
from myorg.example.service import ExampleService

logger = logging.getLogger(__name__)


class ExampleContainer(InfraContainer):
    """Wires an :class:`Example` and its :class:`ExampleService` into a deployment.

    Every accessor is prefixed — `example`, `example_service`, `image_example`
    — rather than left bare (`service`, `impl`, `image`). @singleton
    (cltl.combot.infra.di_container) keys its cache by the BARE method name
    across the whole process, so an unprefixed accessor collides the moment
    this container is mixed into a deployment alongside another component that
    also defines `service`. `image` in particular would collide with more than
    one platform component.

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
    def image_example(self) -> ImageExample:
        # Not optional and not guarded: `ExampleService.from_config` decides
        # whether the image half runs at all, from [myorg.example] topic_image,
        # and constructing a placeholder that is never called costs nothing. A
        # component whose implementation IS optional returns the `False`
        # sentinel instead — @singleton cannot return None; see
        # cltl-monitoring/src/cltl_service/monitoring/container.py's
        # `monitoring_store`.
        return ImageSizeExample()

    @property
    @singleton
    def example_service(self) -> ExampleService:
        return ExampleService.from_config(self.example, self.image_example, self.event_bus,
                                          self.resource_manager, self.config_manager)

    def start(self):
        logger.info("Start Example")
        super().start()
        self.example_service.start()

    def stop(self):
        logger.info("Stop Example")
        self.example_service.stop()
        super().stop()
