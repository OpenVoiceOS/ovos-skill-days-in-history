"""Golden rows in every locale route to their intent on the m2v pipeline.

For each ``golden_utterances_<lang>.jsonl`` in this directory, one MiniCroft
loads the real skill in that language on the m2v prototype pipeline, the
model2vec engine built at boot from the skill's own ``.intent`` files. Each
row's utterance goes through that pipeline's high, medium and low tiers in
order, and the row passes when the first tier to match names its
``intent_label``. The engine embeds the utterance, so a row that no template
spells out word for word still matches when it means the same thing.

``tell_me_more_intent`` requires the shared ``prev_dialog`` intent context,
which the skill sets after it reads a date. Every row runs in a session that
carries that context, as it is after a reading, so the follow-up intent
competes with the other three on every row.

Each ``negative_utterances_<lang>.jsonl`` holds requests for other skills.
They run in the same session and must not match any intent of this skill.

Each locale must match at least ``MIN_MATCH_RATE`` of its golden rows, and at
least ``MIN_MATCHED_ROWS_PER_INTENT`` rows of each intent. A locale listed in
``GOLDEN_LOCALE_GAPS`` records its measured rate: its rate check is an
expected failure, but the per-intent floor and a drop of more than
``GAP_TOLERANCE`` below that rate still fail it. A negative row that
matches this skill fails the locale, unless ``NEGATIVE_KNOWN_CLAIMS`` lists
that claim. All rows run, including rows marked ``needs_manual`` or
``machine_generated``, and the test prints every row that misses with the
intent that matched instead.
"""
import json
from pathlib import Path

import pytest
from ovos_bus_client.message import Message
from ovos_bus_client.session import Session
from ovoscope import M2V_PUBLISHED_MODEL, get_m2v_minicroft
from ovoscope.golden_minicroft import warm_m2v_models

