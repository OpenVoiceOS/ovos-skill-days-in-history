"""A locale with the intents and no day files must not read the key aloud.

`kab` ships `births_in_history.intent`, `deaths_in_history.intent`,
`today_in_history.intent` and `unknown_date.dialog`, and none of the 1098
`day_*.dialog` files. `ca-ES` ships 550 of the 1098. For a date such a locale has no
file for, `dialog_renderer.render("day_25_month_9_births")` returns the KEY, so
`speak_dialog` speaks "day 25 month 9 births" at the user.

`handle_deaths_intent` always checked the file first. `handle_births_intent` and
`handle_today_in_history_intent` did not, which is the defect these tests pin.

The first test is the control for the other three: it renders through the real
`MustacheDialogRenderer` the skill uses, and shows the key coming back for a
missing dialog in kab AND a real sentence coming back for the same key in en-US.
Without that pair, a test asserting "the key is not spoken" could pass because
the renderer was never exercised.
"""
import os
import shutil
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest
from ovos_workshop.resource_files import SkillResources

import ovos_skill_days_in_history as module_under_test
from ovos_skill_days_in_history import TodayInHistory
from ovos_workshop.resource_files import locate_lang_directories

SKILL_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKILL_ID = "ovos-skill-days-in-history.openvoiceos"
MISSING = "day_25_month_9_births"


def _renderer(lang):
    return SkillResources(SKILL_DIR, lang, skill_id=SKILL_ID).dialog_renderer


def test_renderer_returns_the_key_for_a_locale_with_no_day_files():
    """The mechanism, with en-US as the positive control."""
    kab = _renderer("kab")
    en = _renderer("en-US")
    assert kab is not None and en is not None, "both locales must load a renderer"

    # kab has no day_* file at all: the renderer hands back the key itself
    assert kab.render(MISSING, {}) == MISSING

    # en-US has the file: the same call renders a real sentence, so the probe
    # above is measuring a missing resource and not a broken renderer
    rendered = en.render(MISSING, {})
    assert rendered != MISSING and len(rendered) > len(MISSING)

    # and every locale ships unknown_date, which is what the guard must speak
    assert kab.render("unknown_date", {}) != "unknown_date"


def _fake_skill(lang="kab"):
    fake = SimpleNamespace()
    fake.lang = lang
    fake.speak = MagicMock()
    fake.speak_dialog = MagicMock()
    fake._speak_dialog_safe = MagicMock()
    fake.get_date = MagicMock(return_value=SimpleNamespace(day=25, month=9))
    fake.pronounce_year = TodayInHistory.pronounce_year
    # kept conditional so this exact file also runs against a tree without the
    # guard: there it must FAIL on births and events, which is the failing-first
    # control a reviewer can reproduce without editing the test
    if hasattr(TodayInHistory, '_day_dialog_exists'):
        fake._day_dialog_exists = lambda dialog: TodayInHistory._day_dialog_exists(fake, dialog)
    return fake


@pytest.mark.parametrize("handler,suffix", [
    (TodayInHistory.handle_births_intent, "births"),
    (TodayInHistory.handle_today_in_history_intent, "events"),
    (TodayInHistory.handle_deaths_intent, "deaths"),
])
def test_missing_day_file_speaks_unknown_date(handler, suffix, monkeypatch):
    """No handler may pass a per-day dialog name to the speak path when the
    locale does not ship that file."""
    import ovos_skill_days_in_history as module

    session = MagicMock()
    monkeypatch.setattr(module.SessionManager, "get", MagicMock(return_value=session))

    fake = _fake_skill()
    handler(fake, MagicMock())

    fake.speak_dialog.assert_called_once_with("unknown_date")
    assert not fake._speak_dialog_safe.called, (
        f"the {suffix} handler reached the speak path with a dialog this locale "
        f"does not ship, so the resource name is spoken aloud"
    )
    # a follow-up "tell me more" must not be armed against a dialog that is absent
    session.remove_intent_context.assert_called_once_with("prev_dialog", scope="shared")
    assert not session.set_intent_context.called


