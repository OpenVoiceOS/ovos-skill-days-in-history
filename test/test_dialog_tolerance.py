"""Unit test for the runtime tolerance added to `_speak_dialog_safe`.

Regression coverage for the ser9 live finding: a malformed `.dialog` line
(`ovos_spec_tools.expansion.MalformedTemplate`, e.g. the Aug-12
`day_12_month_8_events` `(Extreme)` single-branch group) used to propagate
straight out of the intent handler as `skill.error`. `_speak_dialog_safe`
must catch that and fall back to speaking the raw, unexpanded dialog line
instead of raising -- "tolerate at runtime, flag in CI" per policy; the
CI-side flag is `test/test_template_lint.py`.

This drives `TodayInHistory._speak_dialog_safe` directly against a bare
stand-in object (not a full OVOSSkill/MiniCroft instance) since the method
only touches `self.speak_dialog`, `self.find_resource`, `self.speak`, and
`self.lang` -- all of which are trivial to stub, and a full skill boot adds
nothing this unit test needs.
"""
from types import SimpleNamespace
from unittest.mock import MagicMock

from ovos_spec_tools import MalformedTemplate

from ovos_skill_days_in_history import TodayInHistory


def test_malformed_template_falls_back_to_raw_line(tmp_path):
    """When speak_dialog's render path raises MalformedTemplate, the skill
    must speak a raw fallback line instead of letting the exception escape
    the handler (that's the bug: it used to become skill.error)."""
    dialog_file = tmp_path / "day_12_month_8_events.dialog"
    dialog_file.write_text(
        "# comment, should be skipped\n"
        "1945 - A bomb (Joe 4) is tested.\n"
        "1954 - An earthquake rated (Extreme) struck.\n"
    )

    fake = SimpleNamespace()
    fake.lang = "en-US"
    fake.speak = MagicMock()
    fake.speak_dialog = MagicMock(
        side_effect=MalformedTemplate("single-branch group (Extreme): "
                                       "a group must offer a choice between "
                                       "at least two branches"))
    fake.find_resource = MagicMock(return_value=str(dialog_file))

    TodayInHistory._speak_dialog_safe(fake, "day_12_month_8_events")

    # the handler must NOT propagate MalformedTemplate -- speak_dialog was
    # tried once (and raised), then the raw-line fallback spoke something
    fake.speak_dialog.assert_called_once()
    fake.speak.assert_called_once()
    (spoken_text,), _ = fake.speak.call_args
    assert spoken_text in {
        "1945 - A bomb (Joe 4) is tested.",
        "1954 - An earthquake rated (Extreme) struck.",
    }
    # the "# comment" line must never be a candidate
    assert "#" not in spoken_text


def test_malformed_template_fallback_applies_render_callback(tmp_path):
    """The raw fallback must still run render_callback (e.g. pronounce_year)
    so a births/events dialog doesn't lose year pronunciation just because
    the primary render path hit a malformed line."""
    dialog_file = tmp_path / "day_1_month_1_births.dialog"
    dialog_file.write_text("1900 - Someone (notable) was born.\n")

    fake = SimpleNamespace()
    fake.lang = "en-US"
    fake.speak = MagicMock()
    fake.speak_dialog = MagicMock(side_effect=MalformedTemplate("boom"))
    fake.find_resource = MagicMock(return_value=str(dialog_file))

    callback = MagicMock(return_value="REWRITTEN")
    TodayInHistory._speak_dialog_safe(fake, "day_1_month_1_births", render_callback=callback)

    callback.assert_called_once_with("1900 - Someone (notable) was born.", "en-US")
    fake.speak.assert_called_once_with("REWRITTEN")


def test_no_malformed_template_uses_normal_render_path():
    """The common case: speak_dialog succeeds, so the fallback path is never
    touched at all."""
    fake = SimpleNamespace()
    fake.lang = "en-US"
    fake.speak = MagicMock()
    fake.speak_dialog = MagicMock()
    fake.find_resource = MagicMock()

    TodayInHistory._speak_dialog_safe(fake, "day_12_month_8_events")

    fake.speak_dialog.assert_called_once_with("day_12_month_8_events", render_callback=None)
    fake.speak.assert_not_called()
    fake.find_resource.assert_not_called()


def test_missing_resource_falls_back_to_unknown_date():
    """If even the raw dialog file can't be found, don't crash -- fall back
    to the existing 'unknown_date' dialog rather than raising."""
    fake = SimpleNamespace()
    fake.lang = "en-US"
    fake.speak = MagicMock()
    # only the FIRST call (the real dialog) should raise; the fallback
    # call to "unknown_date" must succeed normally
    fake.speak_dialog = MagicMock(side_effect=[MalformedTemplate("boom"), None])
    fake.find_resource = MagicMock(return_value=None)

    TodayInHistory._speak_dialog_safe(fake, "day_12_month_8_events")

    fake.speak.assert_not_called()
    # first call attempted the real dialog, second call is the fallback
    assert fake.speak_dialog.call_args_list[-1].args[0] == "unknown_date"
    assert fake.speak_dialog.call_count == 2
