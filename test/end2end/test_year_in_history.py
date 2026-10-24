"""A year question speaks an event of that year, taken from the day_*_events dialogs."""
import re
import time
from pathlib import Path
from unittest import TestCase

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import get_minicroft

SKILL_ID = "ovos-skill-days-in-history.openvoiceos"
LOCALE = Path(__file__).resolve().parents[2] / "locale" / "en-US"
PIPELINE = [
    "ovos-padacioso-pipeline-plugin-high",
    "ovos-padacioso-pipeline-plugin-medium",
    "ovos-padacioso-pipeline-plugin-low",
]


def _events_of(year: int) -> list:
    texts = []
    for path in LOCALE.glob("day_*_month_*_events.dialog"):
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(rf"{year} - (.*)", line)
            if match:
                texts.append(match.group(1))
    return texts


def _days_of(year: int) -> set:
    """The (month, day) of every event dialog that holds an event of ``year``."""
    days = set()
    for path in LOCALE.glob("day_*_month_*_events.dialog"):
        if any(line.startswith(f"{year} - ") for line in path.read_text(encoding="utf-8").splitlines()):
            day, month = re.fullmatch(r"day_(\d+)_month_(\d+)_events", path.stem).groups()
            days.add((int(month), int(day)))
    return days


class TestYearInHistory(TestCase):

    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_minicroft([SKILL_ID], lang="en-US", secondary_langs=["de-DE", "es-ES"])

    @classmethod
    def tearDownClass(cls):
        cls.minicroft.stop()

    def _ask(self, utterance: str, lang: str = "en-US") -> str:
        spoken = []
        handler = lambda msg: spoken.append(msg.data["utterance"])
        self.minicroft.bus.on("speak", handler)
        try:
            session = Session(f"e2e-year-{hash(utterance)}")
            session.lang = lang
            session.pipeline = PIPELINE
            self.minicroft.bus.emit(Message(
                "recognizer_loop:utterance",
                {"utterances": [utterance], "lang": lang},
                {"session": session.serialize()},
            ))
            deadline = time.monotonic() + 20
            while not spoken and time.monotonic() < deadline:
                time.sleep(0.2)
        finally:
            self.minicroft.bus.remove("speak", handler)
        self.assertTrue(spoken, f"{utterance!r} was not answered")
        return spoken[0]

    def test_year_with_events_speaks_one_of_them(self):
        events = _events_of(1492)
        self.assertTrue(events)
        answer = self._ask("what happened in the year 1492")
        self.assertTrue(any(event in answer for event in events), answer)

    def test_year_without_events_says_so(self):
        self.assertFalse(_events_of(3))
        answer = self._ask("what happened in the year 3")
        self.assertIn("in this year", answer)

    def test_year_spelled_in_words_speaks_one_of_its_events(self):
        events = _events_of(1492)
        answer = self._ask("what happened in the year fourteen ninety two")
        self.assertTrue(any(event in answer for event in events), answer)

    def test_fractional_year_says_there_are_no_events(self):
        answer = self._ask("what happened in the year 3.5")
        self.assertIn("in this year", answer)

    def test_nineteen_oh_five_is_the_year_1905(self):
        events = _events_of(1905)
        self.assertTrue(events)
        answer = self._ask("what happened in the year nineteen oh five")
        self.assertTrue(any(event in answer for event in events), answer)

    def _assert_no_events(self, utterance: str, lang: str):
        dialog = (LOCALE.parent / lang / "no_events_for_year.dialog").read_text(encoding="utf-8")
        expected = [line for line in dialog.splitlines() if line and not line.startswith("#")]
        self.assertIn(self._ask(utterance, lang), expected)

    def test_fractional_year_in_german_says_there_are_no_events(self):
        self._assert_no_events("was geschah im Jahr 2,5", "de-DE")

    def test_fractional_year_in_spanish_says_there_are_no_events(self):
        self._assert_no_events("qué pasó en el año 3,5", "es-ES")

    def test_january_first_event_speaks_its_date_not_today(self):
        self.assertEqual({(1, 1)}, _days_of(1001))
        self.assertTrue(self._ask("what happened in the year 1001").startswith("january first, "))

    def test_january_event_speaks_its_month(self):
        self.assertEqual({(1, 12)}, _days_of(1528))
        self.assertTrue(self._ask("what happened in the year 1528").startswith("january twelfth, "))
