#!/usr/bin/env python3
"""Check that a card's link opens the verse where a reader can see it.

The study reader scrolls a fragment flush to the top of the window and draws
its chapter toolbar over that same strip, so a link straight to #p23 arrives
with verse 23 already clipped. `scroll_fragment` in `build_daily.py` answers
that by aiming the fragment a verse or two higher, at text that can be covered
instead -- while `id=` goes on highlighting the verse that was quoted.

That leaves two ways to get it wrong, and this checks both:

  * too shallow, and the toolbar still clips the verse it was followed for;
  * too deep, and the run-up above pushes the verse off the bottom instead.

So the cases below do not name a fragment and demand it back. They say how much
text a link is allowed to put above the verse, which is the thing a reader
actually sees, and stays meaningful if the cushion is ever retuned. The
fragment each case produces is printed beside it, so a change is legible in the
diff even when it stays within bounds.

Then `audit_calendar` reads the calendar that is actually shipped and counts
the links that gave up and kept their own anchor. The cases alone were not
enough: seven of them passed for a fortnight while one link in twenty landed
clipped, because a case can only fail on a chapter someone thought to write
down, and the shapes that broke were ordinary ones nobody had.

Run it:

    python tools/test_links.py

The cases need no network -- a chapter is spelt out here as its verse lengths
rather than its verse text, because only the lengths decide where a link lands.
The audit needs no network either: it reads data/daily.json, and skips itself
if the calendar has not been built yet.

Standard library only, like the builder, so CI installs nothing.
"""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_daily as builder  # noqa: E402

CALENDAR = Path(__file__).resolve().parent.parent / "data" / "daily.json"

# A verse's opening line has to clear the toolbar, and the toolbar covers about
# two lines of about thirty-four characters. A cushion shallower than that is
# not a cushion: the link still lands with the verse cut in half, which is the
# whole fault this exists to prevent. The floor here used to be 1 character,
# which nothing could fail -- and 38 links in the calendar were under 68.
MIN_CUSHION = 68

# And the far side: whatever is scrolled above the verse has to leave the verse
# itself on the screen. A phone shows something like twenty lines at a time, so
# a screen is roughly seven hundred characters, and a link may use all of it
# but the few lines the verse needs in order to have arrived at all.
MAX_CUSHION = 580

# Chapters as the shape that matters -- the length of each verse, in order from
# verse 1. Real ones, measured from the published text, except where a case
# says otherwise.
#
# Each case is a reference, its chapter's verse lengths, the verse quoted, and
# what the link should do about it:
#
#   "cushion"  scroll to an earlier verse, leaving MIN..MAX characters above
#   "top"      no fragment at all -- the verse opens the chapter
#   "opening"  scroll to the chapter's first verse and take what is there,
#              which is less than a full cushion, because there is no more
#   "clipped"  keep the verse's own anchor, because the verse above is too long
#              to stand in front of it
CASES = [
    # Mosiah 27: long narrative verses, the chapter in the report that started
    # this. One verse back is already plenty of cushion.
    ("Mosiah 27:23", [232, 411, 268, 322, 405, 240, 300, 383, 262, 293,
                      401, 281, 447, 268, 401, 542, 197, 213, 187, 236,
                      156, 337, 240], 23, "cushion"),
    # Alma 32:21, a mastery verse in a chapter of middling verses.
    ("Alma 32:21", [180, 213, 268, 214, 259, 311, 233, 121, 197, 224,
                    263, 241, 205, 197, 176, 260, 322, 251, 361, 293, 178],
     21, "cushion"),
    # 1 Nephi 3:7, with a short verse 6 above it and a long verse 5 above that.
    # Verse 6 alone already clears the toolbar, so the walk stops there rather
    # than taking verse 5 as well -- this is the case that caught a version of
    # the rule that gathered verses until it had six lines of them, and left
    # 1 Nephi 3:7 some 380 characters down the page when 118 had it clear.
    ("1 Nephi 3:7", [214, 258, 197, 141, 262, 118, 355], 7, "cushion"),
    # Moroni 7:45, deep in a chapter whose verses run very short: the case the
    # lookback exists for, where one verse of cushion is barely a cushion.
    ("Moroni 7:45", [60] * 44 + [280], 45, "cushion"),
    # Alma 57:27, the verse this test was rewritten for. Verse 26 is 402
    # characters -- two over a ceiling that used to be 400 -- so the link gave
    # up over two characters' worth of margin and shipped clipped, which is
    # what a reader photographed. Verse 26 is twelve lines and verse 27 is
    # four, and the two of them fit on one screen with room over.
    ("Alma 57:27", [206, 271, 147, 178, 69, 441, 118, 243, 286, 187,
                    269, 232, 185, 262, 278, 312, 340, 138, 177, 139,
                    234, 231, 115, 198, 371, 402, 144], 27, "cushion"),
    # The other half of the same fault, from a conference talk: the paragraph
    # above the quote is "How do we do this?" -- eighteen characters, a third
    # of a line, and no cushion at all. The walk has to carry on to the
    # paragraph above that, and what stopped it was a rule that read a full
    # cushion as a ceiling rather than a floor. Lengths from 23stevenson.
    ("A quote under a one-line question", [321, 258, 18, 223], 4, "cushion"),
    # A chapter opening: nothing is published above verse 1 to scroll to.
    ("2 Nephi 2:1", [301, 240, 268], 1, "top"),
    # The verse straight after one, where the only thing above it is short --
    # short, but still three lines, so it does the job on its own.
    ("Jacob 5:2", [96, 240, 310], 2, "cushion"),
    # And where it does not: Job 42:1 is 37 characters, one line, and there is
    # nothing above it to add to that. The link takes the one line rather than
    # none. This is the floor of what a fragment can do, and it is written down
    # here so nobody reads the number as a bug and tunes the rule to chase it.
    ("Job 42:2", [37, 87, 143, 88, 76, 55], 2, "opening"),
    # Invented, because the Book of Mormon's longest verses are not quite long
    # enough to show it: a verse whose neighbour above would fill the screen on
    # its own. The link keeps its own anchor and takes the clipping, rather
    # than opening a screen of the verse before and hiding the one it quotes.
    ("A verse under a very long one", [240, 900, 260], 3, "clipped"),
]

