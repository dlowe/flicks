// Shared test harness: runs the *real* in-page scripts (extracted from the
// checked-in template, with fixture rows injected) under a minimal DOM stub, so
// no build, network, or Python is needed. Pure node, no deps.

const fs = require("fs");
const path = require("path");
const vm = require("vm");

const ROOT = path.join(__dirname, "..");
const TEMPLATE = path.join(ROOT, "flicks", "templates", "index.html");
const template = fs.readFileSync(TEMPLATE, "utf8");
// Every inline <script>, in order (the main IIFE, then the reload/offline one).
// `{{ rows_json|safe }}` is the only Jinja inside them.
const SCRIPTS = [...template.matchAll(/<script>([\s\S]*?)<\/script>/g)].map((m) => m[1]).join("\n;\n");
function instantiate(rows) {
  return SCRIPTS.replace("{{ rows_json|safe }}", JSON.stringify(rows));
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

function makeStore(seed) {
  const m = new Map(Object.entries(seed || {}));
  return {
    getItem: (k) => (m.has(k) ? m.get(k) : null),
    setItem: (k, v) => m.set(k, String(v)),
    removeItem: (k) => m.delete(k),
  };
}
function on(target) {
  target.listeners = {};
  target.addEventListener = (t, fn) => (target.listeners[t] = target.listeners[t] || []).push(fn);
  target.fire = (t, ev) => (target.listeners[t] || []).forEach((fn) => fn(ev || {}));
  return target;
}

// opts.live = true makes the IntersectionObserver fire and timers run inline, so
// rows are "viewed" (marked seen) during render. Default (inert) is right for the
// static render assertions.
// opts.fetch: the network (default: always fails, i.e. offline).
// opts.onLine / opts.navigator: extra navigator fields (clipboard, serviceWorker…).
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
    const e = on({
      textContent: "", innerHTML: "", disabled: false, hidden: false, dataset: {},
      classList: { add() {}, remove() {} }, getAttribute: () => "",
      scrollIntoView() {}, value: "", focus() {}, select() {}, _opened: false,
    });
    e.showModal = () => { e._opened = true; };       // track dialog opens
    e.close = () => { e._opened = false; };
    e.setAttribute = (k, v) => { if (k === "open") e._opened = true; e["attr:" + k] = v; };
    e.removeAttribute = (k) => { if (k === "open") e._opened = false; };
    return e;
  };
  const getEl = (id) => (id === "cal" ? cal : (reg[id] || (reg[id] = el())));
  const IO = opts.live
    ? class { constructor(cb) { this.cb = cb; } observe(t) { this.cb([{ target: t, isIntersecting: true }]); } unobserve() {} disconnect() {} }
    : class { observe() {} unobserve() {} disconnect() {} };
  const doc = on({
    getElementById: getEl, querySelectorAll: () => [], querySelector: () => null,
    body: { dataset: { build: opts.build || "build-1" } }, visibilityState: "visible", activeElement: null,
  });
  const fetches = [];
  const fetchImpl = opts.fetch || (() => Promise.reject(new TypeError("Load failed")));
  const location = {
    href: "https://x/flicks/", origin: "https://x", protocol: "https:", pathname: "/flicks/",
    search: "", hash: opts.hash || "", reloads: 0, reload() { location.reloads++; },
  };
  const win = on({ IntersectionObserver: IO, scrollTo() {}, scrollY: 0,
    matchMedia: () => ({ matches: false }), location });
  const sb = {
    document: doc, window: win, localStorage: makeStore(storage),
    sessionStorage: makeStore(),
    navigator: Object.assign({ onLine: opts.onLine !== false }, opts.navigator),
    location, history: { replaceState() {} },
    fetch: (url, init) => { fetches.push({ url: String(url), init }); return fetchImpl(url, init); },
    setTimeout: opts.live ? (fn) => { fn(); return 0; } : () => 0,
    clearTimeout() {}, setInterval: () => 0, console,
    IntersectionObserver: IO, Set, Map, JSON, Date, Math,
    parseInt, parseFloat, String, Array, Object,
    // Web APIs the share/import code uses (Node globals):
    CompressionStream, DecompressionStream, TextEncoder, TextDecoder, Response, Blob,
    Uint8Array, Promise, btoa, atob,
  };
  if (opts.ClipboardItem) sb.ClipboardItem = opts.ClipboardItem;
  vm.createContext(sb);
  vm.runInContext(instantiate(rows), sb);
  const ls = sb.localStorage;
  const o = {
    cal, win, doc, reg, location, fetches, sb,
    get html() { return cal._h; },
    get seen() { return JSON.parse(ls.getItem("flicks.seen") || "[]"); },
    get newPills() { return (cal._h.match(/new-tag/g) || []).length; },
    get leaks() { return (cal._h.match(/is-leak/g) || []).length; },
    get icsCount() { return ((reg.ics || {}).innerHTML || "").replace(/<[^>]+>/g, "").match(/\d+/); },
    has: (re) => re.test(cal._h),
    el: getEl,
    opened: (id) => !!(reg[id] && reg[id]._opened),
    lsGet: (k) => ls.getItem(k),
    // Simulate a click whose target sits inside the elements given as
    // {selector: element} (what e.target.closest(selector) would find).
    click(match) {
      const target = { tagName: "BUTTON", closest: (s) => match[s] || null };
      doc.fire("click", { target, preventDefault() {} });
    },
  };
  return o;
}

// Let pending promise chains (fetch → then → …) settle.
function settle() { return new Promise((r) => setTimeout(r, 20)); }

// --- Tiny assertion harness. Tests register here, then run sequentially (some
// are async) via runTests().
const tests = [];
function test(name, fn) { tests.push({ name, fn }); }
function eq(actual, expected, what) {
  if (actual !== expected) throw new Error((what || "value") + ": expected " + expected + ", got " + actual);
}
async function runTests() {
  let failed = 0;
  for (const { name, fn } of tests) {
    try { await fn(); console.log("  ok  " + name); }
    catch (e) { failed++; console.log("FAIL  " + name + "\n      " + e.message); }
  }
  console.log(failed ? "\n" + failed + " failing" : "\nall passing");
  process.exit(failed ? 1 : 0);
}

module.exports = {
  ROOT, template, run, settle, row, dayPlus, fixtures, showingId, allIds,
  test, eq, runTests,
};
