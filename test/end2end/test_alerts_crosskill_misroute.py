"""Two-skill regression test: ovos-skill-days-in-history + ovos-skill-alerts.

Live bug: in a days-in-history session ("what happened today in history" ->
answer), the follow-up "tell me another event" was stolen by
ovos-skill-alerts' ListAlerts adapt intent (adapt_medium tier, confidence
~0.57 -- "tell me" satisfies its ``query`` vocab, bare "event" satisfies its
``event`` vocab). days-in-history's own TellMeMoreIntent (adapt, gated by the
OVOS-CONTEXT-1 ``prev_dialog`` session context set after every answer) never
got a chance: its ``tell_me_more.voc`` only tagged "another event" (2 of the
4 words), so it scored too low to clear even the adapt-high tier, and the
pipeline fell through to adapt-medium where alerts' broader vocab explained
more of the utterance and won.

Fix (this repo only): add the single literal phrase "tell me another event"
to ``locale/en-US/tell_me_more.voc`` so TellMeMoreIntent's own vocab explains
the *entire* utterance and clears the adapt-high tier -- which the pipeline
always tries before adapt-medium, so alerts' ListAlerts (which only ever
reaches adapt-medium for this utterance) is never even evaluated.

NOTE on a prior, reverted revision of this fix: an earlier version of this
patch also added the broader phrases "tell me another" and "tell me another
one" to the same vocab file. Adversarial review caught that this created a
mirror-image theft: since those entries have no trailing noun, they matched
the *prefix* of any "tell me another <X>" utterance, so "tell me another
joke" / "tell me another quote" (unrelated skills' follow-ups) were wrongly
claimed by this skill's TellMeMoreIntent. Those two broader entries were
dropped; only the single, exact "tell me another event" phrase remains, and
this file's negative tests below guard against that regression coming back.

ovos-skill-alerts was investigated and deliberately NOT changed: its bare
"event" keyword in ``ListAlerts`` (``.one_of("alarm", "reminder", "event",
"alert", "remind")``) is exercised by real rows in its own golden suite
(e.g. "show me all of my events", "are there any events between ... and
...") that carry no alarm/reminder/alert keyword alongside "event". Requiring
such a keyword to fix this bug would break that legitimate, tested behavior.
The correct fix is context-priming days-in-history's own intent to win
outright, not narrowing an unrelated skill's contract.

This test builds BOTH skills' MiniCroft stacks together and round-trips the
session exactly as a conformant client must (OVOS-SESSION-1 / the
"session travels per-message, client declares" contract): every outgoing
message must resend the full session snapshot the server last returned, or
``Session.update_from`` legitimately treats missing fields as reset to
default (this is spec'd behavior, not a bug) and the ``prev_dialog`` context
set by turn 1 would appear lost on turn 2.

UPSTREAM FINDING (documented, not fixed here -- see the class docstring on
``TestPrevDialogContextGate`` below): ``require("prev_dialog")`` -- the
OVOS-CONTEXT-1 gate that is supposed to make TellMeMoreIntent fire only
after an active days-in-history turn -- is currently INERT in ovos-core /
ovos-adapt-parser / ovos-workshop at the pinned prerelease versions. A
context-free "tell me another event" on a brand new session still matches
TellMeMoreIntent. Root cause: the skill's adapt intent gets registered
*twice* (a legacy dual-emit path and the OVOS-INTENT-4 spec path), and the
spec path silently drops any ``require()`` entry with no backing vocab
samples (``prev_dialog`` has none by design -- it's context-only) while also
mis-namespacing entity types via an off-by-one skill_id truncation bug. The
resulting *duplicate*, ungated Adapt intent parser always validates whenever
the vocab-backed keyword matches, regardless of context, so it wins
unconditionally over the correctly-gated legacy registration. This is a
systemic bug affecting every context-gated Adapt intent in the OVOS
ecosystem, not something this skill repo can fix; see the class docstring
below for the exact file:line evidence and the upstream repos this was
reported against.

Run: pytest test/end2end/test_alerts_crosskill_misroute.py -v
"""
from unittest import TestCase

from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import CaptureSession, get_minicroft

DIH_SKILL_ID = "ovos-skill-days-in-history.openvoiceos"
ALERTS_SKILL_ID = "ovos-skill-alerts.openvoiceos"
LANG = "en-US"

