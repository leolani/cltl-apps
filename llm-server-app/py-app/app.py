import logging.config
import os
import time

from cltl.combot.event.emissor import SIG, MEN
from cltl.combot.infra.config.k8config import K8LocalConfigurationContainer
from cltl.combot.infra.di_container import singleton
from cltl.combot.infra.event.api import Event, PAYLOAD
from cltl.combot.infra.event.kombu import KombuEventBusContainer
from cltl.combot.infra.event.memory import SynchronousEventBus
from cltl.combot.infra.event_log import LogWriter
from cltl.combot.infra.resource.threaded import ThreadedResourceContainer
from cltl.emissordata.api import EmissorDataStorage
from cltl.emissordata.file_storage import EmissorDataFileStorage
from cltl.llm.api import LLM
from cltl.llm.llm import LLMImpl
from cltl_service.combot.event_log.service import EventLogService
from cltl_service.emissordata.client import EmissorDataClient
from cltl_service.emissordata.service import EmissorDataService
from cltl_service.llm.service import LLMService
from emissor.representation.util import serializer as emissor_serializer, marshal, unmarshal, register_type_var
from flask import Flask
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.serving import run_simple

logging.config.fileConfig(os.environ.get('CLTL_LOGGING_CONFIG', default='config/logging.config'),
                          disable_existing_loggers=False)
logger = logging.getLogger(__name__)


# Register TypeVar for usage with emissor serialization utils
register_type_var(PAYLOAD)
register_type_var(SIG)
register_type_var(MEN)


def serializer(obj):
    """Serialize events into deserializable JSON using emissor utilities."""
    return marshal(obj, cls=Event)


def deserializer(obj):
    """Deserialize events into propert Python objects using emissor utilities."""
    return unmarshal(obj, cls=Event)


class InfraContainer(KombuEventBusContainer, K8LocalConfigurationContainer, ThreadedResourceContainer):
    @property
    @singleton
    def event_bus_serializer(self):
        return serializer, deserializer

    @property
    @singleton
    def event_bus(self):
        config = self.config_manager.get_config("cltl.event")
        implementation = config.get("implementation")
        if implementation == "internal":
            return SynchronousEventBus()
        elif implementation == "kombu":
            return super().event_bus
        else:
            raise ValueError("Unknown implementation: " + implementation)

    def start(self):
        pass

    def stop(self):
        pass


class EmissorStorageContainer(InfraContainer):
    @property
    @singleton
    def emissor_storage(self) -> EmissorDataStorage:
        return EmissorDataFileStorage.from_config(self.config_manager)

    @property
    @singleton
    def emissor_data_service(self) -> EmissorDataService:
        return EmissorDataService.from_config(self.emissor_storage,
                                              self.event_bus, self.resource_manager, self.config_manager)

    @property
    @singleton
    def emissor_data_client(self) -> EmissorDataClient:
        return EmissorDataClient("http://0.0.0.0:8000/emissor")

    def start(self):
        logger.info("Start Emissor Data Storage")
        super().start()
        self.emissor_data_service.start()

    def stop(self):
        logger.info("Stop Emissor Data Storage")
        self.emissor_data_service.stop()
        super().stop()


class LLMContainer(EmissorStorageContainer, InfraContainer):
    @property
    @singleton
    def llm(self) -> LLM:
        config = self.config_manager.get_config("cltl.llm")

        model = config.get("model") if "model" in config else None
        url = config.get("url")
        instruction ={"role": "system", "content": config.get("instruction")}
        temperature = config.get("temperature")
        max_history = config.get("max_history")
        intro = config.get("intro")
        stop = config.get("stop")
        server = config.get_boolean("server") if "server" in config else False

        return LLMImpl(model_name=model, instruction=instruction,  intro = intro, stop = stop,
                       temperature=float(temperature), max_history=int(max_history),
                       server=server, url=url)


    @property
    @singleton
    def llm_service(self) -> LLMService:
        return LLMService.from_config(self.llm, self.emissor_data_client,
                                        self.event_bus, self.resource_manager, self.config_manager, self.emissor_storage)

    def start(self):
        logger.info("Start LLM")
        super().start()
        self.llm_service.start()

    def stop(self):
        logger.info("Stop LLM")
        self.llm_service.stop()
        super().stop()


class ApplicationContainer(LLMContainer, EmissorStorageContainer):
    @property
    @singleton
    def log_writer(self):
        config = self.config_manager.get_config("cltl.event_log")

        # Serialize in a plain JSON format
        return LogWriter(config.get("log_dir"), emissor_serializer)

    @property
    @singleton
    def event_log_service(self):
        return EventLogService.from_config(self.log_writer, self.event_bus, self.config_manager)

    def start(self):
        logger.info("Start EventLog")
        super().start()
        self.event_log_service.start()

    def stop(self):
        try:
            logger.info("Stop EventLog")
            self.event_log_service.stop()
        finally:
            try:
                logger.info("Stop EventBus")
                if hasattr(self.event_bus, 'close'):
                    self.event_bus.close()
            finally:
                super().stop()


def main():
    ApplicationContainer.load_configuration()
    logger.info("Initialized Application")
    application = ApplicationContainer()

    with application as started_app:
        routes = {
            '/emissor': started_app.emissor_data_service.app,
        }

        web_app = DispatcherMiddleware(Flask("LLM server app"), routes)

        port = started_app.config_manager.get_config("app.server").get_int("port")
        run_simple('0.0.0.0', port, web_app, threaded=True, use_reloader=False, use_debugger=False, use_evalex=True)

        time.sleep(1)


if __name__ == '__main__':
    main()
