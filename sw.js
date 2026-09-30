// Offline-first service worker: the page must work with no network (it's used as
// an iOS home-screen app on a phone with no data plan). See CLAUDE.md "Offline".
//
// * Opening the page (a navigation) is answered from cache first — instant, and
//   the same with or without a connection. The page itself then checks for a
//   newer build (its refresh(): a same-URL fetch) and reloads into it.
// * That check, and any other non-navigation GET of the page, goes to the network
//   and — only on success — replaces the cached copy *before* answering, so the
//   reload it triggers is served the new build.
// * Icons/manifest are precached. Posters (cross-origin) and HEAD polls are left
//   alone.
//
// Bump CACHE if the ASSETS list or their content changes; the page itself needs
// no bump (it's refreshed by the page's own build check).
var CACHE = "flicks-v1";
var ASSETS = ["manifest.webmanifest", "icon.svg", "icon-192.png", "icon-512.png", "apple-touch-icon.png"];
var SCOPE = self.registration.scope;  // e.g. https://dlowe.github.io/flicks/

// Every URL that means "the page" (./, ./index.html, with any query) → one key.
function pageKey(url) {
  var u = new URL(url), s = new URL(SCOPE);
  if (u.origin !== s.origin) return null;
  return u.pathname === s.pathname || u.pathname === s.pathname + "index.html" ? SCOPE : null;
}
function assetKey(url) {
  var u = new URL(url), s = new URL(SCOPE);
  if (u.origin !== s.origin) return null;
  var rel = u.pathname.slice(s.pathname.length);
  return u.pathname.indexOf(s.pathname) === 0 && ASSETS.indexOf(rel) !== -1 ? new URL(rel, SCOPE).href : null;
}

self.addEventListener("install", function (e) {
  e.waitUntil(caches.open(CACHE)
    .then(function (c) { return c.addAll([SCOPE].concat(ASSETS.map(function (a) { return new URL(a, SCOPE).href; }))); })
    .then(function () { return self.skipWaiting(); }));
});

self.addEventListener("activate", function (e) {
  e.waitUntil(caches.keys()
    .then(function (ks) { return Promise.all(ks.filter(function (k) { return k !== CACHE; }).map(function (k) { return caches.delete(k); })); })
    .then(function () { return self.clients.claim(); }));
});

// Network, storing a good response under `key` before handing it back.
function fetchAndStore(req, key) {
  return fetch(req).then(function (r) {
    if (!r.ok || r.redirected) return r;  // a 404/500 (or a redirect) never replaces a good copy
    var copy = r.clone();
    return caches.open(CACHE).then(function (c) { return c.put(key, copy); }).then(function () { return r; });
  });
}
function cacheFirst(req, key) {
  return caches.match(key).then(function (hit) { return hit || fetchAndStore(req, key); });
}

self.addEventListener("fetch", function (e) {
  var req = e.request;
  if (req.method !== "GET") return;
  var key = pageKey(req.url);
  if (key) {
    // Navigation → cache first; a background check → network (updates the cache).
    e.respondWith(req.mode === "navigate" ? cacheFirst(req, key) : fetchAndStore(req, key));
    return;
  }
  key = assetKey(req.url);
  if (key) e.respondWith(cacheFirst(req, key));
});
