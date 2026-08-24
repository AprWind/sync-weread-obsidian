"use strict";

const Module = require("module");
const path = require("path");

class MockElement {
  constructor(tag = "div", options = {}) {
    this.tag = tag; this.children = []; this.parentElement = null; this.attrs = {}; this.dataset = {}; this.isConnected = true;
    this.style = { values: {}, setProperty: (key, value) => { this.style.values[key] = String(value); } };
    this.tabIndex = 0; this.className = options.cls || ""; this.events = {}; this.clientWidth = 760;
    if (options.text !== undefined) this.textContent = options.text;
    if (options.attr) Object.entries(options.attr).forEach(([key, value]) => this.setAttr(key, value));
  }
  get firstChild() { return this.children[0] || null; }
  createDiv(options = {}) { return this.appendChild(new MockElement("div", options)); }
  createSpan(options = {}) { return this.appendChild(new MockElement("span", options)); }
  createEl(tag, options = {}) { return this.appendChild(new MockElement(tag, options)); }
  appendChild(child) { child.parentElement = this; this.children.push(child); return child; }
  append(...children) { children.forEach((child) => this.appendChild(child)); }
  empty() { this.children = []; }
  setAttr(key, value) { this.attrs[key] = String(value); if (key.startsWith("data-")) this.dataset[key.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = String(value); }
  setAttribute(key, value) { this.setAttr(key, value); }
  toggleClass(name, force) { const parts = this.className.split(/\s+/).filter(Boolean); const has = parts.includes(name); const wanted = force === undefined ? !has : Boolean(force); if (wanted && !has) parts.push(name); if (!wanted && has) parts.splice(parts.indexOf(name), 1); this.className = parts.join(" "); }
  addClass(name) { this.toggleClass(name, true); }
  focus() { this.focused = true; }
  setPointerCapture() {}
  querySelectorAll(selector) {
    const matches = []; const classMatch = /^\.([^\s]+)$/.exec(selector); const attrMatch = /\[data-period="([^"]+)"\]/.exec(selector);
    const visit = (element) => element.children.forEach((child) => { if ((selector === "button" && child.tag === "button") || (classMatch && child.className.split(/\s+/).includes(classMatch[1])) || (attrMatch && child.dataset.period === attrMatch[1])) matches.push(child); visit(child); });
    visit(this); return matches;
  }
  querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
}

const originalLoad = Module._load;
let processor; const registered = []; let clearedIntervals = 0;
class MockPlugin { register(callback) { registered.push(callback); } registerDomEvent(element, event, callback) { element.events[event] = callback; } registerMarkdownCodeBlockProcessor(_name, callback) { processor = callback; } }
Module._load = (request, parent, isMain) => request === "obsidian" ? { Plugin: MockPlugin, setIcon() {} } : originalLoad(request, parent, isMain);
global.document = { hidden: false, createElement: (tag) => new MockElement(tag), addEventListener() {}, removeEventListener() {} };
global.window = { matchMedia: () => ({ matches: false }), open() {}, setInterval: () => 1, clearInterval() { clearedIntervals += 1; }, addEventListener() {}, removeEventListener() {} };

const PluginClass = require(path.join(__dirname, "..", "obsidian-plugin", "main.js"));
const { CircularGalleryController, normalizeDashboard } = PluginClass;
const items = Array.from({ length: 12 }, (_, index) => ({ bookId: `book-${index + 1}`, title: `示例书 ${index + 1}`, author: "示例作者", readUpdateTime: 1704067200 - index, finished: index === 11, kind: "ebook" }));
const model = {
  schemaVersion: 1, generatedAt: 1704067200, source: "sample",
  periods: { weekly: { totalReadSeconds: 7200, readDays: 3, dayAverageReadSeconds: 2400, buckets: { "1704067200": 1200, "1704153600": 2400 } }, monthly: { totalReadSeconds: 21600, readDays: 8, dayAverageReadSeconds: 2700, buckets: Object.fromEntries(Array.from({ length: 12 }, (_, index) => [String(1704067200 + index * 86400), 600 + index * 60])) }, overall: { totalReadSeconds: 86400, readDays: 24, dayAverageReadSeconds: 3600, buckets: {} } },
  shelf: { items, totalEntries: 12 }, notebooks: { totalBookCount: 2, totalNoteCount: 7, books: [{ bookId: "book-1", title: "示例书 1", author: "示例作者", highlightCount: 3, reviewCount: 1, bookmarkCount: 0, noteTotal: 4 }] }, progress: [{ bookId: "book-1", progressPercent: 40, recordReadingSeconds: 3600, updatedAt: 1704067200 }],
};
const plugin = new PluginClass(); const reads = []; const openedLinks = []; let renderFailure = null;
const originalRenderError = plugin.renderError;
plugin.renderError = function capture(root, error, statePath) { renderFailure = error; return originalRenderError.call(this, root, error, statePath); };
plugin.app = { vault: { adapter: { exists: async (candidate) => candidate === ".weread/reading-board.json", read: async (candidate) => { reads.push(candidate); return JSON.stringify(model); }, getResourcePath: (candidate) => `app://local/${candidate}` } }, workspace: { openLinkText(target) { openedLinks.push(target); } } };
plugin.onload(); const host = new MockElement(); processor("", host);

