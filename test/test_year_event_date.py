"""The date spoken before a year's event names the event's own day and month."""
import datetime
from pathlib import Path
from types import SimpleNamespace

import pytest
from ovos_bus_client.message import Message
from ovos_date_parser import nice_date

from ovos_skill_days_in_history import TodayInHistory

LOCALES = sorted(path.name for path in (Path(__file__).parents[1] / "locale").iterdir() if path.is_dir())


def _speak_event(lang, month, day, year=1492):
    """Run the year handler on a year whose only event falls on month/day."""
    spoken = []
    fake = SimpleNamespace(
        _get_year=lambda message: year,
        _events_by_year=lambda: {year: [(month, day, f"{year} - the event")]},
        _data_lang=lambda: lang,
        pronounce_year=TodayInHistory.pronounce_year,
        speak=spoken.append,
        voc_match=lambda *args, **kwargs: False,
    )
    TodayInHistory.handle_year_in_history_intent(fake, Message("x", {"utterance": "year"}))
    assert len(spoken) == 1
    return spoken[0]


@pytest.mark.parametrize("lang, month, day, spoken_date", [
    ("en-US", 1, 1, "january first"),
    ("en-US", 1, 2, "january second"),
    ("en-US", 1, 15, "january fifteenth"),
    ("en-US", 12, 31, "december thirty-first"),
    ("de-DE", 1, 1, "erster Januar"),
    ("de-DE", 1, 2, "zweiter Januar"),
    ("de-DE", 1, 15, "fünfzehnter Januar"),
    ("pt-PT", 1, 1, "um de Janeiro"),
    ("pt-PT", 1, 2, "dois de Janeiro"),
    ("pt-PT", 1, 15, "quinze de Janeiro"),
])
def test_event_date_names_the_day_and_month(lang, month, day, spoken_date):
    assert _speak_event(lang, month, day).startswith(f"{spoken_date}, ")


@pytest.mark.parametrize("lang", LOCALES)
@pytest.mark.parametrize("day", [1, 2, 3, 15, 28])
def test_event_date_in_every_locale_is_neither_relative_nor_missing_the_month(lang, day):
    january = _speak_event(lang, 1, day)
    other_months = {_speak_event(lang, month, day).split(",")[0] for month in range(2, 13)}
    assert january.split(",")[0] not in other_months, january
    event = datetime.datetime(1492, 1, day)
    for offset in (-1, 0, 1):
        relative = nice_date(event, lang=lang, now=event + datetime.timedelta(days=offset),
                             include_weekday=False)
        assert not january.startswith(f"{relative}, "), (january, relative)
