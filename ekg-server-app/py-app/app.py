import logging.config
import logging.config
import os
import pathlib
import time

from cltl.about.about import AboutImpl
from cltl.about.api import About
from cltl.brain.long_term_memory import LongTermMemory
from cltl.combot.event.emissor import SIG, MEN
from cltl.combot.infra.config.k8config import K8LocalConfigurationContainer
from cltl.combot.infra.di_container import singleton
from cltl.combot.infra.event import Event
from cltl.combot.infra.event.api import PAYLOAD
from cltl.combot.infra.event.kombu import KombuEventBusContainer
from cltl.combot.infra.event_log import LogWriter
from cltl.combot.infra.resource.threaded import ThreadedResourceContainer
from cltl.emissordata.api import EmissorDataStorage
from cltl.emissordata.file_storage import EmissorDataFileStorage
from cltl.reply_generation.thought_selectors.random_selector import RandomSelector
from cltl.triple_extraction.api import DialogueAct
from cltl.triple_extraction.chat_analyzer import ChatAnalyzer
from cltl_service.about.service import AboutService
from cltl_service.brain.service import BrainService
from cltl_service.combot.event_log.service import EventLogService
from cltl_service.emissordata.client import EmissorDataClient
from cltl_service.emissordata.service import EmissorDataService
from cltl_service.reply_generation.service import ReplyGenerationService
from cltl_service.triple_extraction.service import TripleExtractionService
from emissor.representation.util import serializer as emissor_serializer, register_type_var, marshal, unmarshal
from flask import Flask
from werkzeug.middleware.dispatcher import DispatcherMiddleware
from werkzeug.serving import run_simple

# from gtts import gTTS
# from playsound import playsound

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
        if implementation == "kombu":
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
        try:
            logger.info("Stop Emissor Data Storage")
            self.emissor_data_service.stop()
        finally:
            super().stop()


class TripleExtractionContainer(InfraContainer):
    @property
    @singleton
    def triple_extraction_service(self) -> TripleExtractionService:
        config = self.config_manager.get_config("cltl.triple_extraction")
        implementation = config.get("implementation", multi=True)
        timeout = config.get_float("timeout") if "timeout" in config else 0.0

        analyzers = []
        if "CFGAnalyzer" in implementation:
            from cltl.triple_extraction.cfg_analyzer import CFGAnalyzer
            analyzers.append(CFGAnalyzer(process_questions=False))
        if "CFGQuestionAnalyzer" in implementation:
            from cltl.question_extraction.cfg_question_analyzer import CFGQuestionAnalyzer
            analyzers.append(CFGQuestionAnalyzer())
        if "StanzaQuestionAnalyzer" in implementation:
            from cltl.question_extraction.stanza_question_analyzer import StanzaQuestionAnalyzer
            analyzers.append(StanzaQuestionAnalyzer())
        if "OIEAnalyzer" in implementation:
            from cltl.triple_extraction.oie_analyzer import OIEAnalyzer
            analyzers.append(OIEAnalyzer())
        if "SpacyAnalyzer" in implementation:
            from cltl.triple_extraction.spacy_analyzer import spacyAnalyzer
            analyzers.append(spacyAnalyzer())
        if "LLMAnalyzer" in implementation:
            from cltl.triple_extraction.conversational_llm_analyzer import LLMAnalyzer
            config = self.config_manager.get_config('cltl.triple_extraction.llm')
            model = config.get("model") if "model" in config else None
            server = config.get("server") if "server" in config else None
            url = config.get("url") if "url" in config else None
            port = config.get("port") if "port" in config else None
            context_length = config.get_int('context_length') if 'context_length' in config else 3
            temperature = config.get('temperature') if 'temperature' in config else 0.1
            language = config.get("language") if 'language' in config else 'en'
            credentials = self.config_manager.get_config("credentials.ollama")
            key = credentials.get("key")
            analyzers.append(
                LLMAnalyzer(model_name=model, model_server=server, model_url=url, model_port=port, model_key=key,
                            temperature=temperature, keep_alive=20,
                            lang=language, context_length=context_length))
        if "ConversationalAnalyzer" in implementation:
            from cltl.triple_extraction.conversational_analyzer import ConversationalAnalyzer
            config = self.config_manager.get_config('cltl.triple_extraction.conversational')
            model_path = config.get('model_path')
            base_model = config.get('base_model')
            language = config.get("language")
            threshold = config.get_float("threshold")
            max_triples = config.get_int("max_triples")
            batch_size = config.get_int("batch_size")
            dialogue_acts = [DialogueAct.STATEMENT]
            if "ConversationalQuestionAnalyzer" in implementation:
                dialogue_acts += [DialogueAct.QUESTION]
            analyzers.append(ConversationalAnalyzer(model_path=model_path, base_model=base_model, threshold=threshold,
                                                    max_triples=max_triples, batch_size=batch_size,
                                                    dialogue_acts=dialogue_acts, lang=language))

        if not analyzers:
            raise ValueError("No supported analyzers in " + implementation)

        logger.info("Using analyzers %s in Triple Extraction", implementation)

        return TripleExtractionService.from_config(ChatAnalyzer(analyzers, timeout=timeout),
                                                   self.event_bus, self.resource_manager, self.config_manager)

    def start(self):
        logger.info("Start Triple Extraction")
        super().start()
        self.triple_extraction_service.start()

    def stop(self):
        try:
            logger.info("Stop Triple Extraction")
            self.triple_extraction_service.stop()
        finally:
            super().stop()


