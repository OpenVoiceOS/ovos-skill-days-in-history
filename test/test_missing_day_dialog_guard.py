"""A locale with the intents and no per-day files must not read the key aloud.

`kab` ships `births_in_history.intent` and `deaths_in_history.intent` and none
of the 1098 `day_*.dialog` files. For a missing dialog the renderer returns
the key, so `speak_dialog` would say "day_25_month_9_births" to the user.
The births and deaths handlers check the file first and speak
`unknown_date` instead.
"""
import os
import shutil
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from ovos_workshop.resource_files import SkillResources, locate_lang_directories

import ovos_skill_days_in_history as skill_module
from ovos_skill_days_in_history import TodayInHistory

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_ID = "ovos-skill-days-in-history.openvoiceos"
MISSING = "day_25_month_9_births"
LOCALES = sorted(d for d in os.listdir(os.path.join(SKILL_DIR, "locale"))
                 if os.path.isdir(os.path.join(SKILL_DIR, "locale", d)))


def _renderer(lang):
    return SkillResources(SKILL_DIR, lang, skill_id=SKILL_ID).dialog_renderer


def _fake_skill(lang):
    fake = SimpleNamespace(lang=lang)
    fake.speak_dialog = MagicMock()
    fake._speak_dialog_safe = MagicMock()
    fake.get_date = MagicMock(return_value=SimpleNamespace(day=25, month=9))
    fake.pronounce_year = TodayInHistory.pronounce_year
    fake._day_dialog_exists = lambda dialog: TodayInHistory._day_dialog_exists(fake, dialog)
    return fake


@pytest.fixture
def session(monkeypatch):
    session = MagicMock()
    monkeypatch.setattr(skill_module.SessionManager, "get", MagicMock(return_value=session))
    return session


def test_renderer_returns_the_key_for_a_locale_with_no_day_files():
    """The mechanism, with en-US as the positive control."""
    assert _renderer("kab").render(MISSING, {}) == MISSING
    rendered = _renderer("en-US").render(MISSING, {})
    assert rendered != MISSING and rendered.split(" - ")[0].isdigit()


@pytest.mark.parametrize("handler", [TodayInHistory.handle_births_intent,
                                     TodayInHistory.handle_deaths_intent],
                         ids=["births", "deaths"])
def test_missing_day_file_speaks_unknown_date(handler, session):
    fake = _fake_skill("kab")
    handler(fake, MagicMock())

    fake.speak_dialog.assert_called_once_with("unknown_date")
    fake._speak_dialog_safe.assert_not_called()
    session.remove_intent_context.assert_called_once_with("prev_dialog", scope="shared")
    session.set_intent_context.assert_not_called()


@pytest.mark.parametrize("lang", ["en-US", "en", "pt"])
@pytest.mark.parametrize("handler,suffix", [(TodayInHistory.handle_births_intent, "births"),
                                            (TodayInHistory.handle_deaths_intent, "deaths")],
                         ids=["births", "deaths"])
def test_present_day_file_speaks_the_day_dialog(handler, suffix, lang, session):
    """A bare subtag resolves to the directory the loader uses, so `en` and
    `pt` speak the day the skill ships for them."""
    fake = _fake_skill(lang)
    handler(fake, MagicMock())

    fake.speak_dialog.assert_not_called()
    (spoken,), _ = fake._speak_dialog_safe.call_args
    assert spoken == f"day_25_month_9_{suffix}"
    session.set_intent_context.assert_called_once()


@pytest.mark.parametrize("lang", LOCALES + ["en", "pt", "ca", "de"])
def test_the_guard_agrees_with_the_renderer(lang):
    """The guard says absent for exactly the keys the renderer cannot render."""
    renderer = _renderer(lang)
    fake = SimpleNamespace(lang=lang)
    disagreements = []
    for month, day in ((1, 1), (2, 29), (6, 15), (9, 25), (12, 31)):
        for suffix in ("births", "deaths", "events"):
            key = f"day_{day}_month_{month}_{suffix}"
            renders_key = renderer.render(key, {}) == key
            if renders_key == TodayInHistory._day_dialog_exists(fake, key):
                disagreements.append(f"{key}: renderer_returns_key={renders_key}")
    assert not disagreements, f"{lang}: " + "; ".join(disagreements)


@pytest.mark.parametrize("lang", LOCALES)
def test_unknown_date_is_real_text_in_every_locale(lang):
    assert _renderer(lang).render("unknown_date", {}) != "unknown_date"


def test_the_guard_binds_the_first_matched_directory(tmp_path, monkeypatch):
    """A bare `pt` matches `pt-PT` and `pt-BR`. When only the second one ships
    a day file, the loader still reads the first, renders the key, and the
    guard must say absent."""
    tree = tmp_path / "skill"
    shutil.copytree(os.path.join(SKILL_DIR, "locale"), tree / "locale",
                    ignore=shutil.ignore_patterns("day_*"))
    shutil.copy(os.path.join(SKILL_DIR, "locale", "en-US", f"{MISSING}.dialog"),
                tree / "locale" / "pt-BR" / f"{MISSING}.dialog")
    monkeypatch.setattr(skill_module, "__file__", str(tree / "__init__.py"))

    order = [d.name for d in locate_lang_directories("pt", str(tree))]
    assert len(order) == 2 and order[1] == "pt-BR", order
    renderer = SkillResources(str(tree), "pt", skill_id=SKILL_ID).dialog_renderer
    assert renderer.render(MISSING, {}) == MISSING
    assert TodayInHistory._day_dialog_exists(SimpleNamespace(lang="pt"), MISSING) is False
    assert TodayInHistory._day_dialog_exists(SimpleNamespace(lang="pt-BR"), MISSING) is True
