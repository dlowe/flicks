// The page must work offline — it's used as an iOS home-screen app on a phone
// with no data plan, and this has regressed before. These tests pin the pieces
// that make that true (see CLAUDE.md "Offline"):
//
//   1. the page is self-contained: data inlined, no external scripts/styles/fonts;
//   2. it boots, renders, and never navigates away when the network is dead
//      (offline, or "online" but every request fails);
//   3. sw.js ships, is registered, and serves the last page with no network.
//
// (The other test files also run with the network down — the harness default.)
//
//   node tests/offline.test.js   (or ./test.sh)

const fs = require("fs");
const path = require("path");
const vm = require("vm");
const { ROOT, template, run, fixtures, settle, test, eq, runTests } = require("./harness");

const R = fixtures();
const SW = fs.readFileSync(path.join(ROOT, "sw.js"), "utf8");
const swAssets = JSON.parse(SW.match(/var ASSETS = (\[[^\]]*\])/)[1]);
const publishAssets = fs.readFileSync(path.join(ROOT, "publish.sh"), "utf8").match(/^assets="([^"]+)"/m)[1].split(/\s+/);
const htmlOnly = template.replace(/<script>[\s\S]*?<\/script>/g, "");  // markup + CSS, no JS strings

// --- 1. Self-contained page ---------------------------------------------------

