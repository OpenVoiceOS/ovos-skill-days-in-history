"""The answer has to say WHICH day it read.

A native de-DE speaker reported the answer as unverifiable: the
`.dialog` lines carry the year only ("1066 - William der Eroberer ..."), so a
listener who asked for "gestern" was never told which day came back. The day
and the month were known -- `get_date` has them -- and were simply never
spoken.

`_announce_date` speaks them, out of `date_intro.dialog`. The file ships for
en-US and de-DE. A locale without it must stay silent rather than speak a bare
resource name, so both directions are asserted here.
"""
import datetime
import os
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import ovos_skill_days_in_history as skill_module
from ovos_skill_days_in_history import TodayInHistory

LOCALE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                      "locale")
SHIPS_THE_FILE = ("en-US", "de-DE")


def _locales():
    return sorted(d for d in os.listdir(LOCALE)
                  if os.path.isdir(os.path.join(LOCALE, d)))


def _fake(lang, resource_path):
    fake = SimpleNamespace()
    fake.lang = lang
    fake.speak_dialog = MagicMock()
    fake.find_resource = MagicMock(return_value=resource_path)
    return fake


def test_the_date_is_spoken_when_the_locale_ships_the_carrier():
    path = os.path.join(LOCALE, "en-US", "date_intro.dialog")
    fake = _fake("en-US", path)

    TodayInHistory._announce_date(fake, datetime.datetime(2020, 2, 3))

    fake.speak_dialog.assert_called_once()
    key, data = fake.speak_dialog.call_args[0]
    assert key == "date_intro"
    # The day and the month are what the report asked for. Assert they are in
    # the rendered date, not that the call happened.
    assert "third" in data["date"] and "february" in data["date"].lower(), data["date"]


def test_a_locale_without_the_carrier_stays_silent():
    """The control: no file means no speech, not a spoken resource name."""
    fake = _fake("it-IT", None)

    TodayInHistory._announce_date(fake, datetime.datetime(2020, 2, 3))

    fake.speak_dialog.assert_not_called()


@pytest.mark.parametrize("lang", _locales())
def test_the_carrier_carries_a_literal_word_and_the_date_slot(lang):
    """A slot-only `{date}` file is refused by ovos-spec-lint, and a carrier
    with no slot would announce nothing. Every shipped file needs both."""
    path = os.path.join(LOCALE, lang, "date_intro.dialog")
    if lang not in SHIPS_THE_FILE:
        assert not os.path.isfile(path), (
            f"{lang} ships date_intro.dialog but is not in SHIPS_THE_FILE; "
            "add it there in the same commit, so this row keeps naming the "
            "locales a native speaker has actually written a line for")
        return
    assert os.path.isfile(path), f"{lang} is listed as shipping the file and does not"
    with open(path, encoding="utf-8") as f:
        lines = [ln.strip() for ln in f
                 if ln.strip() and not ln.strip().startswith("#")]
    assert lines, f"{lang}: date_intro.dialog is empty"
    for line in lines:
        assert "{date}" in line, f"{lang}: {line!r} has no date slot"
        assert line.replace("{date}", "").strip(), \
            f"{lang}: {line!r} is slot-only, which ovos-spec-lint refuses"
