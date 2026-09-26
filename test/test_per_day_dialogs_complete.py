"""Every locale that ships per-day dialogs ships the whole set, clean.

The handlers build ``day_<d>_month_<m>_<kind>`` and read
``locale/<lang>/<name>.dialog`` at the locale root. A missing file makes the
skill speak ``unknown_date``; an EMPTY file passes ``os.path.isfile`` and the
skill speaks nothing at all, which is worse. ca-ES shipped 295 such files.

The set is 366 days times three kinds (births, deaths, events), 1,098 files.
Four figures are measured per locale: files missing from the set, files
that are empty, lines with no ``YEAR - `` prefix, and lines that carry an
invisible character (a no-break space or a zero-width space, which
machine translation leaves in the year prefix and which are spoken as
nothing while breaking every exact match).

``KNOWN_GAPS`` is what each locale ships today. The figures must match
exactly: a new defect fails, and a repair fails too until its row is
lowered, so the table stays true and can only shrink. A locale absent from
the table must ship the full set with nothing empty, nothing invisible,
and no more unprefixed lines than the source. The source, en-US, is clean of invisible
characters and its 178 unprefixed lines are undated entries
(``Name, description, b. 1929.``), not lost years.

The prefix is the year, an optional era word in the locale's own spelling
(``BC``, ``f.Kr.``, ``aC``, ``BCE``), and a dash. A translated era and an en
dash are the locale's, and pass; the year must be there.
"""
import re
from pathlib import Path

import pytest

LOCALE = Path(__file__).resolve().parents[1] / "locale"
KINDS = ("births", "deaths", "events")
DAYS_IN_MONTH = (31, 29, 31, 30, 31, 30, 31, 31, 30, 31, 30, 31)
EXPECTED = {f"day_{d}_month_{m}_{k}.dialog"
            for m, n in enumerate(DAYS_IN_MONTH, start=1)
            for d in range(1, n + 1) for k in KINDS}
YEAR_PREFIX = re.compile(r"^\d{1,4}(,? or \d{1,4},)?( ?[A-Za-z.]{2,6})? ?[-–—] ?\S")
INVISIBLE = re.compile(r"[​‌‍﻿ ]")
PER_DAY = re.compile(r"^day_\d{1,2}_month_\d{1,2}_(births|deaths|events)\.dialog$")

#: What each locale ships today. Lower a figure when you repair it; never
#: raise one.
KNOWN_GAPS = {
    # ca-ES: missing fell 548 -> 0 when the per-day files landed, and the
    # unprefixed count rose with them. 15255 of these 15552 lines DO carry
    # their year and lose only the separator: "1344: Aniversari ..." uses a
    # colon where the pattern wants a dash. See SEPARATOR_GAPS below.
    "ca-ES": dict(missing=0, empty=0, unprefixed=15552, invisible=209),
    "da-DK": dict(missing=0, empty=0, unprefixed=395, invisible=2183),
    "en-US": dict(missing=0, empty=0, unprefixed=178, invisible=0),
    "fr-FR": dict(missing=0, empty=0, unprefixed=28, invisible=1263),
    # it-IT and nl-NL sit just above the source's 178, and almost all of the
    # excess is the same undated-entry shape en-US has (163 of it-IT's 182 and
    # 192 of nl-NL's 210 carry no year at all, like "Anna Walentynowicz, ...,
    # nato nel 1929."), not a lost year.
    "it-IT": dict(missing=0, empty=0, unprefixed=182, invisible=0),
    "nl-NL": dict(missing=0, empty=0, unprefixed=210, invisible=0),
    # pt-BR is the largest: 73063 of 76262 carry the year and no separator at
    # all, "1486 Aniversário ...".
    "pt-BR": dict(missing=0, empty=0, unprefixed=76262, invisible=0),
    "pt-PT": dict(missing=0, empty=0, unprefixed=407, invisible=594),
    # sv-SE: 164 of 421 are the colon form, "1906: Ezra Butler Eddys död, ...".
    "sv-SE": dict(missing=0, empty=0, unprefixed=421, invisible=0),
}

#: Of each locale's unprefixed lines, how many DO begin with a year and fail
#: only on the separator. This is recorded because the assertion message below
#: says "years were lost in translation", and for these locales that reading is
#: wrong: the year survived and the dash did not. Normalising the separator
#: would drop the unprefixed figures to roughly the difference.
SEPARATOR_GAPS = {
    "ca-ES": 15255,   # "1344: ..."  colon
    "pt-BR": 73063,   # "1486 ..."   no separator
    "sv-SE": 164,     # "1906: ..."  colon
    "it-IT": 19,
    "nl-NL": 18,
}
#: A locale with no row: the full set, nothing empty, nothing invisible,
#: and no more unprefixed lines than the source. The source's 178 are
#: undated entries a faithful translation carries one to one, so zero is
#: not the bar there; inventing a year for them would be.
SOURCE_UNPREFIXED = 178


def _per_day(lang: str) -> set:
    return {p.name for p in (LOCALE / lang).iterdir() if PER_DAY.match(p.name)}


def _measure(lang: str) -> dict:
    names = _per_day(lang)
    empty = unprefixed = invisible = 0
    for name in names:
        text = (LOCALE / lang / name).read_text(encoding="utf-8")
        if not text.strip():
            empty += 1
        for line in text.splitlines():
            if not line.strip() or line.startswith("#"):
                continue
            if not YEAR_PREFIX.match(line):
                unprefixed += 1
            if INVISIBLE.search(line):
                invisible += 1
    return dict(missing=len(EXPECTED - names), empty=empty,
                unprefixed=unprefixed, invisible=invisible)


LOCALES = sorted(p.name for p in LOCALE.iterdir() if p.is_dir())
SHIPPING = [l for l in LOCALES if _per_day(l)]


def test_the_expected_set_is_1098():
    """The control on the test itself: 366 days, three kinds, and en-US
    ships exactly those names."""
    assert len(EXPECTED) == 1098
    assert _per_day("en-US") == EXPECTED


def test_the_source_carries_no_invisible_character():
    """The source is what every translation is measured against."""
    assert _measure("en-US")["invisible"] == 0


@pytest.mark.parametrize("lang", SHIPPING)
def test_the_locale_ships_what_the_table_says_and_no_worse(lang):
    measured = _measure(lang)
    if lang in KNOWN_GAPS:
        expected = KNOWN_GAPS[lang]
        assert measured == expected, (
            f"{lang}: measured {measured}, table says {expected}. A higher figure "
            f"is a new defect; a lower one is a repair, lower the table with it.")
    else:
        assert measured["missing"] == 0, f"{lang}: {measured['missing']} files missing"
        assert measured["empty"] == 0, f"{lang}: {measured['empty']} empty files"
        assert measured["invisible"] == 0, f"{lang}: {measured['invisible']} lines with an invisible character"
        assert measured["unprefixed"] <= SOURCE_UNPREFIXED, (
            f"{lang}: {measured['unprefixed']} unprefixed lines, more than the "
            f"source's {SOURCE_UNPREFIXED}: years were lost in translation")


def test_every_table_row_names_a_shipping_locale():
    """A row for a locale that ships nothing, or no longer exists, is stale."""
    assert set(KNOWN_GAPS) <= set(SHIPPING), set(KNOWN_GAPS) - set(SHIPPING)