test("no external subresources: scripts/styles/fonts are all inline", () => {
  eq(/<script[^>]*\bsrc=/i.test(template), false, "a <script src> (must be inline)");
  eq(/<link[^>]*rel="?stylesheet/i.test(template), false, "a stylesheet <link> (must be inline)");
  eq(/@import|url\(\s*["']?(https?:)?\/\//i.test(template), false, "a CSS @import / remote url()");
  eq(/<(iframe|object|embed)\b/i.test(template), false, "an embedded document");
});

test("the listings are inlined into the page, not fetched", () => {
  eq(/var ROWS = \{\{ rows_json\|safe \}\};/.test(template), true, "ROWS inlined via Jinja");
  eq(/events\.json/.test(template), false, "page must not load events.json");
});

test("every <link>ed file is local and precached by the service worker", () => {
  const hrefs = [...htmlOnly.matchAll(/<link\b[^>]*\bhref="([^"]+)"/g)].map((m) => m[1]);
  eq(hrefs.length > 0, true, "found <link>s");
  for (const h of hrefs) {
    eq(/^[\w.-]+$/.test(h), true, "relative same-dir href: " + h);
    eq(swAssets.includes(h), true, h + " in sw.js ASSETS");
  }
  const manifest = JSON.parse(fs.readFileSync(path.join(ROOT, "manifest.webmanifest"), "utf8"));
  for (const i of manifest.icons) eq(swAssets.includes(i.src), true, i.src + " (manifest icon) in sw.js ASSETS");
});

test("sw.js and everything it precaches are published", () => {
  eq(publishAssets.includes("sw.js"), true, "publish.sh ships sw.js");
  for (const a of swAssets) {
    eq(publishAssets.includes(a), true, a + " in publish.sh assets");
    eq(fs.existsSync(path.join(ROOT, a)), true, a + " exists in the repo");
  }
  const ci = fs.readFileSync(path.join(ROOT, ".github", "workflows", "publish.yml"), "utf8");
  for (const a of ["sw.js"].concat(swAssets)) eq(ci.includes(a), true, a + " staged by the CI publish workflow");
});

// --- 2. The page with a dead network -------------------------------------------

test("boots offline: renders the listings, makes no request it depends on, never navigates", async () => {
  const o = run(R, { "flicks.welcomed": "1" }, { onLine: false });
  await settle();
  eq(o.has(/Film A/) && o.has(/Film C/), true, "listings rendered");
  eq(o.fetches.length, 0, "no fetches while navigator.onLine is false");
  eq(o.location.reloads, 0, "no reload");
});

test("lie-fi (onLine but every request fails): stays put on load, re-show, and ↻", async () => {
  const o = run(R, { "flicks.welcomed": "1" });  // harness default network: always fails
  await settle();
  o.doc.fire("visibilitychange"); o.win.fire("pageshow");
  o.el("reload").fire("click");
  await settle();
  eq(o.has(/Film A/), true, "still rendered");
  eq(o.location.reloads, 0, "never reloaded into a dead connection");
  for (const f of o.fetches) eq(f.url, o.location.href, "only the page's own build check hits the network");
});

test("↻ offline says so instead of trying", () => {
  const o = run(R, { "flicks.welcomed": "1" }, { onLine: false });
  o.el("reload").fire("click");
  eq(/Offline/.test(o.el("toast").textContent), true, "toast: " + o.el("toast").textContent);
  eq(o.location.reloads, 0, "no reload");
});

// Control: prove the harness *can* see a reload, so the zeros above mean something.
test("online with a newer build: reloads into it (once); same build: doesn't", async () => {
  const page = (b) => () => Promise.resolve({ ok: true, text: () => Promise.resolve('<body data-build="' + b + '">') });
  const newer = run(R, { "flicks.welcomed": "1" }, { build: "old", fetch: page("new") });
  await settle();
  eq(newer.location.reloads, 1, "reloaded to the newer build");
  const same = run(R, { "flicks.welcomed": "1" }, { build: "cur", fetch: page("cur") });
  await settle();
  eq(same.location.reloads, 0, "no reload on the current build");
});

test("registers sw.js", () => {
  const regs = [];
  run(R, { "flicks.welcomed": "1" }, {
    navigator: { serviceWorker: { register: (u) => { regs.push(u); return Promise.resolve(); } } },
  });
  eq(JSON.stringify(regs), JSON.stringify(["sw.js"]), "registered");
});

// --- 3. The service worker ------------------------------------------------------

const SCOPE = "https://x.test/flicks/";
function swEnv(network) {
  const store = new Map();  // url -> Response (one cache is all sw.js uses)
  const key = (k) => (typeof k === "string" ? k : k.url);
  const cache = {
    put: async (k, r) => { store.set(key(k), r); },
    match: async (k) => { const r = store.get(key(k)); return r && r.clone(); },
    addAll: async (urls) => { for (const u of urls) store.set(u, await network({ url: u, method: "GET" })); },
  };
  const listeners = {};
  const self = {
    registration: { scope: SCOPE }, clients: { claim: async () => {} }, skipWaiting: async () => {},
    addEventListener: (t, fn) => { listeners[t] = fn; },
  };
  const sb = {
    self, URL, Promise, console,
    caches: { open: async () => cache, match: cache.match, keys: async () => ["flicks-v1"], delete: async () => true },
    fetch: (req) => network(req),
  };
  vm.createContext(sb);
  vm.runInContext(SW, sb);
  async function event(t, props) {
    const ev = Object.assign({ respondWith(p) { this.res = p; }, waitUntil(p) { this.wait = p; } }, props);
    listeners[t](ev);
    if (ev.wait) await ev.wait;
    return ev;
  }
  return {
    store,
    install: () => event("install"),
    // → the Response body sw.js answers with, or null if it let the request pass.
    async get(url, mode, method) {
      const ev = await event("fetch", { request: { url, mode: mode || "navigate", method: method || "GET" } });
      if (!ev.res) return null;
      return (await ev.res).text();
    },
  };
}
function net(pages) {  // a switchable fake network
  const n = async (req) => {
    if (n.down) throw new TypeError("Load failed");
    const body = pages[req.url] !== undefined ? pages[req.url] : "asset:" + req.url;
    return new Response(body, { status: n.status || 200 });
  };
  return n;
}

test("sw: install precaches the page and every asset", async () => {
  const n = net({ [SCOPE]: "page v1" }), sw = swEnv(n);
  await sw.install();
  eq(sw.store.has(SCOPE), true, "page cached");
  for (const a of swAssets) eq(sw.store.has(SCOPE + a), true, a + " cached");
});

test("sw: offline, opening the page (any spelling of its URL) serves the cached copy", async () => {
  const n = net({ [SCOPE]: "page v1" }), sw = swEnv(n);
  await sw.install();
  n.down = true;
  for (const u of [SCOPE, SCOPE + "index.html", SCOPE + "?utm=x", SCOPE + "#f=abc"]) {
    eq(await sw.get(u), "page v1", u);
  }
  eq(await sw.get(SCOPE + "icon-192.png", "no-cors"), "asset:" + SCOPE + "icon-192.png", "icon offline");
});

test("sw: the page's build check refreshes the cache before answering; failures don't clobber it", async () => {
  const pages = { [SCOPE]: "page v1" }, n = net(pages), sw = swEnv(n);
  await sw.install();
  pages[SCOPE] = "page v2";
  eq(await sw.get(SCOPE, "cors"), "page v2", "check sees the network");
  n.down = true;
  eq(await sw.get(SCOPE), "page v2", "next (offline) open gets v2");
  n.down = false; n.status = 500; pages[SCOPE] = "error page";
  eq(await sw.get(SCOPE, "cors"), "error page", "500 passes through");
  n.status = 200; n.down = true;
  eq(await sw.get(SCOPE), "page v2", "…but didn't replace the good copy");
});

test("sw: first open with nothing cached goes to the network and keeps it", async () => {
  const n = net({ [SCOPE]: "page v1" }), sw = swEnv(n);
  eq(await sw.get(SCOPE), "page v1", "from network");
  n.down = true;
  eq(await sw.get(SCOPE), "page v1", "then from cache");
});

test("sw: leaves HEAD polls and cross-origin posters alone", async () => {
  const sw = swEnv(net({}));
  eq(await sw.get(SCOPE, "cors", "HEAD"), null, "HEAD passes through");
  eq(await sw.get("https://theater.example/poster.jpg", "no-cors"), null, "poster passes through");
  eq(await sw.get(SCOPE + "events.json", "cors"), null, "unlisted same-origin file passes through");
});

runTests();
