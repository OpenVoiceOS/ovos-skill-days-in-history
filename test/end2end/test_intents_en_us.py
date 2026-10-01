"""End-to-end intent-routing tests for ovos-skill-days-in-history (en-US).

Each case feeds an utterance through a MiniCroft stack and asserts it routes
to the expected ``.intent`` handler via the padatious pipeline. Coverage spans
the deictic phrasings (``today``/``this day``/``on this date``), the explicit
``{date}`` slot, and the history-anchored event/birth/death variants.

Run: pytest test/end2end/ -v
"""
import time
from unittest import TestCase

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import get_minicroft

SKILL_ID = "ovos-skill-days-in-history.openvoiceos"
LANG = "en-US"

# Exact phrasings score in the -high band; the {date} slot variants land
# lower, so drive all three padatious confidence bands.
PIPELINE = [
    "ovos-padatious-pipeline-plugin-high",
    "ovos-padatious-pipeline-plugin-medium",
    "ovos-padatious-pipeline-plugin-low",
]


class _IntentRoutingMixin:
    """Shared MiniCroft setup for padatious intent routing."""

    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_minicroft([SKILL_ID])

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "minicroft", None):
            cls.minicroft.stop()

    def _assert_intent(self, utterance: str, intent_file: str):
        # dispatched ovos.intent.matched intent names carry no ".intent"
        # suffix (OVOS-INTENT-2 naming) -- strip it so this assertion tracks
        # the real bus event instead of the on-disk container filename.
        intent_name = intent_file[:-len(".intent")] if intent_file.endswith(".intent") else intent_file
        intent_msg_type = f"{SKILL_ID}:{intent_name}"
        matched = []
        handler = lambda msg: matched.append(msg)
        self.minicroft.bus.on(intent_msg_type, handler)
        try:
            session = Session(f"e2e-en_us-{intent_file}-{hash(utterance)}")
            session.lang = LANG
            session.pipeline = PIPELINE
            self.minicroft.bus.emit(Message(
                "recognizer_loop:utterance",
                {"utterances": [utterance], "lang": LANG},
                {"session": session.serialize()},
            ))
            deadline = time.monotonic() + 15
            while not matched and time.monotonic() < deadline:
                time.sleep(0.2)
        finally:
            self.minicroft.bus.remove(intent_msg_type, handler)
        self.assertTrue(
            matched,
            f"{utterance!r} did not route to {intent_file}",
        )


class TestTodayInHistory(_IntentRoutingMixin, TestCase):
    """today_in_history.intent"""

    def test_today_in_history(self):
        self._assert_intent("today in history", "today_in_history.intent")

    def test_this_day_in_history(self):
        self._assert_intent("this day in history", "today_in_history.intent")

    def test_on_this_day_in_history(self):
        self._assert_intent("on this day in history", "today_in_history.intent")

    def test_what_happened_today_in_history(self):
        self._assert_intent("what happened today in history", "today_in_history.intent")

    def test_what_historical_events_happened_today(self):
        self._assert_intent("what historical events happened today", "today_in_history.intent")

    def test_what_happened_on_date_in_history(self):
        self._assert_intent("what happened on the fifth of may in history", "today_in_history.intent")


class TestBirthsInHistory(_IntentRoutingMixin, TestCase):
    """births_in_history.intent"""

    def test_who_was_born_today_in_history(self):
        self._assert_intent("who was born today in history", "births_in_history.intent")

    def test_famous_people_born_today(self):
        self._assert_intent("what famous people were born today", "births_in_history.intent")

    def test_famous_births_today_in_history(self):
        self._assert_intent("famous births today in history", "births_in_history.intent")


class TestDeathsInHistory(_IntentRoutingMixin, TestCase):
    """deaths_in_history.intent"""

    def test_who_died_today_in_history(self):
        self._assert_intent("who died today in history", "deaths_in_history.intent")

    def test_famous_people_died_today(self):
        self._assert_intent("what famous people died today", "deaths_in_history.intent")

    def test_notable_deaths_today_in_history(self):
        self._assert_intent("notable deaths today in history", "deaths_in_history.intent")