def test_day_file_present_still_speaks_the_day_dialog(monkeypatch):
    """The guard must not swallow the normal path: en-US has this file."""
    import ovos_skill_days_in_history as module

    session = MagicMock()
    monkeypatch.setattr(module.SessionManager, "get", MagicMock(return_value=session))

    fake = _fake_skill(lang="en-US")
    TodayInHistory.handle_births_intent(fake, MagicMock())

    assert not fake.speak_dialog.called, "unknown_date must not be spoken here"
    fake._speak_dialog_safe.assert_called_once()
    (spoken_dialog,), _ = fake._speak_dialog_safe.call_args
    assert spoken_dialog == MISSING
    session.set_intent_context.assert_called_once()


def _locales():
    locale_dir = os.path.join(SKILL_DIR, "locale")
    return sorted(d for d in os.listdir(locale_dir)
                  if os.path.isdir(os.path.join(locale_dir, d)))


@pytest.mark.parametrize("lang", _locales())
def test_no_locale_can_speak_a_bare_resource_name(lang):
    """Per locale: wherever the renderer would hand back the key, the guard must
    already have said no, and the dialog it falls back to must be real text.

    This is the sibling assertion for the golden runner's blind spot. The runner
    reads the routed message types and never the spoken string, so a locale that
    answers with "day 25 month 9 births" passes it. Here the two are tied
    together: `_day_dialog_exists` is checked against what the renderer actually
    does for every per-day key at month boundaries, for every locale that ships.
    """
    fake = SimpleNamespace(lang=lang)
    renderer = _renderer(lang)
    assert renderer is not None, f"{lang}: no dialog renderer"

    disagreements = []
    for month, day in ((1, 1), (2, 29), (6, 15), (9, 25), (12, 31)):
        for suffix in ("births", "deaths", "events"):
            key = f"day_{day}_month_{month}_{suffix}"
            renders_key = renderer.render(key, {}) == key
            guard_says_present = TodayInHistory._day_dialog_exists(fake, key)
            if renders_key == guard_says_present:
                disagreements.append(
                    f"{lang}/{key}: renderer_returns_key={renders_key} "
                    f"guard_says_file_exists={guard_says_present}")
    assert not disagreements, (
        "the guard must say 'absent' for exactly the keys the renderer cannot "
        "render: " + "; ".join(disagreements))


# The five locales below ship the three `.intent` files and no
# `unknown_date.dialog`, so the fallback this guard speaks renders as its own
# key there. That is a locale resource gap, not a handler defect, and it is not
# this lane's to translate. The check is kept and marked expected-to-fail so it
# stays visible: it turns into XPASS the day the files land.
MISSING_UNKNOWN_DATE = ("ca-ES", "de-DE", "es-ES", "eu-ES", "gl-ES")


def test_the_missing_unknown_date_list_is_still_accurate():
    """The tuple above must name exactly the locales that lack the file.

    PR #121 adds `unknown_date.dialog` to all five of these. Because the marker
    below is `strict=True`, an XPASS is a failure, so without this row whichever
    of the two PRs merges second turns five parametrised rows red with reasons
    that point at the locale and not at the cause. This row fails first, once,
    and says what to do. Keep the tuple, do not compute the xfail set from the
    filesystem: a self-erasing expectation would stop reporting the gap at all.
    """
    actual = tuple(l for l in _locales()
                   if _renderer(l).render("unknown_date", {}) == "unknown_date")
    assert actual == MISSING_UNKNOWN_DATE, (
        "MISSING_UNKNOWN_DATE is stale. Locales that ship no usable "
        f"unknown_date.dialog are now {actual!r}. Set the tuple to that value "
        "in the same commit that changes which locales ship the file "
        "(see T-5140 and PR #121).")


@pytest.mark.parametrize("lang", _locales())
def test_unknown_date_is_real_text_in_every_locale(lang, request):
    """The guard has to fall back to something a listener understands."""
    if lang in MISSING_UNKNOWN_DATE:
        request.applymarker(pytest.mark.xfail(
            strict=True,
            reason=f"{lang} ships no unknown_date.dialog; tracked for the "
                   f"locale lane, the handler guard cannot fix it here"))
    renderer = _renderer(lang)
    assert renderer is not None, f"{lang}: no dialog renderer"
    assert renderer.render("unknown_date", {}) != "unknown_date", \
        f"{lang}: unknown_date.dialog is missing, so the guard has nothing to speak"


