#!/usr/bin/env python3
"""Build a prebuilt calendar of daily picks for the static site.

Pulls only publicly readable, no-login content from churchofjesuschrist.org:

  * Book of Mormon chapters      -> a daily verse
  * Come, Follow Me weekly pages -> a daily verse from this week's reading
  * General Conference talks     -> a daily quote

The result is written to data/daily.json, which the site reads directly. The
site never calls churchofjesuschrist.org at runtime, so a page view works even
if that site changes shape or goes down; only a rebuild would notice.

Standard library only, so CI needs no dependencies.
"""

from __future__ import annotations

import argparse
import datetime as dt
import gzip
import html
import http.client
import json
import os
import random
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CACHE = ROOT / ".cache"
OUT = ROOT / "data" / "daily.json"
# The same calendar again, one file per month, for the script to fetch a
# tenth of it instead of the whole two years -- see `write_months`.
MONTH_DIR = ROOT / "data" / "months"
SPEAKERS = ROOT / "assets" / "speakers"

API = "https://www.churchofjesuschrist.org/study/api/v3/language-pages/type/content"
UA = "Mozilla/5.0 (compatible; no-login-daily-verse/1.0; static site builder)"

# Daily picks are indexed from this fixed date, so a given day always resolves
# to the same verse no matter when the calendar was last rebuilt.
EPOCH = dt.date(2026, 1, 1)

# The Book of Mormon's book/chapter structure is fixed, so it is stated here
# rather than scraped -- one less thing that can break upstream.
BOM_BOOKS = [
    ("1-ne", "1 Nephi", 22), ("2-ne", "2 Nephi", 33), ("jacob", "Jacob", 7),
    ("enos", "Enos", 1), ("jarom", "Jarom", 1), ("omni", "Omni", 1),
    ("w-of-m", "Words of Mormon", 1), ("mosiah", "Mosiah", 29),
    ("alma", "Alma", 63), ("hel", "Helaman", 16), ("3-ne", "3 Nephi", 30),
    ("4-ne", "4 Nephi", 1), ("morm", "Mormon", 9), ("ether", "Ether", 15),
    ("moro", "Moroni", 10),
]

# Volume slug -> display name, for resolving Come, Follow Me citations.
VOLUMES = {"ot": "Old Testament", "nt": "New Testament", "bofm": "Book of Mormon",
           "dc-testament": "Doctrine and Covenants", "pgp": "Pearl of Great Price"}

# Book slug -> display name for the books Come, Follow Me is most likely to
# cite. Anything missing falls back to a title-cased slug.
BOOK_NAMES = {
    "gen": "Genesis", "ex": "Exodus", "lev": "Leviticus", "num": "Numbers",
    "deut": "Deuteronomy", "josh": "Joshua", "judg": "Judges", "ruth": "Ruth",
    "1-sam": "1 Samuel", "2-sam": "2 Samuel", "1-kgs": "1 Kings", "2-kgs": "2 Kings",
    "1-chr": "1 Chronicles", "2-chr": "2 Chronicles", "ezra": "Ezra",
    "neh": "Nehemiah", "esth": "Esther", "job": "Job", "ps": "Psalms",
    "prov": "Proverbs", "eccl": "Ecclesiastes", "song": "Song of Solomon",
    "isa": "Isaiah", "jer": "Jeremiah", "lam": "Lamentations", "ezek": "Ezekiel",
    "dan": "Daniel", "hosea": "Hosea", "joel": "Joel", "amos": "Amos",
    "obad": "Obadiah", "jonah": "Jonah", "micah": "Micah", "nahum": "Nahum",
    "hab": "Habakkuk", "zeph": "Zephaniah", "hag": "Haggai", "zech": "Zechariah",
    "mal": "Malachi", "matt": "Matthew", "mark": "Mark", "luke": "Luke",
    "john": "John", "acts": "Acts", "rom": "Romans", "1-cor": "1 Corinthians",
    "2-cor": "2 Corinthians", "gal": "Galatians", "eph": "Ephesians",
    "philip": "Philippians", "col": "Colossians", "1-thes": "1 Thessalonians",
    "2-thes": "2 Thessalonians", "1-tim": "1 Timothy", "2-tim": "2 Timothy",
    "titus": "Titus", "philem": "Philemon", "heb": "Hebrews", "james": "James",
    "1-pet": "1 Peter", "2-pet": "2 Peter", "1-jn": "1 John", "2-jn": "2 John",
    "3-jn": "3 John", "jude": "Jude", "rev": "Revelation",
    "moses": "Moses", "abr": "Abraham", "js-m": "Joseph Smith—Matthew",
    "js-h": "Joseph Smith—History", "a-of-f": "Articles of Faith",
    "dc": "Doctrine and Covenants", "od": "Official Declaration",
}
BOOK_NAMES.update({slug: name for slug, name, _ in BOM_BOOKS})


# --------------------------------------------------------------------------
# scripture mastery
# --------------------------------------------------------------------------

# The hundred passages the Church's seminary programme asks students to know:
# twenty-five from each standard work. They are the settled answer to "which
# verses matter most", arrived at by people whose job was to decide it, so they
# are carried here as a fixed list rather than guessed at by the scoring below.
#
# They matter to this build in two ways. Every one of them is guaranteed a turn
# in the Book of Mormon calendar, spaced through the year; and any of the
# hundred that falls inside a Come, Follow Me week's reading is put into that
# week whether or not the lesson page happens to link it.
#
# Each entry is the chapter's study path and the verses to quote. Non-adjacent
# verses are cited exactly as the mastery list cites them -- "2 Nephi 25:23, 26"
# is that pair and not the four verses between them.
MASTERY: list[tuple[str, list[int]]] = [
    # Old Testament (with the Pearl of Great Price passages it is taught beside)
    ("pgp/moses/1", [39]), ("pgp/moses/7", [18]), ("pgp/abr/3", [22, 23]),
    ("ot/gen/1", [26, 27]), ("ot/gen/2", [24]), ("ot/gen/39", [9]),
    ("ot/ex/19", [5, 6]), ("ot/ex/20", list(range(3, 18))),
    ("ot/josh/24", [15]), ("ot/1-sam/16", [7]), ("ot/ps/24", [3, 4]),
    ("ot/ps/119", [105]), ("ot/ps/127", [3]), ("ot/prov/3", [5, 6]),
    ("ot/isa/1", [18]), ("ot/isa/5", [20]), ("ot/isa/29", [13, 14]),
    ("ot/isa/53", [3, 4, 5]), ("ot/isa/58", [6, 7]), ("ot/isa/58", [13, 14]),
    ("ot/jer/1", [4, 5]), ("ot/ezek/37", [15, 16, 17]), ("ot/amos/3", [7]),
    ("ot/mal/3", [8, 9, 10]), ("ot/mal/4", [5, 6]),
    # New Testament
    ("nt/matt/5", [14, 15, 16]), ("nt/matt/11", [28, 29, 30]),
    ("nt/matt/16", [15, 16, 17, 18, 19]), ("nt/matt/22", [36, 37, 38, 39]),
    ("nt/matt/28", [19, 20]), ("nt/luke/24", [36, 37, 38, 39]),
    ("nt/john/3", [5]), ("nt/john/14", [6]), ("nt/john/14", [15]),
    ("nt/john/17", [3]), ("nt/acts/2", [36, 37, 38]), ("nt/acts/3", [19, 20, 21]),
    ("nt/1-cor/6", [19, 20]), ("nt/1-cor/15", [20, 21, 22]),
    ("nt/1-cor/15", [40, 41, 42]), ("nt/gal/5", [22, 23]),
    ("nt/eph/4", [11, 12, 13, 14]), ("nt/philip/4", [13]),
    ("nt/2-thes/2", [1, 2, 3]), ("nt/2-tim/3", [15, 16, 17]),
    ("nt/heb/12", [9]), ("nt/james/1", [5, 6]), ("nt/james/2", [17, 18]),
    ("nt/1-pet/4", [6]), ("nt/rev/20", [12]),
    # Book of Mormon
    ("bofm/1-ne/3", [7]), ("bofm/2-ne/2", [25]), ("bofm/2-ne/2", [27]),
    ("bofm/2-ne/9", [28, 29]), ("bofm/2-ne/25", [23, 26]),
    ("bofm/2-ne/28", [7, 8, 9]), ("bofm/2-ne/31", [19, 20]),
    ("bofm/2-ne/32", [3]), ("bofm/2-ne/32", [8, 9]), ("bofm/mosiah/2", [17]),
    ("bofm/mosiah/3", [19]), ("bofm/mosiah/4", [30]),
    ("bofm/alma/7", [11, 12, 13]), ("bofm/alma/32", [21]),
    ("bofm/alma/37", [35]), ("bofm/alma/39", [9]), ("bofm/alma/41", [10]),
    ("bofm/hel/5", [12]), ("bofm/3-ne/12", [48]),
    ("bofm/3-ne/18", [15, 20, 21]), ("bofm/ether/12", [6]),
    ("bofm/ether/12", [27]), ("bofm/moro/7", [41]),
    ("bofm/moro/7", [45, 47, 48]), ("bofm/moro/10", [4, 5]),
    # Doctrine and Covenants (with the Joseph Smith—History passage)
    ("pgp/js-h/1", list(range(15, 21))), ("dc-testament/dc/1", [37, 38]),
    ("dc-testament/dc/6", [36]), ("dc-testament/dc/8", [2, 3]),
    ("dc-testament/dc/10", [5]), ("dc-testament/dc/13", [1]),
    ("dc-testament/dc/18", [10, 11]), ("dc-testament/dc/18", [15, 16]),
    ("dc-testament/dc/19", [16, 17, 18, 19]), ("dc-testament/dc/19", [23]),
    ("dc-testament/dc/25", [13]), ("dc-testament/dc/46", [33]),
    ("dc-testament/dc/58", [27]), ("dc-testament/dc/58", [42, 43]),
    ("dc-testament/dc/64", [9, 10, 11]), ("dc-testament/dc/76", [22, 23, 24]),
    ("dc-testament/dc/76", [40, 41]), ("dc-testament/dc/78", [19]),
    ("dc-testament/dc/82", [10]), ("dc-testament/dc/88", [124]),
    ("dc-testament/dc/89", [18, 19, 20, 21]), ("dc-testament/dc/107", [8]),
    ("dc-testament/dc/121", [36, 41, 42]), ("dc-testament/dc/130", [22, 23]),
    ("dc-testament/dc/131", [1, 2, 3, 4]),
]


def verse_ranges(nums: list[int]) -> list[tuple[int, int]]:
    """[45, 47, 48] -> [(45, 45), (47, 48)]"""
    runs: list[tuple[int, int]] = []
    for num in sorted(nums):
        if runs and num == runs[-1][1] + 1:
            runs[-1] = (runs[-1][0], num)
        else:
            runs.append((num, num))
    return runs


def format_verses(nums: list[int]) -> str:
    """[45, 47, 48] -> '45, 47-48', with the en dash the citation style uses."""
    return ", ".join(str(lo) if lo == hi else f"{lo}–{hi}"
                     for lo, hi in verse_ranges(nums))


def passage_anchor(nums: list[int]) -> str:
    """The id= a study link uses to highlight exactly these verses."""
    return ",".join(f"p{lo}" if lo == hi else f"p{lo}-p{hi}"
                    for lo, hi in verse_ranges(nums))


# The study reader does nothing to soften a fragment landing. Its stylesheets
# set no scroll-margin and no scroll-padding, and nothing on the page moves the
# scroll after the browser has jumped. So following #p23 puts verse 23's first
# line flush against the top of the window -- underneath the reader's own
# chapter toolbar, which is drawn over the top of the page. The verse someone
# followed the link to read arrives with its opening line already cut in half.
#
# Only the link is ours to change, and that turns out to be enough, because the
# reader takes `id=` and the fragment as two separate instructions: `id=` says
# what to highlight, the fragment says where to scroll. Its own footnote links
# already use them apart, as `?id=p21#note1_a`. So the fragment is aimed a
# verse or two above the one being quoted, and that earlier text takes the
# toolbar's place at the top of the screen. The highlight lands where it always
# did, on the verse the card actually quoted.
#
# How far above is a compromise between two ways of being wrong: too little and
# the toolbar still clips the verse, too much and the run-up pushes the verse
# off the bottom instead. Both sides of that are measured against one screen of
# the reader, so the screen is what they are written in.
#
# A phone shows about twenty lines of body text between the chapter toolbar
# drawn across the top and the chapter-nav bar across the bottom, and a line
# holds about thirty-four characters: Alma 57:28 is 271 characters and takes
# eight lines of it. Characters stand in for height because lengths are what
# the builder has -- it ignores the gap between paragraphs, worth about half a
# line each, which is why the two limits below are drawn inside the screen
# rather than up against it.
SCREEN_LINES = 20
LINE = 34

# The toolbar covers the top two lines of the page. Anything the reader is
# meant to see has to start below them.
TOOLBAR_LINES = 2

# And the other end: the least of a quoted paragraph that can land on screen
# and still count as having arrived -- enough for the highlight to be visible
# and for the paragraph to have plainly begun.
LANDING_LINES = 3

# So the walk back stops as soon as it has the toolbar covered with a line to
# spare. It is a floor to reach, not a depth to fill: given a choice between a
# cushion that clears the toolbar and a deeper one, the shallower is better,
# because it opens the verse nearer the top of the screen. At six lines this
# was overshooting -- 1 Nephi 3:7 walked past a verse that left it 118
# characters clear to take one that left it 380.
SCROLL_CUSHION = (TOOLBAR_LINES + 1) * LINE

# The far side is where the run-up would push the quoted paragraph off the
# bottom: it may fill the screen down to the last few lines and no further.
# Past that a link gives up and keeps its own anchor, taking the clipping,
# because a verse cut off at the top is at least visibly there.
#
# This is the number that decides how often that giving up happens, and at 400
# it cut straight through the middle of how long a paragraph actually runs.
# Alma 57:26 is 402 characters, so Alma 57:27 was clipped over two characters'
# worth of margin -- along with one link in twenty across the calendar, and a
# fifth of the conference quotes, whose paragraphs are longer than verses.
SCROLL_CEILING = (SCREEN_LINES - LANDING_LINES) * LINE

# How far back the walk may go. The ceiling is what actually bounds it; this
# only stops a chapter of one-line verses from being walked a long way up for a
# cushion the ceiling would allow but no reader asked for.
SCROLL_LOOKBACK = 4