setTimeout(() => {
  if (renderFailure) throw renderFailure;
  const controller = new CircularGalleryController(3);
  if (controller.previous() !== 2 || controller.next() !== 0 || controller.last() !== 2 || controller.first() !== 0) throw new Error("circular controller wraparound failed");
  controller.pause("hover"); if (controller.canAutoplay()) throw new Error("hover pause was ignored"); controller.resume("hover"); if (!controller.canAutoplay()) throw new Error("autoplay did not resume"); controller.setReducedMotion(true); if (controller.canAutoplay()) throw new Error("reduced motion did not stop autoplay");
  if (reads[0] !== ".weread/reading-board.json") throw new Error(`unexpected state path: ${reads[0]}`);
  const galleryCards = host.querySelectorAll(".weread-dashboard__gallery-cover");
  if (galleryCards.length !== 36) throw new Error(`expected 3 gallery cycles, got ${galleryCards.length}`);
  const clones = galleryCards.filter((card) => card.attrs["aria-hidden"] === "true");
  if (clones.length !== 24 || clones.some((card) => card.tabIndex !== -1 || !("inert" in card.attrs))) throw new Error("gallery clones are not inert and unfocusable");
  const viewport = host.querySelector(".weread-dashboard__gallery-viewport"); const live = host.querySelector(".weread-dashboard__live");
  viewport.events.keydown({ key: "ArrowRight", preventDefault() {} });
  if (!live.textContent.includes("示例书 2")) throw new Error("keyboard gallery navigation did not update active book");
  viewport.events.keydown({ key: "End", preventDefault() {} }); if (!live.textContent.includes("示例书 12")) throw new Error("End did not select last gallery book");
  viewport.events.keydown({ key: "Home", preventDefault() {} }); if (!live.textContent.includes("示例书 1")) throw new Error("Home did not select first gallery book");
  const beforePeriodSwitch = live.textContent; const monthly = host.querySelectorAll("button").find((button) => button.dataset.period === "monthly"); monthly.events.click();
  if (live.textContent !== beforePeriodSwitch) throw new Error("period switch reset the active gallery book");
  viewport.events.wheel({ deltaX: 30, deltaY: 0, preventDefault() {} }); if (!live.textContent.includes("示例书 2")) throw new Error("wheel gallery navigation did not work");
  let verticallyPrevented = false; viewport.events.wheel({ deltaX: 0, deltaY: 80, shiftKey: false, preventDefault() { verticallyPrevented = true; } }); if (verticallyPrevented) throw new Error("ordinary vertical wheel was trapped");
  viewport.events.pointerdown({ clientX: 100, clientY: 8, pointerId: 1 }); viewport.events.pointerup({ clientX: 20, clientY: 8, pointerId: 1 }); if (!live.textContent.includes("示例书 3")) throw new Error("pointer swipe did not navigate");
  const galleryButtons = host.querySelectorAll(".weread-dashboard__gallery-button"); const nextButton = galleryButtons[2]; const previousButton = galleryButtons[0]; const rail = host.querySelector(".weread-dashboard__gallery-rail");
  for (let index = 0; index < 10; index += 1) nextButton.events.click(); rail.events.transitionend({ propertyName: "transform" });
  if (rail.style.values["--weread-gallery-x"] !== "-2088") throw new Error("forward clone boundary did not reset to canonical cycle");
  previousButton.events.click(); rail.events.transitionend({ propertyName: "transform" }); if (rail.style.values["--weread-gallery-x"] !== "-4002") throw new Error("backward clone boundary did not reset to canonical cycle");
  const finishedModel = normalizeDashboard({ ...model, shelf: { items: [{ ...items[11], bookId: "finished", title: "已完成", finished: true }], totalEntries: 1 }, progress: [] });
  if (finishedModel.books[0].progressText !== "已读完") throw new Error("finished books were not normalized as completed");
  const v2 = normalizeDashboard({ schemaVersion: 2, generatedAt: 1704067200, source: "sample", periods: { weekly: { totalReadSeconds: 1200, dailyBuckets: {}, buckets: { "1704067200": 1200 }, readStat: [{ label: "读过", value: "1本" }], preferTimeWord: "偏好夜间阅读" }, monthly: { totalReadSeconds: 3600, dailyBuckets: {}, buckets: { "1704067200": 3600 }, rankedItems: [{ bookId: "v2-book", title: "新架构图书", author: "作者", kind: "ebook", readSeconds: 3600, deepLink: "https://weread.qq.com/web/reader/test" }], categories: [{ title: "文学", readSeconds: 1200 }], readingClock: Array.from({ length: 24 }, (_, i) => ({ hour: (i + 6) % 24, label: `${(i + 6) % 24}:00`, readSeconds: i === 0 ? 900 : i === 23 ? 1800 : 0 })), mediaMix: { readRate: 76, readSeconds: 1800, listenSeconds: 600 } }, annually: { totalReadSeconds: 7200, dailyBuckets: Object.fromEntries(Array.from({ length: 366 }, (_, i) => [String(1704067200 + i * 86400), 60])) } }, shelf: { totalEntries: 2, items: [{ bookId: "v2-book", title: "新架构图书", author: "作者", kind: "ebook" }, { bookId: "audio", title: "听书", author: "作者", kind: "audio", progressPercent: 80 }] }, progress: [{ bookId: "v2-book", progressPercent: 0 }], notebooks: { books: [{ bookId: "v2-book", title: "新架构图书", noteBreakdown: { highlights: 2, reviews: 1, bookmarks: 1 }, notePath: "阅读/新架构图书.md", recentNoteAt: 1704067200 }] }, history: { trailingMonths: Array.from({ length: 12 }, (_, i) => ({ month: `2026-${String(i + 1).padStart(2, "0")}`, readSeconds: 1800 })) } });
  if (v2.schemaVersion !== 2 || v2.books[0].title !== "新架构图书" || !v2.books[0].deepLink || v2.books[0].notePath !== "阅读/新架构图书.md") throw new Error("v2 book normalization failed");
  if (!v2.periods.weekly.days.length || !v2.periods.monthly.days.length || v2.periods.annually.days.length !== 366 || v2.periods.today.totalMinutes !== 60) throw new Error("v2 exact bucket fallback or today semantics failed");
  if (v2.history.months.length !== 12 || v2.insights.categories[0].name !== "文学" || v2.insights.readingClock.hours[0] !== 1 || v2.insights.readingClock.hours[23] !== 2 || v2.noteBooks[0].noteBreakdown.highlights !== 2) throw new Error("v2 exact analytical normalization failed");
  if (v2.books.find((book) => book.kind === "audio").progressKnown) throw new Error("audio book invented a percent progress bar");
  if (!v2.books[0].progressKnown || v2.books[0].progressText !== "0% 已读") throw new Error("known zero ebook progress was lost");
  const noteSemantics = new MockElement(); plugin.renderNoteBooks(noteSemantics, [v2.noteBooks[0], { ...v2.noteBooks[0], bookId: "no-link", title: "未导出的摘录", notePath: "" }], "notes-test");
  const noteItems = noteSemantics.querySelectorAll(".weread-dashboard__note-listitem"); const clickableNote = noteItems[0].firstChild; const staticNote = noteItems[1].firstChild;
  if (noteItems.some((item) => item.attrs.role !== "listitem") || clickableNote.tag !== "button" || clickableNote.attrs.role || clickableNote.attrs.type !== "button" || clickableNote.tabIndex === -1) throw new Error("clickable note lost native button or list semantics");
  if (staticNote.tag !== "div" || staticNote.attrs.role) throw new Error("non-clickable note has interactive semantics");
  clickableNote.events.click(); if (!openedLinks.includes("阅读/新架构图书.md")) throw new Error("native note button did not activate its link action");
  const missingActions = new MockElement(); plugin.renderBookShelf(missingActions, { ...v2.books.find((book) => book.kind === "audio"), deepLink: "", notePath: "", finished: false }, "missing"); if (missingActions.querySelectorAll("button").some((button) => !button.disabled)) throw new Error("missing link actions were not individually disabled");
  const finishedActions = new MockElement(); plugin.renderBookShelf(finishedActions, { ...v2.books[0], finished: true, deepLink: "https://weread.qq.com/web/reader/test" }, "finished"); if (!finishedActions.querySelectorAll("button")[0].textContent.includes("查看")) throw new Error("finished action incorrectly says continue reading");
  const host2 = new MockElement(); plugin.renderReady(host2, normalizeDashboard(model), ".weread/reading-board.json");
  if (host.querySelector(".weread-dashboard__live").attrs.id === host2.querySelector(".weread-dashboard__live").attrs.id) throw new Error("dashboard ids are not unique");
  plugin.disposeRender(host); if (!clearedIntervals) throw new Error("local refresh disposer did not clear its timer");
  console.log("reading-board v2 gallery harness: passed");
}, 0);
