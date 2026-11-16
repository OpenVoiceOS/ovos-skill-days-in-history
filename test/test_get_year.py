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


@pytest.mark.parametrize("lang, utterance", [
    ("pt-PT", "conta-me uma curiosidade sobre o ano mil novecentos e oitenta e quatro"),
    ("pt-PT", "diz-me uma curiosidade do ano mil novecentos e oitenta e quatro a.C."),
    ("pt-BR", "me diga uma curiosidade do ano mil novecentos e oitenta e quatro"),
    ("es-ES", "dime una curiosidad del año mil novecientos ochenta y cuatro"),
    ("es-CO", "dime una curiosidad del año mil novecientos ochenta y cuatro"),
    ("ca-ES", "digues-me una curiositat de l'any mil nou-cents vuitanta-quatre"),
    ("gl-ES", "dime unha curiosidade do ano mil novecentos oitenta e catro"),
    ("fr-FR", "donne-moi un fait sur l'année mille neuf cent quatre-vingt-quatre"),
    ("it-IT", "dimmi una curiosità sull'anno millenovecentottantaquattro"),
    ("de-DE", "nenne mir eine Tatsache über das Jahr neunzehnhundertvierundachtzig"),
    ("nl-NL", "geef me een weetje over het jaar negentienhonderdvierentachtig"),
    ("da-DK", "fortæl mig et faktum om året nittenhundrede og fireogfirs"),
    ("sv-SE", "ge mig en kuriosa om året nittonhundraåttiofyra"),
    ("eu-ES", "kontatu mila bederatziehun eta laurogeita lau urteari buruzko gertakari bat"),
])
def test_an_article_before_the_year_is_no_number(lang, utterance):
    fake = SimpleNamespace(lang=lang, voc_match=lambda *_: False)
    assert TodayInHistory._get_year(fake, Message("x", {"utterance": utterance})) == 1984
