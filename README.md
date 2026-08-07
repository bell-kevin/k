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
| Conference quote | The most recent General Conference whose talks are published, with the speaker's photo from that talk |

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

### The speaker's photo

Every conference talk carries a photo of that speaker at the pulpit — the
picture the conference index uses as its thumbnail — and the quote card shows
it beneath the quote.

Those photos are **downloaded during the build and committed to
`assets/speakers/`**, not hot-linked. Hot-linking would have meant every page
view fetching an image from `churchofjesuschrist.org`, which is exactly the
runtime dependency the rest of the site avoids; a local copy keeps a page view
contacting nobody but the host serving the site, and keeps working offline and
from a `file://` URL.

The image URLs are IIIF, so the builder asks for the width it actually serves
(480px, sharp at the card's 240px on a 2x display) rather than taking whatever
size the page happened to link. That is about 35 files and 800 KB — one photo
per talk that contributed a quote, fetched once and skipped on later builds
since a talk's photo never changes. When a new conference takes over the pool,
photos no longer reachable from the calendar are pruned in the same run.

A talk whose photo cannot be fetched simply gets no photo: the figure is
hidden, and the rest of the card is unchanged.

**The page never contacts `churchofjesuschrist.org` at runtime.** Nothing is
tracked or sent anywhere, and the only thing stored is a theme choice, in your
own browser, and only if you make one. If the Church's site changes shape, a
page view is unaffected; only a rebuild would notice.

## Light and dark

The page follows your system's light or dark setting on its own, as it always
has. A **Theme** button in the top corner is there for when you want the other
one anyway — it cycles Auto → Light → Dark → Auto, so an override is always
reversible back to simply following the system again.

A choice is remembered in `localStorage` under `theme` and applied by a short
inline script in `<head>`, before the page is first painted, so overriding a
dark system to light never flashes dark on the way in. Nothing else is stored,
and the entry is removed outright when you cycle back to Auto.

The button is hidden in the markup and revealed by the script, so with
JavaScript switched off you are not shown a control that cannot do anything —
the page just follows the system setting, exactly as before.

## Sharing a card

Each card has a **Share** button under it, which hands the reading to your own
share sheet — the same gesture the Gospel Library app uses, and the text lands
in the same shape, so one passed on from here sits in a thread beside one from
there without looking out of place:

```
On this glorious Easter Sunday, I have chosen to speak first about the
Resurrection, which is a pillar of our faith.

President Dallin H. Oaks

https://www.churchofjesuschrist.org/study/general-conference/2026/04/49oaks?lang=eng&id=p_mZMDI#p_mZMDI
```

The link is the official source on `churchofjesuschrist.org`, pointing at the
exact verse or paragraph — never at this site — so whoever receives it can read
it where it was published.

The sheet is your operating system's and the apps in it are yours; **this page
sends nothing anywhere and is never told what you shared, or with whom.** On a
desktop browser, which usually has no share sheet, the button copies the same
text to your clipboard instead and says so.

Each card is read at the moment its button is clicked, so if the script has
moved the page on to a new day (below), you share the reading actually in front
of you. Like the theme button, the share buttons are hidden in the markup and
revealed by the script — with JavaScript off there is no share sheet to reach,
so no button is shown.

## It works with JavaScript switched off

`index.html` is generated from `tools/template.html` with the day's readings
**already written into the markup**, so the page is complete before any script
runs. With scripts disabled you get the full page — all three cards, every link.

The script is enhancement only. Apart from wiring up the theme and share
buttons, it does nothing at all unless the reader's own date has moved past the
date the page was built for. In that one case it swaps in the right day from
`data/daily.json`. If
that fetch fails, the baked-in readings stay put and the date shown next to them
is the date they belong to, so the page never claims a reading is today's when
it isn't.

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

Responses are cached under `.cache/`; delete it to force a clean fetch. Speaker
photos are kept in `assets/speakers/` and are part of the site rather than the
cache — delete one and the next full build downloads it again.

## Licensing, and what the licence does not cover

The **code, styling and build tooling in this repository** are free software
under the [GNU Affero General Public License v3](LICENSE) or later.

The **scripture and General Conference text is not mine to license**, and
neither are the speaker photographs in `assets/speakers/`. They are published by
The Church of Jesus Christ of Latter-day Saints. The English text of the
standard works is in the public domain in the United States; General Conference
addresses and the conference photographs are © Intellectual Reserve, Inc., and
are reproduced here in short excerpts for personal, non-commercial study, with
every quotation linking back to the official source. The AGPL applies to this
project's own work only, and grants you no rights in the Church's content —
including the photographs, which are redistributed by this repository and are
the part of it most clearly not covered by that licence.

This site is not affiliated with, endorsed by, or produced by The Church of
Jesus Christ of Latter-day Saints. If you want to reuse Church content beyond
personal study, see <https://permissions.churchofjesuschrist.org/>.

https://bell-kevin.github.io/k/

<p align="left"><a href="#readme-top">back to top</a></p>
