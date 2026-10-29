"""Golden rows route to their intent on the m2v prototype pipeline, and
negative rows reach no intent of this skill."""
import json
from pathlib import Path

import pytest
from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope.routing import TALLY, get_prototype_minicroft

SKILL_ID = "ovos-skill-days-in-history.openvoiceos"
END2END_DIR = Path(__file__).parent
LOCALE_ROOT = END2END_DIR.parents[1] / "locale"


def _rows(prefix):
    rows = []
    for path in sorted(END2END_DIR.glob(f"{prefix}*.jsonl")):
        rows += [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()
                 if line.strip()]
    return rows


GOLDEN = _rows("golden_utterances_")
NEGATIVE = _rows("negative_utterances_")
_booted = {}


@pytest.fixture(scope="module")
def engine_for():
    def engine(lang):
        if lang not in _booted:
            for minicroft in _booted.values():
                minicroft.stop()
            _booted.clear()
            _booted[lang] = get_prototype_minicroft([SKILL_ID], lang=lang)
        return _booted[lang].intents.pipeline_plugins["ovos-m2v-prototype-pipeline"]
    yield engine
    for minicroft in _booted.values():
        minicroft.stop()


def _session_after_a_reading(lang):
    """``tell_me_more_intent`` requires the ``prev_dialog`` context that the
    skill sets after it reads a date, so every row runs in such a session."""
    session = Session(f"golden-{lang}")
    session.lang = lang
    session.set_intent_context("prev_dialog", {"value": "day_1_month_1_events", "seen": []},
                               scope="shared", turns_remaining=3)
    return session.serialize()


def _routed(engine, utterance, lang):
    message = Message("recognizer_loop:utterance",
                      {"utterances": [utterance], "lang": lang},
                      {"lang": lang, "session": _session_after_a_reading(lang)})
    match = engine.match_low([utterance], lang, message)
    return [match.match_type] if match else []


def _row_id(row):
    return f"{row['lang']}:{row['utterance']}"


@pytest.mark.parametrize("row", GOLDEN, ids=_row_id)
def test_golden_row_routes_to_its_intent(engine_for, row):
    fired = _routed(engine_for(row["lang"]), row["utterance"], row["lang"])
    TALLY.assert_routed(row["utterance"], f"{SKILL_ID}:{row['intent_label']}", fired)


@pytest.mark.parametrize("row", NEGATIVE, ids=_row_id)
def test_negative_row_reaches_no_intent_of_the_skill(engine_for, row):
    fired = _routed(engine_for(row["lang"]), row["utterance"], row["lang"])
    TALLY.assert_not_routed(row["utterance"],
                            [t for t in fired if t.startswith(f"{SKILL_ID}:")], fired)


def test_every_shipping_locale_has_a_golden_file():
    golden = {p.stem.split("_", 2)[2] for p in END2END_DIR.glob("golden_utterances_*.jsonl")}
    shipping = {d.name for d in LOCALE_ROOT.iterdir() if d.is_dir() and any(d.rglob("*.intent"))}
    assert golden == shipping, f"golden files {sorted(golden ^ shipping)} differ from shipping locales"


#: Locales that ship the date and year intents only: no births, deaths or
#: follow-up intents yet, and event data taken from en-US.
LOCALES_WITHOUT_EVENT_INTENTS = {"fa-IR", "oc-FR", "pl-PL", "ru-RU"}
EVENT_INTENTS = {"births_in_history.intent", "deaths_in_history.intent", "tell_me_more_intent.intent"}


def test_every_locale_ships_every_en_us_intent():
    reference = {p.name for p in (LOCALE_ROOT / "en-US").rglob("*.intent")}
    missing = {d.name: set(reference - {p.name for p in d.rglob("*.intent")})
               for d in LOCALE_ROOT.iterdir() if d.is_dir() and any(d.rglob("*.intent"))}
    missing = {lang: files for lang, files in missing.items() if files}
    expected = {lang: EVENT_INTENTS for lang in LOCALES_WITHOUT_EVENT_INTENTS}
    assert missing == expected, f"locales without an en-US intent file: {missing}"
