"use strict";

const Module = require("module");
const path = require("path");

class MockElement {
  constructor(tag = "div", options = {}) {
    this.tag = tag;
    this.children = [];
    this.parentElement = null;
    this.attrs = {};
    this.dataset = {};
    this.isConnected = true;
    this.style = { setProperty() {} };
    this.tabIndex = 0;
    this.className = options.cls || "";
    this.events = {};
    if (options.text !== undefined) this.textContent = options.text;
    if (options.attr) Object.entries(options.attr).forEach(([key, value]) => this.setAttr(key, value));
  }

  createDiv(options = {}) { return this.appendChild(new MockElement("div", options)); }
  createSpan(options = {}) { return this.appendChild(new MockElement("span", options)); }
  createEl(tag, options = {}) { return this.appendChild(new MockElement(tag, options)); }
  appendChild(child) { child.parentElement = this; this.children.push(child); return child; }
  append(...children) { children.forEach((child) => this.appendChild(child)); }
  empty() { this.children = []; }
  setAttr(key, value) {
    this.attrs[key] = String(value);
    if (key.startsWith("data-")) this.dataset[key.slice(5).replace(/-([a-z])/g, (_, letter) => letter.toUpperCase())] = String(value);
  }
  setAttribute(key, value) { this.setAttr(key, value); }
  toggleClass() {}
  addClass() {}
  focus() {}
  scrollBy() {}
  querySelectorAll(selector) {
    const matches = [];
    const visit = (element) => element.children.forEach((child) => {
      if (selector === "button" && child.tag === "button") matches.push(child);
      visit(child);
    });
    visit(this);
    return matches;
  }
  querySelector(selector) {
    const match = /\[data-period="([^"]+)"\]/.exec(selector);
    return match ? this.querySelectorAll("button").find((button) => button.dataset.period === match[1]) || null : null;
  }
}

const originalLoad = Module._load;
let processor;
class MockPlugin {
  register() {}
  registerDomEvent(element, event, callback) { element.events[event] = callback; }
  registerMarkdownCodeBlockProcessor(_name, callback) { processor = callback; }
}

Module._load = (request, parent, isMain) => request === "obsidian" ? { Plugin: MockPlugin, setIcon() {} } : originalLoad(request, parent, isMain);
global.document = { createElement: (tag) => new MockElement(tag) };

const PluginClass = require(path.join(__dirname, "..", "obsidian-plugin", "main.js"));
const sampleItems = Array.from({ length: 5 }, (_, index) => ({
  bookId: `sample-book-${index + 1}`,
  title: `示例书 ${index + 1}`,
  author: "示例作者",
  readUpdateTime: 1704067200 - index,
  finished: false,
  kind: "ebook",
}));
const monthlyBuckets = Object.fromEntries(Array.from({ length: 12 }, (_, index) => [String(1704067200 + index * 86400), 600 + index * 60]));
const model = {
  schemaVersion: 1,
  generatedAt: 1704067200,
  source: "sample",
  periods: {
    weekly: { totalReadSeconds: 7200, readDays: 3, dayAverageReadSeconds: 2400, buckets: { "1704067200": 1200, "1704153600": 2400 } },
    monthly: { totalReadSeconds: 21600, readDays: 8, dayAverageReadSeconds: 2700, buckets: monthlyBuckets },
    overall: { totalReadSeconds: 86400, readDays: 24, dayAverageReadSeconds: 3600, buckets: {} },
  },
  shelf: { items: sampleItems, totalEntries: 5 },
  notebooks: { totalBookCount: 2, totalNoteCount: 7, books: [{ bookId: "sample-book-1", title: "示例书 1", author: "示例作者", highlightCount: 3, reviewCount: 1, bookmarkCount: 0, noteTotal: 4 }] },
  progress: [{ bookId: "sample-book-1", progressPercent: 40, recordReadingSeconds: 3600, updatedAt: 1704067200 }],
};

const plugin = new PluginClass();
const reads = [];
let renderFailure = null;
const originalRenderError = plugin.renderError;
plugin.renderError = function captureRenderFailure(root, error, statePath) {
  renderFailure = error;
  return originalRenderError.call(this, root, error, statePath);
};
plugin.app = {
  vault: {
    adapter: {
      exists: async (candidate) => candidate === ".weread/reading-board.json",
      read: async (candidate) => { reads.push(candidate); return JSON.stringify(model); },
      getResourcePath: (candidate) => `app://local/${candidate}`,
    },
  },
  workspace: { openLinkText() {} },
};
plugin.onload();
const host = new MockElement();
processor("", host);

setTimeout(() => {
  const images = [];
  const text = [];
  const walk = (element) => {
    if (element.tag === "img") images.push(element.attrs.src);
    if (element.textContent !== undefined) text.push(String(element.textContent));
    element.children.forEach(walk);
  };
  walk(host);
  const monthlyControl = host.querySelectorAll("button").find((button) => button.dataset.period === "monthly");
  monthlyControl.events.click();
  const classesAfterPeriodChange = [];
  const findClasses = (element) => {
    if (element.className) classesAfterPeriodChange.push(element.className);
    element.children.forEach(findClasses);
  };
  findClasses(host);
  if (renderFailure) throw renderFailure;
  const expectedCovers = [1, 2, 3, 4, 5].map((index) => `app://local/.weread/covers/sample-${String(index).padStart(2, "0")}.webp`);
  if (reads[0] !== ".weread/reading-board.json") throw new Error(`unexpected state path: ${reads[0]}`);
  if (!expectedCovers.every((cover) => images.includes(cover))) throw new Error(`sample covers missing: ${images.join(", ")}`);
  if (!text.includes("40% 已读")) throw new Error("progress was not joined by bookId");
  if (!text.includes("笔记较多的书")) throw new Error("notebook aggregate section was not rendered");
  if (text.includes("最近" + "笔记")) throw new Error("unsupported recent-note UI was rendered");
  if (!text.includes("读取本地数据")) throw new Error("local-only refresh copy was not rendered");
  if (!classesAfterPeriodChange.includes("weread-dashboard__chart-viewport is-scrollable")) throw new Error("monthly chart did not become horizontally scrollable");
  if (host.querySelectorAll("button").some((button) => button.attrs.role === "listitem")) throw new Error("a book button was assigned the listitem role");
  console.log("reading-board canonical schema harness: passed");
}, 0);