# How much of the calendar may land clipped. Some links have no better answer
# -- a conference paragraph of 969 characters really will fill a phone screen
# on its own -- so the budget is not zero. It is a ceiling on how ordinary that
# answer is allowed to become: 4 links of 1,141 when this was written, against
# 60 of the same 1,141 the fortnight before, when the rule gave up on any
# paragraph over 400 characters and nothing was counting.
CLIPPED_BUDGET = 0.03


def cushion(lengths: list[int], verse: int, fragment: str) -> int:
    """How much text a link puts above the verse it was followed for."""
    anchor = int(fragment.removeprefix("#p"))
    return sum(lengths[anchor - 1:verse - 1])


def run_cases() -> int:
    failures = []
    for reference, lengths, verse, want in CASES:
        parsed = {n: "x" * length for n, length in enumerate(lengths, start=1)}
        fragment = builder.verse_scroll(parsed, verse)
        above = cushion(lengths, verse, fragment) if fragment else 0

        if want == "top":
            ok = fragment == ""
            got = "no fragment" if ok else f"scrolled to {fragment}"
        elif want == "clipped":
            ok = fragment == f"#p{verse}"
            got = "own anchor" if ok else f"scrolled to {fragment}"
        elif want == "opening":
            ok = fragment == "#p1" and above < MIN_CUSHION
            got = f"{above} characters above it"
        else:
            ok = (fragment not in ("", f"#p{verse}")
                  and MIN_CUSHION <= above <= MAX_CUSHION)
            got = f"{above} characters above it"

        if not ok:
            failures.append((reference, want, fragment, got))
        print(f"  {'ok  ' if ok else 'FAIL'} {want:8} {reference:33} "
              f"{fragment or '(none)':8} {got}")

    print(f"\n{len(CASES)} links, {len(failures)} failures"
          f"  (a cushion is {MIN_CUSHION} to {MAX_CUSHION} characters)")
    for reference, want, fragment, got in failures:
        print(f"\n  {reference} should land \"{want}\" and instead links to "
              f"{fragment or '(no fragment)'}, leaving {got}."
              f"\n  Too little above the verse and the reader's own toolbar "
              f"clips it; too much and the verse starts below the fold.")
    return len(failures)


def audit_calendar() -> int:
    """Count the shipped links that gave up and kept the quoted verse's anchor.

    A link counts once however many days quote it: the calendar runs two years
    and comes back to a conference paragraph five or six times, and one link
    that lands badly is one link, not six.

    This cannot tell a link that had no better option from one the rule failed
    -- that needs the page text, which is neither in the calendar nor in CI.
    What it can see is how many there are, and that is the number that moved.
    """
    if not CALENDAR.exists():
        print("\nNo data/daily.json yet; skipping the calendar audit.")
        return 0

    with open(CALENDAR, encoding="utf-8") as fh:
        days = json.load(fh)["days"]

    links: set[str] = set()
    clipped: set[str] = set()
    for entry in days.values():
        for card in entry.values():
            url = card.get("url") if isinstance(card, dict) else None
            if not url:
                continue
            match = re.search(r"id=([^&#]*)(?:#(.*))?$", url)
            if not match:
                continue
            links.add(url)
            # `id=` may highlight a range or a list -- p45,p47-p48 -- and the
            # fragment is compared against the first of them, which is the
            # paragraph the link is aimed at.
            highlighted = match.group(1).split(",")[0].split("-")[0]
            if match.group(2) == highlighted:
                clipped.add(url)

    if not links:
        print("\nNo links in data/daily.json; skipping the calendar audit.")
        return 0

    share = len(clipped) / len(links)
    ok = share <= CLIPPED_BUDGET
    print(f"\n  {'ok  ' if ok else 'FAIL'} calendar   {len(links)} links, "
          f"{len(clipped)} clipped ({share:.1%}, budget {CLIPPED_BUDGET:.0%})")
    if not ok:
        for url in sorted(clipped)[:10]:
            print(f"         {url}")
        print(f"\n  {len(clipped)} of {len(links)} links in data/daily.json "
              f"scroll to the very paragraph they highlight, which lands it "
              f"under the reader's toolbar."
              f"\n  A few of those are unavoidable, but not this many: check "
              f"SCROLL_CEILING in build_daily.py against how long a paragraph "
              f"actually runs.")
    return 0 if ok else 1


def run() -> int:
    return run_cases() + audit_calendar()


if __name__ == "__main__":
    raise SystemExit(1 if run() else 0)