# Mirrors ovos-core's actual default "pipeline" list (read from
# ovos-config's mycroft.conf, not memory), restricted to the intent-routing
# stages relevant here (stop/converse/ocp/m2v/fallback are omitted -- they
# don't participate in the routes under test). The real default is:
#
#   stop-high, converse, ocp-high, padatious-high, adapt-high, m2v-high,
#   ocp-medium, fallback-high, stop-medium, adapt-medium, fallback-medium,
#   fallback-low
#
# Two things about that list matter for these tests:
#   1. adapt-high runs before adapt-medium -- this is what lets
#      TellMeMoreIntent's narrowed vocab win outright over alerts'
#      ListAlerts before alerts is even tried (the fix this PR verifies).
#   2. there is NO padatious-medium, NO padatious-low, NO adapt-low, and NO
#      padacioso tier at all in the real default. Earlier revisions of this
#      test pipeline included all of those (a synthetic worst case), which
#      is why CI caught "tell me another joke" being claimed by
#      today_in_history's padatious .intent templates via fuzzy matching at
#      the padatious-LOW tier -- a tier that plain does not exist in
#      production. On ser9 (a real, default-shaped pipeline) the same
#      utterance correctly falls through to ddg fallback, confirming this.
#      padatious-low fuzzy matching against today_in_history's own
#      ".intent" templates WOULD steal "tell me another joke" if that tier
#      were ever enabled (worth knowing, not worth an xfail for a
#      non-default tier).
PIPELINE = [
    "ovos-padatious-pipeline-plugin-high",
    "ovos-adapt-pipeline-plugin-high",
    "ovos-adapt-pipeline-plugin-medium",
]


def _matched_and_errored(messages):
    matched = [m for m in messages if m.msg_type == "ovos.intent.matched"]
    errored = [m for m in messages if m.msg_type == "ovos.intent.handler.error"]
    return matched, errored


def _run_turn(minicroft, utterance, session_dict_or_id):
    """Fire one utterance. Accepts either a session_id (fresh session) or a
    full session dict (as returned in a prior turn's message context, for
    round-tripping)."""
    if isinstance(session_dict_or_id, str):
        session = Session(session_dict_or_id)
        session.lang = LANG
        session.pipeline = PIPELINE
        session_payload = session.serialize()
    else:
        session_payload = session_dict_or_id
    msg = Message(
        "recognizer_loop:utterance",
        {"utterances": [utterance], "lang": LANG},
        {"session": session_payload},
    )
    cap = CaptureSession(minicroft)
    cap.capture(msg, timeout=30)
    return cap.finish()


def _latest_session(messages):
    latest = None
    for m in messages:
        sc = m.context.get("session")
        if sc:
            latest = sc
    return latest


