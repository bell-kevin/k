/* Verse & Quote of the Day
   Copyright (C) 2026  Kevin Bell
   Licensed under the GNU Affero General Public License v3 or later.

   Enhancement only. Today's readings are already in the HTML, baked in when
   the page was built, so the site is complete and correct with scripts
   switched off. This file does three things:

     1. offers a theme toggle, for a reader who wants the other theme rather
        than the one their system asks for;
     2. hands a card to the reader's own share sheet, or to their clipboard;
     3. swaps in the right day from the prebuilt calendar for a reader whose
        own date has moved past the date the page was built for -- someone
        ahead of the build timezone, or looking at a copy served from cache.

   No network calls to anyone else; nothing is tracked or sent. The only thing
   stored is the theme choice, in this browser, and only once one is made. */

(function () {
  "use strict";

  /* ---------- theme ----------

     The system setting decides on its own until the reader says otherwise,
     so the cycle runs Auto -> Light -> Dark -> Auto: choosing a theme is
     always reversible, back to simply following the system again. */

  var MODES = ["auto", "light", "dark"];
  var LABELS = { auto: "Auto", light: "Light", dark: "Dark" };
  var HINTS = {
    auto: "Following your system setting. Click for light.",
    light: "Light. Click for dark.",
    dark: "Dark. Click to follow your system setting again."
  };

  function storedMode() {
    try {
      var saved = localStorage.getItem("theme");
      return saved === "light" || saved === "dark" ? saved : "auto";
    } catch (e) {
      return "auto";
    }
  }

  function applyMode(mode, button) {
    var root = document.documentElement;
    // Auto is the absence of a choice, so it clears both the attribute the
    // stylesheet reads and the stored value the next page load reads.
    if (mode === "auto") root.removeAttribute("data-theme");
    else root.setAttribute("data-theme", mode);

    try {
      if (mode === "auto") localStorage.removeItem("theme");
      else localStorage.setItem("theme", mode);
    } catch (e) { /* storage blocked -- the choice just won't outlast the page */ }

    document.getElementById("theme-mode").textContent = LABELS[mode];
    button.title = HINTS[mode];
  }

  var toggle = document.getElementById("theme-toggle");
  if (toggle) {
    applyMode(storedMode(), toggle);
    toggle.hidden = false;
    toggle.addEventListener("click", function () {
      applyMode(MODES[(MODES.indexOf(storedMode()) + 1) % MODES.length], toggle);
    });
  }

  /* ---------- sharing ----------

     A card can be passed on as it stands: the reading, whose words they are,
     and the link back to the official source. Handing that to the reader's
     own share sheet is the whole of it -- the sheet is the operating system's,
     the apps in it are theirs, and nothing about what was shared is sent
     anywhere by this page.

     Each card is read at the moment its button is clicked rather than up
     front, so a card the day-swap below has since rewritten shares the
     reading the reader is actually looking at.

     The markup carries its own share block for a reader without scripts --
     the passage in a field, ready to select and copy. Where this runs, the
     button below replaces it, so the block is put away rather than left
     standing as a second copy of the same offer. */

  var SHAREABLE = [
    { button: "share-bom",   text: "bom-text",   credit: "bom-ref",       link: "bom-link",   fallback: "share-fallback-bom" },
    { button: "share-cfm",   text: "cfm-text",   credit: "cfm-ref",       link: "cfm-link",   fallback: "share-fallback-cfm" },
    { button: "share-quote", text: "quote-text", credit: "quote-speaker", link: "quote-link", fallback: "share-fallback-quote" }
  ];

  function textOf(id) {
    var el = document.getElementById(id);
    // textContent, so the decorative quotation mark and the separators the
    // stylesheet draws around the speaker stay out of what gets shared.
    return el ? el.textContent.trim() : "";
  }

  /* Reading, attribution, link -- the shape a passage arrives in when it is
     shared from the Church's own app, so one pasted from here sits in a thread
     beside one from there without looking out of place. */
  function passage(spec) {
    var link = document.getElementById(spec.link);
    return [textOf(spec.text), textOf(spec.credit), link ? link.href : ""]
      .filter(Boolean).join("\n\n");
  }

  /* The way back for a browser with no share sheet, which mostly means a
     desktop one. The clipboard API needs a secure context, so a page opened
     over plain http or straight off disk falls through to a scratch textarea
     -- the older way, still the only one that works there. */
  function copy(payload) {
    if (navigator.clipboard && navigator.clipboard.writeText) {
      return navigator.clipboard.writeText(payload);
    }
    return new Promise(function (resolve, reject) {
      var field = document.createElement("textarea");
      field.value = payload;
      field.setAttribute("readonly", "");
      field.style.position = "fixed";
      field.style.top = "0";
      field.style.opacity = "0";
      document.body.appendChild(field);
      field.select();
      var copied = false;
      try {
        copied = document.execCommand("copy");
      } catch (e) {
        copied = false;
      }
      document.body.removeChild(field);
      if (copied) resolve();
      else reject(new Error("copy unavailable"));
    });
  }

  /* Say what happened on the button itself, then put it back. The button has
     focus at this point, having just been clicked, so the changed label is
     read out as well as seen. */
  function flash(button, message) {
    button.textContent = message;
    window.clearTimeout(button.resetLabel);
    button.resetLabel = window.setTimeout(function () {
      button.textContent = "Share";
    }, 2000);
  }

  SHAREABLE.forEach(function (spec) {
    var button = document.getElementById(spec.button);
    if (!button) return;
    button.hidden = false;

    // Only now that the button is up: if this line is never reached the
    // markup's own share block stays where it is, still working.
    var fallback = document.getElementById(spec.fallback);
    if (fallback) fallback.hidden = true;

    button.addEventListener("click", function () {
      var payload = passage(spec);
      if (!payload) return;
      if (navigator.share) {
        // Backing out of the share sheet rejects the promise. That is a
        // reader changing their mind, not a failure to report to them.
        navigator.share({ title: document.title, text: payload })
                 .catch(function () {});
        return;
      }
      copy(payload).then(
        function () { flash(button, "Copied"); },
        function () { flash(button, "Couldn't copy"); }
      );
    });
  });

  /* ---------- the day ---------- */

  var builtFor = document.body.getAttribute("data-built-for");

  /* Today in the reader's own timezone. */
  function localToday() {
    var now = new Date();
    return [
      now.getFullYear(),
      String(now.getMonth() + 1).padStart(2, "0"),
      String(now.getDate()).padStart(2, "0")
    ].join("-");
  }

  var today = localToday();

  // The common case: the page was built for the reader's today, so the markup
  // already says the right thing and there is nothing to fetch.
  if (!builtFor || builtFor === today) return;

  function setText(id, value) {
    var el = document.getElementById(id);
    if (el) el.textContent = value || "";
  }

  function setLink(id, href) {
    var el = document.getElementById(id);
    if (el && href) el.href = href;
  }

  /* A scripture mastery passage is quoted whole and can run to several verses,
     so a long reading is set a step smaller -- the same threshold the builder
     uses when it bakes the markup, so a swapped-in day looks like a built one. */
  var LONG_READING = 420;

  function setReading(id, text) {
    var el = document.getElementById(id);
    if (!el) return;
    el.textContent = text || "";
    el.className = (text || "").length > LONG_READING
      ? "scripture scripture--long"
      : "scripture";
  }

  function setHidden(id, hidden) {
    var el = document.getElementById(id);
    if (el) el.hidden = hidden;
  }

  /* The speaker's photo lives in this repository, so this is a local swap --
     still no request to anyone else. A talk without one hides the figure
     rather than showing a broken image. */
  function setPhoto(quote) {
    var img = document.getElementById("quote-photo");
    if (!img) return;
    if (quote.image) {
      img.src = quote.image;
      img.alt = quote.speaker + " speaking at general conference";
    } else {
      img.removeAttribute("src");
      img.alt = "";
    }
    setHidden("quote-portrait", !quote.image);
  }

  /* If the reader has run past the last prebuilt day, cycle through the
     calendar rather than showing nothing. The scheduled rebuild normally
     extends it long before this matters. */
  function entryFor(data, iso) {
    if (data.days[iso]) return data.days[iso];

    var keys = Object.keys(data.days).sort();
    if (!keys.length) return null;

    var day = 86400000;
    var offset = Math.round(
      (Date.parse(iso + "T00:00:00Z") - Date.parse(keys[0] + "T00:00:00Z")) / day
    );
    // Modulo that stays positive for dates before the calendar starts.
    return data.days[keys[((offset % keys.length) + keys.length) % keys.length]];
  }

  function renderDate(iso) {
    var el = document.getElementById("today-date");
    if (!el) return;
    el.setAttribute("datetime", iso);
    var parts = iso.split("-");
    try {
      el.textContent = new Date(+parts[0], +parts[1] - 1, +parts[2])
        .toLocaleDateString(undefined, {
          weekday: "long", year: "numeric", month: "long", day: "numeric"
        });
    } catch (e) {
      el.textContent = iso;
    }
  }

  function render(entry) {
    if (entry.bom) {
      setReading("bom-text", entry.bom.text);
      setText("bom-ref", entry.bom.reference);
      setLink("bom-link", entry.bom.url);
    }

    // The Come, Follow Me card only applies to dates the published manual
    // covers, so it is hidden rather than shown empty.
    if (entry.cfm) {
      setReading("cfm-text", entry.cfm.text);
      setText("cfm-ref", entry.cfm.reference);
      setLink("cfm-link", entry.cfm.url);
      setText("cfm-week", entry.cfm.week);
      setLink("cfm-week-link", entry.cfm.weekUrl);
      setHidden("card-cfm", false);
    } else {
      setHidden("card-cfm", true);
    }

    if (entry.quote) {
      setText("quote-text", entry.quote.text);
      setText("quote-speaker", entry.quote.speaker);
      setText("quote-talk", entry.quote.talk);
      setText("quote-session", entry.quote.session);
      setLink("quote-link", entry.quote.url);
      setPhoto(entry.quote);
    }
  }

  fetch("data/daily.json", { cache: "no-cache" })
    .then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(function (data) {
      var entry = entryFor(data, today);
      if (!entry) return;
      render(entry);
      renderDate(today);
    })
    .catch(function () {
      /* Leave the baked-in readings in place -- they are real readings, and
         the date shown alongside them is the date they belong to, so the page
         stays truthful even when this fails. */
      setText("error-detail",
              "These are the readings for " + builtFor +
              ". Today's could not be loaded, so the page is showing the day " +
              "it was last built for.");
      setHidden("card-error", false);
    });
})();
