import logging

from cltl.combot.infra.container import InfraContainer
from cltl.combot.infra.di_container import singleton

from myorg.tenant.service import TenantService

logger = logging.getLogger(__name__)


class TenantContainer(InfraContainer):
    """Wires the :class:`TenantService` into a deployment. Delete me one day.

    This container exists only because of tenant separation — the reasoning is
    in `myorg/tenant/scenario.py`'s module docstring and in docs/tenancy.md.
    When your deployment runs a real `cltl-context` per tenant, take this class
    out of `src/main.py`'s bases and delete the package. `ExampleContainer` does
    not know it exists, and nothing in `myorg.example` refers to a scenario.

    One accessor, and it is prefixed (`tenant_service`, not `service`) for the
    reason `ExampleContainer`'s docstring gives: @singleton keys its cache by
    the BARE method name across the whole process, so an unprefixed accessor
    collides with any other component mixed into the same deployment that also
    defines one. There is deliberately no `scenario` accessor — see
    `TenantService.scenario`.
    """

    @property
    @singleton
    def tenant_service(self) -> TenantService:
        return TenantService.from_config(self.event_bus, self.resource_manager,
                                         self.config_manager)

    def start(self):
        logger.info("Start Tenant")
        super().start()
        self.tenant_service.start()

    def stop(self):
        logger.info("Stop Tenant")
        self.tenant_service.stop()
        super().stop()
