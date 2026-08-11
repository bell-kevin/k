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

Run it:

    python tools/test_links.py

It needs no network: a chapter is spelt out here as its verse lengths rather
than its verse text, because only the lengths decide where a link lands.

Standard library only, like the builder, so CI installs nothing.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import build_daily as builder  # noqa: E402

# A verse's opening line has to clear the toolbar, so something has to be above
# it. One short verse is not always enough on its own -- which is why the
# builder keeps walking back -- but nothing at all is always too little.
MIN_CUSHION = 1

# And the far side: whatever is scrolled above the verse has to leave the verse
# itself on the screen. A phone shows something like twenty lines of scripture
# at a time, and a line holds about thirty characters, so half a screen is
# roughly three hundred characters. A little over that is still a verse opening
# in the lower half of the screen, which is readable; much over it is a verse
# nobody can see.
MAX_CUSHION = 400

# Chapters as the shape that matters -- the length of each verse, in order from
# verse 1. Real ones, measured from the published text, except where a case
# says otherwise.
#
# Each case is a reference, its chapter's verse lengths, the verse quoted, and
# what the link should do about it:
#
#   "cushion"  scroll to an earlier verse, leaving MIN..MAX characters above
#   "top"      no fragment at all -- the verse opens the chapter
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
    # Taking both would overshoot, so the link stops after the short one --
    # this is the case that caught the first version of the rule, which
    # gathered verses until it had enough and sailed straight past the ceiling.
    ("1 Nephi 3:7", [214, 258, 197, 141, 262, 118, 355], 7, "cushion"),
    # Moroni 7:45, deep in a chapter whose verses run very short: the case the
    # lookback exists for, where one verse of cushion is barely a cushion.
    ("Moroni 7:45", [60] * 44 + [280], 45, "cushion"),
    # A chapter opening: nothing is published above verse 1 to scroll to.
    ("2 Nephi 2:1", [301, 240, 268], 1, "top"),
    # The verse straight after one, where the only thing above it is short.
    ("Jacob 5:2", [96, 240, 310], 2, "cushion"),
    # Invented, because the Book of Mormon's longest verses are not quite long
    # enough to show it: a verse whose neighbour above would fill the screen on
    # its own. The link keeps its own anchor and takes the clipping, rather
    # than opening a screen of the verse before and hiding the one it quotes.
    ("A verse under a very long one", [240, 900, 260], 3, "clipped"),
]


def cushion(lengths: list[int], verse: int, fragment: str) -> int:
    """How much text a link puts above the verse it was followed for."""
    anchor = int(fragment.removeprefix("#p"))
    return sum(lengths[anchor - 1:verse - 1])


def run() -> int:
    failures = []
    for reference, lengths, verse, want in CASES:
        parsed = {n: "x" * length for n, length in enumerate(lengths, start=1)}
        fragment = builder.verse_scroll(parsed, verse)

        if want == "top":
            ok = fragment == ""
            got = "no fragment" if ok else f"scrolled to {fragment}"
        elif want == "clipped":
            ok = fragment == f"#p{verse}"
            got = "own anchor" if ok else f"scrolled to {fragment}"
        else:
            above = cushion(lengths, verse, fragment) if fragment else 0
            ok = fragment not in ("", f"#p{verse}") and MIN_CUSHION <= above <= MAX_CUSHION
            got = f"{above} characters above it"

        if not ok:
            failures.append((reference, want, fragment, got))
        print(f"  {'ok  ' if ok else 'FAIL'} {want:8} {reference:30} "
              f"{fragment or '(none)':8} {got}")

    print(f"\n{len(CASES)} links, {len(failures)} failures"
          f"  (a cushion is {MIN_CUSHION} to {MAX_CUSHION} characters)")
    for reference, want, fragment, got in failures:
        print(f"\n  {reference} should land \"{want}\" and instead links to "
              f"{fragment or '(no fragment)'}, leaving {got}."
              f"\n  Too little above the verse and the reader's own toolbar "
              f"clips it; too much and the verse starts below the fold.")
    return len(failures)


if __name__ == "__main__":
    raise SystemExit(1 if run() else 0)