# A lang is not always a directory name. `self.lang` is
# `standardize_lang(get_message_lang(message))`, which normalises case and
# separator and does NOT add a region, so a device configured `lang: "en"` asks
# for `en` and the loader answers out of `locale/en-US`. The rows above
# parametrise `_locales()`, i.e. directory names only, so they cannot see a
# guard that resolves the directory by hand. These do.
BARE_SUBTAGS = ("en", "pt", "ca", "de", "kab")


@pytest.mark.parametrize("lang", BARE_SUBTAGS)
def test_guard_agrees_with_the_renderer_for_a_bare_primary_subtag(lang):
    """The guard must answer for the directory the LOADER would use.

    `kab` is in this list on purpose: it is both a bare subtag and a real
    directory name, so it is the row that fails if the resolution ever falls
    through to an unrelated language (`find_resource` hands `kab` the `ca-ES`
    file, which would speak Catalan at a Kabyle user).
    """
    renderer = _renderer(lang)
    assert renderer is not None, f"{lang}: the loader resolves no renderer"

    fake = SimpleNamespace(lang=lang)
    renders_key = renderer.render(MISSING, {}) == MISSING
    guard_says_present = TodayInHistory._day_dialog_exists(fake, MISSING)
    assert renders_key != guard_says_present, (
        f"{lang}: renderer_returns_key={renders_key} but "
        f"guard_says_file_exists={guard_says_present}; the guard resolved a "
        f"different locale directory than the renderer did")


def test_a_bare_subtag_still_speaks_the_day_dialog(monkeypatch):
    """The regression this pins: `en` must speak the sentence en-US ships, not
    the not-found fallback."""
    import ovos_skill_days_in_history as module
    monkeypatch.setattr(module.SessionManager, "get", MagicMock(return_value=MagicMock()))

    fake = _fake_skill(lang="en")
    TodayInHistory.handle_births_intent(fake, MagicMock())

    assert not fake.speak_dialog.called, (
        "lang 'en' resolves to locale/en-US, which ships this day file, so the "
        "handler must not fall back to unknown_date")
    fake._speak_dialog_safe.assert_called_once()


def test_the_guard_binds_the_first_matched_directory(tmp_path, monkeypatch):
    """A lang that matches two locale directories must be answered for the one
    the loader binds, not for whichever of them happens to hold the file.

    #121 adds `pt-BR` with the intents and no `day_*` files, beside `pt-PT`
    which ships 1098. `locate_lang_directories("pt-BR", ...)` returns
    `[pt-BR, pt-PT]`, the renderer binds `pt-BR` and returns the KEY, so a
    guard that asked `any()` over both would report present and let the skill
    read `day_25_month_9_births` aloud at a Brazilian user.

    Built on a copy of the tree so it pins the behaviour before #121 lands and
    keeps holding after.
    """
    tree = tmp_path / "skill"
    shutil.copytree(os.path.join(SKILL_DIR, "locale"), tree / "locale",
                    ignore=shutil.ignore_patterns("day_*"))
    # pt-PT keeps its day files, pt-BR ships none: the shape #121 creates
    shutil.copy(os.path.join(SKILL_DIR, "locale", "en-US", f"{MISSING}.dialog"),
                tree / "locale" / "pt-PT" / f"{MISSING}.dialog")
    (tree / "locale" / "pt-BR").mkdir(exist_ok=True)
    (tree / "locale" / "pt-BR" / "unknown_date.dialog").write_text("nao sei\n")

    fake = SimpleNamespace(lang="pt-BR")
    monkeypatch.setattr(module_under_test, "__file__", str(tree / "__init__.py"))

    order = [d.name for d in locate_lang_directories("pt-BR", str(tree))]
    assert order[0] == "pt-BR" and "pt-PT" in order, (
        f"this test only means something while pt-BR matches both: {order}")
    assert TodayInHistory._day_dialog_exists(fake, MISSING) is False, (
        "the guard answered for pt-PT, which holds the file, while the loader "
        "binds pt-BR, which does not")