def scroll_fragment(page: list[tuple[str, str]], index: int) -> str:
    """The '#...' that opens `page[index]` clear of the reader's toolbar.

    `page` is a page's paragraphs in the order they are published, each as its
    anchor id and its text; `index` picks out the one being quoted. The answer
    names an earlier paragraph, whose text becomes what the toolbar covers.

    It walks back from the quoted paragraph and stops on the first one that
    leaves SCROLL_CUSHION characters standing above it -- one step usually,
    more where the verses run short -- and never takes a step that would put
    more than SCROLL_CEILING above it.

    Two cases get no cushion, for opposite reasons. A paragraph with nothing
    published above it gets no fragment at all, which leaves the browser at the
    top of the page -- where that paragraph already is, under the chapter
    heading rather than under the toolbar; scrolling it to the top would be the
    one move guaranteed to clip it. And a paragraph whose neighbour above is
    too long to stand in front of it keeps its own anchor, clipped, because
    being cut off at the top beats starting below the bottom.
    """
    if index == 0:
        return ""
    anchor = index
    cushion = 0
    while (anchor > 0 and cushion < SCROLL_CUSHION
           and index - anchor < SCROLL_LOOKBACK):
        above = cushion + len(page[anchor - 1][1])
        if above > SCROLL_CEILING:
            break
        anchor -= 1
        cushion = above
    return f"#{page[anchor][0]}"


def verse_scroll(parsed: dict[int, str], num: int) -> str:
    """`scroll_fragment` for a chapter, where the paragraphs are numbered verses.

    The verse above is the one published above, which is not always the one a
    number below: a Joseph Smith Translation chapter prints only the verses it
    changes, so JST Matthew 3 runs 4, 5, 6, 24, 25 and the paragraph a reader
    sees above verse 24 is verse 6. Walking the numbers this chapter actually
    has, rather than counting down from the verse, is what gets that right.

    The verse quoted is always one the chapter has, because every caller took
    it out of `parsed` in the first place.
    """
    numbers = sorted(parsed)
    page = [(f"p{n}", parsed[n]) for n in numbers]
    return scroll_fragment(page, numbers.index(num))


def fetch_passage(path: str, nums: list[int]) -> dict | None:
    """One mastery passage, quoted whole: every verse of it, in order.

    A passage is cited as a unit because it teaches as one -- Moroni 7:45's
    list of what charity is only lands with 7:47's "charity is the pure love of
    Christ" after it -- so the verses are joined into a single reading under a
    single reference rather than split across days.
    """
    page = fetch(f"/scriptures/{path}")
    if not page:
        return None
    parsed = parse_verses(page["content"]["body"])
    texts = [parsed[n] for n in sorted(nums) if n in parsed]
    if len(texts) != len(nums):
        # A verse the chapter does not have means this build's idea of the
        # passage and the published chapter disagree; quoting part of it would
        # put the wrong text under the reference, so it is left out entirely.
        print(f"  ! {path} is missing verses of {format_verses(nums)}; skipping",
              file=sys.stderr)
        return None
    _, book, chapter = path.split("/")
    return {
        "reference": f"{book_name(book)} {chapter}:{format_verses(nums)}",
        "text": " ".join(texts),
        "url": f"https://www.churchofjesuschrist.org/study/scriptures/{path}"
               f"?lang=eng&id={passage_anchor(nums)}"
               f"{verse_scroll(parsed, min(nums))}",
        "mastery": True,
    }


def mastery_covering(path: str, verse: int) -> tuple[str, list[int]] | None:
    """The mastery passage containing a chapter's verse, if one does."""
    for entry_path, nums in MASTERY:
        if entry_path == path and verse in nums:
            return entry_path, nums
    return None


# --------------------------------------------------------------------------
# fetching
# --------------------------------------------------------------------------

