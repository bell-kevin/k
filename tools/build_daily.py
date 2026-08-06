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

API = "https://www.churchofjesuschrist.org/study/api/v3/language-pages/type/content"
UA = "Mozilla/5.0 (compatible; no-login-daily-verse/1.0; static site builder)"

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
            if isinstance(err, urllib.error.HTTPError) and err.code == 404:
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

def recent_conferences(count: int = 6) -> list[tuple[int, int]]:
    """The last `count` conferences (April and October) already held."""
    today = dt.date.today()
    sessions: list[tuple[int, int]] = []
    year, month = today.year, 10 if today.month >= 10 else 4
    if today.month < 4:
        year, month = year - 1, 10
    while len(sessions) < count:
        sessions.append((year, month))
        year, month = (year, 4) if month == 10 else (year - 1, 10)
    return sessions


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


def build_quote_pool(count: int = 6) -> list[dict]:
    pool: list[dict] = []
    for year, month in recent_conferences(count):
        index = fetch(f"/general-conference/{year}/{month:02d}")
        if not index:
            continue
        talk_uris = sorted({
            "/" + u for u in re.findall(
                rf"/study/(general-conference/{year}/{month:02d}/[a-z0-9-]+)\?lang=eng",
                index["content"]["body"])
        })
        print(f"General Conference {year}-{month:02d}: fetching {len(talk_uris)} talks ...")
        talks = fetch_many(talk_uris)

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
                    pool.append({
                        "text": text,
                        "speaker": speaker,
                        "role": clean(role.group(1)) if role else "",
                        "talk": title,
                        "session": session,
                        "url": f"https://www.churchofjesuschrist.org/study{uri}"
                               f"?lang=eng&id={pid}#{pid}",
                    })
    print(f"General Conference: {len(pool)} quotable paragraphs")
    return pool


# --------------------------------------------------------------------------
# assembly
# --------------------------------------------------------------------------

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
    ap.add_argument("--manual", default="come-follow-me-for-home-and-church-old-testament-2026")
    ap.add_argument("--manual-year", type=int, default=2026)
    ap.add_argument("--conferences", type=int, default=6)
    args = ap.parse_args()

    start = (dt.date.fromisoformat(args.start) if args.start
             else dt.date.today() - dt.timedelta(days=30))

    bom = build_bom_pool()
    quotes = build_quote_pool(args.conferences)
    weeks = build_cfm_weeks(args.manual, args.manual_year)

    if not bom or not quotes:
        print("error: could not build the required pools", file=sys.stderr)
        return 1

    bom = spread(bom, seed=20260101, key=lambda v: v["reference"].rsplit(" ", 1)[0])
    quotes = spread(quotes, seed=20260102, key=lambda q: q["speaker"])

    days: dict[str, dict] = {}
    for offset in range(args.days):
        date = start + dt.timedelta(days=offset)
        entry = {
            "bom": bom[offset % len(bom)],
            "quote": quotes[offset % len(quotes)],
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

    OUT.parent.mkdir(parents=True, exist_ok=True)
    payload = {
        "generated": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "first": start.isoformat(),
        "last": (start + dt.timedelta(days=args.days - 1)).isoformat(),
        "cfmManual": args.manual,
        "days": days,
    }
    with open(OUT, "w", encoding="utf-8") as fh:
        json.dump(payload, fh, ensure_ascii=False, separators=(",", ":"))

    covered = sum(1 for d in days.values() if "cfm" in d)
    print(f"\nWrote {OUT.relative_to(ROOT)}")
    print(f"  {len(days)} days ({payload['first']} .. {payload['last']})")
    print(f"  {covered} days with a Come, Follow Me verse")
    print(f"  {OUT.stat().st_size / 1024:.0f} KB")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