class BrainContainer(InfraContainer):
    @property
    @singleton
    def brain(self) -> LongTermMemory:
        config = self.config_manager.get_config("cltl.brain")
        brain_address = config.get("address")
        brain_log_dir = config.get("log_dir")
        clear_brain = bool(config.get_boolean("clear_brain"))

        # TODO figure out how to put the brain RDF files in the EMISSOR scenario folder
        return LongTermMemory(address=brain_address,
                              log_dir=pathlib.Path(brain_log_dir),
                              clear_all=clear_brain)

    @property
    @singleton
    def brain_service(self) -> BrainService:
        return BrainService.from_config(self.brain, self.event_bus, self.resource_manager, self.config_manager)

    def start(self):
        logger.info("Start Brain")
        super().start()
        self.brain_service.start()

    def stop(self):
        try:
            logger.info("Stop Brain")
            self.brain_service.stop()
        finally:
            super().stop()


class ReplierContainer(BrainContainer, EmissorStorageContainer, InfraContainer):
    @property
    @singleton
    def reply_service(self) -> ReplyGenerationService:
        config = self.config_manager.get_config("cltl.reply_generation")
        implementations = config.get("implementations")
        repliers = []

        if "LenkaReplier" in implementations:
            from cltl.reply_generation.lenka_replier import LenkaReplier
            thought_options = config.get("thought_options", multi=True) if "thought_options" in config else []
            llamalize = config.get("llamalize") if "llamalize" in config else False
            model = config.get("model") if "model" in config else None
            server = config.get("server") if "server" in config else None
            url = config.get("url") if "url" in config else None
            port = config.get("port") if "port" in config else None
            instruct = config.get("instruct") if "instruct" in config else None
            temperature = config.get("temperature") if "temperature" in config else None
            max_tokens = config.get("max_tokens") if "max_tokens" in config else None
            show_lenka = config.get("show_lenka") if "show_lenka" in config else False
            randomness = float(config.get("randomness")) if "randomness" in config else 1.0
            credentials = self.config_manager.get_config("credentials.ollama")
            key = credentials.get("key")
            replier = LenkaReplier(model="", instruct=instruct, llamalize=llamalize, temperature=float(temperature), max_tokens=int(max_tokens), show_lenka=show_lenka, thought_selector=RandomSelector(randomness=randomness, priority=thought_options))
           # replier = LenkaReplier(model_name=model, model_server=server, model_url=url, model_port=port, model_key = key, instruct=instruct, llamalize=llamalize, temperature=float(temperature), max_tokens=int(max_tokens), show_lenka=show_lenka, thought_selector=RandomSelector(randomness=randomness, priority=thought_options))
            repliers.append(replier)
        if "RLReplier" in implementations:
            from cltl.reply_generation.rl_replier import RLReplier
            # TODO This is OK here, we need to see how this will work in a containerized setting
            replier = RLReplier(self.brain)
            repliers.append(replier)
        if "LlamaReplier" in implementations:
            from cltl.reply_generation.llama_replier import LlamaReplier
            replier = LlamaReplier()
            repliers.append(replier)
        if "SimpleNLGReplier" in implementations:
            from cltl.reply_generation.simplenlg_replier import SimpleNLGReplier
            # TODO This is OK here, we need to see how this will work in a containerized setting
            replier = SimpleNLGReplier()
            repliers.append(replier)
        if not repliers:
            raise ValueError("Unsupported implementation " + implementations)

        return ReplyGenerationService.from_config(repliers, self.event_bus, self.resource_manager, self.config_manager)

    def start(self):
        logger.info("Start Repliers")
        super().start()
        self.reply_service.start()

    def stop(self):
        try:
            logger.info("Stop Repliers")
            self.reply_service.stop()
        finally:
            super().stop()


class AboutAgentContainer(InfraContainer):
    @property
    @singleton
    def about_agent(self) -> About:
        return AboutImpl()

    @property
    @singleton
    def about_agent_service(self) -> AboutService:
        return AboutService.from_config(self.about_agent, self.event_bus, self.resource_manager, self.config_manager)

    def start(self):
        logger.info("Start AboutAgent")
        super().start()
        self.about_agent_service.start()

    def stop(self):
        try:
            logger.info("Stop AboutAgent")
            self.about_agent_service.stop()
        finally:
            super().stop()


class ApplicationContainer(AboutAgentContainer,
                           TripleExtractionContainer, ReplierContainer, BrainContainer,
                           EmissorStorageContainer):
    @property
    @singleton
    def log_writer(self):
        config = self.config_manager.get_config("cltl.event_log")

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
            super().stop()

def main():
    ApplicationContainer.load_configuration()
    logger.info("Initialized Application")
    application = ApplicationContainer()

    with application as started_app:
        routes = {
            '/emissor': started_app.emissor_data_service.app,
        }

        web_app = DispatcherMiddleware(Flask("EKG server app"), routes)

        port = started_app.config_manager.get_config("app.server").get_int("port")
        run_simple('0.0.0.0', port, web_app, threaded=True, use_reloader=False, use_debugger=False, use_evalex=True)

        time.sleep(1)


if __name__ == '__main__':
    main()
