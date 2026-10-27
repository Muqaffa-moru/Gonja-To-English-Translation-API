const fs = require("fs"), vm = require("vm"), assert = require("assert");

// ---------- 1. Apps Script backend against fake Google services ----------
function makeEnv(accessCode) {
  const rows = [], fmts = [];
  const sheet = {
    getLastRow: () => rows.length,
    appendRow: (r) => rows.push(r.slice()),
    setFrozenRows() {},
    getRange(r, c, n, m) {
      return {
        setNumberFormat: (f) => { fmts.push(f); },
        setValues: (v) => v.forEach((row, i) => { rows[r - 1 + i] = row.slice(); }),
        getValues: () => rows.slice(r - 1, r - 1 + n).map((x) => x.slice(c - 1, c - 1 + m)),
      };
    },
  };
  const cacheStore = {};
  const sb = {
    JSON, Date, Array, String, RegExp, Math,
    PropertiesService: { getScriptProperties: () => ({ getProperty: (k) => (k === "ACCESS_CODE" ? accessCode : null) }) },
    CacheService: { getScriptCache: () => ({ get: (k) => cacheStore[k] || null, put: (k, v) => { cacheStore[k] = v; } }) },
    LockService: { getScriptLock: () => ({ waitLock() {}, releaseLock() {} }) },
    SpreadsheetApp: { flush() {}, getActiveSpreadsheet: () => ({ getSheetByName: () => sheet, insertSheet: () => sheet }) },
    ContentService: { MimeType: { JSON: "json" }, createTextOutput: (t) => ({ t, setMimeType() { return this; }, getContent() { return this.t; } }) },
  };
  vm.createContext(sb);
  vm.runInContext(fs.readFileSync("contribute/Code.gs", "utf8"), sb);
  const post = (obj) => JSON.parse(sb.doPost({ postData: { contents: JSON.stringify(obj) } }).getContent());
  const get = () => JSON.parse(sb.doGet().getContent());
  return { rows, fmts, post, get };
}
const good = (over) => Object.assign({
  contributor: "Ama", consent: true, batchId: "batch-0001-aaaa", website: "", accessCode: "",
  items: [{ topic: "greetings", english: "Good morning.", gonja: "G-one ɛɔŋ" }, { topic: "greetings", english: "Welcome.", gonja: "G-two" }],
}, over || {});

let env = makeEnv(null);
let r = env.post(good());
assert.deepStrictEqual([r.ok, r.saved], [true, 2]);
assert.strictEqual(env.rows[0][3], "english");                       // header row created
assert.strictEqual(JSON.stringify(env.rows[1].slice(2)), JSON.stringify(["greetings", "Good morning.", "G-one ɛɔŋ", "Ama", "yes"]));
assert(env.fmts.includes("@"), "rows must be written as plain text");
r = env.post(good());                                                // same batchId again (double click)
assert.deepStrictEqual([r.ok, r.saved, r.duplicate], [true, 0, true]);
assert.strictEqual(env.rows.length, 3);

assert.strictEqual(env.post(good({ batchId: "batch-0002-bbbb", consent: false })).ok, false);       // no consent
assert.strictEqual(env.post(good({ batchId: "batch-0003-cccc", contributor: "  " })).ok, false);     // no name
assert.strictEqual(env.post(good({ batchId: "bad id!" })).ok, false);                                // bad batch id
assert.strictEqual(env.post(good({ batchId: "batch-0004-dddd", items: [] })).ok, false);             // nothing
const many = Array.from({ length: 101 }, (_, i) => ({ topic: "t", english: "e" + i, gonja: "g" + i }));
assert.strictEqual(env.post(good({ batchId: "batch-0005-eeee", items: many })).ok, false);           // too many
r = env.post(good({ batchId: "batch-0006-ffff", website: "http://spam" }));                          // honeypot
assert.deepStrictEqual([r.ok, r.saved], [true, 0]); assert.strictEqual(env.rows.length, 3);

