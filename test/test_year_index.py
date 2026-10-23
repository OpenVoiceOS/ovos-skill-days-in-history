"""The year index holds every year that an event line of the locale starts with."""
import re
from pathlib import Path
from types import SimpleNamespace

import pytest

from ovos_skill_days_in_history import TodayInHistory

LOCALE_ROOT = Path(__file__).parents[1] / "locale"
LOCALES = sorted(path.name for path in LOCALE_ROOT.iterdir() if (path / "day_1_month_1_events.dialog").exists())


def _lines(lang):
    for path in sorted((LOCALE_ROOT / lang).glob("day_*_month_*_events.dialog")):
        yield from (line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                    if line.strip() and not line.startswith("#"))


def _index(lang):
    def dialog_lines(dialog, lang=lang):
        path = LOCALE_ROOT / lang / f"{dialog}.dialog"
        return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()
                if line.strip() and not line.startswith("#")] if path.exists() else []

    fake = SimpleNamespace(_year_index={}, _data_lang=lambda: lang, _dialog_lines=dialog_lines,
                           _era_pattern=TodayInHistory._era_pattern)
    return TodayInHistory._events_by_year(fake)


@pytest.mark.parametrize("lang", LOCALES)
def test_every_year_with_an_event_line_is_indexed(lang):
    # a line starts with its year, followed by a space, a dash or a colon
    expected = {int(match.group(1)) for line in _lines(lang)
                if (match := re.match(r"(\d{1,4})(?=[\s:\u2013-])", line))}
    indexed = {abs(year) for year in _index(lang)}
    assert expected - indexed == set(), f"{len(expected - indexed)} years have event lines and no index entry"


def test_the_separators_of_the_shipped_data_all_index():
    assert any(-660 in _index("pt-PT") for _ in [0])  # "660 AC \u2013 ..."
    assert 1293 in _index("ca-ES")                    # "1293: ..."
    assert 1471 in _index("pt-BR")                    # "1471 Sten Sture, ..."


def test_an_indexed_line_reads_year_dash_text():
    for lang in ("pt-BR", "ca-ES", "pt-PT", "en-US"):
        for year, events in _index(lang).items():
            for _, _, line in events:
                assert re.match(rf"{abs(year)}( BC)? - \S", line), line
                assert (" BC - " in line) == (year < 0), line
