"""Kabyle bare-year and bare-date requests reach the intent that answers them."""
from pathlib import Path

import pytest
from padacioso import IntentContainer

LOCALE = Path(__file__).resolve().parents[1] / "locale" / "kab"


def _route(utterance):
    container = IntentContainer()
    for intent in ("year_in_history", "today_in_history", "births_in_history", "deaths_in_history"):
        lines = (LOCALE / f"{intent}.intent").read_text(encoding="utf-8").splitlines()
        container.add_intent(intent, [line for line in lines if line.strip() and not line.startswith("#")])
    return container.calc_intent(utterance)["name"]


@pytest.mark.parametrize("utterance, intent", [
    ("tadyant n 1990", "year_in_history"),
    ("taqsiṭ n 1990", "year_in_history"),
    ("tadyant n useggas 1990", "year_in_history"),
    ("tadyant n wass 3 meɣres", "today_in_history"),
    ("tadyant n meɣres 3", "today_in_history"),
    ("taqsiṭ n meɣres 3", "today_in_history"),
])
def test_kab_request_reaches_its_intent(utterance, intent):
    assert _route(utterance) == intent