// formulas, control characters, blanks and long text
r = env.post(good({ batchId: "batch-0007-gggg", items: [
  { topic: "x", english: "Formula test", gonja: "=HYPERLINK(\"http://evil\")" },
  { topic: "x", english: "Blank", gonja: "   " },
  { topic: "x", english: "Long", gonja: "g".repeat(501) },
  { topic: "x", english: "Tabs\tand\nlines", gonja: "ok\u0007 fine" }] }));
assert.deepStrictEqual([r.saved, r.skipped], [2, 2]);
assert.strictEqual(env.rows[3][4], "=HYPERLINK(\"http://evil\")");   // stored literally (plain-text cells)
assert.strictEqual(env.rows[4][3], "Tabs and lines");
assert.strictEqual(env.rows[4][4], "ok fine");

// counts for the page
const c = env.get();
assert.strictEqual(c.ok, true); assert.strictEqual(c.counts["good morning."], 1); assert.strictEqual(c.counts["welcome."], 1);

// access code
env = makeEnv("sesame");
assert.strictEqual(env.post(good()).ok, false);
assert.strictEqual(env.post(good({ accessCode: " sesame " })).ok, true);
fs.writeFileSync("/tmp/sheet_rows.json", JSON.stringify(env.rows));
console.log("Apps Script tests passed");

// ---------- 2. Page logic ----------
const html = fs.readFileSync("contribute/gonja-contribute.html", "utf8");
const logic = html.split("// ===== PURE LOGIC START (tested in Node) =====")[1].split("// ===== PURE LOGIC END =====")[0];
const MAX_ITEMS = 100;
const L = new Function("MAX_ITEMS", logic + "; return {normKey, orderPrompts, filledItems, validateSubmission, buildPayload, newBatchId};")(MAX_ITEMS);

const prompts = [{ english: "A", have: 1 }, { english: "B", have: 0 }, { english: "C", have: 0 }, { english: "D", have: 0 }];
assert.deepStrictEqual(L.orderPrompts(prompts, { c: 2, d: 1 }).map((p) => p.english), ["B", "A", "D", "C"]);   // fewest answers first (A and D tie at 1, original order kept)
const items = L.filledItems({ "Good morning.": ["  Anshumaa ", "", "Another way"], Welcome: ["   "] }, { "Good morning.": "greetings" });
assert.deepStrictEqual(items.map((i) => i.gonja), ["Anshumaa", "Another way"]);
assert.strictEqual(items[0].topic, "greetings");
const ok = { name: "Ama", consent: true };
assert.strictEqual(L.validateSubmission(ok, items), "");
assert.match(L.validateSubmission({ name: "", consent: true }, items), /name/);
assert.match(L.validateSubmission({ name: "Ama", consent: false }, items), /consent/);
assert.match(L.validateSubmission(ok, []), /at least one/);
assert.match(L.validateSubmission(ok, [{ english: "Thank you.", gonja: "thank  YOU." }]), /same as the English/);
const p = L.buildPayload({ name: " Ama ", code: " x ", website: "" }, Array.from({ length: 150 }, (_, i) => ({ english: "e" + i, gonja: "g" + i })), "id-1");
assert.deepStrictEqual([p.contributor, p.accessCode, p.consent, p.items.length], ["Ama", "x", true, 100]);
assert(/^[A-Za-z0-9-]{8,64}$/.test(L.newBatchId()), "batch id must match what the server accepts");
console.log("page logic tests passed");

// ---------- 3. wiring checks ----------
const script = html.match(/<script>([\s\S]*)<\/script>/)[1];
fs.writeFileSync("/tmp/contribute.js", script);
const ids = new Set([...script.matchAll(/\$\("([A-Za-z]+)"\)/g)].map((m) => m[1]));
const present = new Set([...html.matchAll(/id="([A-Za-z]+)"/g)].map((m) => m[1]));
const missing = [...ids].filter((i) => !present.has(i));
assert.deepStrictEqual(missing, [], "ids used in JS but missing in HTML: " + missing);
assert(html.includes("PASTE_YOUR_WEB_APP_URL_HERE"));
const embedded = JSON.parse(html.match(/const PROMPTS = (\[.*?\]);\nconst PAGE/s)[1]);
assert.strictEqual(embedded.length, 464);
console.log("wiring checks passed:", embedded.length, "prompts embedded");
