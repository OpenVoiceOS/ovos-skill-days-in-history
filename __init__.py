import datetime
import os.path
import random
from typing import Callable, Optional

from ovos_bus_client.session import SessionManager
from ovos_date_parser import extract_datetime, nice_year
from ovos_spec_tools import MalformedTemplate
from ovos_utils import classproperty
from ovos_utils.log import LOG
from ovos_utils.process_utils import RuntimeRequirements
from ovos_utils.time import now_local
from ovos_workshop.decorators import intent_handler
from ovos_workshop.skills.ovos import OVOSSkill


class TodayInHistory(OVOSSkill):
    @classproperty
    def runtime_requirements(self):
        return RuntimeRequirements(
            internet_before_load=False,
            network_before_load=False,
            gui_before_load=False,
            requires_internet=False,
            requires_network=False,
            requires_gui=False,
            no_internet_fallback=True,
            no_network_fallback=True,
            no_gui_fallback=True,
        )

    def get_date(self, message):
        utt = message.data.get("date") or message.data["utterance"]
        try:
            date = extract_datetime(utt, lang=self.lang)[0]
        except Exception as e:
            date = now_local()
            if message.data.get("date"):
                LOG.exception(f"failed to extract date in {self.lang} from {utt}")
                # TODO - dedicated error dialog
                #  this likely indicated a missing language in lingua-franca
        return date

    def _speak_dialog_safe(self, dialog: str,
                            render_callback: Optional[Callable[[str, str], str]] = None) -> None:
        """Speak a `.dialog` resource, tolerating a malformed template line.

        The historical-event `.dialog` files are scraped from Wikipedia and
        occasionally contain a line that OVOS-INTENT-1's template grammar
        can't parse (e.g. a literal `(word)` parenthetical aside, which the
        grammar reads as an illegal single-branch alternation group). When
        `random.choice` picks exactly that line, the normal render path
        raises `ovos_spec_tools.expansion.MalformedTemplate` out of
        `speak_dialog`, which used to propagate out of the intent handler as
        a bare `skill.error` -- a bad line in a data file taking down the
        whole response instead of just that one sentence.

        Per the "tolerate at runtime, flag in CI" template-lint policy: the
        CI-side guard (`test/test_template_lint.py`) is what should actually
        catch and fix the bad line before it ships. This is just the safety
        net for whatever slips through anyway -- fall back to speaking the
        raw, unexpanded line (still correct, un-templated text) instead of
        raising through the handler.
        """
        try:
            self.speak_dialog(dialog, render_callback=render_callback)
        except MalformedTemplate as err:
            LOG.warning(f"malformed template in dialog '{dialog}': {err} -- "
                        f"falling back to the raw, unexpanded dialog line")
            path = self.find_resource(f"{dialog}.dialog", "dialog")
            if not path or not os.path.isfile(path):
                # nothing to fall back to either -- surface the original dialog
                self.speak_dialog("unknown_date")
                return
            with open(path, encoding="utf-8") as f:
                lines = [line.strip() for line in f
                         if line.strip() and not line.strip().startswith("#")]
            if not lines:
                self.speak_dialog("unknown_date")
                return
            raw = random.choice(lines)
            if render_callback is not None:
                try:
                    raw = render_callback(raw, self.lang)
                except Exception as cb_err:
                    LOG.warning(f"render_callback failed on raw fallback line: {cb_err}")
            self.speak(raw)

    def _dialog_lines(self, dialog: str) -> list:
        """Return the candidate lines of a `.dialog` resource, or `[]` if
        it can't be found -- used by the tell-me-more follow-up to pick an
        as-yet-unspoken line instead of the random-per-call choice
        `speak_dialog` makes internally."""
        path = self.find_resource(f"{dialog}.dialog", "dialog")
        if not path or not os.path.isfile(path):
            return []
        with open(path, encoding="utf-8") as f:
            return [line.strip() for line in f
                    if line.strip() and not line.strip().startswith("#")]

    @intent_handler("deaths_in_history.intent")
    def handle_deaths_intent(self, message):
        date = self.get_date(message)
        dialog = f"day_{date.day}_month_{date.month}_deaths"
        event = f"{os.path.dirname(__file__)}/locale/{self.lang}/{dialog}.dialog"
        if not os.path.isfile(event):
            self.speak_dialog("unknown_date")
            SessionManager.get(message).remove_intent_context("prev_dialog", scope="shared")
        else:
            self._speak_dialog_safe(dialog)
            SessionManager.get(message).set_intent_context(
                "prev_dialog", {"value": dialog, "seen": []},
                scope="shared", turns_remaining=3)

    @staticmethod
    def pronounce_year(dialog: str, lang: str) -> str:
        """Format year pronunciation in dialog text.
        
        Args:
            dialog: Dialog text containing year in format "YEAR - text" or "YEAR BC - text"
            lang: Language code for pronunciation
            
        Returns:
            str: Formatted dialog text with properly pronounced year
        """
        try:
            bc: bool = False
            year, utt = dialog.split(" - ")  # this is how .dialog files are formatted
            if len(year.split()) == 2:
                year, bc_text = year.split()
                bc = bc_text.upper() == "BC"
            if year.isdigit():
                dt = datetime.datetime(year=int(year), day=1, month=1)
                return f"{nice_year(dt, lang=lang, bc=bc)} - {utt}"
        except Exception as e:
            LOG.error(f"Failed to parse year from dialog: {dialog} - {str(e)}")
        return dialog
        
    @intent_handler("births_in_history.intent")
    def handle_births_intent(self, message):
        date = self.get_date(message)
        dialog = f"day_{date.day}_month_{date.month}_births"
        self._speak_dialog_safe(dialog, render_callback=self.pronounce_year)
        SessionManager.get(message).set_intent_context(
            "prev_dialog", {"value": dialog, "seen": []},
            scope="shared", turns_remaining=3)

    @intent_handler("today_in_history.intent")
    def handle_today_in_history_intent(self, message):
        date = self.get_date(message)
        dialog = f"day_{date.day}_month_{date.month}_events"
        self._speak_dialog_safe(dialog, render_callback=self.pronounce_year)
        SessionManager.get(message).set_intent_context(
            "prev_dialog", {"value": dialog, "seen": []},
            scope="shared", turns_remaining=3)

    @intent_handler("TellMeMoreIntent.intent",
                    requires_context=[{"key": "prev_dialog", "scope": "shared"}])
    def handle_tell_me_more_intent(self, message):
        """ Handler for follow-up inquiries 'tell me more'
        enabled after initial response is complete

        NOTE: the gate has no backing vocab/keyword file -- it is only ever
        satisfied through context (SessionManager.set_intent_context),
        never from the utterance itself. The skill writes "prev_dialog"
        with scope="shared" (bare stored key), so the declaration above
        must also use the long-form {"key": ..., "scope": "shared"} --
        the short bare-string form defaults to "private" (OVOS-CONTEXT-1
        §6), which resolves to a different, skill-owner-prefixed stored
        key and would never see this entry. `message.data` does not
        reliably carry the stored value back, so read it from the
        session's `intent_context` map directly instead.

        The writer handlers set "prev_dialog" with turns_remaining=3, so
        the gate closes itself a few turns after a reading instead of
        staying open for the rest of the session -- the old Adapt context
        frame this replaces decayed the same way. scope="shared" is kept
        as-is here; whether it should become "private" (owner-scoped) is
        a separate design call left to the maintainer.
        """
        session = SessionManager.get(message)
        entry = (session.intent_context or {}).get("prev_dialog")
        state = entry["value"] if isinstance(entry, dict) else None
        dialog = state.get("value") if isinstance(state, dict) else None
        seen = state.get("seen", []) if isinstance(state, dict) else []
        unspoken = [line for line in self._dialog_lines(dialog) if line not in seen] \
            if dialog else []
        if not unspoken:
            self.speak_dialog("thats_all")
            session.remove_intent_context("prev_dialog", scope="shared")
        else:
            line = random.choice(unspoken)
            rendered = self.pronounce_year(line, self.lang)
            self.speak(rendered)
            session.set_intent_context(
                "prev_dialog", {"value": dialog, "seen": seen + [line]},
                scope="shared", turns_remaining=entry.get("turns_remaining"))
