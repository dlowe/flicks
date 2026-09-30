// Tests for the page's touch affordances: the footer undo button, the filters
// dialog (copy / paste link), and by-film theater labels. See harness.js.
//
//   node tests/ui.test.js   (or ./test.sh)

const { run, row, dayPlus, fixtures, settle, test, eq, runTests } = require("./harness");

const R = fixtures();

test("undo button is hidden with nothing to undo", () => {
  const o = run(R, { "flicks.welcomed": "1" });
  eq(o.el("undo").hidden, true, "hidden");
});

test("hiding a film shows 'Undo hide <title>', and tapping it restores the film", () => {
  const o = run(R, { "flicks.welcomed": "1" });
  o.click({ ".hide": { dataset: { key: "film-b" } } });
  eq(o.has(/data-rk="film-b"/), false, "film-b hidden");
  const u = o.el("undo");
  eq(u.hidden, false, "undo shown");
  eq(/Undo.*hide Film B/.test(u.innerHTML), true, "names the step: " + u.innerHTML);
  o.click({ "#undo": u });
  eq(o.has(/data-rk="film-b"/), true, "film-b back");
  eq(u.hidden, true, "nothing left to undo");
});

test("undo labels name each kind of step", () => {
  const cases = [
    [{ t: "theater", v: "Cinema 21" }, "hide Cinema 21"],
    [{ t: "day", v: 1 }, "hide Mondays"],
    [{ t: "unday", v: 0 }, "show Sundays"],
    [{ t: "unhide", v: "film-c" }, "restore Film C"],
    [{ t: "reset", v: { hidden: [], off: [], offDays: [], offDates: [] } }, "show all"],
    [{ t: "film", v: "gone-film" }, "hide gone-film"],  // aged out of the listings: key
  ];
  for (const [a, want] of cases) {
    const o = run(R, { "flicks.welcomed": "1", "flicks.undo": JSON.stringify([a]) });
    eq(o.el("undo").innerHTML.includes(want), true, want + " in " + o.el("undo").innerHTML);
  }
});

test("filters button counts every kind of hide", () => {
  const o = run(R, {
    "flicks.welcomed": "1", "flicks.hidden": JSON.stringify(["x", "y"]),
    "flicks.days.off": JSON.stringify([1]),
  });
  eq(o.el("filtersbtn").textContent, "filters (3)", "label");
  eq(o.el("filtersum").textContent, "Hiding 2 films, 1 weekday.", "breakdown");
  eq(o.el("sharebtn").disabled, false, "copy enabled");
});

test("with nothing hidden, filters still offers paste (copy/show all disabled)", () => {
  const o = run(R, { "flicks.welcomed": "1" });
  eq(o.el("filtersbtn").textContent, "filters", "label");
  eq(o.el("sharebtn").disabled, true, "copy disabled");
  eq(o.el("showallbtn").disabled, true, "show all disabled");
});

test("paste link (clipboard) → import dialog → replaces filters", async () => {
  const src = run(R, { "flicks.hidden": JSON.stringify(["film-a", "film-c"]) });
  const url = await src.win.flicksShare.url();
  const o = run(R, { "flicks.welcomed": "1" }, {
    navigator: { clipboard: { readText: () => Promise.resolve("  look: " + url + "\n") } },
  });
  o.click({ "[data-paste]": {} });
  await settle();
  eq(o.opened("import"), true, "import dialog offered");
  o.click({ "[data-import]": { dataset: { import: "apply" } } });
  eq(o.lsGet("flicks.hidden"), JSON.stringify(["film-a", "film-c"]), "filters replaced");
  eq(o.el("undo").innerHTML.includes("import"), true, "undoable as 'import'");
});

test("paste link (typed into the box) works with no clipboard API", async () => {
  const src = run(R, { "flicks.hidden": JSON.stringify(["film-b"]) });
  const url = await src.win.flicksShare.url();
  const o = run(R, { "flicks.welcomed": "1" });
  o.el("pastebox").value = url;
  o.el("pastebox").fire("input");
  await settle();
  eq(o.opened("import"), true, "import dialog offered");
});

test("pasting something that isn't a filter link says so, imports nothing", async () => {
  const o = run(R, { "flicks.welcomed": "1" });
  o.el("pastebox").value = "https://example.com/hello";
  o.el("pastebox").fire("input");
  await settle();
  eq(o.opened("import"), false, "no import");
  eq(/doesn't look like/.test(o.el("fmsg").textContent), true, "message: " + o.el("fmsg").textContent);
});

test("copy link writes the share URL via ClipboardItem (async-safe for Safari)", async () => {
  let written = null;
  class ClipboardItem { constructor(d) { this.d = d; } }
  const o = run(R, { "flicks.welcomed": "1", "flicks.hidden": JSON.stringify(["film-a"]) }, {
    ClipboardItem,
    navigator: { clipboard: { write: async ([item]) => { written = await (await item.d["text/plain"]).text(); } } },
  });
  o.click({ "[data-share]": {} });
  await settle();
  eq(/#f=/.test(written || ""), true, "clipboard got the link: " + written);
  eq(/copied/.test(o.el("fmsg").textContent), true, "says so");
});

test("copy link with no clipboard API leaves the link selected in the box", async () => {
  const o = run(R, { "flicks.welcomed": "1", "flicks.hidden": JSON.stringify(["film-a"]) });
  o.click({ "[data-share]": {} });
  await settle();
  eq(/#f=/.test(o.el("pastebox").value), true, "link in the box");
});

test("by-film: a single-theater film names its theater once; multi-theater per line", () => {
  const rows = [
    row("solo", "Solo Film", "Hollywood Theatre", dayPlus(1), ["19:00"]),
    row("solo", "Solo Film", "Hollywood Theatre", dayPlus(2), ["19:00"]),
    row("duo", "Duo Film", "Cinema 21", dayPlus(1), ["19:00"]),
    row("duo", "Duo Film", "Academy Theater", dayPlus(3), ["19:00"]),
  ];
  const o = run(rows, { "flicks.welcomed": "1", "flicks.view": "film" });
  eq((o.html.match(/Hollywood Theatre/g) || []).length, 1, "solo theater named once");
  eq((o.html.match(/class="line multi"/g) || []).length, 2, "duo lines carry the theater");
  eq(/Cinema 21/.test(o.html) && /Academy Theater/.test(o.html), true, "both duo theaters shown");
});

runTests();
