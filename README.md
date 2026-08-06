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
| Come, Follow Me verse | The current year's weekly manual, using the verses each week actually cites |
| Conference quote | The last six General Conferences |

It filters each pool for passages that read well on their own — dropping
genealogy, travelogue, mid-story narration and endnote bibliographies — then
writes a prebuilt calendar of daily picks to `data/daily.json`.

The website is static HTML and CSS plus about 100 lines of JavaScript whose only
job is to look up today's date in that file. **The page never contacts
`churchofjesuschrist.org` at runtime.** Nothing is tracked, stored, or sent
anywhere. If the Church's site changes shape, a page view is unaffected; only a
rebuild would notice.

A scheduled GitHub Action re-runs the builder monthly to extend the calendar and
pick up newly published conferences and manuals.

## Running it yourself

```sh
python tools/build_daily.py            # rebuild data/daily.json (~350 requests, cached)
python -m http.server 8000             # then open http://localhost:8000
```

Opening `index.html` straight off disk will not work: browsers block the
`fetch` of `data/daily.json` from `file://` URLs. Use the local server above.

Useful flags:

```sh
python tools/build_daily.py --days 1095            # build three years ahead
python tools/build_daily.py --start 2027-01-01     # start from a given date
python tools/build_daily.py \
    --manual come-follow-me-for-home-and-church-new-testament-2027 \
    --manual-year 2027                             # next year's manual
```

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

<p align="right"><a href="#readme-top">back to top</a></p>
