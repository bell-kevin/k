#!/usr/bin/env python3
"""Check that `reads_as_a_reading` still answers the way it has been told to.

Every case in `readings_cases.json` is a verse someone looked at and ruled on:
this one can be read cold, that one cannot. The rules in `build_daily.py` are
regular expressions over English, so they generalise in ways nobody intended --
a pattern written to refuse "And they rehearsed unto his father" also refused
"But this much I can tell you", and one written to keep Moroni 7:44 also kept
2 Nephi 2:7. This is what catches that.

Run it:

    python tools/test_readings.py

It needs no network and no cache: the verses are committed alongside it. That
matters, because the one thing this file must never do is test text that is not
the text a card would show. An earlier version of these cases was typed out by
hand, and a 2 Nephi 2:7 missing its last clause passed a test that the verse as
published fails -- the rule was wrong, the test agreed with it, and only a
sweep of the whole book caught it.

So the text is never written by hand. To add a case, put in the reference and
the verdict, leave "text" out, and run:

    python tools/test_readings.py --refresh

which fills it in from the study API, through the same fetch and the same
parser the builder uses. To confirm the committed text is still what the Church
publishes -- worth doing if a case ever looks wrong -- run:

    python tools/test_readings.py --verify

Standard library only, like the builder, so CI installs nothing.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_daily as builder  # noqa: E402

CASES = Path(__file__).resolve().parent / "readings_cases.json"


def load() -> dict:
    with open(CASES, encoding="utf-8") as fh:
        return json.load(fh)


def save(data: dict) -> None:
    CASES.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n",
                     encoding="utf-8", newline="\n")


def published(case: dict) -> str | None:
    """The verse as the study API gives it, through the builder's own parser."""
    page = builder.fetch(f"/scriptures/{case['path']}")
    if not page:
        return None
    return builder.parse_verses(page["content"]["body"]).get(case["verse"])


def run(data: dict) -> int:
    """Every case, checked against the rule. Returns the number of failures."""
    failures = []
    for case in data["cases"]:
        want = case["verdict"] == "keep"
        got = builder.reads_as_a_reading(case["text"])
        if got != want:
            failures.append(case)
        mark = "ok  " if got == want else "FAIL"
        ruled = " *" if case.get("ruled") else "  "
        print(f"  {mark}{ruled} {case['verdict']:6} {case['reference']}")

    print(f"\n{len(data['cases'])} cases, {len(failures)} failures"
          f"  (* = ruled on by a reader, not a guess)")
    for case in failures:
        print(f"\n  {case['reference']} should {case['verdict']}, and does not."
              f"\n  Why it was ruled that way: {case['why']}"
              f"\n  {case['text']}")
    return len(failures)


def refresh(data: dict, verify_only: bool) -> int:
    """Refill (or check) each case's text from the study API."""
    problems = 0
    for case in data["cases"]:
        text = published(case)
        if not text:
            print(f"  ?? {case['reference']}: could not be fetched")
            problems += 1
            continue
        if verify_only:
            if text != case.get("text"):
                print(f"  !! {case['reference']}: committed text differs from "
                      f"what is published now")
                print(f"     committed: {case.get('text', '')[:100]}")
                print(f"     published: {text[:100]}")
                problems += 1
            continue
        case["text"] = text

    if not verify_only:
        save(data)
        print(f"Refreshed {len(data['cases'])} cases in {CASES.name}")
    elif not problems:
        print(f"All {len(data['cases'])} cases match what is published.")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    group = ap.add_mutually_exclusive_group()
    group.add_argument("--refresh", action="store_true",
                       help="refill every case's text from the study API and "
                            "rewrite readings_cases.json")
    group.add_argument("--verify", action="store_true",
                       help="check the committed text still matches what the "
                            "study API publishes, without rewriting anything")
    args = ap.parse_args()

    data = load()
    if args.refresh or args.verify:
        return 1 if refresh(data, verify_only=args.verify) else 0
    return 1 if run(data) else 0


if __name__ == "__main__":
    raise SystemExit(main())
