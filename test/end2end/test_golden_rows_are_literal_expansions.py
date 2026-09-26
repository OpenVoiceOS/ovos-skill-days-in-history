"""Every golden row must be a literal expansion of its own intent template.

A row that no template covers still passes whenever padatious' fuzzy score
happens to clear its threshold, and fails when it does not. That is how
issue #124 read as a dev-red: the same sha, the same Python minor and the
same pytest command gave 1 failed in CI and 165 passed locally. The row was
'tell me about what happened on today', and `today_in_history.intent`
expanded to 103 phrasings without it, because every line starting
"tell me about" required "historical events".

A row that matches only on a score proves nothing about the templates, so
the check is expansion, not a live match: the utterance must be in the
expanded sample set of the `.intent` file for its own label and locale.
"""
import json
import os
from pathlib import Path

import pytest
from ovos_spec_tools.expansion import expand

ROOT = Path(__file__).resolve().parents[2]
END2END = Path(__file__).resolve().parent


def _expansions(path: Path) -> set:
    out = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line and not line.startswith("#"):
            out |= {" ".join(s.split()) for s in expand(line)}
    return out


def _rows():
    for path in sorted(END2END.glob("golden_utterances_*.jsonl")):
        lang = path.name[len("golden_utterances_"):-len(".jsonl")]
        for line in path.read_text(encoding="utf-8").splitlines():
            if line.strip():
                row = json.loads(line)
                row.setdefault("lang", lang)
                yield row


ROWS = list(_rows())


def test_the_golden_files_are_read():
    """The control: an empty sweep would make every case below vacuous."""
    assert len(ROWS) > 20, f"{len(ROWS)} golden rows found; the glob is stale"
    assert len({r["lang"] for r in ROWS}) > 1


@pytest.mark.parametrize("row", ROWS,
                         ids=lambda r: f"{r['lang']}-{r['utterance']}")
def test_the_row_is_a_literal_expansion(row):
    path = ROOT / "locale" / row["lang"] / f"{row['intent_label']}.intent"
    assert path.exists(), f"{path.relative_to(ROOT)} does not ship"
    assert row["utterance"] in _expansions(path), (
        f"[{row['lang']}] {row['utterance']!r} is not an expansion of "
        f"{row['intent_label']}.intent; the row can only match on a fuzzy "
        f"score, so it passes or fails by threshold")


def test_an_uncovered_phrasing_is_refused():
    """The control in the other direction: the check can still fail.

    This is the exact phrasing of issue #124, with the words that made it
    uncovered before the template landed.
    """
    covered = _expansions(ROOT / "locale" / "en-US" / "today_in_history.intent")
    assert "tell me about what happened on today" in covered
    assert "tell me about what happened on tomorrow" not in covered
