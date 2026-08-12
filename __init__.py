import datetime
import os.path

from ovos_bus_client.session import SessionManager
from ovos_date_parser import extract_datetime, nice_year
from ovos_utils import classproperty
from ovos_utils.log import LOG
from ovos_utils.process_utils import RuntimeRequirements
from ovos_utils.time import now_local
from ovos_workshop.decorators import intent_handler
from ovos_workshop.intents import IntentBuilder
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

    @intent_handler("deaths_in_history.intent")
    def handle_deaths_intent(self, message):
        date = self.get_date(message)
        dialog = f"day_{date.day}_month_{date.month}_deaths"
        event = f"{os.path.dirname(__file__)}/locale/{self.lang}/{dialog}.dialog"
        if not os.path.isfile(event):
            self.speak_dialog("unknown_date")
            SessionManager.get(message).remove_intent_context("prev_dialog", scope="shared")
        else:
            self.speak_dialog(dialog)
            SessionManager.get(message).set_intent_context("prev_dialog", dialog, scope="shared")

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
        self.speak_dialog(dialog, render_callback=self.pronounce_year)
        SessionManager.get(message).set_intent_context("prev_dialog", dialog, scope="shared")

    @intent_handler("today_in_history.intent")
    def handle_today_in_history_intent(self, message):
        date = self.get_date(message)
        dialog = f"day_{date.day}_month_{date.month}_events"
        self.speak_dialog(dialog, render_callback=self.pronounce_year)
        SessionManager.get(message).set_intent_context("prev_dialog", dialog, scope="shared")

    @intent_handler(IntentBuilder("TellMeMoreIntent").
                    require("tell_me_more").
                    require("prev_dialog"))
    def handle_tell_me_more_intent(self, message):
        """ Handler for follow-up inquiries 'tell me more'
        enabled after initial response is complete

        NOTE: `require("prev_dialog")` has no backing vocab/keyword file --
        it is only ever satisfied through context (self.set_context /
        SessionManager.set_intent_context), never from the utterance itself.
        Verified against the currently-installed ovos-adapt: the intent
        still matches correctly on a live "prev_dialog" context entry, but
        `message.data` does not reliably carry the stored value back (see
        the bug this fixes -- `message.data["prev_dialog"]` raised
        `KeyError` even on a successful match). Read the value back from
        the session's `intent_context` map directly instead of trusting
        `message.data`.

        NOTE 2: until ovos-workshop#525 ships, this intent can (and on live
        ser9 deployments, does) fire with NO "prev_dialog" entry at all --
        the require("prev_dialog") gate is currently inert upstream (the
        skill's adapt intent gets registered twice; the OVOS-INTENT-4 spec
        path silently drops context-only requirements and produces an
        ungated duplicate that matches on "tell_me_more" alone). Even after
        that upstream fix ships, a conformant client may legitimately replay
        a stale/expired session that no longer carries the entry. Either
        way "no prev_dialog" is a real, expected state here -- there is
        simply nothing to elaborate on yet -- not a bug to mask with a
        defensive `.get()`: branch on it explicitly and say so, the same
        dialog already used for "no more to add".
        """
        # TODO - add mechanism to avoid repeated responses
        all_spoken = False
        session = SessionManager.get(message)
        entry = (session.intent_context or {}).get("prev_dialog")
        if all_spoken or not isinstance(entry, dict) or "value" not in entry:
            self.speak_dialog("thats_all")
            session.remove_intent_context("prev_dialog", scope="shared")
        else:
            dialog = entry["value"]
            self.speak_dialog(dialog, render_callback=self.pronounce_year)
