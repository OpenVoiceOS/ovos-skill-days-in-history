"""Unit test for the tell-me-more repeat-avoidance mechanism.

Regression coverage for the in-source TODO ("add mechanism to avoid
repeated responses"): a consecutive "tell me more"/"another fact" follow-up
used to re-run `speak_dialog`, which picks a uniformly random line from the
`.dialog` file on every call -- nothing stopped it from repeating the exact
line just spoken. `handle_tell_me_more_intent` now tracks already-served
lines inside the `prev_dialog` context entry (`{"value": <dialog>, "seen":
[...]}`) and picks from the remaining, unseen lines, falling to the
"thats_all" dialog once every line has been served.

This drives `TodayInHistory.handle_tell_me_more_intent` directly against a
bare stand-in object (not a full OVOSSkill/MiniCroft instance), the same
pattern `test_dialog_tolerance.py` uses -- the handler only touches
`self.speak`, `self.find_resource`, `self.lang`, and the module-level
`SessionManager.get`, all trivial to stub.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from ovos_skill_days_in_history import TodayInHistory


def _fake_skill(dialog_file):
    fake = SimpleNamespace()
    fake.lang = "en-US"
    fake.speak = MagicMock()
    fake.speak_dialog = MagicMock()
    fake.find_resource = MagicMock(return_value=str(dialog_file))
    fake.pronounce_year = TodayInHistory.pronounce_year
    fake._dialog_lines = lambda dialog: TodayInHistory._dialog_lines(fake, dialog)
    return fake


def _fake_session(state):
    session = MagicMock()
    session.intent_context = {
        "prev_dialog": {"value": state, "turns_remaining": 3},
    }
    return session


def test_two_consecutive_followups_speak_different_dialogs(tmp_path):
    dialog_file = tmp_path / "day_5_month_9_events.dialog"
    dialog_file.write_text(
        "1900 - First event happened.\n"
        "1910 - Second event happened.\n"
        "1920 - Third event happened.\n"
    )
    fake = _fake_skill(dialog_file)

    session1 = _fake_session({"value": "day_5_month_9_events", "seen": []})
    with patch("ovos_skill_days_in_history.SessionManager") as sm:
        sm.get.return_value = session1
        TodayInHistory.handle_tell_me_more_intent(fake, MagicMock())
    first_spoken = fake.speak.call_args[0][0]
    # second positional arg is the updated {"value": dialog, "seen": [...]} state
    updated_state = session1.set_intent_context.call_args[0][1]
    assert updated_state["seen"], "first continuation must record the served line"

    fake.speak.reset_mock()
    session2 = _fake_session(updated_state)
    with patch("ovos_skill_days_in_history.SessionManager") as sm:
        sm.get.return_value = session2
        TodayInHistory.handle_tell_me_more_intent(fake, MagicMock())
    second_spoken = fake.speak.call_args[0][0]

    assert first_spoken != second_spoken, (
        "two consecutive tell-me-more continuations must not repeat the "
        f"same dialog line, both were {first_spoken!r}"
    )
    fake.speak_dialog.assert_not_called()


def test_exhausted_dialog_speaks_thats_all(tmp_path):
    dialog_file = tmp_path / "day_5_month_9_events.dialog"
    dialog_file.write_text(
        "1900 - First event happened.\n"
        "1910 - Second event happened.\n"
    )
    fake = _fake_skill(dialog_file)
    already_seen = [
        "1900 - First event happened.",
        "1910 - Second event happened.",
    ]
    session = _fake_session({"value": "day_5_month_9_events", "seen": already_seen})
    with patch("ovos_skill_days_in_history.SessionManager") as sm:
        sm.get.return_value = session
        TodayInHistory.handle_tell_me_more_intent(fake, MagicMock())

    fake.speak_dialog.assert_called_once_with("thats_all")
    fake.speak.assert_not_called()
    session.remove_intent_context.assert_called_once_with("prev_dialog", scope="shared")


def test_no_context_speaks_thats_all_without_crashing():
    """A fired-without-context call (the upstream context-gate bug
    documented in test_alerts_crosskill_misroute.py) must not crash --
    "nothing to elaborate on" is a legitimate state."""
    fake = _fake_skill("/nonexistent")
    session = MagicMock()
    session.intent_context = {}
    with patch("ovos_skill_days_in_history.SessionManager") as sm:
        sm.get.return_value = session
        TodayInHistory.handle_tell_me_more_intent(fake, MagicMock())

    fake.speak_dialog.assert_called_once_with("thats_all")
    fake.speak.assert_not_called()
