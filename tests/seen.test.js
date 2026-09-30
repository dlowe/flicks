// Tests for the page's "new to you" / leak logic — the densest, least
// eyeball-able client code. See harness.js for how the page is run.
//
//   node tests/seen.test.js   (or ./test.sh)

const {
  run, row, dayPlus, fixtures, showingId, allIds, test, eq, runTests,
} = require("./harness");

function countLeaks(o) { return (o.cal._h.match(/is-leak/g) || []).length; }

const R = fixtures();
const ALL = allIds(R);                       // every showing id in the fixture
const seenAll = JSON.stringify(ALL);

test("cold start (empty storage): baselines everything, flags nothing", () => {
  const o = run(R, {});
  eq(o.newPills, 0, "new pills");
  eq(o.leaks, 0, "leaks");
  eq(o.seen.length, ALL.length, "seen size");
});

test("a few unseen showings flag as New (below the re-baseline threshold)", () => {
  const seen = ALL.filter((id) => id !== ALL[0]);          // drop 1 of 5
  const o = run(R, { "flicks.seen": JSON.stringify(seen) });
  eq(o.newPills, 1, "new pills");
  eq(o.leaks, 0, "leaks");
});

// A bigger fixture for the flood path (which needs an *absolute* flood, ≥30 new).
function manyFilms(n) {
  const rows = [];
  for (let i = 0; i < n; i++) rows.push(row("film-" + i, "Film " + i, "Theater", dayPlus(1 + (i % 20)), ["19:00"]));
  return rows;
}

test("a genuine flood (≥30 new and >50%) re-baselines silently instead of flooding", () => {
  const rows = manyFilms(40);
  const ids = allIds(rows);
  const o = run(rows, { "flicks.seen": JSON.stringify(ids.slice(0, 4)) }); // 36 of 40 new
  eq(o.newPills, 0, "no wall of New (re-baselined)");
  eq(o.seen.length, ids.length, "everything baselined");
});

test("a handful of new in-filter showings does NOT flood — shows New (absolute floor)", () => {
  const rows = manyFilms(40);
  const ids = allIds(rows);
  const o = run(rows, { "flicks.seen": JSON.stringify(ids.slice(0, 35)) }); // only 5 new
  eq(o.newPills, 5, "5 New pills, no re-baseline");
});

test("a flood does NOT consume a hidden film's pending leak", () => {
  const visible = manyFilms(40);
  const rows = visible.concat([row("gem", "Hidden Gem", "Theater", dayPlus(2), ["20:00"])]);
  const ids = allIds(visible);                              // in-filter ids only
  const o = run(rows, {
    "flicks.seen": JSON.stringify(ids.slice(0, 4)),         // 36 in-filter new -> flood
    "flicks.hidden": JSON.stringify(["gem"]),               // gem's new showing NOT in seen
  });
  eq(o.newPills, 0, "flood suppressed in-filter New");
  eq(o.leaks, 1, "the hidden gem still leaks despite the flood (baseline never touched its id)");
});

test("seen ids for aged-out showings are pruned", () => {
  const seen = ALL.concat(["gone|Nowhere|2099-01-01T00:00:00-07:00"]);
  const o = run(R, { "flicks.seen": JSON.stringify(seen) });
  eq(o.seen.includes("gone|Nowhere|2099-01-01T00:00:00-07:00"), false, "stale pruned");
});

test("a new showing of a HIDDEN film leaks through, faded, with a +", () => {
  const seen = ALL.filter((id) => id !== showingId(R[0], 0)); // film-a's first showing unseen
  const o = run(R, { "flicks.seen": JSON.stringify(seen), "flicks.hidden": JSON.stringify(["film-a"]) });
  eq(o.leaks, 1, "leak rows");
  eq(o.has(/data-unhide="film-a"/), true, "+ (restore) button for film-a");
  eq(o.newPills, 0, "no green New pill on a leaked (hidden) row");
});

test("leaked (still-hidden) films are excluded from the .ics export", () => {
  const seen = ALL.filter((id) => id !== showingId(R[0], 0));
  const o = run(R, { "flicks.seen": JSON.stringify(seen), "flicks.hidden": JSON.stringify(["film-a"]) });
  // Visible non-hidden showings: film-b (1) + film-c (2) = 3; film-a's leak is omitted.
  eq(o.icsCount && o.icsCount[0], "3", "ics showing count");
});

test("same unseen showing, NOT hidden, is a normal New (not a leak)", () => {
  const seen = ALL.filter((id) => id !== showingId(R[0], 0));
  const o = run(R, { "flicks.seen": JSON.stringify(seen) });
  eq(o.newPills, 1, "new pills");
  eq(o.leaks, 0, "leaks");
});

test("cold start with a film already hidden does not leak it (baseline covers it)", () => {
  const o = run(R, { "flicks.hidden": JSON.stringify(["film-a"]) });
  eq(o.leaks, 0, "leaks");
});

