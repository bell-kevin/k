/* Verse & Quote of the Day
   Copyright (C) 2026  Kevin Bell
   Licensed under the GNU Affero General Public License v3 or later.

   Reads the prebuilt calendar in data/daily.json and shows today's entry.
   No network calls to anyone else; nothing is tracked, stored or sent. */

(function () {
  "use strict";

  /* Today in the reader's own timezone -- not UTC, so the page turns over at
     the reader's midnight rather than somewhere in the middle of their day. */
  function localToday() {
    var now = new Date();
    return [
      now.getFullYear(),
      String(now.getMonth() + 1).padStart(2, "0"),
      String(now.getDate()).padStart(2, "0")
    ].join("-");
  }

  function show(id) {
    var el = document.getElementById(id);
    if (el) el.hidden = false;
  }

  function setText(id, value) {
    var el = document.getElementById(id);
    if (el) el.textContent = value || "";
  }

  function setLink(id, href) {
    var el = document.getElementById(id);
    if (el && href) el.href = href;
  }

  function fail(message) {
    setText("error-detail", message);
    show("card-error");
  }

  /* If the calendar has run past its last prebuilt day, keep cycling through
     it rather than showing an empty page. The scheduled rebuild normally
     extends the calendar long before this matters. */
  function entryFor(data, iso) {
    if (data.days[iso]) return data.days[iso];

    var keys = Object.keys(data.days).sort();
    if (!keys.length) return null;

    var wanted = Date.parse(iso + "T00:00:00Z");
    var first = Date.parse(keys[0] + "T00:00:00Z");
    var day = 86400000;
    var offset = Math.round((wanted - first) / day);
    // Modulo that stays positive for dates before the calendar starts.
    var index = ((offset % keys.length) + keys.length) % keys.length;
    return data.days[keys[index]];
  }

  function renderDate(iso) {
    var el = document.getElementById("today-date");
    if (!el) return;
    el.setAttribute("datetime", iso);
    var parts = iso.split("-");
    var local = new Date(+parts[0], +parts[1] - 1, +parts[2]);
    try {
      el.textContent = local.toLocaleDateString(undefined, {
        weekday: "long", year: "numeric", month: "long", day: "numeric"
      });
    } catch (e) {
      el.textContent = iso;
    }
  }

  function render(data, entry) {
    if (entry.bom) {
      setText("bom-text", entry.bom.text);
      setText("bom-ref", entry.bom.reference);
      setLink("bom-link", entry.bom.url);
      show("card-bom");
    }

    /* The Come, Follow Me card only appears for dates the published manual
       actually covers, so it stays absent rather than wrong. */
    if (entry.cfm) {
      setText("cfm-text", entry.cfm.text);
      setText("cfm-ref", entry.cfm.reference);
      setLink("cfm-link", entry.cfm.url);
      setText("cfm-week", entry.cfm.week);
      setLink("cfm-week-link", entry.cfm.weekUrl);
      show("card-cfm");
    }

    if (entry.quote) {
      setText("quote-text", entry.quote.text);
      setText("quote-speaker", entry.quote.speaker);
      setText("quote-talk", entry.quote.talk);
      setText("quote-session", entry.quote.session);
      setLink("quote-link", entry.quote.url);
      show("card-quote");
    }

    if (data.generated) {
      setText("generated", "Readings last refreshed " +
              data.generated.slice(0, 10) + ".");
    }
  }

  fetch("data/daily.json", { cache: "no-cache" })
    .then(function (response) {
      if (!response.ok) throw new Error("HTTP " + response.status);
      return response.json();
    })
    .then(function (data) {
      var iso = localToday();
      var entry = entryFor(data, iso);
      renderDate(iso);
      if (!entry) {
        fail("The readings calendar is empty. It is rebuilt automatically; " +
             "please try again later.");
        return;
      }
      render(data, entry);
    })
    .catch(function (err) {
      renderDate(localToday());
      fail("Could not read the readings calendar (" + err.message + "). " +
           "If you opened this file directly from disk, your browser may be " +
           "blocking local file requests — use the published web address " +
           "instead.");
    });
})();
