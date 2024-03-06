import random
import re
from datetime import date

import wikipedia as wiki
from lingua_franca.parse import extract_datetime
from ovos_workshop.decorators import intent_handler
from ovos_workshop.intents import IntentBuilder
from ovos_workshop.skills import OVOSSkill


class TodayInHistory(OVOSSkill):

    @intent_handler(
        IntentBuilder('TodayInHistoryIntent').require("TodayInHistoryKeyword"))
    def handle_today_in_history_intent(self, message):
        day_query = extract_datetime(
            message.data.get("utterance"))[0].strftime("%B %d")

        if day_query:
            self._search(day_query)
        else:
            self._search(date.today().strftime("%B %d"))

    @intent_handler(
        IntentBuilder("TellMeMoreIntent").require("TellMeMoreKeyword").require(
            "initial_response"))
    def handle_tell_me_more_intent(self, message):
        """ Handler for follow-up inquiries 'tell me more'

            enabled after initial response is complete
        """

        if not self.events_list:
            self.speak("That's all the information I can find.")
        else:
            events_list = self.events_list
            day = self.day

            selection_index = random.randrange(len(events_list))
            selected_event = events_list[selection_index]

            selected_event = day + ", " + selected_event
            self.speak(selected_event)

            events_list.pop(selection_index)
            self.events_list = events_list

    def _search(self, day_query):
        """ Searches wikipedia for an entry about a given day and replies to user
            Arguments:
                day_query: a string referencing a calendar day
                e.g. "March 15" or "May 6th"
        """
        try:

            # let the user know we're looking
            self.speak_dialog("searching", {"day": day_query})

            # get the wikipedia article for the chosen day
            # wiki.page will accept a range of day formats
            # including "August 5", "August 5th", and "5th of August"
            results = wiki.page(day_query)

            # remove irrelevant content so we are just looking at events
            events = re.search(r'(?<=Events ==\n).*?(?=\n\n\n==)',
                               results.content, re.DOTALL).group()

            # remove words between parenthesis and brackets for better speech
            # these are often birth/death days and less relevant asides.
            events = re.sub(r'\([^)]*\)|/[^/]*/', '', events)

            # parse results into a list.
            # Entries are seperated by newline characters
            events_list = re.split(r'\n', events)

            # choose a random entry from the list
            selection_index = random.randrange(len(events_list))
            selected_event = events_list[selection_index]

            # a little string concatenation for clarity
            # right now our selection only contains a year
            self.speak(day_query + ", " + selected_event)

            # remove spoken entries and save data for further inquiry.
            # Flag initial response as complete to enable 'Tell Me More'
            # this doesn't work with bool'True'.... wants a string
            events_list.pop(selection_index)
            self.events_list = events_list
            self.day = day_query
            self.set_context("initial_response", "complete")

        except wiki.exceptions.PageError:
            self.speak_dialog("notfound")

        except wiki.exceptions.WikipediaExeption:
            self.speak("I'm sorry, something went wrong")

        except Exception as e:
            self.log.error("Error: {0}".format(e))
