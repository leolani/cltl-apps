from myorg.example.api import Example

MARKER = " (via myorg.example)"


class EchoExample(Example):
    """Shouts your own words back at you, with a marker on the end. Delete this.

    It is deliberately not conversational logic. If it looked like a real
    answer, the first thing a reader would do is try to improve it; because it
    obviously is not, the first thing they do is replace it — which is the
    point of a template.

    The marker earns its keep twice: it is how you tell this module's reply
    from cltl-eliza's in a deployment where both answer on cltl.topic.text_out
    (see docs/getting-started.md), and it is what the loop guard below matches
    on.
    """

    def __init__(self, prefix: str = "YOU SAID:"):
        self._prefix = prefix

    def process(self, text: str):
        if not text or not text.strip():
            # An utterance with nothing in it — ASR publishes these when a VAD
            # segment turns out to hold no speech. Nothing to say back.
            return None

        text = text.strip()

        if text.endswith(MARKER):
            # Our own output, heard back. Not reachable with the shipped
            # config — topic_input and topic_output are different topics, so
            # this module cannot hear itself there. It IS reachable the moment
            # someone edits config/default.config to point topic_output at
            # topic_input to see a quick round trip: without this guard that
            # edit is an infinite loop that saturates the broker in seconds.
            return None

        return f"{self._prefix} {text.upper()}{MARKER}"
