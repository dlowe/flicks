// Tests for the page's "new to you" / leak logic — the densest, least
// eyeball-able client code. Runs the *real* in-page script (extracted from the
// checked-in template, with fixture rows injected) under a minimal DOM stub, so
// no build, network, or Python is needed. Pure node, no deps.
//
//   node tests/seen.test.js   (or ./test.sh)

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const TEMPLATE = path.join(__dirname, "..", "flicks", "templates", "index.html");

// --- Pull the main IIFE out of the template and feed it fixture rows in place
// of the Jinja `{{ rows_json|safe }}` blob. (That token is the only Jinja in the
// first <script>; the rest live in HTML / the second script.)
const template = fs.readFileSync(TEMPLATE, "utf8");
const SCRIPT = template.match(/<script>([\s\S]*?)<\/script>/)[1];
function instantiate(rows) {
  return SCRIPT.replace("{{ rows_json|safe }}", JSON.stringify(rows));
}

// --- Fixtures: dates are relative to the run, so rows stay "upcoming". A film
// is identified by `key`; a row is one film+theater+day with a list of `starts`.
function pad(n) { return n < 10 ? "0" + n : "" + n; }
function dayPlus(n) {
  const d = new Date(); d.setDate(d.getDate() + n);
  return d.getFullYear() + "-" + pad(d.getMonth() + 1) + "-" + pad(d.getDate());
}
function row(key, title, theater, date, starts) {
  return {
    date, title, key, theater, home: "https://x", url: "https://x",
    poster: null, imdb: null, rating: null,
    times: starts.map(() => "7:00pm"),
    starts: starts.map((t) => date + "T" + t + "-07:00"),
    sort: date + "T" + starts[0] + "-07:00",
  };
}
function fixtures() {
  return [
    row("film-a", "Film A", "Theater 1", dayPlus(2), ["19:00"]),
    row("film-a", "Film A", "Theater 1", dayPlus(5), ["19:00"]),
    row("film-b", "Film B", "Theater 2", dayPlus(3), ["19:00"]),
    row("film-c", "Film C", "Theater 3", dayPlus(4), ["20:00", "22:00"]),
  ];
}
function showingId(r, i) { return r.key + "|" + r.theater + "|" + r.starts[i]; }
function allIds(rows) {
  return rows.flatMap((r) => r.starts.map((_, i) => showingId(r, i)));
}

// --- Minimal DOM stub: enough for the script to load + render once without
// throwing. cal.innerHTML captures the rendered HTML for assertions; everything
// else is inert (the IntersectionObserver never fires here).
function makeStore(seed) {
  const m = new Map(Object.entries(seed || {}));
  return {
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => m.set(k, String(v)),
    removeItem: (k) => m.delete(k),
  };
}
// opts.live = true makes the IntersectionObserver fire and timers run inline, so
// rows are "viewed" (marked seen) during render — for testing the seen→refresh
// flow. Default (inert) is right for the static render assertions.
function run(rows, storage, opts) {
  opts = opts || {};
  const reg = {};
  const cal = {
    _h: "", set innerHTML(v) { this._h = v; }, get innerHTML() { return this._h; },
    // In live mode, hand back the rendered new/leak units (those carry data-ids)
    // so the observer can mark them seen.
    querySelectorAll: opts.live
      ? () => [...cal._h.matchAll(/data-ids="([^"]*)"/g)].map((m) => ({ dataset: { ids: m[1] } }))
      : () => [],
  };
  const el = () => {
    const e = {
      textContent: "", innerHTML: "", disabled: false, hidden: false, dataset: {},
      classList: { add() {}, remove() {} }, getAttribute: () => "",
      addEventListener() {}, scrollIntoView() {}, value: "", focus() {}, _opened: false,
    };
    e.showModal = () => { e._opened = true; };       // track dialog opens
    e.setAttribute = (k) => { if (k === "open") e._opened = true; };
    return e;
  };
  const getEl = (id) => (id === "cal" ? cal : (reg[id] || (reg[id] = el())));
  const IO = opts.live
    ? class { constructor(cb) { this.cb = cb; } observe(t) { this.cb([{ target: t, isIntersecting: true }]); } unobserve() {} disconnect() {} }
    : class { observe() {} unobserve() {} disconnect() {} };
  const doc = {
    getElementById: getEl, querySelectorAll: () => [], addEventListener() {},
    body: { dataset: {} }, visibilityState: "visible", activeElement: null,
  };
  const win = { IntersectionObserver: IO, scrollTo() {}, addEventListener() {},
    matchMedia: () => ({ matches: false }) };
  const sb = {
    document: doc, window: win, localStorage: makeStore(storage),
    sessionStorage: makeStore(), navigator: { onLine: true },
    location: { href: "x", origin: "https://x", pathname: "/", search: "", hash: "", reload() {} },
    history: { replaceState() {} },
    setTimeout: opts.live ? (fn) => { fn(); return 0; } : () => 0,
    clearTimeout() {}, setInterval: () => 0, console,
    IntersectionObserver: IO, Set, Map, JSON, Date, Math,
    parseInt, parseFloat, String, Array, Object,
    // Web APIs the share/import code uses (Node globals):
    CompressionStream, DecompressionStream, TextEncoder, TextDecoder, Response,
    Uint8Array, Promise, btoa, atob,
  };
  win.location = sb.location;
  vm.createContext(sb);
  vm.runInContext(instantiate(rows), sb);
  const ls = sb.localStorage;
  return {
    cal, win,
    html: cal._h,
    seen: JSON.parse(ls.getItem("flicks.seen") || "[]"),
    newPills: (cal._h.match(/new-tag/g) || []).length,
    leaks: (cal._h.match(/is-leak/g) || []).length,
    icsCount: ((reg.ics || {}).innerHTML || "").replace(/<[^>]+>/g, "").match(/\d+/),
    has: (re) => re.test(cal._h),
    opened: (id) => !!(reg[id] && reg[id]._opened),
    lsGet: (k) => ls.getItem(k),
  };
}
function countLeaks(o) { return (o.cal._h.match(/is-leak/g) || []).length; }

// --- Tiny assertion harness. Tests register here, then run sequentially (some
// are async) in the runner at the bottom.
let failed = 0;
const tests = [];
function test(name, fn) { tests.push({ name, fn }); }
function eq(actual, expected, what) {
  if (actual !== expected) throw new Error((what || "value") + ": expected " + expected + ", got " + actual);
}

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

(async () => {
  for (const { name, fn } of tests) {
    try { await fn(); console.log("  ok  " + name); }
    catch (e) { failed++; console.log("FAIL  " + name + "\n      " + e.message); }
  }
  console.log(failed ? "\n" + failed + " failing" : "\nall passing");
  process.exit(failed ? 1 : 0);
})();
