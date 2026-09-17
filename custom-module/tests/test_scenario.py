"""`myorg.tenant.scenario` — pure construction, no bus, no config.

The counterpart of tests/test_echo.py: four-ish assertions with no scaffolding,
which is the payoff for keeping the file free of platform infrastructure.
"""
import unittest

from cltl.combot.event.emissor import LeolaniContext
from emissor.representation.scenario import Scenario

from myorg.tenant.scenario import AGENT_URI, SIGNALS, SPEAKER_URI, new_scenario


class NewScenarioTest(unittest.TestCase):
    def test_builds_a_leolani_context_with_the_constant_uris(self):
        scenario = new_scenario(agent="Agent A", speaker="Speaker A")

        self.assertIsInstance(scenario, Scenario)
        self.assertIsInstance(scenario.context, LeolaniContext)
        # Names are cosmetic and configurable — the chat UI renders them.
        self.assertEqual("Agent A", scenario.context.agent.name)
        self.assertEqual("Speaker A", scenario.context.speaker.name)
        # URIs are identity and are NOT configurable: two tenants get the same
        # agent identity, because the separation is the routing key and not the
        # agent. See the module docstring.
        self.assertEqual(AGENT_URI, scenario.context.agent.uri)
        self.assertEqual(SPEAKER_URI, scenario.context.speaker.uri)

    def test_defaults_match_the_platforms_own(self):
        scenario = new_scenario()

        self.assertEqual("Leolani", scenario.context.agent.name)
        self.assertEqual("Human", scenario.context.speaker.name)

    def test_location_is_free_text_and_not_looked_up(self):
        # ContextService._create_scenario calls requests.get("https://ipinfo.io")
        # inside a bare except. A template must not geolocate the machine it
        # runs on, so this is a plain label.
        self.assertEqual("somewhere", new_scenario(location="somewhere").context.location)

    def test_an_explicit_id_is_honoured_and_reaches_the_ruler(self):
        scenario = new_scenario(scenario_id="s-1")

        self.assertEqual("s-1", scenario.id)
        self.assertEqual("s-1", scenario.ruler.container_id)

    def test_is_open(self):
        # `end is None` is what "still open" means on the wire. TenantService.stop
        # is what sets it.
        self.assertIsNone(new_scenario().ruler.end)
        self.assertIsNotNone(new_scenario().ruler.start)

    def test_two_scenarios_share_nothing(self):
        one, two = new_scenario(), new_scenario()

        self.assertNotEqual(one.id, two.id)
        # The location_id is a fresh uuid per scenario too — a shared one would
        # silently claim two conversations happened in the same place.
        self.assertNotEqual(one.context.location_id, two.context.location_id)

    def test_carries_every_modality_signal_path(self):
        # Carried even though this deployment runs no cltl-emissor-data: a
        # scenario missing them is silently unpersistable, and the failure would
        # not surface until someone added storage.
        self.assertEqual({"image", "text", "audio"}, set(SIGNALS))
        self.assertEqual(SIGNALS, new_scenario().signals)


if __name__ == "__main__":
    unittest.main()
