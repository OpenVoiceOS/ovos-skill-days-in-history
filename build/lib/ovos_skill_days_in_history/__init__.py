import os.path

from lingua_franca.parse import extract_datetime
from ovos_utils import classproperty
from ovos_utils.log import LOG
from ovos_utils.process_utils import RuntimeRequirements
from ovos_utils.time import now_local
from ovos_workshop.decorators import intent_handler
from ovos_workshop.intents import IntentBuilder
from ovos_workshop.skills.auto_translatable import UniversalSkill


class TodayInHistory(UniversalSkill):
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
            self.remove_context("prev_dialog")
        else:
            self.speak_dialog(dialog)
            self.set_context("prev_dialog", dialog)

    @intent_handler("births_in_history.intent")
    def handle_births_intent(self, message):
        date = self.get_date(message)
        dialog = f"day_{date.day}_month_{date.month}_births"
        self.speak_dialog(dialog)
        self.set_context("prev_dialog", dialog)

    @intent_handler("today_in_history.intent")
    def handle_today_in_history_intent(self, message):
        date = self.get_date(message)
        dialog = f"day_{date.day}_month_{date.month}_events"
        self.speak_dialog(dialog)
        self.set_context("prev_dialog", dialog)

    @intent_handler(IntentBuilder("TellMeMoreIntent").
                    require("TellMeMore").
                    require("prev_dialog"))
    def handle_tell_me_more_intent(self, message):
        """ Handler for follow-up inquiries 'tell me more'
        enabled after initial response is complete
        """
        # TODO - add mechanism to avoid repeated responses
        all_spoken = False
        if all_spoken:
            self.speak_dialog("thats_all")
            self.remove_context("prev_dialog")
        else:
            dialog = message.data["prev_dialog"]
            self.speak_dialog(dialog)