def fetch(uri: str, retries: int = 3) -> dict | None:
    """GET a study-API page as JSON, memoised on disk."""
    key = re.sub(r"[^a-zA-Z0-9]+", "_", uri).strip("_") + ".json.gz"
    path = CACHE / key
    if path.exists():
        try:
            with gzip.open(path, "rt", encoding="utf-8") as fh:
                return json.load(fh)
        except (OSError, ValueError):
            path.unlink(missing_ok=True)

    url = f"{API}?{urllib.parse.urlencode({'lang': 'eng', 'uri': uri})}"
    for attempt in range(retries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                       "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=45) as resp:
                data = json.loads(resp.read().decode("utf-8"))
            CACHE.mkdir(parents=True, exist_ok=True)
            with gzip.open(path, "wt", encoding="utf-8") as fh:
                json.dump(data, fh)
            time.sleep(0.25)  # be a polite client
            return data
        except (OSError, http.client.HTTPException, ValueError) as err:
            # OSError is the whole family: URLError and TimeoutError are both
            # subclasses, and so are the ConnectionResetError and friends that
            # the *read* half of a request raises rather than the open. Those,
            # and http.client's IncompleteRead, are what an earlier, narrower
            # clause let through -- and with the pool below, one of them took
            # down a 1,100-request build rather than costing one retry.
            #
            # 404 means no such page. 401/403 means the page exists but is not
            # public yet -- a manual is staged behind auth for months before it
            # is published. Neither answer improves on a retry.
            if isinstance(err, urllib.error.HTTPError) and err.code in (401, 403, 404):
                return None
            if attempt == retries - 1:
                print(f"  ! giving up on {uri}: {err}", file=sys.stderr)
                return None
            time.sleep(1.5 * (attempt + 1))
    return None


def fetch_many(uris: list[str], workers: int = 6) -> dict[str, dict | None]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(zip(uris, pool.map(fetch, uris)))


# --------------------------------------------------------------------------
# html -> text
# --------------------------------------------------------------------------

def clean(fragment: str) -> str:
    """Strip markup, footnote markers and page furniture down to plain text."""
    fragment = re.sub(r"<span class=\"page-break\".*?</span>", "", fragment, flags=re.S)
    fragment = re.sub(r"<sup class=\"marker\".*?</sup>", "", fragment, flags=re.S)
    fragment = re.sub(r"<span class=\"verse-number\".*?</span>", "", fragment, flags=re.S)
    fragment = re.sub(r"<[^>]+>", "", fragment)
    return re.sub(r"\s+", " ", html.unescape(fragment)).strip()


def parse_verses(body: str) -> dict[int, str]:
    """Pull {verse number: text} out of a scripture chapter body."""
    verses: dict[int, str] = {}
    for match in re.finditer(r'<p class="verse"[^>]*id="p(\d+)"[^>]*>(.*?)</p>',
                             body, re.S):
        text = clean(match.group(2))
        if text:
            verses[int(match.group(1))] = text
    return verses


def book_name(slug: str) -> str:
    return BOOK_NAMES.get(slug, slug.replace("-", " ").title())


def talk_paragraphs(body: str) -> list[tuple[str, str]]:
    """A conference talk's paragraphs as (id, text), stopping at the endnotes.

    The endnotes are bibliography lines, not anything worth quoting. Every
    paragraph is returned, including the ones no quote could come from, because
    a quote's link is aimed at the paragraph above it -- see `scroll_fragment`.
    """
    block = re.search(r'<div class="body-block">(.*?)(?:<footer class="notes">|\Z)',
                      body, re.S)
    return [(pid, clean(raw)) for pid, raw in
            re.findall(r'<p [^>]*id="(p[_A-Za-z0-9]+)"[^>]*>(.*?)</p>',
                       block.group(1) if block else "", re.S)]


# --------------------------------------------------------------------------
# source 1 -- Book of Mormon verses
# --------------------------------------------------------------------------

def reads_as_a_reading(text: str) -> bool:
    """Whether a verse can stand alone at all, whatever it would score.

    This asks only whether a verse is disqualified outright -- a fragment, a
    label, a page of bookkeeping. Which of the survivors is worth a day is
    `verse_score`'s question. Both cards ask this, so both are held to it: the
    Come, Follow Me card used to apply only a length test, and let through
    verses like "...which was spoken of the Lord by the prophet, saying,".
    """
    lowered = text.lower()
    # Skip bare genealogy, chronology and travelogue, which read poorly cold.
    if re.search(r"\bbegat\b|\bthe record of\b|\bplates of\b|\bpitch(ed)? our tents\b"
                 r"|\bjourney(ed|ing)? in the wilderness\b|\bthe account of\b"
                 r"|\bthe words? of \w+ which he spake\b", lowered):
        return False
    # The back half of a sentence that started in the verse before.
    if FRAGMENT_OPENER.match(text):
        return False
    # And the mirror image: the front half of a sentence that finishes in the
    # verse after. This book marks a thought carried across a verse boundary
    # with a trailing em dash, and the mark is reliable -- of the 150 verses
    # that end in one, 122 open the next verse on a conjunction.
    #
    # What the dash leaves behind is a verse that sets something up and never
    # pays it off. 3 Nephi 28:36 is Mormon saying he "knew not whether they
    # were cleansed from mortality to immortality"; 28:37 is where he says he
    # asked the Lord and was told. Alone, the verse is a question with its
    # answer held back, and the reader is given the half that stopped being
    # true a verse later.
    #
    # Mosiah 2:20 is the same fault at its most conspicuous, and shows why the
    # score cannot catch it: "if you should render all the thanks and praise
    # which your whole soul has power to possess ... " -- and the "yet ye
    # would be unprofitable servants" the whole sentence is built to arrive at
    # is in 2:21. It scored 13.8, the highest of anything in the tier, because
    # the score reads vocabulary and every gospel word is present. Only the
    # sentence is missing. So this is a question of shape, and belongs here
    # with the other things a verse is refused for outright.
    #
    # A bare comma is the same fault said more quietly, and goes with it. The
    # colon and semicolon do not: the King James punctuates whole sentences
    # that way, which is why `verse_score` only ever charged them a little.
    if text.rstrip().endswith(("—", ",")):
        return False
    # "Who shall ascend into the hill of the Lord?" is a reading; "Who is he
    # that hideth counsel without knowledge" is a relative clause carrying on.
    if re.match(r"^who\b", text, re.I) and "?" not in text:
        return False
    # A whole sentence, but pointing out of itself -- see DANGLING_OPENER. The
    # lead-in comes off first so the test looks at the verse's subject rather
    # than at the conjunction tying it to the last one.
    opening = LEAD_IN.sub("", text)
    if DANGLING_OPENER.match(opening):
        return False
    # An "it" standing in for a clause the verse never supplies.
    if unfilled_it(opening):
        return False
    # A "thus" standing in for a manner the verse never describes. Asked of the
    # whole verse, because the lead-in is where the word itself is.
    if unfilled_thus(text):
        return False
    # A "they" the verse only ever has things done to.
    if UNANCHORED_PLURAL.match(opening):
        return False
    # A "he" the verse never answers, unless it arrives at a conviction of its
    # own: "Though he slay me, yet will I trust in him" is remembered for the
    # half that speaks for itself. See `unanchored_singular`.
    if unanchored_singular(text) and not TESTIMONY.search(text):
        return False
    # A verse that only introduces the speech in the next one.
    return not SPEECH_STUB.search(text)


def is_quotable_verse(text: str) -> bool:
    """Keep Book of Mormon verses that stand on their own when read cold."""
    return (90 <= len(text) <= 340 and reads_as_a_reading(text)
            and verse_score(text) >= VERSE_FLOOR)


# The score a verse has to reach to be worth a day at all. Roughly two gospel
# words and nothing working against it, or one and a note of conviction.
VERSE_FLOOR = 3.0


# How much of the quotable pool the ordinary days draw on. 1,830 of the book's
# 6,604 verses clear the floor, and 1,806 are left once the mastery passages
# are taken out of the ordinary pool -- more than four years of reading, and it
# takes in a lot that merely cleared the bar; keeping the best of it means every
# day is a verse worth meeting cold, and still turns over enough that a reader
# through a second year is not shown the first year again.
BOM_TIER = 500

# Days between one mastery passage and the next. Twenty-six turns a year for
# twenty-five passages, so each of them comes round every year, and the extra
# turn walks the cycle forward so a passage does not land on the same date
# twice running.
MASTERY_EVERY = 14


def build_bom_pool() -> list[dict]:
    uris = [f"/scriptures/bofm/{slug}/{ch}"
            for slug, _, chapters in BOM_BOOKS
            for ch in range(1, chapters + 1)]
    print(f"Book of Mormon: fetching {len(uris)} chapters ...")
    pages = fetch_many(uris)

    # Verses spoken for by a mastery passage are left out of the ordinary pool,
    # so one is never shown alone a few days after being shown in its passage.
    spoken_for = {(path, num) for path, nums in MASTERY
                  if path.startswith("bofm/") for num in nums}

    pool: list[dict] = []
    for slug, name, chapters in BOM_BOOKS:
        for ch in range(1, chapters + 1):
            page = pages.get(f"/scriptures/bofm/{slug}/{ch}")
            if not page:
                continue
            parsed = parse_verses(page["content"]["body"])
            for num, text in sorted(parsed.items()):
                if is_quotable_verse(text) and (f"bofm/{slug}/{ch}", num) not in spoken_for:
                    pool.append({
                        "reference": f"{name} {ch}:{num}",
                        "text": text,
                        "url": f"https://www.churchofjesuschrist.org/study/scriptures/"
                               f"bofm/{slug}/{ch}?lang=eng&id=p{num}"
                               f"{verse_scroll(parsed, num)}",
                        "score": verse_score(text),
                    })
    print(f"Book of Mormon: {len(pool)} quotable verses")
    return pool


def build_mastery_passages(volume: str) -> list[dict]:
    """Every mastery passage from one volume, in the order it is bound."""
    wanted = [(path, nums) for path, nums in MASTERY if path.startswith(volume)]
    print(f"Scripture mastery: fetching {len(wanted)} passages from {volume.rstrip('/')} ...")
    passages = [p for p in (fetch_passage(path, nums) for path, nums in wanted) if p]
    if len(passages) < len(wanted):
        print(f"  ! only {len(passages)} of {len(wanted)} mastery passages available",
              file=sys.stderr)
    return passages


def build_bom_tier(pool: list[dict]) -> list[dict]:
    """The verses the ordinary days rotate through: the best of the pool,
    shuffled so consecutive days are not from the same book."""
    best = sorted(pool, key=lambda v: v["score"], reverse=True)[:BOM_TIER]
    cutoff = best[-1]["score"] if best else 0
    print(f"Book of Mormon: keeping the best {len(best)} (score >= {cutoff:.1f})")
    # The score got the verse this far and is no reader's business; the Come,
    # Follow Me card already drops its own before writing the calendar.
    best = [{k: v for k, v in verse.items() if k != "score"} for verse in best]
    return spread(best, seed=20260101, key=lambda v: v["reference"].rsplit(" ", 1)[0])


def bom_for(index: int, tier: list[dict], mastery: list[dict]) -> dict:
    """The Book of Mormon reading for a day, as a pure function of its index.

    Every fourteenth day is a mastery passage and the rest walk the curated
    tier. Both are worked out from the day's distance from the epoch rather
    than from a running count, so a given date resolves to the same reading no
    matter what span a build happens to cover.
    """
    # No passages at all -- a build whose every mastery fetch failed -- and
    # every day is ordinary, with no slot to take out of the numbering below.
    # Without this the tier still skipped one, and two days running showed
    # the same verse, which is what tools/test_calendar.py caught.
    if not mastery:
        return tier[index % len(tier)]
    if index % MASTERY_EVERY == MASTERY_EVERY // 2:
        return mastery[(index // MASTERY_EVERY) % len(mastery)]
    # The day's position with the mastery days taken out, so the tier is walked
    # straight through rather than skipping an entry on every mastery day.
    ordinary = index - (index // MASTERY_EVERY) - (index % MASTERY_EVERY > MASTERY_EVERY // 2)
    return tier[ordinary % len(tier)]


# --------------------------------------------------------------------------
# source 2 -- Come, Follow Me weekly readings
# --------------------------------------------------------------------------

MONTHS = {m: i for i, m in enumerate(
    ["January", "February", "March", "April", "May", "June", "July", "August",
     "September", "October", "November", "December"], start=1)}

# Come, Follow Me rotates through the four standard works on a fixed cycle, so
# a year's manual is derivable rather than something to look up: 2026 Old
# Testament, 2027 New Testament, 2028 Book of Mormon, 2029 Doctrine and
# Covenants, then round again. Deriving the slug and probing for it is what
# makes the January changeover automatic -- a scheduled rebuild picks up a new
# manual within days of it going public, with no edit here.
CFM_CYCLE = ["old-testament", "new-testament", "book-of-mormon",
             "doctrine-and-covenants"]
CFM_CYCLE_EPOCH = 2026  # the year CFM_CYCLE[0] is taught
CFM_SLUG = "come-follow-me-for-home-and-church-{volume}-{year}"


def cfm_manual_for(year: int) -> str:
    return CFM_SLUG.format(volume=CFM_CYCLE[(year - CFM_CYCLE_EPOCH) % len(CFM_CYCLE)],
                           year=year)


def resolve_cfm_manuals(start: dt.date, end: dt.date, limit: int = 2
                        ) -> list[tuple[str, int]]:
    """The published manuals covering a calendar span, oldest first.

    A manual's opening week starts in late December of the preceding year, so
    the year after the span's last day can still own days inside it -- hence
    probing one year past `end`. Only the site can say whether a manual is
    readable: an unpublished year answers 404, and one that is staged but still
    embargoed answers 401, so probing keeps unreadable manuals out of the
    calendar without needing to know the publication date.

    Manuals tile contiguously (2026 ends December 27, the 2027 opening week
    starts December 28), so merging several years leaves no gap or overlap.
    """
    found: list[tuple[str, int]] = []
    for year in range(start.year, end.year + 2):
        if len(found) >= limit:
            break
        manual = cfm_manual_for(year)
        if fetch(f"/manual/{manual}"):
            found.append((manual, year))
        else:
            print(f"  - Come, Follow Me {year} not published yet; skipping")
    return found


def parse_week_range(title: str, year: int) -> tuple[dt.date, dt.date] | None:
    """Turn 'January 5-11. ...' or 'December 29-January 4. ...' into dates."""
    head = re.split(r"\.\s", title, maxsplit=1)[0]
    head = head.replace("–", "-").replace("—", "-")
    m = re.match(r"([A-Z][a-z]+)\s+(\d{1,2})\s*-\s*(?:([A-Z][a-z]+)\s+)?(\d{1,2})", head)
    if not m:
        return None
    m1, d1, m2, d2 = m.group(1), int(m.group(2)), m.group(3) or m.group(1), int(m.group(4))
    if m1 not in MONTHS or m2 not in MONTHS:
        return None
    # Only the opening week straddles the new year ("December 29-January 4");
    # December weeks at the far end of the manual stay in the manual's year.
    straddles = MONTHS[m1] == 12 and MONTHS[m2] == 1
    y1 = year - 1 if straddles else year
    y2 = year
    try:
        return dt.date(y1, MONTHS[m1], d1), dt.date(y2, MONTHS[m2], d2)
    except ValueError:
        return None


# Longest first, so "1 Corinthians" is matched before "Corinthians" could be,
# and "Joseph Smith—History" before any shorter name sharing its opening.
BOOK_SLUGS = {name.lower(): slug for slug, name in BOOK_NAMES.items()}
BOOK_SLUGS["psalm"] = "ps"
BOOK_SLUGS["d&c"] = "dc"
BOOK_NAMES_BY_LENGTH = sorted(BOOK_SLUGS, key=len, reverse=True)


def parse_reading_block(title: str) -> list[tuple[str, int | None]] | None:
    """The chapters a week actually assigns, in the order it lists them.

    A week is titled `January 4-10. "We Have Come to Worship Him": Matthew 2;
    Luke 2`, so the assignment is what follows the last colon. A chapter of
    `None` means the whole book, which is how a week reading all of Esther or
    Ruth states it.

    Returning None means the title did not parse, which the caller treats as
    "no opinion" rather than "nothing assigned" -- better to fall back to
    taking the week's citations at face value than to empty the card.
    """
    if ": " not in title:
        return None
    block: list[tuple[str, int | None]] = []
    current: str | None = None
    for segment in title.rsplit(": ", 1)[1].split(";"):
        segment = segment.strip()
        if not segment:
            continue

        # A week reading several numbered books of the same name states them
        # together -- "1 and 2 Thessalonians", "1-3 John" -- which names no
        # chapters and means all of each.
        series = re.match(r"(\d)\s*(?:and|[-–—])\s*(\d)\s+(\S.*)$", segment)
        if series:
            lo, hi, tail = int(series.group(1)), int(series.group(2)), series.group(3)
            books = [BOOK_SLUGS.get(f"{n} {tail}".lower()) for n in range(lo, hi + 1)]
            if all(books):
                block.extend((slug, None) for slug in books)
                current = books[-1]
                continue

        lowered = segment.lower()
        for name in BOOK_NAMES_BY_LENGTH:
            if lowered.startswith(name):
                current = BOOK_SLUGS[name]
                segment = segment[len(name):].strip()
                break
        if not current:
            return None
        if not segment:
            block.append((current, None))
            continue
        # Only now is it safe to normalise dashes into range separators: the
        # book name, which can hold an em dash of its own, is already off.
        for part in segment.replace("–", "-").replace("—", "-").split(","):
            # A chapter can be cited with verses ("1:1-26"); the chapter is
            # what decides whether a passage is in the week's reading.
            match = re.match(r"(\d+)(?:\s*-\s*(\d+))?", part.strip())
            if not match:
                continue
            lo = int(match.group(1))
            hi = int(match.group(2) or lo)
            if hi < lo or hi - lo > 60:
                continue
            block.extend((current, ch) for ch in range(lo, hi + 1))
    return block or None


def in_block(block: list[tuple[str, int | None]], book: str, chapter: int) -> bool:
    return (book, chapter) in block or (book, None) in block


def block_rank(block: list[tuple[str, int | None]], book: str, chapter: int) -> int:
    """Where a chapter falls in the week's reading, for putting the days in
    the order someone reading through the assignment would meet them."""
    for position, (slug, ch) in enumerate(block):
        if slug == book and ch in (chapter, None):
            return position
    return len(block)


def parse_verse_ids(query: str) -> list[int]:
    """Read verse numbers out of a citation's id= parameter (p12-p26, p4,p6)."""
    m = re.search(r"id=([^&#\"]+)", html.unescape(query))
    if not m:
        return []
    nums: list[int] = []
    for part in urllib.parse.unquote(m.group(1)).split(","):
        part = part.strip()
        rng = re.match(r"p(\d+)-p(\d+)$", part)
        one = re.match(r"p(\d+)$", part)
        if rng:
            lo, hi = int(rng.group(1)), int(rng.group(2))
            if 0 < hi - lo <= 40:
                nums.extend(range(lo, hi + 1))
        elif one:
            nums.append(int(one.group(1)))
    return nums


# The vocabulary of the gospel, carried as word *stems* rather than whole
# words. This list is most of what decides a reading, so what it misses it
# misses badly, and an earlier list of exact forms missed a great deal:
# scripture is written in Early Modern English and inflects heavily, so
# "commandment" matched and "commandments" did not, "repent" matched and
# "repentance" did not, "redeem" matched and "redeemer" did not. The cost was
# not a rounding error. Job 19:25, "For I know that my redeemer liveth", scored
# zero and was dropped, while Satan's speech eighteen chapters earlier -- "Hast
# not thou made an hedge about him", Job 1:10 -- scored 3.5 on the strength of
# one "blessed" and was chosen. So the stems, and the suffixes below, are the
# foundation the rest of the scoring stands on.
DOCTRINAL_STEMS = [
    # deity
    "lord", "god", "christ", "jesus", "messiah", "savior", "saviour", "redeem",
    "creator", "almighty", "immanuel", "jehovah",
    # the first principles
    "faith", "believ", "repent", "baptiz", "baptism", "gospel", "doctrine",
    "convert", "forgiv", "remission", "atone", "resurrect", "salvation",
    "save", "redemption", "exalt", "sanctif", "justif",
    # covenant and ordinance
    "covenant", "command", "ordinance", "sacrament", "priesthood", "temple",
    "endow", "seal", "consecrat", "restor", "keys",
    # the attributes a reading is usually about
    "love", "charity", "hope", "mercy", "merci", "grace", "truth", "virtue",
    "meek", "humbl", "humility", "patien", "diligen", "kind", "compassion",
    "gentl", "long-suffering", "forbear", "chaste", "pure", "purity", "honest",
    "integrity", "worthy", "worthi", "holy", "holi", "righteous", "perfect",
    # the life of a disciple
    "pray", "worship", "fast", "obey", "obedien", "hearken", "heed", "endure",
    "enduring", "serve", "servic", "minister", "disciple", "follow",
    "sacrific", "offering", "tithe", "labor", "labour", "witness", "testif",
    "testimony", "preach", "teach", "ponder", "remember", "watch", "trust",
    "rely", "wait", "seek", "knock", "ask",
    # what is promised
    "bless", "peace", "peacemak", "joy", "rejoic", "comfort", "heal", "rest",
    "glory", "glori", "eternal", "everlasting", "immortal", "celestial",
    "heaven", "paradise", "crown", "inherit", "reward", "promise",
    # the soul and the spirit
    "spirit", "soul", "heart", "mind", "conscience", "light", "life", "live",
    "grateful", "gratitude", "thank", "praise", "prophet", "revelation",
    "scripture", "word", "angel", "power", "strength", "courage", "fear not",
]

# The suffixes those stems take. Deliberately narrow: each one turns a stem
# into another form of the same word, so a match is still the word itself and
# not a coincidence of spelling.
_INFLECTION = (r"(?:e|es|s|ies|ed|eth|est|ing|ings|er|ers|ment|ments|ness|"
               r"ful|fully|ous|ly|y|ance|ence|ion|ions|ity|able)?")

# Longest stem first, so "commandment" is not matched as "command" before the
# longer stem has been tried.
DOCTRINAL = re.compile(
    r"\b(" + "|".join(sorted(DOCTRINAL_STEMS, key=len, reverse=True)) + r")"
    + _INFLECTION + r"\b", re.I)


def doctrinal_stems(text: str) -> set[str]:
    """The distinct gospel words a reading uses, counted by stem.

    By stem, so "commandment" and "commandments" in one verse count once: the
    score is meant to reward a reading that is *about* something, not one that
    repeats itself.
    """
    return {m.group(1).lower() for m in DOCTRINAL.finditer(text)}


NARRATIVE_OPENER = re.compile(
    r"^(nevertheless|so |then |and when|now when|and it came to pass that when|"
    r"and he sent|and they came|and they began|after this|and after|moreover|"
    r"likewise|now it came to pass|and now when|and thus)\b", re.I)

# A verse that opens with a relative pronoun is the back half of a sentence
# that began in the verse before it -- "That ye may not be cursed with a sore
# cursing", "Whom I shall see for myself". No amount of doctrine in the rest of
# it makes it a reading, so this is a rejection rather than a penalty.
#
# The conjunction in front of it can be stacked, which one word of allowance
# missed: "And also that we may preserve unto them the words which have been
# spoken by the mouth of all the holy prophets" is 1 Nephi 3:20, and the reason
# it is a reading in nobody's hands is that the sentence saying what it is that
# "we may preserve" for is 3:19. So one additive adverb is allowed after the
# conjunction as well.
#
# That allowance is where "that" stops being reliable, though, because the
# extra step reaches verses using it as a determiner rather than to open a
# clause: "And again, that same God has brought our fathers out of the land of
# Jerusalem" is a whole sentence with a subject. Only the second step is
# guarded, so a single conjunction still decides these the way it always has.
#
# "So" belongs in that list and was missing from it. A verse that opens "So
# that" is the tail of a sentence begun in the verse before, without exception
# in anything read here -- "So that ye come behind in no gift", "So that we
# ourselves glory in you in the churches of God for your patience and faith",
# "So that the priests could not stand to minister because of the cloud", whose
# cloud filled the house back in 1 Kings 8:10.
FRAGMENT_OPENER = re.compile(
    r"^(?:and|but|now|yea|so|wherefore|therefore)?[,\s]*"
    r"(?:(?:also|again|moreover|likewise)\b[,\s]*(?!that\s+(?:same|such|very|"
    r"great)\b))?"
    r"(that|which|whom|whose)\b", re.I)

# A verse that only introduces speech -- "Then Job answered and said," -- is
# the label on the reading, not the reading.
SPEECH_STUB = re.compile(r"(and )?(said|saying|spake|answered)\s*[:,]\s*$", re.I)

# The scaffolding a verse opens with before it reaches its subject. Scripture
# is punctuated as one continuous telling, so nearly every verse starts by
# joining itself to the one before, and these words have to be lifted off
# before the test below can see what a verse is actually about: "And it came to
# pass that they did ..." is a verse about "they", not a verse about "and".
LEAD_IN = re.compile(
    r"^(?:(?:and|but|now|yea|behold|verily|wherefore|therefore|nevertheless|"
    r"notwithstanding|for|so|then|thus|moreover|likewise|again|also|"
    r"it came to pass)\b[,;:\s]*)+", re.I)

# A verse can point out of itself in three ways that reading it cold does not
# survive, and this pattern catches two of them. The third -- a pronoun with
# nobody in the verse to mean -- is `unanchored_singular` below, because
# answering it needs to know where the words are and not merely which ones.
#
# The first is a dangling speech attribution: the speaker left behind instead
# of the subject. Job 1:21 reaches the card as "And said, Naked came I out of
# my mother's womb", because the man saying it is back in verse 20. Only an
# attribution naming nobody counts -- "thus said Jesus Christ, the Son of God,
# unto his disciples" says whose words follow, and reads as well cold as
# anything in the book.
#
# The second is a demonstrative standing where the subject goes. Two things
# that only look like it are exempted:
#
#   * the expletive "it is", which stands in for nothing at all ("It is better
#     that one man should perish than that a nation should dwindle and perish
#     in unbelief");
#   * a demonstrative used as a determiner, where the subject is still to come
#     and usually turns out to be the speaker: "But this much I can tell you,
#     that if ye do not watch yourselves ... ye must perish", "These things
#     have I written unto you". Only a demonstrative standing alone as the
#     subject is looked at, which is why the test wants a verb after it.
#
# Standing alone, it is still let through when what follows names the thing it
# means, since the verse then says what it is about rather than pointing out of
# itself: "And this is my doctrine", "For behold, this is my church", "This is
# the way; and there is none other way", "And this is life eternal, that they
# might know thee the only true God". What is refused is the demonstrative that
# hands off to another pronoun -- "And these are those who have part in the
# first resurrection" -- or to a verb standing in for an act the verse never
# describes: "Now this was done because there were so many people", "This shall
# ye always do".
#
# "This is not all" is none of those. It is a turn in the argument rather than
# a subject, the teaching arrives immediately after it, and what "all" referred
# to is no part of what the reader takes away: "But this is not all; ye must
# pour out your souls in your closets, and your secret places, and in your
# wilderness" is Alma 34:26, and it wants nothing from Alma 34:25. So a
# negated demonstrative is left alone.
#
# The General Conference card has refused paragraphs on this ground since it
# was written -- see `is_quotable_paragraph` -- and got the cleaner readings for
# it. This brings the two scripture cards up to the same standard.
DANGLING_OPENER = re.compile(
    r"^(?:"
    r"(?:thereof|therein|thereby)\b"
    r"|it\b(?!\s+(?:is|was|were|shall|should|must|would|will|may|might|can|"
    r"behooveth|cometh|mattereth|needs|hath)\b)"
    r"|(?:this|these|those|such)\s+(?:is|are|was|were|be|shall|should|have|"
    r"hath|had|did|do|doth)\s+(?:all|they|them|these|those|this|it|he|she|"
    r"him|her|ye|done|so)\b"
    r"|(?:said|answered|spake|replied)\b(?=\s*[,:;]|\s+(?:he|she|they|i|we|it|"
    r"unto)\b)"
    r")", re.I)

# The exemption above lets every "it is" through, and half of them should not
# be. An "it" at the head of a verse is doing one of two opposite jobs, and
# which one decides whether the verse can be read cold at all.
#
# It is a placeholder when the verse goes on to say what it stands for: "It is
# better *that* one man should perish than that a nation should dwindle and
# perish in unbelief", "it is expedient *that* an atonement should be made",
# "It is a fearful thing *to fall* into the hands of the living God", "It is
# better *to trust* in the Lord than to put confidence in man". None of those
# wants anything from outside, because the "it" is not about anything until the
# clause after it arrives -- which it does, in the same sentence.
#
# It is a pointer when the clause never comes. "But it is mockery before God,
# denying the mercies of Christ, and the power of his Holy Spirit, and putting
# trust in dead works" is Moroni 8:23, and the "it" is the baptising of little
# children, back in 8:22; the verse never says so. As a day's reading it calls
# something a mockery without ever saying what, which is how it was reported.
# Helaman 7:18 is the same word answering a question asked in Helaman 7:17 --
# "It is because you have hardened your hearts" -- and 2 Nephi 2:12's "it must
# needs have been created for a thing of naught" is the creation 2:11 spent
# itself describing.
#
# So the verse is read as far as its first full stop and the placeholder has to
# be filled inside it. Two constructions fill it without a complementiser and
# are named directly: "it shall come to pass", which is this book's way of
# saying that what follows happened and always carries what follows with it;
# and "it is written", where the "it" is the quotation that comes after the
# comma. A negated opener is left alone for the reason "this is not all" is --
# Alma 58:37's "But, behold, it mattereth not--we trust God will deliver us" is
# a turn in the argument rather than a subject, and the teaching lands after it.
IT_OPENER = re.compile(r"^it\b", re.I)

QUOTING_IT = re.compile(
    r"^it\s+(?:is|was|hath\s+been|has\s+been)\s+(?:written|said|spoken)\b", re.I)

# The "to" here has to be the infinitive that fills the placeholder and not the
# preposition that merely points somewhere, so the words a prepositional "to"
# takes are refused the job: "according to their faith" fills nothing.
IT_FILLED = re.compile(
    r"\b(?:that|if|when|what|whether|which|who|whom|lest)\b"
    r"|\bto\s+(?!the|a|an|his|her|their|its|my|thy|your|our|this|that|these|"
    r"those|him|them|me|us|you|thee|it|all|every|any|no|one|whom|which|what)\w"
    r"|\bcome\s+to\s+pass\b"
    r"|\bnot\b", re.I)

FIRST_SENTENCE = re.compile(r"^[^;.—]*")


def unfilled_it(opening: str) -> bool:
    """Whether an "it" opening a verse stands for something outside it.

    `opening` is the verse with its lead-in already off, so "And it is ..." and
    "it is ..." are the same question.
    """
    if not IT_OPENER.match(opening) or QUOTING_IT.match(opening):
        return False
    return not IT_FILLED.search(FIRST_SENTENCE.match(opening).group(0))


# The same fault in adverb form, and the only one of these that word order
# decides.
#
# A verse that fronts "thus" is doing one of two opposite jobs with it. It is
# inferential when it means "and therefore", and then what follows is a
# conclusion that stands by itself: "And thus mercy can satisfy the demands of
# justice", "Thus all mankind were lost", "And thus we see that the gate of
# heaven is open unto all". The reader loses the derivation and keeps the
# point, and the point is the whole of the verse.
#
# It is a manner adverb when it means "in this way", and then it is a pointer
# with nothing in the verse to point at. Alma 46:14 is the clearest case there
# is: "For thus were all the true believers of Christ, who belonged to the
# church of God, called by those who did not belong to the church." What they
# were called is "Christians", and it is in 46:13. The verse spends itself
# saying that a people were named something without ever saying what -- and it
# scored 7.3 doing it, high enough for the tier, because every word it uses is
# a gospel word. It was reported as broken.
#
# English marks which job the word is doing by inverting the subject and the
# verb. "Thus WERE all the true believers ... called", "Thus PASSED AWAY the
# thirty and second year", "Thus HATH the Lord dealt with me" -- against "thus
# WE SEE", "thus MERCY can satisfy", "Thus GOD has provided a means". So the
# test is for a finite verb standing where the subject belongs, which is also
# the shape this book keeps its bookkeeping in: "And thus ended the tenth year
# of the reign of the judges over the people of Nephi."
#
# The exception is a speech attribution, where the inversion is idiom and the
# words the "thus" stands for arrive right after it. Around two in three of the
# fronted verbs are this, and they are among the best readings there are: "For
# thus saith the Lord God: They shall write the things which shall be done
# among them", "Thus did Alma teach his people, that every man should love his
# neighbor as himself", "For so hath the Lord commanded us, saying, I have set
# thee to be a light of the Gentiles". Those are filled by their own next
# clause and want nothing from the verse before.
#
# "So" fronts the same way and is refused on the same ground -- "So shall they
# fear the name of the Lord from the west", "Yea, so have I strived to preach
# the gospel". Its other uses are untouched, because none of them puts a verb
# in the subject's place: the degree correlative of "And so great was the faith
# of Enoch that he led the people of God" is answered by its own "that".
#
# Two verses look at first like the rule overreaching, and a reader ruled that
# it does not. Ether 12:31 -- "For thus didst thou manifest thyself unto thy
# disciples; for after they had faith, and did speak in thy name, thou didst
# show thyself unto them in great power" -- points outward and then re-supplies
# the manner itself, in a clause restating the same act with the same subject,
# so it could be argued to fill its own "thus". It goes out anyway. Mosiah 28:4
# is the same shape and no closer call ("And thus did the Spirit of the Lord
# work upon them, for they were the very vilest of sinners" -- a reason for the
# mercy, not the manner of the working). Both are refused, and neither is a
# loss the pool feels.
#
# The verse the exemption is for is Doctrine and Covenants 137:7, "Thus came
# the voice of the Lord unto me, saying: All who have died without a knowledge
# of this gospel ... shall be heirs of the celestial kingdom of God" -- ruled a
# reading that stands on its own two feet, and kept by leaving "came" out of
# `FRONTED_VERB` below.
THUS_LEAD = re.compile(r"\b(?:thus|so)\b[,;:\s]*$", re.I)

# "Came" is deliberately absent. The few verses that front "thus came" or
# "thus cometh" -- none of them in the Book of Mormon -- all name the thing
# that came on the spot, and it brings its own manner with it: "Thus came the
# voice of the Lord unto me, saying: All who have died without a knowledge of
# this gospel ... shall be heirs of the celestial kingdom of God", "Thus came
# John, preaching and baptizing in the river of Jordan". The word would buy
# nothing and cost those.
FRONTED_VERB = re.compile(
    r"^(?:is|was|were|are|art|be|been|hath|has|have|had|shall|shalt|will|"
    r"wilt|would|should|may|might|must|can|could|do|dost|doth|did|didst|"
    r"saith|said|say|speak|speaketh|spake|prophesied|commandeth|"
    r"passed|ended|endeth|commenced|began)\b", re.I)

# Either the verb of saying leads, or an auxiliary reaches one before the
# clause breaks. The punctuation matters: "Thus did Moses: according to all
# that the Lord commanded him, so did he" reaches "commanded" only across a
# colon, and is an account of an obedience rather than a record of the words.
QUOTING_THUS = re.compile(
    r"^(?:saith|said|say|speak|speaketh|spake|spoken|prophesied|commandeth)\b"
    r"|^(?:hath|has|have|had|shall|shalt|will|would|should|do|doth|did|didst)"
    r"\b[^,;:.]{0,40}?\b(?:say|saith|said|speak|spake|spoken|speaketh|command|"
    r"commanded|teach|taught|prophesy|prophesied|declare|declared|testify|"
    r"testified|write|written)\b", re.I)


def unfilled_thus(text: str) -> bool:
    """Whether a fronted "thus" stands for a manner the verse never describes.

    This one is asked of the whole verse rather than of the opening, because
    the lead-in is where the word itself is: `LEAD_IN` lifts "thus" off with
    the conjunctions, and whether it was there at all is the question.
    """
    lead = LEAD_IN.match(text)
    if not lead or not THUS_LEAD.search(lead.group(0)):
        return False
    rest = text[lead.end():]
    return bool(FRONTED_VERB.match(rest)) and not QUOTING_THUS.match(rest)


# The plural's own version of the same fault. `unanchored_singular` below
# leaves every plural alone, on the ground that a reader supplies "people who
# do this" -- and that holds exactly as far as the verse says what "this" is.
# "Nevertheless they did fast and pray oft, and did wax stronger and stronger
# in their humility" never says who they were and does not need to, because
# what they did is the whole of the reading and anyone can do it.
#
# A verse that only reports what was done to them supplies nothing to stand in
# for the name. "They are raised to dwell with God who has redeemed them; thus
# they have eternal life through Christ, who has broken the bands of death" is
# Mosiah 15:23, and who is raised is the entire question -- the answer is in
# 15:24, which this build already refuses for pointing at it ("and these are
# they that have died before Christ came, in their ignorance"). Alone, the
# verse promises the resurrection to somebody it declines to name.
#
# Two predicates are let through because they answer the pronoun themselves. A
# verse that says what they were *called* has named them -- "And they were
# called the people of God", "they were called the church of God" -- and the
# four plurals that end in the participle's own letters are nouns doing the
# same work: "they were men of truth and soberness" says who they are as
# plainly as a name would.
UNANCHORED_PLURAL = re.compile(
    r"^they\s+"
    r"(?:are|is|was|were|be|been|shall\s+be|will\s+be|would\s+be|should\s+be|"
    r"(?:have|had|hath)\s+been)\s+"
    r"(?!(?:called|named|men|women|children|brethren)\b)"
    r"\w+(?:ed|en)\b", re.I)

# The third way out of itself, and the one that decides most verses: a
# third-person *singular* pronoun with nobody in the verse to mean.
#
# Number is what matters here, and it took a while to see. A plural reads as
# generic however it got there -- "Nevertheless they did fast and pray oft, and
# did wax stronger and stronger in their humility, and firmer and firmer in the
# faith of Christ" never says who "they" were, and loses nothing by it, because
# a reader supplies "people who do this" and the verse means exactly what it
# meant. A singular cannot be read that way. "Behold, he offereth himself a
# sacrifice for sin, to answer the ends of the law" is doctrine as plain as any
# in the book, and still lands wrong on anyone who does not already know that
# "he" is Christ -- which 2 Nephi 2:6 says and 2 Nephi 2:7 does not.
#
# So a plural is left alone, and a singular has to find its referent inside its
# own verse. Position is the whole of the test: "And the Lord did pour out his
# Spirit upon them" names the Lord before it says "his", while "And they
# rehearsed unto his father ... for he knew that it was the power of God"
# reaches "God" only after three pronouns have gone by unanswered, which is why
# that verse cannot be read cold and this one can.
# Somebody named, or deity, whom a reader of these books resolves on sight.
ANCHOR = re.compile(
    r"\b(?:Lord|God|Christ|Jesus|Messiah|Savior|Saviour|Redeemer|Almighty|"
    r"Jehovah|Immanuel|Creator|Father|Son|Spirit|Ghost|Comforter|Lamb)\b"
    r"|(?<![.!?]\s)(?<!^)\b[A-Z][a-z]{2,}\b")

THIRD_SINGULAR = re.compile(r"\b(?:he|him|his|she|her|hers)\b", re.I)

# "He that hath ears to hear, let him hear." A generic singular means whoever
# fits rather than anybody in particular, needs nothing named, and binds the
# pronouns that follow it in the same verse.
GENERIC_SINGULAR = re.compile(r"^(?:he|him|his)\s+(?:that|which|who|whom|whose)\b",
                              re.I)

# A verse that states its teaching of a generic somebody has supplied its own
# referent, and the pronouns around it read as generic whatever came first.
# Moroni 7:43 and 7:44 sit next to each other and divide on exactly this. 7:43
# is "he cannot have faith and hope, save he shall be meek, and lowly of
# heart", where the pronoun is the only subject there is and the reader has to
# bring one. 7:44 opens on a dangling "his faith and hope is vain" and then
# says the whole thing again with a subject in it -- "none is acceptable before
# God, save the meek and lowly in heart; and if a man be meek and lowly in
# heart ... he must needs have charity" -- so the opening is a turn in the
# argument and the teaching after it stands on its own.
#
# The verb is required, because it is what makes the generic a *subject*. 2
# Nephi 2:7 closes "and unto none else can the ends of the law be answered",
# and that "none" is who the verse is for rather than who it is about -- "he
# offereth himself a sacrifice for sin" still wants Christ named to be read.
# 7:44's "none is acceptable before God" is the subject of its own clause.
GENERIC_SUBJECT = re.compile(
    r"\b(?:a man|a woman|a person|a soul|a child|none|no man|no one|any man|"
    r"every man|whoso|whosoever)\s+"
    r"(?:is|are|was|were|be|can|cannot|shall|will|hath|has|have|had|could|"
    r"would|should|must|may|might|do|doth|did|cometh|receiveth|seeketh)\b", re.I)

# The same somebodies, as an antecedent rather than a subject. Standing before
# the pronoun, a generic answers it just as a name would: Moroni 7:9's "And
# likewise also is it counted evil unto a man, if he shall pray and not with
# real intent of heart" needs nobody named, because "a man" is already who
# "he" is.
GENERIC_ANTECEDENT = re.compile(
    r"\b(?:a man|a woman|a person|a soul|a child|none|no man|no one|any man|"
    r"every man|whoso|whosoever)\b", re.I)


def unanchored_singular(text: str) -> bool:
    """Whether a he/him/his in the verse has nothing in the verse to mean.

    A name is not the only thing a pronoun can be resting on. "And charity
    suffereth long ... seeketh not her own" names nobody and wants nobody: the
    "her" is charity, which the verse opened with. So a gospel word standing
    before the pronoun anchors it too, and that one change is the difference
    between refusing that verse and keeping it -- along with "for a man
    sometimes, if he is compelled to be humble, seeketh repentance", and "trust
    no one to be your teacher nor your minister, except he be a man of God".
    What stays refused is the verse with nothing at all in front of the
    pronoun: "Behold, he offereth himself a sacrifice for sin", "And they
    rehearsed unto his father".
    """
    pronoun = THIRD_SINGULAR.search(text)
    if not pronoun or GENERIC_SINGULAR.match(text[pronoun.start():]):
        return False
    # The verse states its teaching of a generic somebody, so whatever dangles
    # ahead of that is a turn in the argument rather than the subject.
    if GENERIC_SUBJECT.search(text):
        return False
    before = text[:pronoun.start()]
    if DOCTRINAL.search(before) or GENERIC_ANTECEDENT.search(before):
        return False
    for match in ANCHOR.finditer(before):
        # Words capitalised for opening a sentence name nobody; see
        # `proper_nouns`, which discounts them for the same reason.
        if match.group(0).lower() not in SENTENCE_OPENERS:
            return False
    return True

# First-person conviction, which is what a verse is usually remembered for.
TESTIMONY = re.compile(
    r"\b(i know that|i do know|we know that|i testif|i bear (?:my |solemn )?"
    r"(?:record|witness|testimony)|i will trust|will i trust|i will go and do|"
    r"i glory in|my soul (?:delighteth|hungered)|i am the (?:way|light|life)|"
    r"i would that ye should)\b", re.I)

# Counsel addressed to the reader, rather than a report of what someone did.
COUNSEL = re.compile(
    r"\b(come unto|blessed are|blessed is|blessed art|if ye will|if ye shall|"
    r"ye must|thou shalt|see that ye|let us|press forward|watch and pray|"
    r"ask, and|seek, and|knock, and|be ye|deny (?:yourselves|not)|"
    r"cleave unto|hold (?:fast|to) the)\b", re.I)

# The register of destruction, judgement and lament. These words are not
# forbidden -- "wickedness never was happiness" is one of the best verses there
# is -- but a verse thick with them is an account of a battle or a cry of
# distress, and it lands badly as the one thing someone reads today.
LAMENT = re.compile(
    r"\b(destroy|destruction|destroyed|perish|slain|slay|slew|smite|smote|"
    r"smitten|sword|swords|battle|wars|captivity|bondage|torment|hell|devil|"
    r"damnation|abomination|abominable|mourn|weep|wept|lament|wo|woe|vex|"
    r"curse|cursed|cursing|wrath|anger|angry|fierce|death|dying|corrupt|"
    r"wicked|wickedness|iniquity|iniquities|filthiness|carnal|devour|famine|"
    r"pestilence|bloodshed|vengeance|torment|afflict|affliction|deprav|brutal|"
    r"savage|degenerat|hardness|blindness|depravity)\w*",
    re.I)

# The voice of an accuser or a mocker: a verse that opens by challenging
# someone, or that tells the reader their faith has been for nothing. This is
# how the words of Satan and of the unbelieving get quoted as if they were
# counsel -- they use the vocabulary of the gospel to argue against it.
ACCUSATION = re.compile(
    r"^(hast|doth|dost|wilt thou|art thou|why (?:do|hast|art|should)|how long)\b"
    r"|\b(?:your|thy|ye)\b[^.]{0,60}\b(?:vain|nought|naught)\b", re.I)

# Scripture reports what the proud and the foolish tell themselves by quoting
# their own thought back at them -- "the fool hath said in his heart, There is
# no God", "thou hast said in thy heart: I will ascend into heaven". Alone,
# with the rebuke that follows it left behind in the next verse, the boast is
# all the reader gets, and it is dressed in the vocabulary of the gospel.
BOAST = re.compile(
    r"\b(?:thou|he|she|they|ye|fool)\s+(?:hast|hath|have|had)\s+said\s+in\s+"
    r"(?:thy|his|her|their|your)\s+heart", re.I)


# A complaint to God about what he has done: "he hath destroyed me on every
# side", "he hath stripped me of my glory". Job's, mostly, and true to the book
# he is in -- but a reader meeting one of these cold, with nothing either side
# of it and no answer for another thirty chapters, is left holding it.
COMPLAINT = re.compile(
    r"\b(?:he|thou|god|the lord) hath (?:destroyed|stripped|taken|removed|"
    r"broken|cast|torn|overthrown|compassed|hedged|fenced) me\b"
    r"|\bhath (?:destroyed|stripped|broken|forsaken) me\b", re.I)

# A verse reporting that people refused what they were taught is *about* them
# rather than *to* the reader. These are the verses that carry the vocabulary
# of the gospel while describing its rejection -- "they do set at naught his
# counsels", "they harden their hearts against it" -- so they score well on
# words alone and read as an indictment of somebody else.
REBELLION = re.compile(
    r"\bthey (?:do not|did not|will not|would not|had not)\b"
    r"|\bharden(?:ed|eth)? (?:their|his|her|not) heart"
    r"|\bthey (?:reject|rejected|deny|denied|revile|reviled|mock|mocked|"
    r"murmur|murmured|rebel|rebelled|dwindle|dwindled|stiffen|stiffened)\b"
    r"|\bset at naught\b|\bi fear lest\b", re.I)

# Words that are capitalised because they open a sentence or a quotation, not
# because they name anybody. Counting them as names taxed some of the best
# verses there are: "Naked came I out of my mother's womb" lost as much ground
# for "Naked" as a page of genealogy loses for a name.
SENTENCE_OPENERS = {
    "behold", "yea", "verily", "wherefore", "therefore", "naked", "blessed",
    "hearken", "hosanna", "amen", "nay", "nevertheless", "notwithstanding",
    "hallelujah", "woe", "wo", "awake", "arise", "remember", "repent", "come",
    "go", "know", "believe", "trust", "fear", "peace", "hear", "listen",
    "depart", "take", "look", "thus", "now", "and", "but", "for", "oh", "how",
    "what", "who", "when", "there", "then", "these", "this", "they", "we",
}


def proper_nouns(text: str) -> set[str]:
    """The names in a reading. Dense ones mean genealogy or a battle account.

    Deity is not counted. "the Lord", "God", "Jesus Christ" are what a verse of
    the day is most often about, and they are already rewarded as gospel words,
    so counting them here as well charged a verse for its own subject.
    """
    return {word for word in re.findall(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-z]{2,}\b", text)
            if word.lower() not in SENTENCE_OPENERS and not DOCTRINAL.fullmatch(word)}


def verse_score(text: str) -> float:
    """Rank a verse by how well it reads on its own, cold, as today's reading.

    The question is not whether a verse is important -- every verse is -- but
    whether it teaches something to someone who reads it with nothing either
    side of it. So the score rewards what a verse says (gospel vocabulary,
    conviction, counsel) and penalises what makes it lean on its neighbours
    (narrative openers, dense names) or land badly alone (lament, accusation,
    a bare question).
    """
    score = 1.6 * len(doctrinal_stems(text))
    if TESTIMONY.search(text):
        score += 3.0
    if COUNSEL.search(text):
        score += 1.5
    if NARRATIVE_OPENER.match(text):
        score -= 2.5
    if ACCUSATION.search(text):
        score -= 4.0
    if REBELLION.search(text):
        score -= 3.0
    if COMPLAINT.search(text):
        score -= 3.0
    if BOAST.search(text):
        score -= 4.0
    # Thick with destruction or distress. Capped, so a single hard word costs a
    # verse a little and cannot sink it on its own.
    score -= min(4.5, 0.9 * len({m.group(0).lower() for m in LAMENT.finditer(text)}))
    propers = proper_nouns(text)
    score -= 0.7 * len(propers)
    # A verse that is nothing but a question asks something the next verse
    # answers; alone, it leaves the reader holding it.
    if text.rstrip().endswith("?") and "." not in text:
        score -= 2.5
    # A verse running into the next one through its punctuation is usually
    # finishing there too. A light touch: the King James punctuates complete
    # sentences this way as well.
    if text.rstrip().endswith((":", ";")):
        score -= 0.8
    if 120 <= len(text) <= 300:
        score += 1.0
    # Short, whole and nameless: the shape of a verse people quote from memory.
    if 90 <= len(text) <= 200 and not propers:
        score += 1.5
    return score


# What being inside the week's assigned chapters is worth when the week's seven
# days are chosen. Large enough that an ordinary week is filled from the
# assignment before any cross-reference is looked at, small enough that a week
# whose own reading is thin does not spend a day on a verse that says nothing.
ASSIGNED_BONUS = 6.0

# How many days one chapter may take in a week. Come, Follow Me often links a
# long consecutive run -- the lesson on Job cites verses 1 through 27 of Job
# 19's twenty-nine -- and without a cap the week reads as one passage dealt out
# slowly rather than as a walk through the whole assignment.
#
# It is what shortens a week when one does run short. Of the 76 full weeks in
# the last calendar, 74 got their seven; the week on Esther had eight verses
# worth a day but they sat in five chapters, and the week on Matthew 1; Luke 1
# had twenty-seven with twenty-four of them in Luke 1 alone. Six days walking a
# week's whole reading is a better week than seven walking one chapter of it.
CFM_PER_CHAPTER = 2

# The score a verse needs to be worth one of the week's days. Below this the
# week simply runs shorter and its readings come round again, which is better
# than filling the last days with whatever was left.
CFM_VERSE_FLOOR = 2.5


def build_cfm_weeks(manual: str, year: int) -> list[dict]:
    """Collect each week's date range and the verses that week actually cites."""
    index = fetch(f"/manual/{manual}")
    if not index:
        print(f"Come, Follow Me: manual '{manual}' unavailable; skipping")
        return []

    week_uris = sorted({
        u for u in re.findall(rf"/study/(manual/{re.escape(manual)}/\d+)\?lang=eng",
                              index["content"]["body"])
    })
    print(f"Come, Follow Me: fetching {len(week_uris)} weeks ...")
    pages = fetch_many(["/" + u for u in week_uris])

    weeks: list[dict] = []
    unparsed: list[str] = []
    for uri, page in pages.items():
        if not page:
            continue
        title = page["meta"]["title"]
        span = parse_week_range(title, year)
        if not span:
            continue

        body = page["content"]["body"]
        # Gather the specific verses this week's lesson points at.
        wanted: dict[str, set[int]] = {}
        for chapter_path, query in re.findall(
                r'href="/study/scriptures/([a-z0-9-]+/[a-z0-9-]+/\d+)\?lang=eng([^"]*)"',
                body):
            nums = parse_verse_ids(query)
            if nums:
                wanted.setdefault(chapter_path, set()).update(nums)

        block = parse_reading_block(title)
        if block is None:
            unparsed.append(title)

        # Any mastery passage the week's reading covers belongs in that week --
        # it is the passage the reader is likeliest to be asked about, and a
        # week only comes round once, so it is put in whether or not the lesson
        # page happens to hyperlink those particular verses.
        mastery: list[dict] = []
        covered: set[tuple[str, int, int]] = set()
        if block:
            for path, nums in MASTERY:
                _, mbook, mchapter = path.split("/")
                if not in_block(block, mbook, int(mchapter)):
                    continue
                passage = fetch_passage(path, nums)
                if passage:
                    passage["rank"] = block_rank(block, mbook, int(mchapter))
                    passage["book"] = mbook
                    passage["chapter"] = int(mchapter)
                    passage["verse"] = min(nums)
                    mastery.append(passage)
                    covered.update((mbook, int(mchapter), n) for n in nums)

        chapters = fetch_many([f"/scriptures/{p}" for p in wanted])
        verses: list[dict] = []
        for chapter_path, nums in wanted.items():
            chapter = chapters.get(f"/scriptures/{chapter_path}")
            if not chapter:
                continue
            volume, book, ch = chapter_path.split("/")
            parsed = parse_verses(chapter["content"]["body"])
            for num in sorted(nums):
                text = parsed.get(num)
                if text and 60 <= len(text) <= 400 and reads_as_a_reading(text):
                    verses.append({
                        "reference": f"{book_name(book)} {ch}:{num}",
                        "text": text,
                        "url": f"https://www.churchofjesuschrist.org/study/scriptures/"
                               f"{chapter_path}?lang=eng&id=p{num}"
                               f"{verse_scroll(parsed, num)}",
                        "assigned": block is None or in_block(block, book, int(ch)),
                        "rank": block_rank(block, book, int(ch)) if block else 0,
                        "chapter": int(ch),
                        "verse": num,
                        "score": verse_score(text),
                        "key": (book, int(ch), num),
                    })

        # A verse already inside one of this week's mastery passages is dropped,
        # so a day is not spent on a fragment of what another day quotes whole.
        verses = [v for v in verses if v["key"] not in covered]

        # The week's own chapters are what is discussed on Sunday, so being in
        # the assignment is worth a great deal -- but as a bonus rather than an
        # absolute, because some weeks the assignment cannot fill seven days on
        # its own. The week of Job 1-3; 12-14; 19 is the case that settled it:
        # ranking every assigned verse above every cross-reference spent three
        # days of that week on Job 19:2, 19:9 and 19:10 -- "how long will ye vex
        # my soul", "he hath stripped me of my glory", "he hath destroyed me on
        # every side" -- while Ether 12:27 and D&C 121:7, which the lesson cites
        # precisely because they answer Job, waited outside. A bonus keeps the
        # assignment first in every ordinary week and lets a strong
        # cross-reference in when the reading itself is a week of lament.
        seen = {m["reference"] for m in mastery}
        ordered = list(mastery)
        # How many days one chapter may take, so a week cannot spend most of
        # itself on consecutive verses of a single passage.
        per_chapter: dict[tuple[str, int], int] = {}
        for verse in mastery:
            per_chapter[(verse.get("book", ""), verse.get("chapter", 0))] = 1
        ranked = sorted(verses, reverse=True,
                        key=lambda v: v["score"] + (ASSIGNED_BONUS if v["assigned"] else 0))
        for verse in ranked:
            if len(ordered) >= 7:
                break
            if verse["reference"] in seen:
                continue
            chapter_key = (verse["key"][0], verse["key"][1])
            if per_chapter.get(chapter_key, 0) >= CFM_PER_CHAPTER:
                continue
            # A week is better one day short than spent on a verse that does
            # not read as a reading.
            if verse["score"] < CFM_VERSE_FLOOR:
                continue
            seen.add(verse["reference"])
            per_chapter[chapter_key] = per_chapter.get(chapter_key, 0) + 1
            ordered.append(verse)

        if not ordered:
            continue
        # Monday through Sunday in the order the reading runs, so the week
        # walks through the assignment and arrives at church having read it.
        # Chapter is part of the key because a week assigned a whole book gives
        # every chapter of it the same place in the block.
        ordered.sort(key=lambda v: (v.get("rank", 0), v.get("chapter", 0),
                                    v.get("verse", 0)))
        chosen = [{k: v for k, v in verse.items()
                   if k not in ("assigned", "rank", "book", "chapter", "verse",
                                "score", "key")}
                  for verse in ordered]

        # Strip the leading date from the title to get the reading's name.
        label = re.split(r"\.\s", title, maxsplit=1)
        weeks.append({
            "start": span[0].isoformat(),
            "end": span[1].isoformat(),
            "title": (label[1] if len(label) > 1 else title).strip(),
            "url": f"https://www.churchofjesuschrist.org/study{uri}?lang=eng",
            "verses": chosen,
        })

    weeks.sort(key=lambda w: w["start"])
    mastered = sum(1 for w in weeks for v in w["verses"] if v.get("mastery"))
    print(f"Come, Follow Me: {len(weeks)} weeks with citable verses, "
          f"{mastered} mastery passages placed")
    if unparsed:
        print(f"  ! {len(unparsed)} week titles did not name a reading; "
              f"their citations were taken at face value", file=sys.stderr)
    return weeks


# --------------------------------------------------------------------------
# source 3 -- General Conference quotes
# --------------------------------------------------------------------------

# A full conference is about forty talks -- 41 in April 2026, 40 the October
# before it. Requiring half of them stops a half-posted conference from being
# chosen while it is still going up.
CONFERENCE_MIN_TALKS = 20

# Speaker photos are saved into the repository rather than hot-linked, so a
# page view still contacts nobody but the host serving the site. The card shows
# one at up to 17rem -- 272 CSS pixels -- so 480 is just under twice the width
# it is displayed at, which holds up on a 2x display.
PORTRAIT_WIDTH = 480


def conference_candidates(today: dt.date, depth: int = 8):
    """Conference sessions, newest first.

    Conference is held early in April and early in October, so the session for
    a month that has begun is the newest one that could exist.
    """
    if today.month >= 10:
        year, month = today.year, 10
    elif today.month >= 4:
        year, month = today.year, 4
    else:
        year, month = today.year - 1, 10
    for _ in range(depth):
        yield year, month
        year, month = (year, 4) if month == 10 else (year - 1, 10)


def talk_uris_for(year: int, month: int) -> list[str]:
    index = fetch(f"/general-conference/{year}/{month:02d}")
    if not index:
        return []
    return sorted({
        "/" + u for u in re.findall(
            rf"/study/(general-conference/{year}/{month:02d}/[a-z0-9-]+)\?lang=eng",
            index["content"]["body"])
    })


def resolve_conferences(count: int, today: dt.date | None = None
                        ) -> list[tuple[int, int, list[str]]]:
    """The `count` most recent conferences whose talks are actually published.

    The date says which conference is newest; only the site can say whether its
    text is up yet. Conference is held on a weekend and the talks appear over
    the following days, so between those two moments the newest session either
    404s or is half-posted. Probing rather than assuming means the changeover
    happens on its own, a few days after each conference, with no lag to keep
    in step with the calendar.
    """
    today = today or dt.date.today()
    chosen: list[tuple[int, int, list[str]]] = []
    for year, month in conference_candidates(today):
        if len(chosen) >= count:
            break
        uris = talk_uris_for(year, month)
        if not uris:
            print(f"  - {year}-{month:02d} not published yet; falling back")
            continue
        if len(uris) < CONFERENCE_MIN_TALKS:
            print(f"  - {year}-{month:02d} only {len(uris)} talks posted so far; "
                  f"falling back")
            continue
        chosen.append((year, month, uris))
    return chosen


def portrait_url(meta: dict, width: int = PORTRAIT_WIDTH) -> str | None:
    """The talk's own photo of its speaker, asked for at the width we serve.

    Every conference talk carries a photo of that speaker at the pulpit as its
    share image -- the same picture the conference index uses as a thumbnail.
    The URL is IIIF, so the size is ours to choose rather than whatever the
    page happened to link.
    """
    match = re.match(r"(https://\S+?)/full/[^/]+/0/default$",
                     meta.get("ogTagImageUrl") or "")
    return f"{match.group(1)}/full/%21{width}%2C/0/default" if match else None


def portrait_path(uri: str) -> Path:
    """/general-conference/2026/04/53hall -> assets/speakers/2026-04-53hall.jpg"""
    return SPEAKERS / ("-".join(uri.strip("/").split("/")[1:]) + ".jpg")


def fetch_portrait(item: tuple[str, dict | None]) -> tuple[str, str]:
    """Save one speaker photo, returning its path relative to the site root."""
    uri, talk = item
    url = portrait_url(talk["meta"]) if talk else None
    if not url:
        return uri, ""

    dest = portrait_path(uri)
    rel = dest.relative_to(ROOT).as_posix()
    # A talk's photo never changes, so one already in the repository is done.
    if dest.exists() and dest.stat().st_size:
        return uri, rel

    try:
        req = urllib.request.Request(url, headers={"User-Agent": UA,
                                                   "Accept": "image/jpeg,image/*"})
        with urllib.request.urlopen(req, timeout=45) as resp:
            if not resp.headers.get_content_type().startswith("image/"):
                return uri, ""
            data = resp.read()
    except (OSError, http.client.HTTPException) as err:
        print(f"  ! no photo for {uri}: {err}", file=sys.stderr)
        return uri, ""

    # Write beside the target first, so an interrupted build cannot leave a
    # truncated JPEG that later runs would take for a finished download.
    SPEAKERS.mkdir(parents=True, exist_ok=True)
    part = dest.with_suffix(".part")
    part.write_bytes(data)
    part.replace(dest)
    time.sleep(0.25)  # be a polite client
    return uri, rel


def fetch_portraits(talks: dict[str, dict | None], workers: int = 6) -> dict[str, str]:
    with ThreadPoolExecutor(max_workers=workers) as pool:
        return dict(pool.map(fetch_portrait, talks.items()))


def prune_portraits(days: dict[str, dict]) -> int:
    """Drop photos of speakers no longer in the calendar.

    The pool moves on with each conference, so without this the repository
    would keep every photo it had ever downloaded.
    """
    if not SPEAKERS.exists():
        return 0
    keep = {entry["quote"].get("image", "")
            for entry in days.values() if entry.get("quote")}
    removed = 0
    # Everything, not just *.jpg, so a half-written .part left by an
    # interrupted build is cleared out rather than committed with the rest.
    for path in SPEAKERS.iterdir():
        if path.is_file() and path.relative_to(ROOT).as_posix() not in keep:
            path.unlink()
            removed += 1
    return removed


# Conference is more than preaching: officers are sustained, the audit is read,
# a solemn assembly is called. Those items are minutes rather than teaching --
# "We invite the Quorum of the Twelve Apostles please to stand" is not a quote
# of the day -- so the talks carrying them are left out of the pool entirely.
BUSINESS = re.compile(
    r"solemn assembly|sustaining of|church auditing|statistical report|"
    r"church officers", re.I)


def is_business(title: str, speaker: str, role: str) -> bool:
    # Every one of these items is read on someone else's behalf, which is what
    # "Presented by" in place of "By" marks.
    return bool(BUSINESS.search(title) or speaker.startswith("Presented by")
                or re.search(r"auditing|managing director", role, re.I))


# What a speaker holds, which decides how much of the calendar their talk gets.
# The prophet speaks to the whole Church a handful of times a year and those
# talks are the ones members return to, so they are given the most room; the
# ordering below is read top down, so the more specific title wins.
SPEAKER_RANKS = [
    ("prophet", re.compile(r"^President of The Church", re.I)),
    ("presidency", re.compile(r"Counselor in the First Presidency", re.I)),
    ("twelve", re.compile(r"Quorum of the Twelve Apostles", re.I)),
]

QUOTA = {"prophet": 12, "presidency": 9, "twelve": 7, "other": 3}

# The score a paragraph has to reach to be worth a day at all. Every talk that
# has something to say is meant to get a turn, but the floor comes first: a
# session's opening and closing are talks like any other to the filters above,
# and without this their housekeeping -- "welcome to general conference", "the
# choir has just sung" -- is what a quota reaches down and takes. Better that
# a strong quote comes round twice in six months than that one of those runs
# once.
QUOTE_FLOOR = 1.0

# ...and the teaching it has to carry before its shape is allowed to count for
# anything. Roughly two gospel words, or one invitation. See `quote_substance`.
QUOTE_SUBSTANCE_FLOOR = 2.0


def speaker_rank(role: str) -> str:
    for name, pattern in SPEAKER_RANKS:
        if pattern.search(role):
            return name
    return "other"


# The turns of phrase that carry a conference talk's teaching: what the speaker
# invites, promises, and witnesses. A paragraph doing one of those is what a
# reader remembers a talk by, far more than its narration or its statistics.
INVITATION = re.compile(
    r"\b(i invite|i urge|i plead|i encourage|i counsel|my invitation|"
    r"i promise|i assure|my prayer|let us|may we|we can|you can|"
    r"consider|ponder|remember that|choose to|begin today)\b", re.I)

WITNESS = re.compile(
    r"\b(i testify|i bear (?:my )?(?:solemn )?witness|i know that|i declare|"
    r"i witness|i bear testimony)\b", re.I)

PROMISE = re.compile(
    r"\b(will bless|will come|will help|will strengthen|will guide|promise[sd]?|"
    r"blessings? (?:of|will|come)|the lord will|god will)\b", re.I)

# Every talk ends by closing in the name of Jesus Christ, and those closings
# are the highest-scoring paragraphs in the whole conference: they are dense
# with gospel words and almost always carry an invitation or a blessing, so the
# scoring loved them and the per-talk quotas took them first. One in six of the
# quotes chosen was one.
#
# They are not all alike, though, and refusing them outright went too far.
# Some are nothing but the form of words -- "...is my prayer and my blessing in
# the holy name of Jesus Christ, amen." Others are a real teaching with the
# formula added after it, and for a speaker who writes in long paragraphs the
# closing can be the only thing short enough to quote at all: refusing every
# one of them cost Elder Walker's talk its every quote, and his testimony that
# "as we obey the Savior's voice and keep our covenants -- even by small and
# quiet sacrifices each day -- we will feel His love more deeply and receive His
# guidance more clearly" with it. So a closing is judged on what it says with
# the formula set aside, and those that survive are ranked below everything else
# in their talk rather than above it.
BENEDICTION = re.compile(r"\bamen\b\W*$", re.I)


def benediction_core(text: str) -> str:
    """A closing paragraph with its formula dropped, for judging it.

    For judging only -- never for publishing. Every quote on the site is the
    paragraph as it was given, linked to the place it was given, so what is cut
    here is cut to weigh the paragraph and then thrown away.
    """
    sentences = re.split(r"(?<=[.!?])\s+", text.strip())
    while sentences and re.search(r"\bamen\b", sentences[-1], re.I):
        sentences.pop()
    return " ".join(sentences).strip()

# A paragraph about the talk it is in -- what the speaker will cover, what will
# appear in the published version, what is left of their time. It reads as
# housekeeping anywhere but in its place.
#
# The greeting a talk opens with belongs here too. It is the counterpart of the
# closing formula: "I am humbled by the privilege to speak to you", "I pray
# that the Spirit will be with you and with me". Unlike a closing there is
# rarely a teaching inside one to salvage, so these are simply refused -- and
# every speaker who opened this way had a good deal else to say.
SELF_REFERENTIAL = re.compile(
    r"\b((?:privilege|honor|honour|opportunity) (?:to|of) (?:speak|address)|"
    r"i (?:am|[’']m) (?:humbled|grateful|honored|honoured) to "
    r"(?:be with you|speak|stand|address)|"
    r"i pray that the (?:spirit|holy ghost)[^.]{0,60}(?:be with|with you)|"
    r"my (?:message|remarks|talk|address)\b|published version|"
    r"i (?:will|would like to|want to|have chosen to|have decided to|should like to)"
    r" (?:speak|address|talk|share)|"
    r"i will (?:mention|discuss|suggest|offer|consider) (?:three|two|four|five|"
    r"six|a few|several)|"
    r"as i (?:conclude|close|begin)|in the time (?:i have|that remains|remaining)|"
    r"i have been asked to speak|in my (?:message|remarks|talk))\b", re.I)

# "Second, the question is asked ..." picks up a list begun several paragraphs
# earlier, and says nothing on its own.
ENUMERATION = re.compile(
    r"^(first|second|third|fourth|fifth|sixth|seventh|next|finally|lastly|"
    r"number \w+)\b\s*[,:]", re.I)

# The furniture of a session rather than the preaching in it.
HOUSEKEEPING = re.compile(
    r"\b(the choir|we have just (?:heard|sung)|welcome to this|welcome you to|"
    r"we are grateful to (?:be|have)|this morning'?s session|"
    r"the closing (?:prayer|hymn)|will now be|please be seated)\b", re.I)


def quote_substance(text: str) -> float:
    """What a paragraph actually says, with the presentational bonuses left out.

    `quote_score` also rewards a paragraph for being a convenient length, and
    it has to: of two paragraphs that teach equally well, the shorter is the
    better quote. But a bonus for being the right *shape* was enough to clear
    the floor on its own, so paragraphs that said nothing whatsoever -- an
    airline's baggage handling, a family dog named Lady -- qualified on length
    and went into the calendar. Substance is measured separately so that having
    something to say can be required before shape is rewarded.
    """
    score = 1.2 * len(doctrinal_stems(text))
    if INVITATION.search(text):
        score += 3.5
    if WITNESS.search(text):
        score += 4.0
    if PROMISE.search(text):
        score += 2.0
    return score


def quote_score(text: str) -> float:
    """Rank a paragraph by how much teaching it carries on its own."""
    score = quote_substance(text)
    # A quote has to be short enough to be carried away in one reading.
    if 130 <= len(text) <= 260:
        score += 2.5
    elif len(text) > 300:
        score -= 1.5
    # Numbers and dense proper nouns mean a report or an anecdote, not counsel.
    score -= 1.5 * len(re.findall(r"\b\d{2,}\b|\bpercent\b", text))
    score -= 0.5 * len(proper_nouns(text))
    # A paragraph that is only questions sets something up rather than saying it.
    if text.count("?") >= 2 and "." not in text:
        score -= 2.5
    return score


# A demonstrative in front of a word for an occasion -- "that day", "at that
# moment", "this experience" -- is a pointer, and in a conference talk what it
# points at is nearly always the paragraph before. "To you in this vast
# worldwide congregation who lovingly remember that day in your life, I speak
# especially to you" is Elder Andersen's, and the day is the one the paragraph
# above it describes: kneeling across the altar from Kathy in a holy temple of
# God. Alone on a card it asks the reader to remember a day it never names, and
# it was reported for it.
#
# This is the fault `unfilled_it` and `unfilled_thus` answer on the scripture
# cards, in the form a talk takes it. A talk is built out of stories, and the
# paragraph after a story refers back to it instead of retelling it -- which is
# why the fault is common enough here to be worth a rule of its own, and why
# the rule stays on this card. Scripture's "in that day" is the day of the
# Lord, and a reader supplies it.
#
# Two kinds of word are looked at, and not in the same way.
#
#   * A word that can mean *now* at a pulpit -- day, morning, moment, time --
#     points backwards only with "that" or "those". "This day" and "this
#     moment" are the ones the speaker is standing in, and want nothing from
#     any paragraph.
#   * A word for something already told -- experience, story, incident, visit
#     -- cannot mean now however it is introduced, so "this experience" and
#     "these stories" point back exactly as "that experience" does. Elder
#     Wakolo's "These stories are not about statistics. They are about souls"
#     is the plainest of them: read cold, there are no stories.
#
# What fills one is the paragraph saying which occasion it means, and it has
# three ways to:
#
#   * it named the occasion earlier in its own text, in either number -- "The
#     next morning their ward members gathered ... No one expected the bishop's
#     family to be at church that morning";
#   * a clause or an "of" follows and says which -- "on that day when a
#     priesthood leader felt impressed for us to visit a mother and a son",
#     "that moment of weakness";
#   * the occasion has not happened yet. "That day will be filled with joy for
#     the righteous", "That moment will come" -- what is still ahead is not
#     anything a speaker has already narrated, and the day of the Lord is a day
#     every reader can name.
OCCASION_NOW = (r"day|days|morning|mornings|evening|evenings|night|nights|"
                r"moment|moments|time|times|hour|hours|season|seasons")
OCCASION_TOLD = (r"experience|experiences|story|stories|incident|incidents|"
                 r"episode|episodes|encounter|encounters|conversation|"
                 r"conversations|errand|errands|occasion|occasions|event|"
                 r"events|visit|visits|trip|trips|meeting|meetings")

# The clause or the complement that says which occasion is meant.
OCCASION_FILLED = r"(?!\s+(?:when|where|which|who|whom|that|of|in\s+which)\b)"

POINTING_BACK = re.compile(
    rf"\b(?:that|those)\s+({OCCASION_NOW}|{OCCASION_TOLD})\b{OCCASION_FILLED}"
    rf"|\b(?:this|these)\s+({OCCASION_TOLD})\b{OCCASION_FILLED}", re.I)

# An occasion still ahead of the reader, which no story can already have told.
OCCASION_AHEAD = re.compile(r"^\s+(?:will|shall)\b", re.I)

# "That" in front of one of these words is not always a determiner. "Sometimes
# I need the perspective that time gives to see the refining and perfecting
# hand of our Savior, Jesus Christ" is a relative clause: the "that" is the
# object of "gives", and "time" is the subject of it. It is told apart by
# needing both of the things a relative clause has and a pointer never does --
# a noun phrase in front of it to modify, and a verb after it left without the
# object it wants. Both halves are required because either on its own is
# ordinary: "As the disciples walked away from the Savior that day" has the
# noun phrase, and "What I experienced that day was a small yet powerful
# manifestation" has the verb. Over the whole conference cache the pair
# exempts that one paragraph and nothing else.
RELATIVE_ANTECEDENT = re.compile(
    r"\b(?:the|a|an|my|our|your|his|her|their|its)\s+\w+\s+$", re.I)
RELATIVE_GAP = re.compile(
    r"^\s+\w+s\s+(?:to|for|us|me|them|him|her|you|the|a|an|in|into|on|with|"
    r"and|from)\b", re.I)


def occasion_named(noun: str) -> str:
    """The word in either number, for finding it earlier in the paragraph."""
    noun = noun.lower()
    if noun.endswith("ies"):
        noun = noun[:-3] + "y"
    elif noun.endswith("s"):
        noun = noun[:-1]
    if noun.endswith("y"):
        return rf"\b{noun[:-1]}(?:y|ies)\b"
    return rf"\b{noun}s?\b"


def unnamed_occasion(text: str) -> bool:
    """Whether a "that day" here points at a day the paragraph never names."""
    for match in POINTING_BACK.finditer(text):
        noun = match.group(1) or match.group(2)
        before, after = text[:match.start()], text[match.end():]
        if re.search(occasion_named(noun), before, re.I):
            continue
        if OCCASION_AHEAD.match(after):
            continue
        if RELATIVE_ANTECEDENT.search(before) and RELATIVE_GAP.match(after):
            continue
        return True
    return False


def is_quotable_paragraph(text: str) -> bool:
    """Whether a paragraph can stand alone at all.

    This asks only whether a paragraph is disqualified -- a fragment, a
    continuation, half a quotation. Which of the ones that survive is worth a
    day is `quote_score`'s question, and leaving that judgement to the scoring
    is what keeps the best of a talk in contention: rejecting everything a
    little suspect here starved the ranking, and hit the plainest speakers
    hardest.
    """
    if not 90 <= len(text) <= 420:
        return False
    if not text.endswith((".", "!", "?", '."', '!"', '?"')):
        return False
    if HOUSEKEEPING.search(text):
        return False
    # A closing that is nothing but the form of words. One that still teaches
    # something with the formula set aside is kept, and ranked last in its talk.
    if BENEDICTION.search(text):
        core = benediction_core(text)
        if len(core) < 90 or quote_substance(core) < QUOTE_SUBSTANCE_FLOOR:
            return False
    # A paragraph about the talk it sits in, or one carrying on a list begun
    # several paragraphs earlier.
    if SELF_REFERENTIAL.search(text) or ENUMERATION.match(text):
        return False
    # Skip paragraphs that only make sense next to the one before them, and
    # scene-setting narration that is not a teaching. The possessives and
    # objects are here for the same reason the subjects are -- "Their example
    # has stayed with me" is as unreadable cold as "They stayed with me" -- and
    # they cost this conference's pool nothing, having found no paragraph the
    # rest of the test was not already refusing. They are the standard the two
    # scripture cards are held to as well; see DANGLING_OPENER.
    if re.match(r"^(But|So|Then|Yet|However|That|This|These|Those|It was|"
                r"He |She |They |His|Her|Their|Its|Him|Them|Such|"
                r"We were|I was|After |Later|Then,)\b", text):
        return False
    # "Tragically, the bullet ..." -- an adverb opener almost always continues
    # a story told in the paragraph before.
    if re.match(r"^[A-Z][a-z]+ly,", text):
        return False
    # A demonstrative pointing at an occasion the paragraph never names --
    # "remember that day in your life". See `unnamed_occasion`.
    if unnamed_occasion(text):
        return False
    # Storytelling rather than counsel. The verbs are named rather than matched
    # as any past tense, because "-ed" alone throws out the counsel that is
    # phrased in it -- "I have learned", "He suffered", "I promised".
    if re.search(r"\b(I|we|he|she|they)\s+(was|were|had|sought|went|came|"
                 r"told|said|saw|felt|knew|gave|took|found|began|met|left|"
                 r"heard|spoke|wrote|sat|stood|witnessed|watched|looked|"
                 r"visited|attended|arrived|returned|recalled|noticed)\b",
                 text[:120], re.I):
        return False
    # Academic asides and dangling half-quotations.
    if "(see " in text or "(compare" in text:
        return False
    if text.count('"') == 1 or text.count("“") != text.count("”"):
        return False
    return not text.startswith(("“", '"'))


def build_quote_pool(count: int = 1) -> list[dict]:
    sessions = resolve_conferences(count)
    if not sessions:
        return []
    newest = sessions[0]
    print(f"General Conference: quoting from "
          f"{'April' if newest[1] == 4 else 'October'} {newest[0]}"
          f"{f' and {len(sessions) - 1} earlier' if len(sessions) > 1 else ''}")

    pool: list[dict] = []
    skipped: list[str] = []
    for year, month, talk_uris in sessions:
        print(f"General Conference {year}-{month:02d}: fetching {len(talk_uris)} talks ...")
        talks = fetch_many(talk_uris)

        # Held aside so the photos can be fetched for the talks that actually
        # contributed a quote -- a talk whose every paragraph was filtered out
        # can never be shown, so its photo is not worth downloading.
        found: list[tuple[str, dict]] = []

        for uri, talk in talks.items():
            if not talk:
                continue
            body = talk["content"]["body"]
            title = talk["meta"]["title"]
            author = re.search(r'<p class="author-name"[^>]*>(.*?)</p>', body, re.S)
            role = re.search(r'<p class="author-role"[^>]*>(.*?)</p>', body, re.S)
            if not author:
                continue
            speaker = re.sub(r"^By\s+", "", clean(author.group(1))).strip()
            if not speaker:
                continue
            role_text = clean(role.group(1)) if role else ""
            if is_business(title, speaker, role_text):
                skipped.append(title)
                continue

            paragraphs = talk_paragraphs(body)
            session = f"{'April' if month == 4 else 'October'} {year}"
            rank = speaker_rank(role_text)
            candidates = []
            for index, (pid, text) in enumerate(paragraphs):
                if (is_quotable_paragraph(text)
                        and quote_substance(text) >= QUOTE_SUBSTANCE_FLOOR
                        and quote_score(text) >= QUOTE_FLOOR):
                    candidates.append({
                        "text": text,
                        "speaker": speaker,
                        "role": role_text,
                        "talk": title,
                        "session": session,
                        "url": f"https://www.churchofjesuschrist.org/study{uri}"
                               f"?lang=eng&id={pid}"
                               f"{scroll_fragment(paragraphs, index)}",
                        "score": quote_score(text),
                        "closing": bool(BENEDICTION.search(text)),
                    })

            # Only the best of a talk, and how many depends on whose talk it is.
            # Every quota is several deep, so a talk with anything above the
            # floor is heard from -- no speaker who stood at that pulpit and
            # taught goes unquoted, however the scoring happened to fall.
            #
            # A closing sorts below every other paragraph however it scored, so
            # a talk with anything else to offer is never quoted by its last
            # line -- and one with nothing else still gets its turn.
            candidates.sort(key=lambda q: (q["closing"], -q["score"]))
            for quote in candidates[:QUOTA[rank]]:
                found.append((uri, quote))

        quoted = {uri: talks[uri] for uri, _ in found}
        print(f"General Conference {year}-{month:02d}: "
              f"fetching {len(quoted)} speaker photos ...")
        photos = fetch_portraits(quoted)
        for uri, quote in found:
            quote["image"] = photos.get(uri, "")
            # The score and the speaker's role decided which paragraphs got
            # here and how many; neither is rendered, and the calendar repeats
            # a quote's object on every day it falls on, so they are dropped
            # rather than shipped 730 times over.
            pool.append({k: v for k, v in quote.items()
                         if k not in ("score", "role", "closing")})

    if skipped:
        print(f"General Conference: skipped {len(set(skipped))} items of "
              f"church business ({', '.join(sorted(set(skipped))[:3])})")
    print(f"General Conference: {len(pool)} quotes from "
          f"{len(set(q['talk'] for q in pool))} talks")
    return pool


# --------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------

# --------------------------------------------------------------------------
# rendering -- today's readings are baked into the page so it is complete
# before any script runs
# --------------------------------------------------------------------------

TEMPLATE = Path(__file__).resolve().parent / "template.html"
INDEX = ROOT / "index.html"

WEEKDAYS = ["Monday", "Tuesday", "Wednesday", "Thursday", "Friday",
            "Saturday", "Sunday"]
MONTH_NAMES = ["January", "February", "March", "April", "May", "June", "July",
               "August", "September", "October", "November", "December"]


# A mastery passage is quoted whole, and some of them run to several verses.
# Past about this many characters the reading is set a little smaller so it
# still reads as one block rather than overrunning the card.
LONG_READING = 420


def esc(value: str) -> str:
    return html.escape(value or "", quote=True)


def scripture_class(text: str) -> str:
    return "scripture scripture--long" if len(text or "") > LONG_READING else "scripture"


def human_date(date: dt.date) -> str:
    return (f"{WEEKDAYS[date.weekday()]}, {MONTH_NAMES[date.month - 1]} "
            f"{date.day}, {date.year}")


def share_text(text: str, credit: str, url: str) -> str:
    """A card as it goes out: the reading, whose words they are, and the link
    back to the official source -- the same three parts, in the same order,
    that the script hands to a share sheet, so a card passed on from a page
    without JavaScript arrives looking no different."""
    return "\n\n".join(part for part in (text, credit, url) if part)


def share_block(card: str, payload: str) -> str:
    """The share block for a reader whose JavaScript is switched off.

    A share sheet and a clipboard are both things only a script can ask for,
    so what markup can offer in their place is the card itself, written out in
    the shape it is passed on in, in a field ready to be selected and copied --
    into a mail app, a message, a note, wherever the reader wants to put it.
    The page sends nothing anywhere, and nothing goes anywhere at all until the
    reader presses send in an app of their own.

    There are deliberately no app links above the field. Whether a `mailto:`
    or `sms:` link does anything at all is settled after the page is out of it,
    when the browser hands the address to the operating system, and if that
    handoff declines the page is told nothing: the link is pressed and it just
    sits there. `mailto:` is at least specified, and it was offered here for a
    while, but it was found dead on a current phone all the same -- a Pixel 9
    Pro, Brave, scripts off -- and markup cannot ask first, cannot be told it
    failed, and cannot fall back. `sms:` is worse: a prefilled body is custom
    only, never specification, Apple's own URL scheme reference says the
    address must not carry message text, and the platforms disagree over how to
    introduce it, Android reading `sms:?body=` and iOS `sms:&body=`, while
    `sms:?&body=` -- the spelling meant to satisfy both -- does nothing on a
    phone that satisfies neither.

    On a page that promises to work without scripts, a link that quietly fails
    is worse than one never offered, so the field is the whole of it: select,
    copy, paste, and certain of it on every phone there is.

    The script hides this block once it has a working Share button, so nobody
    is offered the same thing twice.
    """
    return f"""<details class="share-fallback" id="share-fallback-{card}">
      <summary>Share</summary>
      <label class="share-fallback__hint" for="share-payload-{card}">Copy it, to send it any way you like:</label>
      <textarea class="share-fallback__text" id="share-payload-{card}" rows="10" readonly spellcheck="false">{esc(payload)}</textarea>
    </details>"""


def today_in(timezone: str) -> dt.date:
    """Today's date where the site's readers are, not in UTC."""
    try:
        from zoneinfo import ZoneInfo
        return dt.datetime.now(ZoneInfo(timezone)).date()
    except Exception as err:  # missing tzdata on a bare system
        print(f"  ! timezone {timezone!r} unavailable ({err}); using UTC",
              file=sys.stderr)
        return dt.datetime.now(dt.timezone.utc).date()


def render_cards(entry: dict) -> str:
    """Build the three cards as static markup."""
    bom, quote, cfm = entry.get("bom"), entry.get("quote"), entry.get("cfm")

    # The Come, Follow Me card is emitted even when the published manual does
    # not cover this date, so that the script can fill it in later for a
    # reader whose local date does fall inside the manual.
    cfm_hidden = "" if cfm else " hidden"
    cfm = cfm or {}

    # Likewise the speaker's photo: the figure is always in the markup so the
    # script has something to fill, but an <img> with no src at all -- rather
    # than an empty one, which some browsers re-request the page for.
    photo = quote.get("image", "")
    photo_src = f' src="{esc(photo)}"' if photo else ""
    photo_alt = esc(f"{quote.get('speaker', '')} speaking at general conference") if photo else ""

    # Each card's reading written out once more, in the shape it is passed on
    # in, for the share block underneath it.
    bom_share = share_block(
        "bom",
        share_text(bom.get("text", ""), bom.get("reference", ""), bom.get("url", "")))
    cfm_share = share_block(
        "cfm",
        share_text(cfm.get("text", ""), cfm.get("reference", ""), cfm.get("url", "")))
    quote_share = share_block(
        "quote",
        share_text(quote.get("text", ""), quote.get("speaker", ""), quote.get("url", "")))

    return f"""
  <section class="card" id="card-bom">
    <h2 class="card__label">Book of Mormon <span>Verse of the Day</span></h2>
    <blockquote class="{scripture_class(bom.get('text', ''))}" id="bom-text">{esc(bom.get('text', ''))}</blockquote>
    <p class="ref"><a id="bom-link" href="{esc(bom.get('url', '#'))}" target="_blank" rel="noopener noreferrer"><cite id="bom-ref">{esc(bom.get('reference', ''))}</cite></a></p>
    <button type="button" class="share" id="share-bom" hidden>Share</button>
    {bom_share}
  </section>

  <section class="card" id="card-cfm"{cfm_hidden}>
    <h2 class="card__label">Come, Follow Me <span>Verse of the Day</span></h2>
    <p class="week">This week: <a id="cfm-week-link" href="{esc(cfm.get('weekUrl', '#'))}" target="_blank" rel="noopener noreferrer"><span id="cfm-week">{esc(cfm.get('week', ''))}</span></a></p>
    <blockquote class="{scripture_class(cfm.get('text', ''))}" id="cfm-text">{esc(cfm.get('text', ''))}</blockquote>
    <p class="ref"><a id="cfm-link" href="{esc(cfm.get('url', '#'))}" target="_blank" rel="noopener noreferrer"><cite id="cfm-ref">{esc(cfm.get('reference', ''))}</cite></a></p>
    <button type="button" class="share" id="share-cfm" hidden>Share</button>
    {cfm_share}
  </section>

  <section class="card" id="card-quote">
    <h2 class="card__label">General Conference <span>Quote of the Day</span></h2>
    <blockquote class="quote" id="quote-text">{esc(quote.get('text', ''))}</blockquote>
    <figure class="portrait" id="quote-portrait"{'' if photo else ' hidden'}>
      <img id="quote-photo"{photo_src} alt="{photo_alt}" width="{PORTRAIT_WIDTH}" height="{PORTRAIT_WIDTH * 9 // 16}" loading="lazy" decoding="async">
    </figure>
    <p class="ref">
      <span id="quote-speaker" class="speaker">{esc(quote.get('speaker', ''))}</span><a id="quote-link" href="{esc(quote.get('url', '#'))}" target="_blank" rel="noopener noreferrer"><cite id="quote-talk">{esc(quote.get('talk', ''))}</cite></a><span id="quote-session" class="session">{esc(quote.get('session', ''))}</span>
    </p>
    <button type="button" class="share" id="share-quote" hidden>Share</button>
    {quote_share}
  </section>
"""


def render_site(payload: dict, timezone: str, date: dt.date | None = None) -> dt.date:
    """Write index.html with the current day's readings already in place."""
    date = date or today_in(timezone)
    entry = payload["days"].get(date.isoformat())
    if not entry:
        # Fall back to the nearest built day so the page is never blank.
        keys = sorted(payload["days"])
        nearest = min(keys, key=lambda k: abs(dt.date.fromisoformat(k).toordinal()
                                              - date.toordinal()))
        print(f"  ! no entry for {date}; baking {nearest} instead", file=sys.stderr)
        entry = payload["days"][nearest]

    page = TEMPLATE.read_text(encoding="utf-8")
    for token, value in (("{{DATE_ISO}}", date.isoformat()),
                         ("{{DATE_HUMAN}}", human_date(date)),
                         ("{{CARDS}}", render_cards(entry)),
                         ("{{GENERATED}}", payload["generated"][:10])):
        page = page.replace(token, value)
    INDEX.write_text(page, encoding="utf-8", newline="\n")
    return date


def write_months(days: dict[str, dict]) -> tuple[int, int]:
    """The calendar again, sliced by month, beside the whole of it.

    The script only ever needs one day -- the reader's today, when the page
    was built for a different one -- and the whole calendar is two years and
    the better part of a megabyte. That was every reader east of Denver in the
    morning, and everyone at all on a morning GitHub rendered late, fetching
    730 days to show one. A month is a tenth of that, and it is what the
    script asks for first; the whole calendar is the fallback, for a day past
    the end of what was built. See assets/app.js.

    A month carries no timestamp, so its bytes change only when a pick in it
    does -- a new conference, a new manual -- and a routine refetch commits
    nothing here. Months the calendar has moved past are removed. A render-only
    run writes them too, from the calendar it already has.
    """
    by_month: dict[str, dict[str, dict]] = {}
    for iso, entry in days.items():
        by_month.setdefault(iso[:7], {})[iso] = entry
    MONTH_DIR.mkdir(parents=True, exist_ok=True)
    for month, month_days in by_month.items():
        with open(MONTH_DIR / f"{month}.json", "w", encoding="utf-8") as fh:
            json.dump({"days": month_days}, fh, ensure_ascii=False,
                      separators=(",", ":"))
    removed = 0
    for path in MONTH_DIR.glob("*.json"):
        if path.stem not in by_month:
            path.unlink()
            removed += 1
    return len(by_month), removed


def spread(pool: list[dict], seed: int, key) -> list[dict]:
    """Shuffle a pool so consecutive days are not from the same place."""
    shuffled = pool[:]
    random.Random(seed).shuffle(shuffled)
    # Push items sharing a key (book, or speaker) apart from each other.
    buckets: dict[str, list[dict]] = {}
    for item in shuffled:
        buckets.setdefault(key(item), []).append(item)
    order = sorted(buckets.values(), key=len, reverse=True)
    spread_out: list[dict] = []
    while any(order):
        for bucket in order:
            if bucket:
                spread_out.append(bucket.pop())
    return spread_out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--start", default=None, help="first date (YYYY-MM-DD)")
    ap.add_argument("--days", type=int, default=730, help="how many days to build")
    ap.add_argument("--manual", default=None,
                    help="pin a Come, Follow Me manual slug instead of deriving "
                         "it from the four-year cycle (needs --manual-year)")
    ap.add_argument("--manual-year", type=int, default=None,
                    help="the year --manual is taught")
    ap.add_argument("--cfm-years", type=int, default=2,
                    help="how many years of Come, Follow Me manuals to build "
                         "(2 = this year's and next year's, once published)")
    ap.add_argument("--conferences", type=int, default=1,
                    help="how many recent conferences to quote from "
                         "(1 = the most recent one only)")
    ap.add_argument("--timezone", default="America/Denver",
                    help="whose 'today' the page is built for")
    ap.add_argument("--render-only", action="store_true",
                    help="re-render index.html from the existing calendar "
                         "without fetching anything")
    ap.add_argument("--date", default=None,
                    help="render for this date instead of today (YYYY-MM-DD)")
    args = ap.parse_args()

    as_of = dt.date.fromisoformat(args.date) if args.date else None

    # The daily job only needs to move the page on to the next day, which the
    # prebuilt calendar already answers -- no need to refetch anything.
    if args.render_only:
        if not OUT.exists():
            print(f"error: {OUT} does not exist; run a full build first",
                  file=sys.stderr)
            return 1
        with open(OUT, encoding="utf-8") as fh:
            payload = json.load(fh)
        # The month slices are derived from the calendar, so they are written
        # here as well as by a full build: the same bytes for the same
        # calendar, which costs a render nothing and means a calendar that
        # arrived without them -- built by an older tool, say -- is put right
        # by the next render rather than the next refetch.
        write_months(payload["days"])
        date = render_site(payload, args.timezone, as_of)
        print(f"Rendered index.html for {date} ({args.timezone})")
        return 0

    start = (dt.date.fromisoformat(args.start) if args.start
             else dt.date.today() - dt.timedelta(days=30))
    end = start + dt.timedelta(days=args.days - 1)

    if args.manual and args.manual_year is None:
        print("error: --manual-year is required with --manual", file=sys.stderr)
        return 1

    bom = build_bom_pool()
    bom_mastery = build_mastery_passages("bofm/")
    quotes = build_quote_pool(args.conferences)

    manuals = ([(args.manual, args.manual_year)] if args.manual
               else resolve_cfm_manuals(start, end, args.cfm_years))
    weeks: list[dict] = []
    for manual, manual_year in manuals:
        weeks.extend(build_cfm_weeks(manual, manual_year))
    weeks.sort(key=lambda w: w["start"])

    if not bom or not quotes:
        print("error: could not build the required pools", file=sys.stderr)
        return 1

    tier = build_bom_tier(bom)
    quotes = spread(quotes, seed=20260102, key=lambda q: q["speaker"])

    days: dict[str, dict] = {}
    for offset in range(args.days):
        date = start + dt.timedelta(days=offset)
        # Index from a fixed epoch rather than from the start of this build, so
        # a date always resolves to the same pick and a rebuild part-way
        # through the day does not change the verse under the reader.
        index = (date - EPOCH).days
        entry = {
            "bom": bom_for(index, tier, bom_mastery),
            "quote": quotes[index % len(quotes)],
        }
        for week in weeks:
            if week["start"] <= date.isoformat() <= week["end"]:
                verses = week["verses"]
                # The week's verses run in reading order from its first day, so
                # the reader walks through the assignment and reaches Sunday
                # having read it rather than meeting it in a jumble.
                day = (date - dt.date.fromisoformat(week["start"])).days
                entry["cfm"] = {
                    **verses[day % len(verses)],
                    "week": week["title"],
                    "weekUrl": week["url"],
                }
                break
        days[date.isoformat()] = entry

    dropped = prune_portraits(days)

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "first": start.isoformat(),
        "last": end.isoformat(),
        "cfmManuals": [manual for manual, _ in manuals],
        "days": days,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))
    months, stale_months = write_months(days)

    covered = sorted(d for d, entry in days.items() if "cfm" in entry)
    print(f"\nWrote {OUT.relative_to(ROOT)}")
    print(f"  {len(days)} days ({payload['first']} .. {payload['last']})")
    # The last covered day is when the Come, Follow Me card would go dark if no
    # further manual were ever published, so it is worth stating outright.
    print(f"  {len(covered)} days with a Come, Follow Me verse"
          + (f" ({covered[0]} .. {covered[-1]})" if covered else ""))
    print(f"  manuals: {', '.join(m for m, _ in manuals) or 'none'}")
    print(f"  {OUT.stat().st_size / 1024:.0f} KB")
    print(f"  {months} month files in {MONTH_DIR.relative_to(ROOT).as_posix()}/"
          + (f", {stale_months} stale ones removed" if stale_months else ""))

    photos = sorted(SPEAKERS.glob("*.jpg")) if SPEAKERS.exists() else []
    print(f"  {len(photos)} speaker photos "
          f"({sum(p.stat().st_size for p in photos) / 1024:.0f} KB)"
          + (f", {dropped} pruned" if dropped else ""))

    date = render_site(payload, args.timezone, as_of)
    print(f"Wrote index.html for {date} ({args.timezone})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
