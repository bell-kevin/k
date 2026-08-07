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
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError,
                ValueError) as err:
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


# --------------------------------------------------------------------------
# source 1 -- Book of Mormon verses
# --------------------------------------------------------------------------

def is_quotable_verse(text: str) -> bool:
    """Keep verses that stand on their own when read cold."""
    if not 90 <= len(text) <= 340:
        return False
    lowered = text.lower()
    # Skip bare genealogy, chronology and travelogue, which read poorly cold.
    if re.search(r"\bbegat\b|\bthe record of\b|\bplates of\b|\bpitch(ed)? our tents\b"
                 r"|\bjourney(ed|ing)? in the wilderness\b", lowered):
        return False
    # Require some doctrinal substance, and reject dense narrative.
    return verse_score(text) >= 3.0


def build_bom_pool() -> list[dict]:
    uris = [f"/scriptures/bofm/{slug}/{ch}"
            for slug, _, chapters in BOM_BOOKS
            for ch in range(1, chapters + 1)]
    print(f"Book of Mormon: fetching {len(uris)} chapters ...")
    pages = fetch_many(uris)

    pool: list[dict] = []
    for slug, name, chapters in BOM_BOOKS:
        for ch in range(1, chapters + 1):
            page = pages.get(f"/scriptures/bofm/{slug}/{ch}")
            if not page:
                continue
            for num, text in sorted(parse_verses(page["content"]["body"]).items()):
                if is_quotable_verse(text):
                    pool.append({
                        "reference": f"{name} {ch}:{num}",
                        "text": text,
                        "url": f"https://www.churchofjesuschrist.org/study/scriptures/"
                               f"bofm/{slug}/{ch}?lang=eng&id=p{num}#p{num}",
                    })
    print(f"Book of Mormon: {len(pool)} quotable verses")
    return pool


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


# Words that mark a verse as teaching rather than plot. Come, Follow Me cites
# whole passages, so a week's citations mix doctrine with narrative connective
# tissue; scoring lets the better-standing-alone verses win.
DOCTRINAL = re.compile(
    r"\b(lord|god|christ|jesus|saviour|savior|spirit|faith|love|charity|hope|"
    r"heart|soul|covenant|commandment|righteous|mercy|merciful|grace|truth|"
    r"bless|blessed|repent|forgive|holy|glory|redeem|salvation|eternal|"
    r"everlasting|worship|pray|prayer|humble|peace|joy|light|trust|obey|"
    r"remember|witness|testimony|thanksgiving|rejoice)\b", re.I)

NARRATIVE_OPENER = re.compile(
    r"^(nevertheless|so |then |and when|now when|and it came to pass that when|"
    r"and he sent|and they came|after this|and after|moreover|likewise)\b", re.I)


def verse_score(text: str) -> float:
    """Rank a cited verse by how well it reads on its own."""
    score = 2.0 * len(set(m.group(0).lower() for m in DOCTRINAL.finditer(text)))
    if NARRATIVE_OPENER.match(text):
        score -= 3.0
    # Dense proper nouns usually mean genealogy or a battle account.
    propers = re.findall(r"(?<![.!?]\s)(?<!^)\b[A-Z][a-z]{2,}\b", text)
    score -= 0.8 * len(set(propers))
    if 120 <= len(text) <= 300:
        score += 1.5
    return score


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
                if text and 60 <= len(text) <= 400:
                    verses.append({
                        "reference": f"{book_name(book)} {ch}:{num}",
                        "text": text,
                        "url": f"https://www.churchofjesuschrist.org/study/scriptures/"
                               f"{chapter_path}?lang=eng&id=p{num}#p{num}",
                    })

        if not verses:
            continue
        # Keep the verses that stand best on their own, so every day of the
        # week gets a distinct one worth reading cold.
        seen: set[str] = set()
        ranked = []
        for verse in sorted(verses, key=lambda v: verse_score(v["text"]), reverse=True):
            if verse["reference"] not in seen:
                seen.add(verse["reference"])
                ranked.append(verse)
        verses = ranked[:7]

        # Strip the leading date from the title to get the reading's name.
        label = re.split(r"\.\s", title, maxsplit=1)
        weeks.append({
            "start": span[0].isoformat(),
            "end": span[1].isoformat(),
            "title": (label[1] if len(label) > 1 else title).strip(),
            "url": f"https://www.churchofjesuschrist.org/study{uri}?lang=eng",
            "verses": verses,
        })

    weeks.sort(key=lambda w: w["start"])
    print(f"Come, Follow Me: {len(weeks)} weeks with citable verses")
    return weeks


# --------------------------------------------------------------------------
# source 3 -- General Conference quotes
# --------------------------------------------------------------------------

# A full conference is a little under forty talks. Requiring most of them
# stops a half-posted conference from being chosen while it is still going up.
CONFERENCE_MIN_TALKS = 20

# Speaker photos are saved into the repository rather than hot-linked, so a
# page view still contacts nobody but the host serving the site. The card shows
# one at up to 240 CSS pixels wide, so 480 stays sharp on a 2x display.
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
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as err:
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