SKILL_ID = "ovos-skill-days-in-history.openvoiceos"
M2V_PROTOTYPE = "ovos-m2v-prototype-pipeline"
TIERS = ("high", "medium", "low")
# m2v gives some rows a different answer on each boot, so the test gates on
# the share of rows that match per locale, not on each row.
MIN_MATCH_RATE = 0.8
# A locale also fails when any of its intents has fewer matched rows than this.
MIN_MATCHED_ROWS_PER_INTENT = 1
END2END_DIR = Path(__file__).parent
LOCALE_ROOT = END2END_DIR.parents[1] / "locale"
# Locales whose golden rows match below MIN_MATCH_RATE on the published m2v
# model, with the rate measured in two runs. The rate check of such a locale
# is an expected failure. The locale still fails when any intent has no
# matched row, when its rate falls more than GAP_TOLERANCE below the measured
# rate, and when its rate reaches MIN_MATCH_RATE: the stale entry goes.
GOLDEN_LOCALE_GAPS = {
    "ca-ES": (0.636, "published m2v model predates these templates; remove after retrain"),
    "da-DK": (0.72, "published m2v model predates these templates; remove after retrain"),
    "de-DE": (0.727, "published m2v model predates these templates; remove after retrain"),
    "en-US": (0.585, "published m2v model predates these templates; remove after retrain"),
    "es-CO": (0.682, "published m2v model predates these templates; remove after retrain"),
    "es-ES": (0.68, "published m2v model predates these templates; remove after retrain"),
    "eu-ES": (0.545, "published m2v model predates these templates; remove after retrain"),
    "fa-IR": (0.3, "published m2v model predates these templates; remove after retrain"),
    "fr-FR": (0.625, "published m2v model predates these templates; remove after retrain"),
    "gl-ES": (0.571, "published m2v model predates these templates; remove after retrain"),
    "it-IT": (0.586, "published m2v model predates these templates; remove after retrain"),
    "kab": (0.545, "published m2v model predates these templates; remove after retrain"),
    "nl-NL": (0.567, "published m2v model predates these templates; remove after retrain"),
    "oc-FR": (0.4, "published m2v model predates these templates; remove after retrain"),
    "pl-PL": (0.4, "published m2v model predates these templates; remove after retrain"),
    "pt-BR": (0.69, "published m2v model predates these templates; remove after retrain"),
    "pt-PT": (0.682, "published m2v model predates these templates; remove after retrain"),
    "ru-RU": (0.3, "published m2v model predates these templates; remove after retrain"),
    "sv-SE": (0.767, "published m2v model predates these templates; remove after retrain"),
}
# The prototype engine embeds the template's typed ``{year}`` slot as literal
# text, so a gold row with a real year scores under its low-tier cosine of 0.65
# against the year_in_history anchors, though that intent is the nearest one.
YEAR_SLOT_GAP = "m2v prototype anchors keep the {year} placeholder unfilled; remove when the engine fills typed number slots"
# {lang: {intent: reason}}: intents with no matched row on the published m2v
# model. Such an intent is allowed to have no matched row; the test fails when
# it gains one, so the entry goes after a retrain.
GOLDEN_INTENT_GAPS = {
    "ca-ES": {"tell_me_more_intent": "published m2v model predates these templates; remove after retrain"},
    "de-DE": {"tell_me_more_intent": "published m2v model predates these templates; remove after retrain"},
    "es-ES": {"tell_me_more_intent": "published m2v model predates these templates; remove after retrain"},
    "fa-IR": {"year_in_history": YEAR_SLOT_GAP},
    "gl-ES": {"year_in_history": YEAR_SLOT_GAP},
    "kab": {"tell_me_more_intent": "published m2v model predates these templates; remove after retrain", "year_in_history": YEAR_SLOT_GAP},
    "nl-NL": {"year_in_history": YEAR_SLOT_GAP},
    "oc-FR": {"year_in_history": YEAR_SLOT_GAP},
    "pt-BR": {"tell_me_more_intent": "published m2v model predates these templates; remove after retrain"},
    "pt-PT": {"year_in_history": YEAR_SLOT_GAP},
    "ru-RU": {"year_in_history": YEAR_SLOT_GAP},
}
GAP_TOLERANCE = 0.10
# Locales whose negative rows the published m2v model cannot separate from
# this skill, with the measured reason.
NEGATIVE_ENGINE_GAPS = {}
# Negative rows that m2v claimed for this skill in two separate runs. A listed
# claim is allowed, not required, so a row that flips between boots does not
# fail the test. Any other claim fails the locale.
NEGATIVE_KNOWN_CLAIMS = {
    "sv-SE": {"berätta ett skämt": "tell_me_more_intent"},
    "es-ES": {"qué fecha es hoy": "today_in_history",
              "cuéntame un chiste": "tell_me_more_intent"},
    "gl-ES": {"cóntame un chiste": "tell_me_more_intent"},
    "it-IT": {"raccontami una barzelletta": "tell_me_more_intent"},
}


def _rows_by_lang(prefix):
    rows = {}
    for path in sorted(END2END_DIR.glob(f"{prefix}_*.jsonl")):
        lang = path.stem.removeprefix(f"{prefix}_")
        for number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if line.strip():
                row = json.loads(line)
                assert row["lang"] == lang, f"{path.name}:{number} has lang {row['lang']!r}"
                rows.setdefault(lang, []).append(row)
    return rows


ROWS = _rows_by_lang("golden_utterances")
NEGATIVE_ROWS = _rows_by_lang("negative_utterances")


def _session_after_a_reading(lang):
    session = Session(f"golden-{lang}")
    session.lang = lang
    session.set_intent_context("prev_dialog", {"value": "day_1_month_1_events", "seen": []},
                               scope="shared", turns_remaining=3)
    return session.serialize()


def _matched_intent(engine, utterance, lang):
    message = Message("recognizer_loop:utterance",
                      {"utterances": [utterance], "lang": lang},
                      {"lang": lang, "session": _session_after_a_reading(lang)})
    match = next(filter(None, (getattr(engine, f"match_{tier}")([utterance], lang, message)
                               for tier in TIERS)), None)
    return match.match_type if match else None


