"""Regression test for the live finding in the gate ledger
(live-ovos-skill-days-in-history-93.md, cell 3): `handle_deaths_intent`
passed no `render_callback` to `_speak_dialog_safe`, so a deaths line spoke
its year unpronounced (e.g. "1996") while `handle_births_intent`, which
does pass `pronounce_year`, spoke it as words. Both handlers must render
the year the same way.

Drives `TodayInHistory.handle_deaths_intent` and `.handle_births_intent`
directly against a bare stand-in object -- the handlers only touch
`self.get_date`, `self.lang`, `self._speak_dialog_safe`/`self.speak_dialog`,
and `SessionManager` -- with a fixed date and a stubbed data source (a real
`.dialog` file for that date, written to a temp locale directory the stub
points `__file__`-style lookups at is unnecessary since `_speak_dialog_safe`
itself is stubbed to capture the render callback and apply it, exactly like
the real one does).
"""
import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock

import ovos_skill_days_in_history as skill_module
from ovos_skill_days_in_history import TodayInHistory


def _make_fake(monkeypatch, dialog_line, isfile=True):
    fake = SimpleNamespace()
    fake.lang = "en-US"
    fake.get_date = MagicMock(return_value=datetime.date(2020, 2, 3))
    fake.speak_dialog = MagicMock()
    fake.pronounce_year = TodayInHistory.pronounce_year

    captured = {}

    def fake_speak_dialog_safe(dialog, render_callback=None):
        captured["dialog"] = dialog
        captured["render_callback"] = render_callback
        captured["spoken"] = render_callback(dialog_line, fake.lang) if render_callback else dialog_line

    fake._speak_dialog_safe = fake_speak_dialog_safe

    monkeypatch.setattr(skill_module.os.path, "isfile", lambda *_a, **_k: isfile)

    session = MagicMock()
    monkeypatch.setattr(skill_module, "SessionManager",
                         SimpleNamespace(get=MagicMock(return_value=session)))

    return fake, captured


def test_births_intent_pronounces_year(monkeypatch):
    fake, captured = _make_fake(monkeypatch, "1996 - Birthday of someone.")

    TodayInHistory.handle_births_intent(fake, MagicMock())

    expected = TodayInHistory.pronounce_year("1996 - Birthday of someone.", "en-US")
    assert expected.split(" - ")[0] in captured["spoken"]


def test_deaths_intent_pronounces_year(monkeypatch):
    fake, captured = _make_fake(monkeypatch, "1996 - Death of someone.")

    TodayInHistory.handle_deaths_intent(fake, MagicMock())

    expected = TodayInHistory.pronounce_year("1996 - Death of someone.", "en-US")
    assert expected.split(" - ")[0] in captured["spoken"]
