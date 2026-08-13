"""Template-lint gate for ovos-skill-days-in-history's resource files.

This is the permanent CI guard for the class of bug found live on ser9:
a malformed OVOS-INTENT-1 template line (a `(word)` single-branch group,
CSS/markup leaked from the Wikipedia scrape, or an unbalanced bracket) makes
it into a ``.dialog``/``.intent``/``.voc`` file, ``random.choice`` eventually
picks that exact line, and rendering raises
``ovos_spec_tools.expansion.MalformedTemplate`` -- which used to propagate
out of the intent handler as ``skill.error`` (see ``__init__.py``'s
``_speak_dialog_safe``, which now tolerates this at runtime; this test is
the CI-side flag per the "tolerate at runtime, FLAG in CI" policy, so the
defect gets fixed instead of silently swallowed forever).

Every non-comment, non-blank line of every locale resource file is expanded
with the same ``ovos_spec_tools.expand`` call the runtime dialog renderer
uses. A small, explicitly documented allowlist covers the handful of lines
where the *content itself* is literal, unescapable parenthesis characters
(ASCII emoticons) that the current OVOS-INTENT-1 grammar has no way to
represent -- there is no escape syntax for a literal ``(`` or ``)`` -- so
fixing them would require inventing/rewording the historical text, which is
out of scope for a syntax-only fix. Everything else must expand cleanly.

Deliberately NOT `@pytest.mark.parametrize`d over all ~580k lines: a
parametrized run creates one `pytest.param` (and one collected/reported
test item) per line, which measured at 494s wall clock and ~3.6GB peak RSS
-- close to OOM on a 7GB CI runner -- with the 580k Item/param objects
being the entire overhead, not the actual `expand()` work. A single test
that loops `_iter_resource_lines()` in plain Python and collects every
failure into one assertion message does the same check in ~5s with
negligible memory, at the cost of pytest reporting one pass/fail instead of
580k individual selectable test IDs -- an acceptable trade for a data-file
syntax lint (nobody needs to `pytest -k` a single bad line; the failure
message below already gives file:line for every offender).
"""
from pathlib import Path

from ovos_spec_tools import expand, MalformedTemplate

SKILL_ROOT = Path(__file__).parent.parent
LOCALE_ROOT = SKILL_ROOT / "locale"
RESOURCE_EXTS = (".dialog", ".intent", ".voc")

# file-relative-to-locale-root -> {1-based line numbers}
# Each entry is a literal ASCII emoticon (":-)"/":-(" ) baked into historical
# text describing Scott Fahlman's 1982 emoticon post. OVOS-INTENT-1 has no
# escape mechanism for literal metacharacters, so the parenthesis in the
# emoticon itself cannot be represented without changing the quoted text.
# The runtime dialog renderer tolerates this (falls back to the raw line);
# this allowlist keeps that one narrow, understood exception from paging CI
# for something a resource-file syntax fix can't actually solve.
KNOWN_UNFIXABLE = {
    "ca-ES/day_19_month_9_events.dialog": {29},
    "da-DK/day_19_month_9_events.dialog": {29},
    "en-US/day_19_month_9_events.dialog": {29},
    "fr-FR/day_19_month_9_events.dialog": {32},
    "pt-PT/day_19_month_9_events.dialog": {29},
}


def _iter_resource_lines():
    for path in sorted(LOCALE_ROOT.rglob("*")):
        if not path.is_file() or path.suffix not in RESOURCE_EXTS:
            continue
        rel = path.relative_to(LOCALE_ROOT).as_posix()
        with open(path, encoding="utf-8") as f:
            for lineno, line in enumerate(f, start=1):
                body = line.rstrip("\n")
                if not body.strip() or body.strip().startswith("#"):
                    continue
                yield rel, lineno, body


def test_all_resource_lines_expand():
    """Every non-comment, non-blank resource line (minus the documented
    literal-parenthesis allowlist) must expand without raising
    MalformedTemplate. Collects every failure so one run reports the full
    list, not just the first offender."""
    failures = []
    checked = 0
    for rel, lineno, body in _iter_resource_lines():
        if lineno in KNOWN_UNFIXABLE.get(rel, ()):
            continue
        checked += 1
        try:
            expand(body)
        except MalformedTemplate as err:
            failures.append(f"{rel}:{lineno}: {err}\n    {body!r}")

    assert checked > 0, "no resource lines were found to check -- locale layout changed?"
    assert not failures, (
        f"{len(failures)} malformed template line(s) out of {checked} checked:\n\n"
        + "\n".join(failures)
    )


def test_known_unfixable_allowlist_is_still_accurate():
    """The allowlist should only ever contain lines that genuinely still
    fail -- if a line on it now expands cleanly, remove it instead of
    letting the exception rot."""
    for relpath, linenos in KNOWN_UNFIXABLE.items():
        path = LOCALE_ROOT / relpath
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
        for lineno in linenos:
            body = lines[lineno - 1].rstrip("\n")
            try:
                expand(body)
            except MalformedTemplate:
                continue
            raise AssertionError(
                f"{relpath}:{lineno} is allowlisted as unfixable but now "
                f"expands cleanly -- remove it from KNOWN_UNFIXABLE: {body!r}"
            )