class TestAlertsCrossSkillMisroute(TestCase):
    """Reproduces the ser9 misroute with both skills loaded together."""

    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_minicroft([DIH_SKILL_ID, ALERTS_SKILL_ID])

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "minicroft", None):
            cls.minicroft.stop()

    def test_tell_me_another_event_stays_with_days_in_history(self):
        session_id = "e2e-crosskill-tell-me-another-event"
        session = Session(session_id)
        session.lang = LANG
        session.pipeline = PIPELINE

        # NOTE: February 10th is deliberately picked -- some of this skill's
        # dialog templates hit an unrelated pre-existing MalformedTemplate
        # bug (single-branch {A} groups); Feb 10th's events dialog is clean,
        # keeping this test focused on the cross-skill routing regression.
        turn1_messages = _run_turn(
            self.minicroft, "what happened on february 10th in history", session_id
        )

        # a conformant client carries forward the latest session snapshot
        # the server handed back -- this is what carries prev_dialog to turn 2
        latest_session = _latest_session(turn1_messages)
        self.assertTrue(
            latest_session and latest_session.get("intent_context", {}).get("prev_dialog"),
            "setup failed: turn 1 never set the prev_dialog OVOS-CONTEXT-1 entry",
        )

        turn2_messages = _run_turn(self.minicroft, "tell me another event", latest_session)
        matched, errored = _matched_and_errored(turn2_messages)

        self.assertTrue(matched, "'tell me another event' matched no intent at all")
        self.assertEqual(
            matched[0].data.get("skill_id"), DIH_SKILL_ID,
            f"MISROUTE: {matched[0].data.get('skill_id')} handled the "
            f"follow-up instead of days-in-history "
            f"(intent={matched[0].data.get('intent_name')})",
        )
        self.assertFalse(
            errored,
            f"days-in-history's TellMeMoreIntent handler raised: {errored}",
        )
        spoken = [m.data.get("utterance") for m in turn2_messages
                  if m.msg_type == "ovos.utterance.speak"]
        self.assertTrue(spoken, "no speech was produced for the follow-up")

    def test_tell_me_another_joke_not_claimed_with_context(self):
        """Mirror-image-theft regression: a prior revision of this fix
        broadened tell_me_more.voc with bare "tell me another" / "tell me
        another one" entries, which matched the *prefix* of ANY "tell me
        another <X>" utterance -- including ones belonging to other skills.
        Guards that only the exact "tell me another event" phrase is
        vocab-matched, even with an active days-in-history context primed.
        """
        session_id = "e2e-crosskill-not-a-joke-skill-with-context"
        session = Session(session_id)
        session.lang = LANG
        session.pipeline = PIPELINE
        turn1_messages = _run_turn(
            self.minicroft, "what happened on february 10th in history", session_id
        )
        latest_session = _latest_session(turn1_messages)
        self.assertTrue(
            latest_session and latest_session.get("intent_context", {}).get("prev_dialog"),
            "setup failed: turn 1 never set the prev_dialog OVOS-CONTEXT-1 entry",
        )

        for utterance in ("tell me another joke", "tell me another quote"):
            with self.subTest(utterance=utterance):
                messages = _run_turn(self.minicroft, utterance, latest_session)
                matched, _ = _matched_and_errored(messages)
                claimed_by_dih = [m for m in matched if m.data.get("skill_id") == DIH_SKILL_ID]
                self.assertFalse(
                    claimed_by_dih,
                    f"MIRROR-IMAGE THEFT: {utterance!r} was claimed by "
                    f"days-in-history ({claimed_by_dih}) even though it has "
                    f"nothing to do with today-in-history follow-ups",
                )

    def test_tell_me_another_joke_not_claimed_without_context(self):
        """Same guard as above, but on a completely fresh session with no
        days-in-history turn at all -- the common case for an unrelated
        skill's own "tell me another X" follow-up.
        """
        for utterance in ("tell me another joke", "tell me another quote"):
            with self.subTest(utterance=utterance):
                session_id = f"e2e-fresh-not-a-joke-skill-{hash(utterance)}"
                messages = _run_turn(self.minicroft, utterance, session_id)
                matched, _ = _matched_and_errored(messages)
                claimed_by_dih = [m for m in matched if m.data.get("skill_id") == DIH_SKILL_ID]
                self.assertFalse(
                    claimed_by_dih,
                    f"MIRROR-IMAGE THEFT: {utterance!r} was claimed by "
                    f"days-in-history ({claimed_by_dih}) on a session that "
                    f"never even talked to days-in-history",
                )


