"""The year slot is text: spelled-out, fractional and non-numeric years must not crash."""
from types import SimpleNamespace

import pytest
from ovos_bus_client.message import Message

from ovos_skill_days_in_history import TodayInHistory


@pytest.mark.parametrize("lang, utterance, slot, expected", [
    ("en-US", "what happened in the year 1492", "1492", 1492),
    ("en-US", "what happened in the year fourteen ninety two", "ninety two", 1492),
    ("en-US", "what happened in the year fourteen hundred ninety two", "fourteen hundred ninety two", 1492),
    ("en-US", "what happened in the year twenty twenty", "twenty", 2020),
    ("en-US", "what happened in the year nineteen oh five", "five", 1905),
    ("en-US", "what happened in the year nineteen banana five", "five", None),
    ("en-US", "what happened in the year 3.5", "3.5", None),
    ("en-US", "what happened in the year banana", "banana", None),
    ("de-DE", "was geschah im Jahr 2,5", "2,5", None),
    ("de-DE", "was geschah im Jahr vierzehnhundertzweiundneunzig", "vierzehnhundertzweiundneunzig", 1492),
    ("es-ES", "qué pasó en el año 1492 y medio", "1492 y medio", None),
    ("es-ES", "qué pasó en el año mil cuatrocientos noventa y dos", "mil cuatrocientos noventa y dos", 1492),
])
def test_year_read_from_the_utterance(lang, utterance, slot, expected):
    fake = SimpleNamespace(lang=lang, voc_match=lambda text, voc: lang == "en-US" and text == "oh")
    message = Message("x", {"utterance": utterance, "year": slot})
    assert TodayInHistory._get_year(fake, message) == expected


def test_fractional_typed_slot_is_not_truncated():
    message = Message("x", {"utterance": "year 3.5", "typed_slots": {"number": [{"name": "year", "value": 3.5}]}})
    assert TodayInHistory._get_year(SimpleNamespace(lang="en-US", voc_match=lambda *_: False), message) is None
