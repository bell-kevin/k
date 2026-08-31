// A trigger for the deploy workflow that does not live on GitHub.
//
// The workflow already asks GitHub to render the page three times a day.
// GitHub runs a scheduled workflow when it has capacity and is free to skip
// one outright, and on 2026-08-27, 2026-08-28 and 2026-08-31 it did: eleven
// hours late, then not at all, then not at all again -- the last of those
// taking every scheduled run of the day with it. Readers with JavaScript
// never saw any of it, because assets/app.js re-renders from the calendar
// whenever data-built-for disagrees with their own today. The readers this
// site is for -- no app, no account, no JavaScript -- were served the
// previous day all three times.
//
// This runs on Cloudflare's scheduler instead, and it dispatches the same
// workflow. That covers a dropped or delayed schedule, which is the whole of
// what went wrong. It does not cover GitHub Actions being down: a dispatch
// queues behind the same outage a cron would have. It is a second way to ask,
// not a second place to run.
//
// It asks only when the answer is wrong. Rendering an already-current page
// costs a deploy and writes identical bytes, so the worker reads the live
// page first and stays quiet unless the day on it is stale. A morning where
// GitHub behaved leaves no trace here at all.

const DISPATCH_TIMEOUT_MS = 10_000;

// The rendered page carries the day it was built for on <body>. This is the
// same attribute assets/app.js reads to decide whether to re-render, so the
// worker and the browser are answering one question from one source.
const BUILT_FOR = /<body[^>]*\sdata-built-for="(\d{4}-\d{2}-\d{2})"/;

// en-CA formats as YYYY-MM-DD, which is the form the page uses. The timezone
// has to match tools/build_daily.py --timezone, or the worker will read a
// correct page as stale every night between the two midnights.
function todayIn(timeZone) {
  return new Intl.DateTimeFormat("en-CA", {
    timeZone,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
  }).format(new Date());
}

async function builtForOf(siteUrl) {
  // Pages sits behind a CDN and the whole point is to see what a reader is
  // being served right now, not what was published.
  const res = await fetch(siteUrl, {
    headers: { "user-agent": "verse-render-pinger" },
    cf: { cacheTtl: 0, cacheEverything: false },
  });
  if (!res.ok) throw new Error(`site returned ${res.status}`);
  const match = BUILT_FOR.exec(await res.text());
  if (!match) throw new Error("no data-built-for on the served page");
  return match[1];
}

async function dispatch(env) {
  const url =
    `https://api.github.com/repos/${env.REPO}` +
    `/actions/workflows/${env.WORKFLOW}/dispatches`;
  const res = await fetch(url, {
    method: "POST",
    headers: {
      authorization: `Bearer ${env.GITHUB_TOKEN}`,
      accept: "application/vnd.github+json",
      "x-github-api-version": "2022-11-28",
      // GitHub rejects an API request that does not identify itself.
      "user-agent": "verse-render-pinger",
      "content-type": "application/json",
    },
    body: JSON.stringify({ ref: env.BRANCH }),
    signal: AbortSignal.timeout(DISPATCH_TIMEOUT_MS),
  });
  // A dispatch answers 204 and says nothing else. Anything with a body is a
  // refusal worth reading -- an expired token answers 401 here, and that is
  // the way this stops working silently.
  if (res.status !== 204) {
    throw new Error(`dispatch returned ${res.status}: ${await res.text()}`);
  }
}

// Returns what it decided so both the cron and the manual GET can report it.
async function check(env) {
  const today = todayIn(env.TIMEZONE);
  let builtFor;
  try {
    builtFor = await builtForOf(env.SITE_URL);
  } catch (err) {
    // The site being unreachable is not something a render fixes, and
    // dispatching blind would hide it. Say so and leave it alone.
    return { ok: false, today, reason: `could not read the site: ${err.message}` };
  }

  if (builtFor === today) {
    return { ok: true, today, builtFor, dispatched: false, reason: "page is current" };
  }

  try {
    await dispatch(env);
  } catch (err) {
    return { ok: false, today, builtFor, dispatched: false, reason: err.message };
  }
  return {
    ok: true,
    today,
    builtFor,
    dispatched: true,
    reason: `page was built for ${builtFor}, asked for a render`,
  };
}

export default {
  async scheduled(event, env, ctx) {
    ctx.waitUntil(
      check(env).then((r) => {
        // wrangler tail shows these; a stale morning is one line.
        console.log(JSON.stringify({ at: new Date().toISOString(), ...r }));
      }),
    );
  },

  // Visiting the worker runs the same check by hand, which is how you confirm
  // the token works without waiting for a morning that goes wrong.
  async fetch(request, env) {
    const result = await check(env);
    return new Response(JSON.stringify(result, null, 2) + "\n", {
      status: result.ok ? 200 : 503,
      headers: { "content-type": "application/json; charset=utf-8" },
    });
  },
};
