"""End-to-end intent-routing tests for ovos-skill-days-in-history (en-US).

Each case feeds an utterance through a MiniCroft stack and asserts it routes
to the expected ``.intent`` handler. Coverage spans
the deictic phrasings (``today``/``this day``/``on this date``), the explicit
``{date}`` slot, and the history-anchored event/birth/death variants.

Run: pytest test/end2end/ -v
"""
from unittest import TestCase

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession
from ovoscope.routing import PIPELINE, TALLY, get_prototype_minicroft

SKILL_ID = "ovos-skill-days-in-history.openvoiceos"
LANG = "en-US"


class _IntentRoutingMixin:
    """Shared MiniCroft setup for intent routing."""

    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_prototype_minicroft([SKILL_ID], lang=LANG)

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "minicroft", None):
            cls.minicroft.stop()

    def _assert_intent(self, utterance: str, intent_file: str):
        session = Session(f"e2e-en_us-{intent_file}-{hash(utterance)}")
        session.lang = LANG
        session.pipeline = PIPELINE
        message = Message(
            "recognizer_loop:utterance",
            {"utterances": [utterance], "lang": LANG},
            {"session": session.serialize()},
        )
        capture = CaptureSession(
            self.minicroft,
            eof_msgs=["mycroft.skill.handler.start", "ovos.intent.unmatched"])
        capture.capture(message, timeout=30)
        TALLY.assert_routed(utterance, f"{SKILL_ID}:{intent_file}",
                            [m.msg_type for m in capture.finish()])


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
