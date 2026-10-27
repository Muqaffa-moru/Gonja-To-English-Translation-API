/**
 * Gonja contribution collector (Google Apps Script, bound to a Google Sheet).
 * Setup steps: see SETUP.md.
 *
 * - doPost: receives a batch of answers from the web page and appends rows
 * - doGet : returns how many answers each English sentence already has
 * Optional Script property ACCESS_CODE: if set, submitters must know it.
 */
var SHEET_NAME = "Submissions";
var HEADERS = ["timestamp", "batch_id", "topic", "english", "gonja", "contributor", "consent"];
var MAX_ITEMS = 100;     // answers per submission
var MAX_LEN = 500;       // characters per sentence
var MAX_NAME = 60;

function doPost(e) {
  try {
    var data = JSON.parse((e && e.postData && e.postData.contents) || "{}");
    return json_(handleSubmission_(data));
  } catch (err) {
    return json_({ ok: false, error: "Bad request." });
  }
}

function doGet() {
  try {
    return json_({ ok: true, counts: counts_() });
  } catch (err) {
    return json_({ ok: false, error: "Could not load counts." });
  }
}

function clean_(v) {
  return String(v == null ? "" : v)
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

function handleSubmission_(data) {
  if (data.website) return { ok: true, saved: 0 };                       // honeypot: bots filled a hidden field

  var code = PropertiesService.getScriptProperties().getProperty("ACCESS_CODE");
  if (code && String(data.accessCode || "").trim() !== code) {
    return { ok: false, error: "That access code is not correct." };
  }
  if (data.consent !== true) {
    return { ok: false, error: "Please tick the consent box first." };
  }
  var name = clean_(data.contributor);
  if (!name || name.length > MAX_NAME) {
    return { ok: false, error: "Please enter your name (up to 60 characters)." };
  }
  var batchId = String(data.batchId || "");
  if (!/^[A-Za-z0-9-]{8,64}$/.test(batchId)) {
    return { ok: false, error: "Bad request." };
  }
  var items = data.items;
  if (!Array.isArray(items) || items.length === 0) {
    return { ok: false, error: "There is nothing to save yet." };
  }
  if (items.length > MAX_ITEMS) {
    return { ok: false, error: "Too many answers at once (maximum " + MAX_ITEMS + ")." };
  }

  var cache = CacheService.getScriptCache();
  if (cache.get("batch_" + batchId)) {                                    // double-click / retry protection
    return { ok: true, saved: 0, duplicate: true };
  }

  var now = new Date().toISOString();
  var rows = [];
  for (var i = 0; i < items.length; i++) {
    var it = items[i] || {};
    var english = clean_(it.english);
    var gonja = clean_(it.gonja);
    if (!english || !gonja) continue;
    if (english.length > MAX_LEN || gonja.length > MAX_LEN) continue;
    rows.push([now, batchId, clean_(it.topic).slice(0, 40), english, gonja, name, "yes"]);
  }
  if (rows.length === 0) {
    return { ok: false, error: "None of the answers could be saved (empty or too long)." };
  }

  var lock = LockService.getScriptLock();
  lock.waitLock(20000);
  try {
    var sheet = sheet_();
    var range = sheet.getRange(sheet.getLastRow() + 1, 1, rows.length, HEADERS.length);
    range.setNumberFormat("@");                                           // plain text: nothing is treated as a formula
    range.setValues(rows);
    cache.put("batch_" + batchId, "1", 21600);
    SpreadsheetApp.flush();
  } finally {
    lock.releaseLock();
  }
  return { ok: true, saved: rows.length, skipped: items.length - rows.length };
}

function sheet_() {
  var ss = SpreadsheetApp.getActiveSpreadsheet();
  var sh = ss.getSheetByName(SHEET_NAME) || ss.insertSheet(SHEET_NAME);
  if (sh.getLastRow() === 0) {
    sh.appendRow(HEADERS);
    sh.setFrozenRows(1);
  }
  return sh;
}

function counts_() {
  var cache = CacheService.getScriptCache();
  var hit = cache.get("counts");
  if (hit) return JSON.parse(hit);
  var sh = sheet_();
  var last = sh.getLastRow();
  var counts = {};
  if (last >= 2) {
    var col = sh.getRange(2, 4, last - 1, 1).getValues();
    for (var i = 0; i < col.length; i++) {
      var key = clean_(col[i][0]).toLowerCase();
      if (key) counts[key] = (counts[key] || 0) + 1;
    }
  }
  cache.put("counts", JSON.stringify(counts), 60);
  return counts;
}

function json_(obj) {
  return ContentService.createTextOutput(JSON.stringify(obj)).setMimeType(ContentService.MimeType.JSON);
}
