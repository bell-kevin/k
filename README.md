<a name="readme-top"></a>

# Verse &amp; Quote of the Day

https://bell-kevin.github.io/k/

A plain website that shows, every day:

- a **Book of Mormon verse of the day**,
- a **Come, Follow Me verse of the day** drawn from the current week's reading, and
- a **General Conference quote of the day**.

No app, no account, no sign-in. Open the page and read it.

## Why this exists

The Church publishes a Verse of the Day and a Quote of the Day, but they are
only reachable through the Gospel Library and Book of Mormon mobile apps, or on
`churchofjesuschrist.org` after signing in. There is no public feed: the
`my-home` page serves a "Sign in to access personalized content" prompt to
anonymous visitors, and its data route redirects to the login flow.

This project does **not** work around that. It does not log in, store
credentials, or republish anything that sits behind the sign-in wall. Instead it
builds its own daily readings from the parts of `churchofjesuschrist.org` that
anyone can already read without an account, and serves them as a static page.

The picks are therefore *not* the Church's official daily selections. The
Come, Follow Me verse does follow the same weekly curriculum the Gospel Library
verse is drawn from, so it stays in step with what wards are studying.

## How it works

`tools/build_daily.py` reads three public sources through the study API:

| Card | Source |
| --- | --- |
| Book of Mormon verse | All 239 Book of Mormon chapters |
| Come, Follow Me verse | The weekly manuals covering the calendar, using the verses each week actually cites |
| Conference quote | The most recent General Conference whose talks are published |

It filters each pool for passages that read well on their own — dropping
genealogy, travelogue, mid-story narration and endnote bibliographies — then
writes a prebuilt calendar of daily picks to `data/daily.json`.

Each day's pick is indexed from a fixed epoch rather than from whenever the
calendar was last built, so a given date always resolves to the same verse and a
rebuild part-way through the day does not change it under the reader.

### Following the Come, Follow Me curriculum automatically

Come, Follow Me rotates through the four standard works on a fixed cycle — Old
Testament, New Testament, Book of Mormon, Doctrine and Covenants — so a year's
manual is *derivable* rather than something to look up:

| 2026 | 2027 | 2028 | 2029 | 2030 |
| --- | --- | --- | --- | --- |
| Old Testament | New Testament | Book of Mormon | Doctrine and Covenants | Old Testament |

The builder derives each year's slug from that cycle and then **probes for it**,
the same way it handles conference: the cycle says which manual a year *should*
have, and only the site can say whether it is readable yet. An unpublished year
answers 404; one that is staged but still embargoed answers 401. Either way it is
left out and retried on the next refetch, so a new manual joins the calendar
within days of going public.

Because manuals tile contiguously — the 2026 manual ends December 27 and the
2027 manual's opening week starts December 28 — the years merge with no gap at
the January changeover. The builder covers two years by default (`--cfm-years`),
so next year's manual is already in the calendar long before it is needed.

### Following General Conference automatically

Conference is held early in April and early in October, and the talks are posted
over the following days. Two different things therefore decide which conference
to quote, and only one of them is a date:

- today's date says which session is the newest that *could* exist;
- only the site can say whether its text is up **yet**.

So the builder walks candidate sessions newest-first and takes the first one
that actually returns a full set of talks — treating a session as unavailable
while it 404s or is still going up, rather than assuming a fixed publication
lag. Between conference weekend and the talks appearing, it simply keeps quoting
the previous conference; the changeover then happens on its own within a few
days, with no date to keep in step by hand.

The refetch runs Mondays and Thursdays, which bounds how long after publication
a new conference takes to show up.

**The page never contacts `churchofjesuschrist.org` at runtime.** Nothing is
tracked, stored, or sent anywhere. If the Church's site changes shape, a page
view is unaffected; only a rebuild would notice.

## It works with JavaScript switched off

`index.html` is generated from `tools/template.html` with the day's readings
**already written into the markup**, so the page is complete before any script
runs. With scripts disabled you get the full page — all three cards, every link.

The script is enhancement only, and does nothing at all unless the reader's own
date has moved past the date the page was built for. In that one case it swaps
in the right day from `data/daily.json`. If that fetch fails, the baked-in
readings stay put and the date shown next to them is the date they belong to, so
the page never claims a reading is today's when it isn't.

Two scheduled GitHub Actions keep it current:

- **daily**, just after midnight in the build timezone — re-renders the page for
  the new day from the calendar already in the repository, fetching nothing;
- **Mondays and Thursdays** — refetches to extend the calendar and pick up a
  newly published conference or manual.

Because the daily job is what moves a no-JavaScript page on to the next day, the
site depends on it running. The calendar is built two years ahead, so a missed
run costs you the right day, never the whole site.

## Running it yourself

```sh
python tools/build_daily.py              # refetch, rebuild the calendar, render index.html
python tools/build_daily.py --render-only  # just re-render today's page, no network
python -m http.server 8000               # then open http://localhost:8000
```

`index.html` is generated — **edit `tools/template.html`, not `index.html`.**

Opening the file straight off disk works for reading, since the readings are in
the markup; only the script's `fetch` is blocked on `file://` URLs, and it has
nothing to do when the page is already current.

Useful flags:

```sh
python tools/build_daily.py --days 1095              # build three years ahead
python tools/build_daily.py --start 2027-01-01       # start the calendar at a date
python tools/build_daily.py --conferences 4          # quote from the last four conferences
python tools/build_daily.py --timezone Europe/London # whose "today" the page is built for
python tools/build_daily.py --render-only --date 2026-12-25   # render a specific day
python tools/build_daily.py --cfm-years 3            # build a third year of manuals
python tools/build_daily.py \
    --manual come-follow-me-for-home-and-church-new-testament-2027 \
    --manual-year 2027                               # pin one manual, skipping the cycle
```

`--manual` is an override for testing; leave it alone and the four-year cycle
picks the manuals on its own.

Quoting only the most recent conference gives a pool of roughly 250 passages, so
over a two-year calendar a quote comes round again about every eight months.
Raise `--conferences` if you would rather trade freshness for variety.

`--timezone` and the daily cron in `.github/workflows/deploy.yml` need to agree;
change them together.

Responses are cached under `.cache/`; delete it to force a clean fetch.

## Licensing, and what the licence does not cover

The **code, styling and build tooling in this repository** are free software
under the [GNU Affero General Public License v3](LICENSE) or later.

The **scripture and General Conference text is not mine to license.** It is
published by The Church of Jesus Christ of Latter-day Saints. The English text
of the standard works is in the public domain in the United States; General
Conference addresses are © Intellectual Reserve, Inc., and are reproduced here
in short excerpts for personal, non-commercial study, with every quotation
linking back to the official source. The AGPL applies to this project's own
work only, and grants you no rights in the Church's content.

This site is not affiliated with, endorsed by, or produced by The Church of
Jesus Christ of Latter-day Saints. If you want to reuse Church content beyond
personal study, see <https://permissions.churchofjesuschrist.org/>.

https://bell-kevin.github.io/k/

<p align="left"><a href="#readme-top">back to top</a></p>
