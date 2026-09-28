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
from ovos_workshop.resource_files import locate_lang_directories
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

    def _day_dialog_exists(self, dialog: str) -> bool:
        """Whether this locale ships the per-day `.dialog` this request needs.

        A locale can ship the `.intent` files and none of the 1098 `day_*`
        files: `kab` does today, and `ca-ES` ships 550 of the 1098. For such a
        request `dialog_renderer.render(key)` returns the KEY, so
        `speak_dialog` speaks "day_25_month_9_births" aloud. Every handler that
        builds a per-day dialog name therefore checks first and falls back to
        `unknown_date`, which is one string per locale instead of 1098.

        The locale directory is resolved the way the resource loader resolves
        it, with `locate_lang_directories`. A hand-built `locale/{self.lang}`
        path is wrong for any lang that is not itself a directory name:
        `self.lang` is `standardize_lang(get_message_lang(message))`, which
        normalises case and separator and does NOT add a region, so a session
        lang of `pt`, `ca` or `en` (a bare primary subtag is valid BCP-47, and
        `lang: "en"` in mycroft.conf is ordinary) misses `locale/pt-PT`,
        `locale/ca-ES` and `locale/en-US`. The guard would then report absent
        for a date the skill has a full sentence for and answer "I do not know
        that date" instead of speaking it.

        `find_resource` is NOT usable here: it falls through to another
        language's directory, and for `kab` it returns the `ca-ES` file, so a
        guard built on it would report present and speak Catalan at a Kabyle
        user.

        The FIRST matched directory is the answer, not any of them. The
        loader binds one directory and reads from it, so a lang that matches
        two must be asked about the one the loader picked: once `pt-BR` ships
        the intents with no day files beside `pt-PT` which has 1098, `any()`
        over both reports present while the renderer, bound to `pt-BR`,
        returns the key and the skill reads it aloud.
        """
        directories = locate_lang_directories(self.lang, os.path.dirname(__file__))
        if not directories:
            return False
        return (directories[0] / f"{dialog}.dialog").is_file()

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
        if not self._day_dialog_exists(dialog):
            self.speak_dialog("unknown_date")
            SessionManager.get(message).remove_intent_context("prev_dialog", scope="shared")
        else:
            self._speak_dialog_safe(dialog, render_callback=self.pronounce_year)
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
        if not self._day_dialog_exists(dialog):
            self.speak_dialog("unknown_date")
            SessionManager.get(message).remove_intent_context("prev_dialog", scope="shared")
            return
        self._speak_dialog_safe(dialog, render_callback=self.pronounce_year)
        SessionManager.get(message).set_intent_context(
            "prev_dialog", {"value": dialog, "seen": []},
            scope="shared", turns_remaining=3)

    @intent_handler("today_in_history.intent")
    def handle_today_in_history_intent(self, message):
        date = self.get_date(message)
        dialog = f"day_{date.day}_month_{date.month}_events"
        if not self._day_dialog_exists(dialog):
            self.speak_dialog("unknown_date")
            SessionManager.get(message).remove_intent_context("prev_dialog", scope="shared")
            return
        self._speak_dialog_safe(dialog, render_callback=self.pronounce_year)
        SessionManager.get(message).set_intent_context(
            "prev_dialog", {"value": dialog, "seen": []},
            scope="shared", turns_remaining=3)

    @intent_handler("tell_me_more_intent.intent",
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