def is_quotable_paragraph(text: str) -> bool:
    if not 110 <= len(text) <= 330:
        return False
    if not text.endswith((".", "!", "?", '."', '!"', '?"')):
        return False
    # Skip paragraphs that only make sense next to the one before them, and
    # scene-setting narration that is not a teaching.
    if re.match(r"^(But|So|Then|Yet|However|That|This|These|Those|It was|"
                r"He |She |They |We were|I was|After |Later|Then,)\b", text):
        return False
    # "Tragically, the bullet ..." -- an adverb opener almost always continues
    # a story told in the paragraph before.
    if re.match(r"^[A-Z][a-z]+ly,", text):
        return False
    # Past-tense storytelling rather than counsel.
    if re.search(r"\b(I|we|he|she|they)\s+(\w+ed|was|were|had|sought|went|came|"
                 r"told|said|saw|felt|knew|gave|took|found|began|met|left|"
                 r"heard|spoke|wrote|sat|stood)\b", text[:120], re.I):
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

            # Take the talk proper, stopping before the endnotes -- those are
            # bibliography lines, not anything worth quoting.
            block = re.search(r'<div class="body-block">(.*?)(?:<footer class="notes">|\Z)',
                              body, re.S)
            paragraphs = re.findall(r'<p [^>]*id="(p[_A-Za-z0-9]+)"[^>]*>(.*?)</p>',
                                    block.group(1) if block else "", re.S)
            session = f"{'April' if month == 4 else 'October'} {year}"
            for pid, raw in paragraphs:
                text = clean(raw)
                if is_quotable_paragraph(text):
                    found.append((uri, {
                        "text": text,
                        "speaker": speaker,
                        "role": clean(role.group(1)) if role else "",
                        "talk": title,
                        "session": session,
                        "url": f"https://www.churchofjesuschrist.org/study{uri}"
                               f"?lang=eng&id={pid}#{pid}",
                    }))

        quoted = {uri: talks[uri] for uri, _ in found}
        print(f"General Conference {year}-{month:02d}: "
              f"fetching {len(quoted)} speaker photos ...")
        photos = fetch_portraits(quoted)
        for uri, quote in found:
            quote["image"] = photos.get(uri, "")
            pool.append(quote)

    print(f"General Conference: {len(pool)} quotable paragraphs")
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


def esc(value: str) -> str:
    return html.escape(value or "", quote=True)


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
    <blockquote class="scripture" id="bom-text">{esc(bom.get('text', ''))}</blockquote>
    <p class="ref"><a id="bom-link" href="{esc(bom.get('url', '#'))}" target="_blank" rel="noopener noreferrer"><cite id="bom-ref">{esc(bom.get('reference', ''))}</cite></a></p>
    <button type="button" class="share" id="share-bom" hidden>Share</button>
    {bom_share}
  </section>

  <section class="card" id="card-cfm"{cfm_hidden}>
    <h2 class="card__label">Come, Follow Me <span>Verse of the Day</span></h2>
    <p class="week">This week: <a id="cfm-week-link" href="{esc(cfm.get('weekUrl', '#'))}" target="_blank" rel="noopener noreferrer"><span id="cfm-week">{esc(cfm.get('week', ''))}</span></a></p>
    <blockquote class="scripture" id="cfm-text">{esc(cfm.get('text', ''))}</blockquote>
    <p class="ref"><a id="cfm-link" href="{esc(cfm.get('url', '#'))}" target="_blank" rel="noopener noreferrer"><cite id="cfm-ref">{esc(cfm.get('reference', ''))}</cite></a></p>
    <button type="button" class="share" id="share-cfm" hidden>Share</button>
    {cfm_share}
  </section>

  <section class="card" id="card-quote">
    <h2 class="card__label">General Conference <span>Quote of the Day</span></h2>
    <blockquote class="quote" id="quote-text">{esc(quote.get('text', ''))}</blockquote>
    <figure class="portrait" id="quote-portrait"{'' if photo else ' hidden'}>
      <img id="quote-photo"{photo_src} alt="{photo_alt}" width="{PORTRAIT_WIDTH}" height="{PORTRAIT_WIDTH * 9 // 16}" decoding="async">
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

    bom = spread(bom, seed=20260101, key=lambda v: v["reference"].rsplit(" ", 1)[0])
    quotes = spread(quotes, seed=20260102, key=lambda q: q["speaker"])

    days: dict[str, dict] = {}
    for offset in range(args.days):
        date = start + dt.timedelta(days=offset)
        # Index from a fixed epoch rather than from the start of this build, so
        # a date always resolves to the same pick and a rebuild part-way
        # through the day does not change the verse under the reader.
        index = (date - EPOCH).days
        entry = {
            "bom": bom[index % len(bom)],
            "quote": quotes[index % len(quotes)],
        }
        for week in weeks:
            if week["start"] <= date.isoformat() <= week["end"]:
                verses = week["verses"]
                entry["cfm"] = {
                    **verses[date.toordinal() % len(verses)],
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

    covered = sorted(d for d, entry in days.items() if "cfm" in entry)
    print(f"\nWrote {OUT.relative_to(ROOT)}")
    print(f"  {len(days)} days ({payload['first']} .. {payload['last']})")
    # The last covered day is when the Come, Follow Me card would go dark if no
    # further manual were ever published, so it is worth stating outright.
    print(f"  {len(covered)} days with a Come, Follow Me verse"
          + (f" ({covered[0]} .. {covered[-1]})" if covered else ""))
    print(f"  manuals: {', '.join(m for m, _ in manuals) or 'none'}")
    print(f"  {OUT.stat().st_size / 1024:.0f} KB")

    photos = sorted(SPEAKERS.glob("*.jpg")) if SPEAKERS.exists() else []
    print(f"  {len(photos)} speaker photos "
          f"({sum(p.stat().st_size for p in photos) / 1024:.0f} KB)"
          + (f", {dropped} pruned" if dropped else ""))

    date = render_site(payload, args.timezone, as_of)
    print(f"Wrote index.html for {date} ({args.timezone})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
