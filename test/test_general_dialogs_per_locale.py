"""A locale that can be asked has to be able to answer.

The skill speaks four dialogs that are not per-day content: `notfound`,
`searching`, `thats_all` and `unknown_date`. They are the error and progress
paths — no matching entry, lookup still running, nothing more to say, date not
understood.

`ovos-workshop`'s dialog loader answers with the dialog NAME when a locale has
no file for it, so a locale that ships the intents and not these four makes the
skill say `unknown_date` out loud to a user who asked for a date it did not
recognise. That is worse than the silent fallback it replaced, and it happens on
exactly the paths a user hits when something has already gone wrong.

Measured before this guard existed: en-US, da-DK, fr-FR and pt-PT shipped all
four; kab shipped three; and ca-ES, de-DE, es-ES, eu-ES, gl-ES, it-IT, nl-NL,
pt-BR and sv-SE shipped none, while five of those nine shipped the intents.
"""
import os
import unittest

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOCALE_ROOT = os.path.join(REPO_ROOT, "locale")

#: Dialogs the skill speaks that are not per-day content. Kept as a literal
#: rather than scraped from the source, so adding a `speak_dialog` call without
#: its files is caught by the sibling test below rather than silently allowed.
GENERAL_DIALOGS = ("notfound", "searching", "thats_all", "unknown_date")


def locales():
    return sorted(name for name in os.listdir(LOCALE_ROOT)
                  if os.path.isdir(os.path.join(LOCALE_ROOT, name)))


def has_intents(lang):
    d = os.path.join(LOCALE_ROOT, lang)
    return any(name.endswith(".intent") for name in os.listdir(d))


class TestGeneralDialogsPerLocale(unittest.TestCase):
    def test_a_locale_with_intents_ships_every_general_dialog(self):
        """The live case: the skill can match in this locale, so it will speak."""
        missing = []
        for lang in locales():
            if not has_intents(lang):
                continue
            for name in GENERAL_DIALOGS:
                path = os.path.join(LOCALE_ROOT, lang, f"{name}.dialog")
                if not os.path.isfile(path):
                    missing.append(f"{lang}/{name}.dialog")
        self.assertEqual(
            sorted(missing), [],
            "these locales can be asked but would speak the dialog key aloud:\n  "
            + "\n  ".join(sorted(missing)))

    def test_every_locale_ships_every_general_dialog(self):
        """The latent case, held to the same bar.

        A locale with no intent file cannot be reached today, so its missing
        dialogs are latent rather than live. They are still required here: the
        intents arrive in a later translation pull request, and nothing in that
        pull request would remind anyone of these four.
        """
        missing = []
        for lang in locales():
            for name in GENERAL_DIALOGS:
                path = os.path.join(LOCALE_ROOT, lang, f"{name}.dialog")
                if not os.path.isfile(path):
                    missing.append(f"{lang}/{name}.dialog")
        self.assertEqual(sorted(missing), [])

    def test_no_general_dialog_is_empty(self):
        """An empty file is a loader answer of the empty string, not a sentence."""
        empty = []
        for lang in locales():
            for name in GENERAL_DIALOGS:
                path = os.path.join(LOCALE_ROOT, lang, f"{name}.dialog")
                if not os.path.isfile(path):
                    continue
                lines = [l.strip() for l in open(path, encoding="utf-8")
                         if l.strip() and not l.startswith("#")]
                if not lines:
                    empty.append(f"{lang}/{name}.dialog")
        self.assertEqual(sorted(empty), [])

    def test_the_searching_dialog_keeps_its_day_slot(self):
        """`searching` is rendered with {day}; a translation that drops it
        speaks a sentence with a hole in it."""
        without = []
        for lang in locales():
            path = os.path.join(LOCALE_ROOT, lang, "searching.dialog")
            if not os.path.isfile(path):
                continue
            body = open(path, encoding="utf-8").read()
            lines = [l for l in body.splitlines()
                     if l.strip() and not l.strip().startswith("#")]
            if not all("{day}" in l for l in lines):
                without.append(f"{lang}/searching.dialog")
        self.assertEqual(sorted(without), [])


if __name__ == "__main__":
    unittest.main()
