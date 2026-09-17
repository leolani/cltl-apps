"""Build the `Scenario` a tenant's conversation needs. NOT custom functionality.

Opening a scenario is normally `cltl-context`'s job. It is in this template
only because of tenant separation: `cltl-chat-ui` runs *inside* a tenant (it
publishes utterances without `source=`, so an untenanted one would route to a
bare topic key nothing binds), it renders nothing and refuses to publish until
it has seen a `ScenarioStarted`, and a tenant's `ScenarioStarted` can only be
published on that tenant's own bus. Something on the tenant side has to open
it, and in this deployment that something is us.

So: the day your deployment runs a real `cltl-context` per tenant, delete this
package, its `[myorg.tenant]` config section and its tests, and take
`TenantContainer` out of `src/main.py`. Nothing in `myorg.example` refers to
any of it — that separation is deliberate and is the point being made.

There is no `api.py` beside this file, and that absence is also deliberate.
`myorg/example/api.py` exists because `EchoExample` is meant to be replaced;
nothing here is. A scenario is built exactly one way, by
`ContextService._create_scenario` (cltl-context/src/cltl_service/context/service.py),
of which this is the reduction that
integration/src/cltl_integration/drivers/scenario.py already made. An ABC here
would advertise a choice that does not exist.

Pure construction, no bus: `service.py` is what publishes. The only platform
infrastructure imported is the clock, for the same reason drivers/scenario.py
imports it — `tests/test_layering.py` pins that boundary.
"""
import uuid
from typing import Optional

from cltl.combot.event.emissor import Agent, LeolaniContext
from cltl.combot.infra.time_util import timestamp_now
from emissor.representation.scenario import Modality, Scenario

# The agent's and speaker's IDENTITIES, and deliberately constants rather than
# configuration. A URI is what a knowledge graph would join on; the display
# name below it is only what the chat UI renders
# (cltl-chat-ui/src/cltl_service/chatui/service.py). Giving tenant-a and
# tenant-b different agent *names* makes the isolation visible on screen and is
# a demo convenience — it must not be read as identity separation. The
# separation is the routing key, and nothing else. See docs/tenancy.md.
AGENT_URI = "http://cltl.nl/leolani/world/leolani"
SPEAKER_URI = "http://cltl.nl/leolani/world/human_speaker"

# Where EMISSOR would write each modality, relative to the scenario directory.
# Carried even though this deployment runs no cltl-emissor-data: a scenario
# that omits them is silently unpersistable, and the failure would not surface
# until someone added storage.
SIGNALS = {
    Modality.IMAGE.name.lower(): "./image.json",
    Modality.TEXT.name.lower(): "./text.json",
    Modality.AUDIO.name.lower(): "./audio.json",
}


def new_scenario(scenario_id: Optional[str] = None, agent: str = "Leolani",
                 speaker: str = "Human", location: str = "unknown") -> Scenario:
    """A `Scenario` ready to be announced with `ScenarioStarted`.

    `ruler.end` is left None — that is what "still open" means; `TenantService.stop`
    sets it. `location` is a free-text label rather than a lookup:
    `ContextService._create_scenario` calls `requests.get("https://ipinfo.io")`
    on every scenario start inside a bare `except`, and a template should not
    geolocate the machine it runs on.
    """
    context = LeolaniContext(Agent(agent, AGENT_URI), Agent(speaker, SPEAKER_URI),
                             str(uuid.uuid4()), location, [], [])

    return Scenario.new_instance(scenario_id or str(uuid.uuid4()),
                                 timestamp_now(), None, context, SIGNALS)
