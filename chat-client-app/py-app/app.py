import json
import logging.config
import os
import uuid

import time
from cltl.chatui.api import Chats
from cltl.chatui.memory import MemoryChats
from cltl.combot.event.bdi import IntentionEvent, Intention
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
from cltl_service.bdi.service import BDIService
from cltl_service.chatui.service import ChatUiService
from cltl_service.combot.event_log.service import EventLogService
from cltl_service.emissordata.client import EmissorDataClient
from cltl_service.emissordata.service import EmissorDataService
from cltl_service.intentions.init import InitService
from cltl_service.keyword.service import KeywordService
from emissor.representation.util import serializer as emissor_serializer, marshal, unmarshal, register_type_var
from flask import Flask
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.serving import run_simple

from app_service.context.service import ContextService

os.environ["CLTL_TENANT"] = str(uuid.uuid4())
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


class AppComponentsContainer(InfraContainer):
    @property
    @singleton
    def keyword_service(self) -> KeywordService:
        return KeywordService.from_config(self.event_bus, self.resource_manager, self.config_manager)

    @property
    @singleton
    def context_service(self) -> ContextService:
        return ContextService.from_config(self.event_bus, self.resource_manager, self.config_manager)

    @property
    @singleton
    def bdi_service(self) -> BDIService:
        bdi_model = json.loads(self.config_manager.get_config("cltl.bdi").get("model"))

        return BDIService.from_config(bdi_model, self.event_bus, self.resource_manager, self.config_manager)

    @property
    @singleton
    def init_intention(self) -> InitService:
        return InitService.from_config(self.event_bus, self.resource_manager, self.config_manager)

    def start(self):
        logger.info("Start App components services")
        super().start()
        self.bdi_service.start()
        self.keyword_service.start()
        self.context_service.start()
        self.init_intention.start()

    def stop(self):
        logger.info("Stop App components services")
        self.init_intention.stop()
        self.bdi_service.stop()
        self.keyword_service.stop()
        self.context_service.stop()
        super().stop()


class ChatUIContainer(InfraContainer):
    @property
    @singleton
    def chats(self) -> Chats:
        return MemoryChats()

    @property
    @singleton
    def chatui_service(self) -> ChatUiService:
        return ChatUiService.from_config(MemoryChats(), self.event_bus, self.resource_manager, self.config_manager)

    def start(self):
        logger.info("Start Chat UI")
        super().start()
        self.chatui_service.start()

    def stop(self):
        logger.info("Stop Chat UI")
        self.chatui_service.stop()
        super().stop()


class ApplicationContainer(AppComponentsContainer, ChatUIContainer, EmissorStorageContainer):
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
        logger.info("Starting the application")
        time.sleep(1)

        intention_topic = started_app.config_manager.get_config("cltl.bdi").get("topic_intention")
        init_event = Event.for_payload(IntentionEvent([Intention("init", None)]))
        started_app.event_bus.publish(intention_topic, init_event)

        logger.info("Started 'init' intention")

        routes = {
            '/emissor': started_app.emissor_data_service.app,
            '/chatui': started_app.chatui_service.app,
        }

        web_app = DispatcherMiddleware(Flask("Chat UI app"), routes)

        port = started_app.config_manager.get_config("app.server").get_int("port")
        run_simple('0.0.0.0', port, web_app, threaded=True, use_reloader=False, use_debugger=False, use_evalex=True)

        intention_topic = started_app.config_manager.get_config("cltl.bdi").get("topic_intention")
        termination_event = Event.for_payload(IntentionEvent([Intention("terminate", None)]))
        started_app.event_bus.publish(intention_topic, termination_event)
        time.sleep(1)


if __name__ == '__main__':
    main()
