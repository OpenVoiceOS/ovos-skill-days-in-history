"""A year before Christ speaks an event of that year, not one of the same year after Christ.

Each question goes through a MiniCroft. The data holds events of 660 BC and
of 660 AD under the same number.
"""
import re
from pathlib import Path
from unittest import SkipTest, TestCase

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession
from ovoscope.routing import PIPELINE, TALLY, get_prototype_minicroft

SKILL_ID = "ovos-skill-days-in-history.openvoiceos"
YEAR_IN_HISTORY = f"{SKILL_ID}:year_in_history"
LOCALE = Path(__file__).resolve().parents[2] / "locale" / "en-US"


ERA = r"(?:BC|BCE|aC|a\.C\.|AC|f\.Kr\.|v\. ?Chr\.|V\.CHR\.)"
# (language, question about 69 BC with the era written as the normalizer spaces it out)
SPACED_ERAS = [
    ("en-US", "what happened in the year 69 B. C."),
    ("de-DE", "was geschah im Jahr 69 v. Chr."),
    ("es-ES", "qué pasó en el año 69 a. C."),
    ("fr-FR", "que s'est-il passé en l'année 69 av. J.-C."),
    ("it-IT", "cosa è successo nell'anno 69 a. C."),
    ("nl-NL", "wat gebeurde er in het jaar 69 v. Chr."),
    ("sv-SE", "vad hände år 69 f. Kr."),
]


def _events(number: str, era: str, lang: str = "en-US") -> set:
    """Texts of the lines that start with the number, with or without the era marker."""
    texts = set()
    for path in (LOCALE.parent / lang).glob("day_*_month_*_events.dialog"):
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(rf"{number}( {ERA})?(?:\s*\[\d+\])? - (.*)", line)
            if match and bool(match.group(1)) == (era == "BC"):
                texts.add(match.group(2))
    return texts


SECONDARY = [lang for lang, _ in SPACED_ERAS if lang != "en-US"] + ["pt-BR", "ca-ES"]


def _events_any(lang: str, number: str) -> set:
    """Texts of every line of the locale that starts with the number, whatever follows."""
    texts = set()
    for path in (LOCALE.parent / lang).glob("day_*_month_*_events.dialog"):
        for line in path.read_text(encoding="utf-8").splitlines():
            match = re.match(rf"{number}(?:\s*[-:\u2013])?\s+(.*)", line)
            if match:
                texts.add(match.group(1))
    return texts


class BcYears:
    @classmethod
    def tearDownClass(cls):
        cls.minicroft.stop()

    def _ask(self, utterance: str, lang: str = "en-US") -> str:
        """What the skill speaks for ``utterance``, after its route is recorded."""
        session = Session(f"e2e-bc-{hash(utterance)}")
        session.lang = lang
        session.pipeline = PIPELINE
        capture = CaptureSession(self.minicroft, eof_msgs=["ovos.utterance.handled"])
        capture.capture(Message("recognizer_loop:utterance",
                                {"utterances": [utterance], "lang": lang},
                                {"session": session.serialize(), "lang": lang}),
                        timeout=30)
        messages = capture.finish()
        TALLY.assert_routed(utterance, YEAR_IN_HISTORY, [m.msg_type for m in messages])
        spoken = [m.data.get("utterance", "") for m in messages
                  if m.msg_type in ("speak", "ovos.utterance.speak")]
        self.assertTrue(spoken, f"{utterance!r} was not answered")
        return spoken[0]

    def _assert_spoken_from(self, utterance, number, era, lang="en-US"):
        wanted = _events(number, era, lang)
        other = _events(number, "AD" if era == "BC" else "BC", lang)
        self.assertTrue(wanted and other, "the data must hold both eras")
        answer = self._ask(utterance, lang)
        self.assertTrue(any(text in answer for text in wanted), (utterance, answer))
        self.assertFalse(any(text in answer for text in other), (utterance, answer))

    def test_a_year_before_christ_speaks_a_bc_event(self):
        self._assert_spoken_from("what happened in the year 660 BC", "660", "BC")

    def test_the_year_with_the_word_year_before_christ(self):
        self._assert_spoken_from("what happened in the year 69 BC", "69", "BC")

    def test_the_same_number_without_an_era_speaks_an_ad_event(self):
        self._assert_spoken_from("what happened in the year 660", "660", "AD")

    def test_an_era_abbreviation_spaced_out_by_the_normalizer(self):
        wrong = []
        for lang, utterance in SPACED_ERAS:
            wanted, other = _events("69", "BC", lang), _events("69", "AD", lang)
            self.assertTrue(wanted and other, lang)
            try:
                answer = self._ask(utterance, lang)
            except SkipTest:
                continue  # a misroute, counted in the tally
            if any(text in answer for text in other) or not any(text in answer for text in wanted):
                wrong.append((lang, utterance, answer))
        self.assertEqual(wrong, [])

    def test_a_year_that_the_data_lists_without_a_dash_has_events(self):
        # pt-BR lines read "1471 Sten Sture, ..." and the ca-ES ones "1293: ..."
        for lang, utterance, number in (("pt-BR", "o que aconteceu no ano 1471", "1471"),
                                        ("ca-ES", "què va passar l'any 1293", "1293")):
            try:
                answer = self._ask(utterance, lang)
            except SkipTest:
                continue  # a misroute, counted in the tally
            self.assertNotIn("no_events", answer)
            self.assertTrue(any(text.split(",")[0].split(":")[0][:25] in answer
                                for text in _events_any(lang, number)), (lang, answer))

    def test_a_bc_year_without_events_says_so(self):
        self.assertFalse(_events("15", "BC"))
        self.assertIn("in this year", self._ask("what happened in the year 15 BC"))


class TestM2vPipeline(BcYears, TestCase):

    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_prototype_minicroft([SKILL_ID], lang="en-US",
                                                secondary_langs=SECONDARY)

    def test_the_short_question_speaks_a_bc_event(self):
        self._assert_spoken_from("what happened in 660 BC", "660", "BC")