test("by-film: New pill floats down to the new line when only some showings are new", () => {
  const seen = ALL.filter((id) => id !== showingId(R[0], 0)); // only film-a's first showing unseen
  const o = run(R, { "flicks.seen": JSON.stringify(seen), "flicks.view": "film" });
  eq(o.newPills, 1, "one New pill total");
  eq((o.html.match(/class="line is-new/g) || []).length, 1, "pill on a line");
  eq(/class="film[^"]*is-new/.test(o.html), false, "not on the card");
});

test("by-film: New pill stays on the card when every showing is new", () => {
  const filmA = new Set([showingId(R[0], 0), showingId(R[1], 0)]); // both film-a showings
  const seen = ALL.filter((id) => !filmA.has(id));
  const o = run(R, { "flicks.seen": JSON.stringify(seen), "flicks.view": "film" });
  eq(o.newPills, 1, "one New pill total");
  eq(/class="film[^"]*is-new/.test(o.html), true, "pill on the card");
  eq((o.html.match(/class="line is-new/g) || []).length, 0, "not on a line");
});

test("by-film: a film at multiple theaters lists lines by date/time, not theater", () => {
  // Same film, two theaters, where the earlier date is at the alphabetically-LATER
  // theater — so date-first and theater-first orders are opposites. ROWS arrive
  // build-sorted by date (render.py's _fold); the client must preserve that and
  // not re-sort the card's lines by theater.
  const rows = [
    row("multi", "Multi Film", "Zeta Theater", dayPlus(1), ["19:00"]),
    row("multi", "Multi Film", "Alpha Theater", dayPlus(3), ["19:00"]),
  ];
  const o = run(rows, { "flicks.view": "film" });
  const zeta = o.html.indexOf("Zeta Theater");   // earlier date
  const alpha = o.html.indexOf("Alpha Theater");  // later date
  if (zeta < 0 || alpha < 0) throw new Error("both theaters should render");
  eq(zeta < alpha, true, "earlier-date line (Zeta) before later-date line (Alpha)");
});

test("first visit pops the welcome dialog; a returning visit does not", () => {
  const first = run(R, {});
  eq(first.opened("help"), true, "welcome shown on first visit");
  const ret = run(R, { "flicks.welcomed": "1" });
  eq(ret.opened("help"), false, "not shown again once welcomed");
});

test("share link round-trips the full filter set (compressed)", async () => {
  const o = run(R, {
    "flicks.hidden": JSON.stringify(["the odyssey", "back to the future", "eraserhead"]),
    "flicks.theaters.off": JSON.stringify(["Cinema 21"]),
    "flicks.days.off": JSON.stringify([0, 6]),
    "flicks.dates.off": JSON.stringify(["2026-07-04"]),
  });
  const url = await o.win.flicksShare.url();
  eq(/#f=[A-Za-z0-9_-]+$/.test(url), true, "url carries a #f= fragment");
  const f = await o.win.flicksShare.decode(url.slice(url.indexOf("#")));
  eq(JSON.stringify(f.hidden.sort()),
    JSON.stringify(["back to the future", "eraserhead", "the odyssey"]), "hidden round-trips");
  eq(JSON.stringify(f.off), JSON.stringify(["Cinema 21"]), "theaters round-trip");
  eq(JSON.stringify(f.offDays), JSON.stringify([0, 6]), "weekdays round-trip (as numbers)");
  eq(JSON.stringify(f.offDates), JSON.stringify(["2026-07-04"]), "dates round-trip");
});

test("importing a filter set replaces the device's filters", async () => {
  const o = run(R, { "flicks.hidden": JSON.stringify(["keep-me"]) });
  o.win.flicksShare.apply({ hidden: ["a", "b"], off: ["Some Theater"], offDays: [1], offDates: [] });
  eq(o.lsGet("flicks.hidden"), JSON.stringify(["a", "b"]), "hidden replaced (keep-me gone)");
  eq(o.lsGet("flicks.theaters.off"), JSON.stringify(["Some Theater"]), "theaters replaced");
  eq(o.lsGet("flicks.days.off"), JSON.stringify([1]), "weekdays replaced");
});

// --- Fresh session: New/leaks are frozen for a visit, and a home-screen app is
// rarely reloaded — so ↻, a view switch, and returning after a while away each
// re-baseline, dropping what you've looked at (but not what you haven't).
function leakSetup(opts) {
  const seen = ALL.filter((id) => id !== showingId(R[0], 0));  // film-a has a new showing…
  return run(R, { "flicks.seen": JSON.stringify(seen), "flicks.hidden": JSON.stringify(["film-a"]) }, opts);
}

test("↻ drops a leak you've already viewed, without a reload (works offline)", () => {
  const o = leakSetup({ live: true, onLine: false });  // live: rows get "viewed" on render
  eq(countLeaks(o), 1, "leak shown on the visit you viewed it");
  o.el("reload").fire("click");
  eq(countLeaks(o), 0, "leak dropped after ↻");
  eq(o.location.reloads, 0, "no navigation");
});

test("switching views drops a viewed leak", () => {
  const o = leakSetup({ live: true });
  o.click({ ".seg button": { dataset: { view: "film" } } });
  eq(countLeaks(o), 0, "leak dropped on view switch");
});

test("returning after ≥30 min away drops a viewed leak; a brief app switch doesn't", () => {
  const o = leakSetup({ live: true });
  const realNow = Date.now;
  try {
    let t = realNow();
    Date.now = () => t;
    o.doc.visibilityState = "hidden"; o.doc.fire("visibilitychange");
    t += 5 * 60 * 1000;
    o.doc.visibilityState = "visible"; o.doc.fire("visibilitychange");
    eq(countLeaks(o), 1, "still shown after 5 min away");
    o.doc.visibilityState = "hidden"; o.doc.fire("visibilitychange");
    t += 31 * 60 * 1000;
    o.doc.visibilityState = "visible"; o.doc.fire("visibilitychange");
    eq(countLeaks(o), 0, "dropped after 31 min away");
  } finally { Date.now = realNow; }
});

test("a fresh session keeps a leak you haven't viewed yet", () => {
  const o = leakSetup();  // inert: nothing gets viewed
  o.win.flicksNewSession();
  eq(countLeaks(o), 1, "unviewed leak survives");
});

runTests();