def _match_all(lang, rows):
    """Boot the skill on m2v in ``lang`` and return the intent each row matches."""
    minicroft = get_m2v_minicroft([SKILL_ID], model=M2V_PUBLISHED_MODEL,
                                  lang=lang, classifier=False)
    try:
        warm_m2v_models(minicroft)
        engine = minicroft.intents.pipeline_plugins[M2V_PROTOTYPE]
        return [_matched_intent(engine, row["utterance"], lang) for row in rows]
    finally:
        minicroft.stop()


@pytest.mark.timeout(900)
@pytest.mark.parametrize("lang", sorted(ROWS))
def test_golden_rows_match_their_intent(lang):
    rows = ROWS[lang]
    matched = _match_all(lang, rows)
    misses = []
    hits = {row["intent_label"]: 0 for row in rows}
    for row, got in zip(rows, matched):
        if got == f"{SKILL_ID}:{row['intent_label']}":
            hits[row["intent_label"]] += 1
        else:
            misses.append(f"{row['utterance']!r}: expected {row['intent_label']}, got {got}")
    intent_gaps = GOLDEN_INTENT_GAPS.get(lang, {})
    starved = sorted(label for label, count in hits.items()
                     if count < MIN_MATCHED_ROWS_PER_INTENT and label not in intent_gaps)
    revived = sorted(label for label in intent_gaps if hits.get(label, 0) >= MIN_MATCHED_ROWS_PER_INTENT)
    assert not revived, f"[{lang}] intents matched rows again, remove them from GOLDEN_INTENT_GAPS: {revived}"
    rate = 1 - len(misses) / len(rows)
    print(f"[{lang}] {rate:.1%} of {len(rows)} rows match", *misses, sep="\n  ")
    if starved:
        print(f"[{lang}] intents below {MIN_MATCHED_ROWS_PER_INTENT} matched rows: {starved}")
    assert not starved, (
        f"[{lang}] intents below {MIN_MATCHED_ROWS_PER_INTENT} matched rows: {starved}"
    )
    if lang in GOLDEN_LOCALE_GAPS:
        measured, reason = GOLDEN_LOCALE_GAPS[lang]
        assert rate >= measured - GAP_TOLERANCE, (
            f"[{lang}] {rate:.1%} of rows match, more than {GAP_TOLERANCE:.0%} below "
            f"the measured {measured:.1%}:\n  " + "\n  ".join(misses)
        )
        assert rate < MIN_MATCH_RATE, (
            f"[{lang}] {rate:.1%} of rows match, at the gate: remove its GOLDEN_LOCALE_GAPS entry"
        )
        pytest.xfail(f"[{lang}] {rate:.1%} of rows match: {reason}")
    assert rate >= MIN_MATCH_RATE, (
        f"[{lang}] {rate:.1%} of rows match, below {MIN_MATCH_RATE:.0%}:\n  " + "\n  ".join(misses)
    )


@pytest.mark.timeout(900)
@pytest.mark.parametrize("lang", [
    pytest.param(lang, marks=pytest.mark.xfail(reason=NEGATIVE_ENGINE_GAPS[lang]))
    if lang in NEGATIVE_ENGINE_GAPS else lang
    for lang in sorted(NEGATIVE_ROWS)
])
def test_negative_rows_match_no_skill_intent(lang):
    rows = NEGATIVE_ROWS[lang]
    known = NEGATIVE_KNOWN_CLAIMS.get(lang, {})
    matched = _match_all(lang, rows)
    claims = [(row["utterance"], got.removeprefix(f"{SKILL_ID}:"))
              for row, got in zip(rows, matched)
              if got and got.startswith(f"{SKILL_ID}:")]
    unknown = [f"{utterance!r}: matched {intent}" for utterance, intent in claims
               if known.get(utterance) != intent]
    print(f"[{lang}] {len(claims)} of {len(rows)} negative rows claimed, "
          f"{len(unknown)} not in NEGATIVE_KNOWN_CLAIMS", *unknown, sep="\n  ")
    assert not unknown, f"[{lang}] negative rows matched this skill:\n  " + "\n  ".join(unknown)


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
