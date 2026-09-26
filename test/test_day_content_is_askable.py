"""A locale that ships day content has to be askable.

`locale/<lang>/day_<d>_month_<m>_<role>.dialog` is the answer. The four intent
files are the question. A locale with 1098 day dialogs and no intent file ships
1098 unreachable answers: the skill cannot match anything in that language, so
none of that content can ever be spoken.

Measured at `origin/dev` before this guard: it-IT, nl-NL, pt-BR and sv-SE each
held 1098 day dialogs and zero intent files, which is 4392 unreachable files.
`kab` is the deliberate exception -- it ships 3 intents and 3 day files, a stub
locale rather than a full one, and is named below rather than skipped by a
count, so filling it in fails this test and someone removes it from the list.
"""
import os
import re
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALE_ROOT = os.path.join(REPO_ROOT, "locale")

DAY_FILE = re.compile(r"^day_\d+_month_\d+_(births|deaths|events)\.dialog$")

#: The four intents the skill registers. A locale that ships day content and
#: not these cannot be asked for it.
INTENTS = ("births_in_history", "deaths_in_history", "today_in_history",
           "tell_me_more_intent")

#: Locales that ship a handful of day files rather than the full set, and are
#: not expected to carry every intent yet. Named rather than inferred, so that
#: a locale filling in trips this list instead of silently leaving it.
STUB_LOCALES = ("kab",)

#: How many day files make a locale a real one rather than a stub.
FULL_LOCALE_DAY_FILES = 100

#: Locales whose births and deaths intents ask only about today: the single
#: line they ship carries no {date} slot, so "who was born on 5 May" cannot be
#: asked in them. Measured 2026-09-26 and filed; named here rather than skipped
#: so that the gap is visible and a locale that gains the slot trips the list.
NO_DATE_SLOT = {}


def locales():
    return sorted(name for name in os.listdir(LOCALE_ROOT)
                  if os.path.isdir(os.path.join(LOCALE_ROOT, name)))


def day_file_count(lang):
    return sum(1 for name in os.listdir(os.path.join(LOCALE_ROOT, lang))
               if DAY_FILE.match(name))


def intents_of(lang):
    return {name[:-len(".intent")]
            for name in os.listdir(os.path.join(LOCALE_ROOT, lang))
            if name.endswith(".intent")}


class TestEveryLocaleWithDayContentIsAskable(unittest.TestCase):
    def test_a_locale_with_day_files_ships_the_intents(self):
        unreachable = []
        for lang in locales():
            if lang in STUB_LOCALES:
                continue
            days = day_file_count(lang)
            if days < FULL_LOCALE_DAY_FILES:
                continue
            missing = sorted(set(INTENTS) - intents_of(lang))
            if missing:
                unreachable.append(
                    f"{lang}: {days} day files and no {', '.join(missing)}")
        self.assertEqual(
            unreachable, [],
            "these locales ship day content nobody can ask for:\n  "
            + "\n  ".join(unreachable))

    def test_the_stub_list_is_still_accurate(self):
        """Fails when a stub locale fills in, so the exemption cannot go stale."""
        stubs = tuple(lang for lang in locales()
                      if day_file_count(lang) < FULL_LOCALE_DAY_FILES)
        self.assertEqual(
            STUB_LOCALES, stubs,
            f"locales below {FULL_LOCALE_DAY_FILES} day files are now {stubs}; "
            "set STUB_LOCALES to that in the same commit that changes which "
            "locales ship day content")

    def test_no_intent_file_is_empty(self):
        empty = []
        for lang in locales():
            for name in sorted(intents_of(lang)):
                path = os.path.join(LOCALE_ROOT, lang, f"{name}.intent")
                lines = [l.strip() for l in open(path, encoding="utf-8")
                         if l.strip() and not l.startswith("#")]
                if not lines:
                    empty.append(f"{lang}/{name}.intent")
        self.assertEqual(sorted(empty), [])

    def test_every_intent_file_keeps_the_date_slot_where_en_us_has_it(self):
        """The dated question is half the skill; a translation that drops
        {date} leaves only "today"."""
        reference = {name for name in INTENTS
                     if "{date}" in open(os.path.join(
                         LOCALE_ROOT, "en-US", f"{name}.intent"),
                         encoding="utf-8").read()}
        without = []
        for lang in locales():
            if lang in STUB_LOCALES:
                continue
            allowed = set(NO_DATE_SLOT.get(lang, ()))
            for name in sorted(reference & intents_of(lang)):
                body = open(os.path.join(LOCALE_ROOT, lang, f"{name}.intent"),
                            encoding="utf-8").read()
                if "{date}" not in body and name not in allowed:
                    without.append(f"{lang}/{name}.intent")
        self.assertEqual(sorted(without), [])

    def test_the_no_date_slot_list_is_still_accurate(self):
        """Fails when a listed locale gains the slot, or another loses it."""
        reference = {name for name in INTENTS
                     if "{date}" in open(os.path.join(
                         LOCALE_ROOT, "en-US", f"{name}.intent"),
                         encoding="utf-8").read()}
        found = {}
        for lang in locales():
            if lang in STUB_LOCALES:
                continue
            missing = tuple(
                name for name in sorted(reference & intents_of(lang))
                if "{date}" not in open(os.path.join(
                    LOCALE_ROOT, lang, f"{name}.intent"), encoding="utf-8").read())
            if missing:
                found[lang] = missing
        self.assertEqual(
            NO_DATE_SLOT, found,
            "the locales asking only about today are now "
            f"{found}; set NO_DATE_SLOT to that in the same commit")


if __name__ == "__main__":
    unittest.main()