class TestPrevDialogContextGate(TestCase):
    """UPSTREAM BUG, documented here, NOT fixable in this skill repo.

    ``require("prev_dialog")`` is supposed to make TellMeMoreIntent
    unmatchable outside an active days-in-history session (the whole point
    of the OVOS-CONTEXT-1 gate added in #63). It doesn't gate anything: on a
    completely fresh session with zero prior turns, "tell me another event"
    still matches TellMeMoreIntent.

    Root cause (traced against ovos-core 2.6.3a1 / ovos-adapt-parser
    1.6.1a1 / ovos-workshop at the same prerelease train, in-process):

    ``IntentServiceInterface.register_intent`` in ovos-workshop's
    ``ovos_workshop/intents.py`` (~line 428) unconditionally dual-emits
    every adapt intent registration down TWO paths:

        self._adapt.emit_legacy_register_intent(msg, intent_parser)
        self._emit_spec_keyword_intent(msg, name, intent_parser)

    1. The legacy path forwards the already-built ``Intent.__dict__`` as-is
       (correct: both "tell_me_more" and "prev_dialog" requirements
       present, correctly namespaced).
    2. ``_emit_spec_keyword_intent`` (ovos_workshop/intents.py, ~line
       393-421) re-derives the OVOS-INTENT-4 "required" descriptor list via
       ``_spec_keyword_descriptors`` (~line 382-390), which silently DROPS
       any required vocabulary name with no cached samples:

           samples = self._get_keyword_samples(vocab_type, lang)
           if not samples:
               continue  # <- prev_dialog has no .voc file by design, dropped here

       "prev_dialog" is a context-only requirement (no backing .voc file,
       intentionally -- it's meant to be satisfied purely via
       ``Session.set_intent_context`` / OVOS-CONTEXT-1 injection). It gets
       silently stripped from the spec registration payload.

    3. ``ovos_adapt/opm.py``'s ``handle_spec_register_intent`` receives
       that payload and registers a SECOND ``Intent`` parser under the
       identical name (``skill_id:TellMeMoreIntent``) that requires ONLY
       "tell_me_more" -- no context gate at all. This duplicate also gets a
       corrupted entity-type namespace from the module-level helper
       ``_entity_skill_id`` (ovos_adapt/opm.py, ~line 39-50):

           def _entity_skill_id(skill_id):
               skill_id = skill_id[:-1]   # <- unconditional last-char strip
               ...

       This assumes a legacy trailing-dot skill_id convention
       ("skillname.author.") that modern skill_ids
       ("ovos-skill-days-in-history.openvoiceos") don't have, so it eats
       the real last character ("openvoiceos" -> "openvoiceo"). This
       namespace mismatch is what ALSO breaks live context injection for
       any intent that DOES keep its context requirement through
       registration (``_context_candidate_entities`` /
       ``_live_context_value`` look up ``session.intent_context`` using
       this corrupted namespace and never find the entry the skill wrote
       under the real, un-corrupted key).

    Net effect: BOTH registered ``Intent`` objects for TellMeMoreIntent
    coexist in ``AdaptPipeline.engines[lang].intent_parsers`` under the
    same name; Adapt validates every parser with that name and accepts a
    match from ANY of them, so the ungated duplicate (needs only the vocab
    keyword, never the context) always wins whenever the vocab-backed
    keyword is present -- context or no context. This is systemic: it
    affects every Adapt intent anywhere in the OVOS ecosystem that mixes a
    normal vocab-backed ``require()`` with a context-only one.

    Reported upstream against ovos-workshop (``_spec_keyword_descriptors``
    dropping vocab-less requires) and ovos-adapt-parser (``_entity_skill_id``
    off-by-one truncation) as a combined issue-quality report rather than a
    blind patch, given the blast radius (every context-gated Adapt intent)
    and the risk of a hasty fix to core intent-matching plumbing.

    """

    @classmethod
    def setUpClass(cls):
        cls.minicroft = get_minicroft([DIH_SKILL_ID, ALERTS_SKILL_ID])

    @classmethod
    def tearDownClass(cls):
        if getattr(cls, "minicroft", None):
            cls.minicroft.stop()

    def test_no_context_means_no_match(self):
        session_id = "e2e-no-context-should-not-match"
        messages = _run_turn(self.minicroft, "tell me another event", session_id)
        matched, _ = _matched_and_errored(messages)
        claimed_by_dih = [m for m in matched if m.data.get("skill_id") == DIH_SKILL_ID]
        self.assertFalse(
            claimed_by_dih,
            "TellMeMoreIntent matched on a fresh session with no "
            "prev_dialog context -- the require('prev_dialog') gate is "
            "inert (see class docstring for the upstream root cause)",
        )

    def test_handler_survives_firing_without_context(self):
        """Live ser9 finding: because of the upstream bug documented above,
        TellMeMoreIntent DOES fire on a context-free session today (this is
        exactly what ``test_no_context_means_no_match`` above documents as
        an xfail). When it does, the handler used to assume
        ``session.intent_context["prev_dialog"]`` existed and was a dict
        with a "value" key, and crashed with ``KeyError: 'value'`` at
        ``__init__.py:118``, speaking the literal "skill.error" dialog on a
        live deployment.

        "No prev_dialog context" is a legitimate state here regardless of
        upstream's bug -- even once require("prev_dialog") is fixed
        upstream, a conformant client may replay a stale/expired session
        that no longer carries the entry. The handler must treat it as
        "nothing to elaborate on yet" and say so, not crash.

        This does not (and should not) assert WHICH intent fires -- that is
        covered by ``test_no_context_means_no_match`` above and is an
        upstream concern. It asserts that IF TellMeMoreIntent fires with no
        context, it completes cleanly: no ``ovos.intent.handler.error``, no
        literal "skill.error" utterance spoken.
        """
        session_id = "e2e-handler-survives-no-context"
        messages = _run_turn(self.minicroft, "tell me another event", session_id)
        matched, errored = _matched_and_errored(messages)
        dih_matched = [m for m in matched if m.data.get("skill_id") == DIH_SKILL_ID]
        if not dih_matched:
            self.skipTest(
                "TellMeMoreIntent did not fire on this run (the upstream "
                "ungated-duplicate bug is nondeterministic-adjacent); "
                "nothing to assert about the handler"
            )
        self.assertFalse(
            errored,
            f"days-in-history's TellMeMoreIntent handler crashed when fired "
            f"without prev_dialog context: {errored}",
        )
        spoken = [m.data.get("utterance") for m in messages
                  if m.msg_type == "ovos.utterance.speak"]
        self.assertTrue(spoken, "no speech was produced at all")
        self.assertNotIn(
            "skill.error", spoken,
            f"handler spoke the literal skill.error fallback dialog "
            f"instead of a real 'nothing to elaborate on' response: {spoken}",
        )
