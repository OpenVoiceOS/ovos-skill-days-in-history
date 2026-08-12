"""Golden-utterance end-to-end coverage for ovos-skill-days-in-history (en-US).

The golden corpus (``golden_utterances.jsonl``) is a vendored slice of the
shared ovoscope golden-utterance dataset, keyed by
``skill_id == "ovos-skill-days-in-history.openvoiceos"``. One shared
``MiniCroft`` (module-scoped fixture) is booted for the whole suite. Seven
rows are the padatious ``today/births/deaths_in_history.intent`` phrasings,
routed and asserted directly. The eighth row, "another event", is the adapt
``TellMeMoreIntent`` -- a stateful follow-up that only fires after a prior
``today_in_history``/``births_in_history``/``deaths_in_history`` intent has
set the ``prev_dialog`` context, so it is driven as a two-turn conversation
(first turn sets the context, second turn fires the follow-up) rather than
in isolation.
"""
import json
from pathlib import Path

import pytest
from ovos_bus_client.message import Message
from ovos_bus_client.session import Session, SessionManager
from ovoscope import CaptureSession, get_minicroft

SKILL_ID = "ovos-skill-days-in-history.openvoiceos"
LANG = "en-US"

PADATIOUS_PIPELINE = [
    "ovos-padatious-pipeline-plugin-high",
    "ovos-padatious-pipeline-plugin-medium",
    "ovos-padatious-pipeline-plugin-low",
]
ADAPT_PIPELINE = PADATIOUS_PIPELINE + ["ovos-adapt-pipeline-plugin-high"]

GOLDEN_PATH = Path(__file__).parent / "golden_utterances.jsonl"

# utterances lifted verbatim from OTHER skills' golden-utterance slices,
# picked for lexical overlap with this skill's "today"/"history"/"event"
# vocabulary.
NEGATIVE_UTTERANCES = [
    ("what color is something", "ovos-skill-color-picker.openvoiceos"),
    ("take a picture", "ovos-skill-camera.openvoiceos"),
    ("count forever", "ovos-skill-count.openvoiceos"),
    ("launch spotify", "ovos-skill-application-launcher.openvoiceos"),
    ("are you ready", "ovos-skill-boot-finished.openvoiceos"),
    ("what's the weather today", "ovos-skill-weather.openvoiceos"),
    ("set a timer for 5 minutes", "ovos-skill-alerts.openvoiceos"),
]


def _label_to_bus_name(intent_label: str) -> str:
    return intent_label.removesuffix(".intent")


def _load_golden_rows():
    rows = []
    with open(GOLDEN_PATH, encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            row = json.loads(line)
            if row.get("needs_manual"):
                continue
            rows.append(row)
    return rows


ALL_ROWS = _load_golden_rows()
PADATIOUS_ROWS = [r for r in ALL_ROWS if r["intent_type"] == "padatious"]
ADAPT_ROWS = [r for r in ALL_ROWS if r["intent_type"] == "adapt"]

GOLDEN_ROWS = [pytest.param(r, id=r["utterance"]) for r in PADATIOUS_ROWS]


@pytest.fixture(scope="module")
def minicroft():
    mc = get_minicroft([SKILL_ID])
    yield mc
    mc.stop()


def _types(mc, text, session_id, pipeline):
    # Reuse the live SessionManager singleton for this session_id when one
    # already exists (i.e. a prior turn in the same conversation ran through
    # this same in-process bus). A brand-new Session object here would carry
    # OVOS-CONTEXT-1's session.intent_context as empty/omitted, and
    # SessionManager.get() folds the incoming wire snapshot onto the
    # singleton with whole-field last-writer-wins semantics -- so sending a
    # context-less snapshot on turn 2 would silently wipe whatever a skill's
    # turn-1 handler wrote via set_intent_context, exactly like a real
    # client that fails to carry the session forward between turns.
    session = SessionManager.sessions.get(session_id) or Session(session_id)
    session.lang = LANG
    session.pipeline = list(pipeline)
    utterance = Message(
        "recognizer_loop:utterance",
        {"utterances": [text], "lang": LANG},
        {"session": session.serialize(), "source": "A", "destination": "B"},
    )
    capture = CaptureSession(
        mc,
        eof_msgs=["ovos.utterance.handled"],
        # NOTE: "speak" / "ovos.utterance.speak" are deliberately NOT
        # ignored -- test_golden_utterance_adapt_followup asserts on their
        # presence to confirm the follow-up intent actually produced spoken
        # output, not just a bus match. Ignoring purely-cosmetic audio
        # plumbing keeps that assertion's noise down without hiding the
        # signal it checks for.
        ignore_messages=["recognizer_loop:audio_output_start",
                          "recognizer_loop:audio_output_end",
                          "mycroft.audio.play_sound"],
    )
    capture.capture(utterance, timeout=30)
    return [m.msg_type for m in capture.finish()]


@pytest.mark.timeout(60)
@pytest.mark.parametrize("row", GOLDEN_ROWS, ids=lambda r: r["utterance"])
def test_golden_utterance(minicroft, row):
    intent_name = _label_to_bus_name(row["intent_label"])
    types = _types(minicroft, row["utterance"], f"golden-{row['utterance']}",
                    PADATIOUS_PIPELINE)
    assert f"{SKILL_ID}:{intent_name}" in types, (
        f"{row['utterance']!r}: expected {SKILL_ID}:{intent_name!r}, got {types!r}"
    )


@pytest.mark.timeout(60)
@pytest.mark.parametrize("row", [pytest.param(r, id=r["utterance"]) for r in ADAPT_ROWS])
def test_golden_utterance_adapt_followup(minicroft, row):
    intent_name = _label_to_bus_name(row["intent_label"])
    # turn 1: fire a today_in_history phrasing to set the prev_dialog context
    session_id = f"golden-{row['utterance']}"
    _types(minicroft, "today in history", session_id, ADAPT_PIPELINE)
    # turn 2: the actual golden row, in the same session so the context carries
    types = _types(minicroft, row["utterance"], session_id, ADAPT_PIPELINE)
    assert f"{SKILL_ID}:{intent_name}" in types, (
        f"{row['utterance']!r}: expected {SKILL_ID}:{intent_name!r}, got {types!r}"
    )
    assert any(t in ("speak", "ovos.utterance.speak") for t in types), (
        f"{row['utterance']!r}: intent matched but produced no spoken output, got {types!r}"
    )


@pytest.mark.timeout(60)
@pytest.mark.parametrize("negative", NEGATIVE_UTTERANCES, ids=lambda n: n[0])
def test_negative_confusable_not_claimed(minicroft, negative):
    text, source_skill = negative
    types = _types(minicroft, text, f"negative-{text}", PADATIOUS_PIPELINE)
    claimed = any(t.startswith(f"{SKILL_ID}:") for t in types)
    assert not claimed, f"{text!r} (from {source_skill}) was incorrectly claimed by {SKILL_ID}"
