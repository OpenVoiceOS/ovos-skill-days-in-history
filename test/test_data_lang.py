"""A locale without per-day event dialogs answers from the en-US events."""
import datetime
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ovos_skill_days_in_history import TodayInHistory


def _skill(lang, has_events):
    fake = SimpleNamespace(lang=lang)
    fake.find_resource = MagicMock(return_value="x.dialog" if has_events else None)
    fake.speak = MagicMock()
    fake.speak_dialog = MagicMock()
    fake.get_date = MagicMock(return_value=datetime.datetime(2000, 10, 10))
    fake.pronounce_year = TodayInHistory.pronounce_year
    fake._data_lang = lambda: TodayInHistory._data_lang(fake)
    fake._dialog_lines = MagicMock(return_value=["1492 - The crew mutinies."])
    return fake


def test_locale_with_events_keeps_its_language():
    assert TodayInHistory._data_lang(_skill("de-DE", True)) == "de-DE"


def test_locale_without_events_falls_back_to_en_us():
    assert TodayInHistory._data_lang(_skill("pl-PL", False)) == "en-US"


def test_today_in_history_speaks_en_us_event_for_locale_without_events():
    fake = _skill("pl-PL", False)
    with patch("ovos_skill_days_in_history.SessionManager") as sm:
        TodayInHistory.handle_today_in_history_intent(fake, SimpleNamespace(data={}))
    fake._dialog_lines.assert_called_once_with("day_10_month_10_events", "en-US")
    assert "The crew mutinies." in fake.speak.call_args[0][0]
    fake.speak_dialog.assert_not_called()
    sm.get.return_value.set_intent_context.assert_called_once_with(
        "prev_dialog", {"value": "day_10_month_10_events", "seen": []},
        scope="shared", turns_remaining=3)


def test_tell_me_more_after_the_fallback_reads_en_us_events():
    fake = _skill("kab", False)
    fake._dialog_lines = MagicMock(return_value=["1492 - The crew mutinies."])
    session = MagicMock()
    session.intent_context = {"prev_dialog": {
        "value": {"value": "day_10_month_10_events", "seen": []}, "turns_remaining": 3}}
    with patch("ovos_skill_days_in_history.SessionManager") as sm:
        sm.get.return_value = session
        TodayInHistory.handle_tell_me_more_intent(fake, MagicMock())
    fake._dialog_lines.assert_called_once_with("day_10_month_10_events", "en-US")
    assert "The crew mutinies." in fake.speak.call_args[0][0]
    fake.speak_dialog.assert_not_called()


def test_today_in_history_without_data_speaks_unknown_date():
    fake = _skill("pl-PL", False)
    fake._dialog_lines = MagicMock(return_value=[])
    with patch("ovos_skill_days_in_history.SessionManager") as sm:
        TodayInHistory.handle_today_in_history_intent(fake, SimpleNamespace(data={}))
    fake.speak_dialog.assert_called_once_with("unknown_date")
    sm.get.return_value.set_intent_context.assert_not_called()
