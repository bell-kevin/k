# Off-GitHub render pinger

A trigger for the deploy workflow that does not depend on GitHub's scheduler.

## Why this exists

`.github/workflows/deploy.yml` asks GitHub to re-render the page twice a day.
GitHub runs a scheduled workflow when it has capacity and is free to skip one
outright. On 2026-08-27 the 08:10 UTC schedule fired eleven hours late; on
2026-08-28 it did not fire at all.

Nobody with JavaScript noticed either time. `assets/app.js` reads
`data-built-for` off `<body>`, compares it to the reader's own today, and
re-renders from `data/daily.json` when they disagree — and the calendar runs
to 2028. The readers this site is built for got the previous day, twice, and
the only reason it was caught is that someone looked.

## What it does and does not cover

It covers a **dropped or delayed schedule**, which is the whole of what went
wrong. `workflow_dispatch` is a queued API call, not best-effort scheduling.

It does **not** cover GitHub Actions being unavailable. A dispatch queues
behind the same outage a cron would have. This is a second way to *ask*, not a
second place to *run*. Nothing hosted outside GitHub can render this page,
because the renderer and the calendar live here.

It asks only when the answer is wrong: the worker reads the live page first
and stays quiet unless the day on it is stale. A morning where GitHub behaved
produces no dispatch, no run and no deploy.

## Setup

Two of these need an account only you have. About ten minutes.

### 1. A token that may dispatch the workflow

Create a **fine-grained** personal access token at
<https://github.com/settings/personal-access-tokens/new>:

| Field             | Value                          |
| ----------------- | ------------------------------ |
| Repository access | Only select repositories → `bell-kevin/verse` |
| Repository permissions | **Actions: Read and write** |

Nothing else. `Actions: write` is the whole of what a dispatch needs — this
token cannot read your code, push, or touch another repository.

> **This is how the backup dies quietly.** A fine-grained token expires, and an
> expired one answers `401` where a working one answers `204`. Either set the
> expiry to *No expiration*, or put the expiry date in a calendar. A pinger
> nobody has checked in a year is not a backup.

### 2. Deploy the worker

Cloudflare Workers' free tier covers this: cron triggers are included and this
uses one request a day against a 100,000/day allowance.

```sh
cd tools/pinger
npx wrangler login
npx wrangler secret put GITHUB_TOKEN   # paste the token from step 1
npx wrangler deploy
```

### 3. Confirm it works

`wrangler deploy` prints the worker's URL. Opening it runs the same check the
cron runs, by hand:

```sh
curl https://verse-render-pinger.<your-subdomain>.workers.dev
```

On a good day, `200`:

```json
{ "ok": true, "today": "2026-08-28", "builtFor": "2026-08-28",
  "dispatched": false, "reason": "page is current" }
```

A bad token gives `503` and says so in `reason` — which is the point of the
endpoint. To watch the scheduled runs instead: `npx wrangler tail`.

To prove the dispatch path itself works rather than waiting for a bad morning,
temporarily set `TIMEZONE` in `wrangler.toml` to `Pacific/Kiritimati` and
redeploy: it is a day ahead, the page reads as stale, and you get a real
dispatch. Put it back afterwards.

## Timing

Three attempts, all landing on the same Denver day the page is built for:

| When (UTC) | Denver (MDT / MST) | Who asks    |
| ---------- | ------------------ | ----------- |
| 08:10      | 02:10 / 01:10      | GitHub cron |
| 14:40      | 08:40 / 07:40      | GitHub cron |
| 16:25      | 10:25 / 09:25      | this worker |

The worker runs last, on purpose: it is the one that goes when GitHub has
already had two chances and taken neither.

`TIMEZONE` in `wrangler.toml` must match `--timezone` in
`tools/build_daily.py` (`America/Denver`). If they drift apart, the worker
reads a correct page as stale every night between the two midnights and
dispatches a pointless render daily.

## If you would rather not run a worker

Any scheduler that can send an authenticated POST will do — [cron-job.org] is
free and needs no code:

* URL `https://api.github.com/repos/bell-kevin/verse/actions/workflows/deploy.yml/dispatches`
* Method `POST`, body `{"ref":"main"}`
* Headers: `Authorization: Bearer <token>`, `Accept: application/vnd.github+json`,
  `User-Agent: verse-render-pinger`, `Content-Type: application/json`

The trade is that it fires unconditionally, so you get a render and a deploy
every day whether or not one was needed. Harmless — `--render-only` writes the
same bytes and the commit step exits on `Nothing changed` — but it is a third
scheduled render rather than a thing that speaks up only when something broke,
and a daily green run is a poor place to notice a red one.

[cron-job.org]: https://cron-job.org
