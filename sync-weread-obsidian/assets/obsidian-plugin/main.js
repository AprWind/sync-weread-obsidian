const { Plugin, setIcon } = require("obsidian");

const DASHBOARD_PATH = ".weread/reading-board.json";
const STALE_AFTER_MS = 36 * 60 * 60 * 1000;
const PERIODS = [
  { id: "monthly", label: "本月" },
  { id: "weekly", label: "本周" },
  { id: "today", label: "今天" },
  { id: "annually", label: "年度" },
];
let dashboardInstance = 0;

/** A DOM-independent state model for the rail. */
class CircularGalleryController {
  constructor(count, options = {}) {
    this.count = Math.max(0, Number(count) || 0);
    this.activeIndex = this.count ? modulo(options.activeIndex || 0, this.count) : 0;
    this.reducedMotion = Boolean(options.reducedMotion);
    this.autoplayEnabled = options.autoplay !== false && !this.reducedMotion;
    this.pauses = new Set();
  }

  select(index) { if (this.count) this.activeIndex = modulo(index, this.count); return this.activeIndex; }
  next() { return this.select(this.activeIndex + 1); }
  previous() { return this.select(this.activeIndex - 1); }
  first() { return this.select(0); }
  last() { return this.select(this.count - 1); }
  physicalIndex(cycle = 1) { return this.count * cycle + this.activeIndex; }
  pause(reason) { if (reason) this.pauses.add(reason); }
  resume(reason) { if (reason) this.pauses.delete(reason); }
  toggleAutoplay() { if (!this.reducedMotion) this.autoplayEnabled = !this.autoplayEnabled; return this.autoplayEnabled; }
  canAutoplay() { return this.count > 1 && this.autoplayEnabled && !this.reducedMotion && this.pauses.size === 0; }
  setReducedMotion(value) { this.reducedMotion = Boolean(value); if (this.reducedMotion) this.autoplayEnabled = false; }
}

class WeReadReadingBoardPlugin extends Plugin {
  onload() {
    this.unloaded = false;
    this.renderDisposers = new WeakMap();
    this.allRenderDisposers = new Set();
    this.register(() => { this.unloaded = true; this.disposeAllRenders(); });
    this.registerMarkdownCodeBlockProcessor("weread-dashboard", (source, el) => {
      const requestedPath = source.trim().split(/\r?\n/)[0] || DASHBOARD_PATH;
      void this.renderDashboard(el, requestedPath);
    });
  }

  onunload() { this.unloaded = true; this.disposeAllRenders(); }

  async renderDashboard(container, requestedPath) {
    this.disposeRender(container);
    const path = normalizeDashboardPath(requestedPath);
    const root = this.createRoot(container, "loading");
    this.renderLoading(root);
    try {
      const data = await this.readDashboard(path);
      if (!this.unloaded && root.isConnected) this.renderReady(root, data, path);
    } catch (error) {
      if (!this.unloaded && root.isConnected) this.renderError(root, error, path);
    }
  }

  registerRender(container, dispose) { this.renderDisposers.set(container, dispose); this.allRenderDisposers.add(dispose); }
  disposeRender(container) { const dispose = this.renderDisposers && this.renderDisposers.get(container); if (dispose) { dispose(); this.renderDisposers.delete(container); this.allRenderDisposers.delete(dispose); } }
  disposeAllRenders() { if (this.allRenderDisposers) this.allRenderDisposers.forEach((dispose) => dispose()); if (this.allRenderDisposers) this.allRenderDisposers.clear(); }

  createRoot(container, state) {
    container.empty();
    const root = container.createDiv({ cls: "weread-dashboard" });
    root.setAttr("data-weread-state", state);
    return root;
  }

  async readDashboard(path) {
    if (!this.app.vault.adapter.exists || !(await this.app.vault.adapter.exists(path))) {
      const error = new Error("找不到数据文件"); error.code = "ENOENT"; throw error;
    }
    return normalizeDashboard(JSON.parse(await this.app.vault.adapter.read(path)));
  }

  renderLoading(root) {
    root.empty(); root.setAttr("data-weread-state", "loading");
    const header = root.createDiv({ cls: "weread-dashboard__header weread-dashboard__skeleton-header" });
    header.createDiv({ cls: "weread-dashboard__skeleton weread-dashboard__skeleton--title" });
    header.createDiv({ cls: "weread-dashboard__skeleton weread-dashboard__skeleton--action" });
    root.createDiv({ cls: "weread-dashboard__skeleton weread-dashboard__skeleton--gallery" });
  }

  renderReady(root, dashboard, path) {
    root.empty();
    root.setAttr("data-weread-state", getDashboardState(dashboard));
    const instanceId = `weread-board-${++dashboardInstance}`;
    const live = root.createDiv({ cls: "weread-dashboard__live", attr: { id: `${instanceId}-live`, "aria-live": "polite", "aria-atomic": "true" } });
    const header = root.createDiv({ cls: "weread-dashboard__header" });
    const heading = header.createDiv({ cls: "weread-dashboard__heading" });
    heading.createEl("h2", { text: "阅读看板" });
    const freshness = heading.createEl("p", { cls: "weread-dashboard__freshness", text: freshnessText(dashboard, getDashboardState(dashboard)) });
    if (dashboard.sample) freshness.createSpan({ cls: "weread-dashboard__state-tag", text: "示例数据" });
    const refresh = this.iconButton("重新读取本地数据", "refresh-cw", "weread-dashboard__refresh");
    refresh.setAttr("title", "读取本地 reading-board.json，不会同步网络");
    refresh.createSpan({ cls: "weread-dashboard__refresh-text", text: "读取本地数据" });
    this.registerDomEvent(refresh, "click", () => void this.renderDashboard(root.parentElement, path));
    header.appendChild(refresh);

    if (getDashboardState(dashboard) === "empty") { this.renderEmpty(root); return; }
    const galleryState = this.renderGallery(root, dashboard, instanceId, live);
    this.registerRender(root.parentElement || root, galleryState.dispose);
    const controls = root.createDiv({ cls: "weread-dashboard__periods", attr: { role: "radiogroup", "aria-label": "阅读数据时间范围" } });
    const panels = root.createDiv({ cls: "weread-dashboard__analytics" });
    const updatePeriod = (next) => {
      controls.querySelectorAll("button").forEach((button) => {
        const selected = button.dataset.period === next;
        button.setAttr("aria-checked", String(selected)); button.toggleClass("is-selected", selected); button.tabIndex = selected ? 0 : -1;
      });
      // The gallery controller lives outside this subtree, so period changes retain activeIndex.
      this.renderPeriodPanels(panels, dashboard, next, instanceId);
      galleryState.controller.resume("period-switch");
    };
    PERIODS.forEach((period, index) => {
      const button = controls.createEl("button", { cls: `weread-dashboard__period${index === 0 ? " is-selected" : ""}`, text: period.label, attr: { type: "button", role: "radio", "aria-checked": String(index === 0), "data-period": period.id } });
      button.tabIndex = index === 0 ? 0 : -1;
      this.registerDomEvent(button, "click", () => updatePeriod(period.id));
      this.registerDomEvent(button, "keydown", (event) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        const at = PERIODS.findIndex((item) => item.id === period.id);
        const target = event.key === "Home" ? 0 : event.key === "End" ? PERIODS.length - 1 : modulo(at + (event.key === "ArrowRight" ? 1 : -1), PERIODS.length);
        updatePeriod(PERIODS[target].id); controls.querySelector(`[data-period="${PERIODS[target].id}"]`).focus();
      });
    });
    updatePeriod("monthly");
  }

  renderGallery(parent, dashboard, instanceId, live) {
    const books = dashboard.books;
    const controller = new CircularGalleryController(books.length, { reducedMotion: reducedMotion() });
    const section = parent.createEl("section", { cls: "weread-dashboard__gallery", attr: { "aria-labelledby": `${instanceId}-gallery-title` } });
    const header = section.createDiv({ cls: "weread-dashboard__gallery-header" });
    const titleGroup = header.createDiv();
    titleGroup.createEl("h3", { text: "循环书架", attr: { id: `${instanceId}-gallery-title` } });
    titleGroup.createEl("p", { cls: "weread-dashboard__gallery-caption", text: "滑动、拖拽或用方向键浏览" });
    const actions = header.createDiv({ cls: "weread-dashboard__gallery-actions" });
    const previous = this.iconButton("上一册", "chevron-left", "weread-dashboard__gallery-button");
    const play = this.iconButton("暂停自动浏览", "pause", "weread-dashboard__gallery-button weread-dashboard__gallery-play");
    const next = this.iconButton("下一册", "chevron-right", "weread-dashboard__gallery-button");
    const counter = actions.createSpan({ cls: "weread-dashboard__gallery-counter", text: `1 / ${books.length}` });
    actions.append(previous, play, next, counter);
    if (controller.reducedMotion || books.length < 2) { play.disabled = true; play.setAttr("aria-label", "自动浏览已关闭"); }
    const viewport = section.createDiv({ cls: "weread-dashboard__gallery-viewport", attr: { tabindex: "0", role: "region", "aria-roledescription": "循环书籍画廊", "aria-label": "循环书籍画廊。可用左右方向键浏览" } });
    const rail = viewport.createDiv({ cls: "weread-dashboard__gallery-rail" });
    const detail = section.createDiv({ cls: "weread-dashboard__book-shelf" });
    const cycle = books.length > 1 ? 3 : 1;
    const physicalBooks = [];
    for (let pass = 0; pass < cycle; pass += 1) books.forEach((book, index) => physicalBooks.push({ book, index, clone: cycle > 1 && pass !== 1, pass }));
    physicalBooks.forEach((entry) => this.renderGalleryCover(rail, entry, instanceId));
    const cards = Array.from(rail.children);
    let physicalIndex = controller.physicalIndex();
    let resetHandle = null;
    let transitionFallback = null;
    let observer = null;
    let resizeObserver = null;
    const setPosition = (animate) => {
      const width = Math.max(132, Math.min(168, Math.round(viewport.clientWidth / 4.7) || 156));
      const gap = 12;
      const stride = width + gap;
      rail.style.setProperty("--weread-cover-unit", `${width}px`);
      rail.style.setProperty("--weread-gallery-gap", `${gap}px`);
      rail.style.setProperty("--weread-gallery-pad", `${Math.max(0, Math.round(viewport.clientWidth / 2 - width / 2))}px`);
      rail.style.setProperty("--weread-gallery-x", String(-(physicalIndex * stride)));
      rail.toggleClass("is-instant", !animate || controller.reducedMotion);
      cards.forEach((card, cardPosition) => {
        const logical = Number(card.dataset.logicalIndex);
        card.toggleClass("is-active", logical === controller.activeIndex && cardPosition === physicalIndex);
      });
      counter.textContent = `${controller.activeIndex + 1} / ${books.length}`;
    };
    const renderDetail = () => {
      detail.empty();
      const book = books[controller.activeIndex];
      if (!book) return;
      this.renderBookShelf(detail, book, instanceId);
      live.textContent = `当前书籍：《${book.title}》${book.author ? `，${book.author}` : ""}`;
    };
    const change = (action, animate = true) => { action(); physicalIndex = controller.physicalIndex(); setPosition(animate); renderDetail(); };
    const resetToCanonical = () => {
      if (!resetHandle && !transitionFallback) return;
      if (resetHandle) { clearTimeout(resetHandle); resetHandle = null; }
      if (transitionFallback) { clearTimeout(transitionFallback); transitionFallback = null; }
      physicalIndex = controller.physicalIndex(); setPosition(false);
    };
    const move = (direction) => {
      if (books.length < 2) return;
      resetToCanonical();
      direction > 0 ? controller.next() : controller.previous();
      physicalIndex += direction;
      setPosition(true); renderDetail();
      const edge = direction > 0 ? physicalIndex === books.length * 2 : physicalIndex === books.length - 1;
      if (edge) {
        resetHandle = true;
        transitionFallback = setTimeout(resetToCanonical, controller.reducedMotion ? 0 : 520);
      }
    };
    const select = (index) => change(() => controller.select(index));
    cards.forEach((card) => this.registerDomEvent(card, "click", () => select(Number(card.dataset.logicalIndex))));
    this.registerDomEvent(previous, "click", () => move(-1));
    this.registerDomEvent(next, "click", () => move(1));
    this.registerDomEvent(rail, "transitionend", (event) => { if (!event.propertyName || event.propertyName === "transform") resetToCanonical(); });
    this.registerDomEvent(play, "click", () => {
      const enabled = controller.toggleAutoplay();
      play.setAttr("aria-label", enabled ? "暂停自动浏览" : "开始自动浏览");
      const holder = play.firstChild; if (holder) setIcon(holder, enabled ? "pause" : "play");
      play.setAttr("data-autoplay", enabled ? "playing" : "paused");
    });
    this.registerDomEvent(viewport, "mouseenter", () => controller.pause("hover"));
    this.registerDomEvent(viewport, "mouseleave", () => controller.resume("hover"));
    this.registerDomEvent(viewport, "focusin", () => controller.pause("focus"));
    this.registerDomEvent(viewport, "focusout", () => controller.resume("focus"));
    this.registerDomEvent(viewport, "keydown", (event) => {
      if (["ArrowLeft", "ArrowRight"].includes(event.key)) { event.preventDefault(); move(event.key === "ArrowRight" ? 1 : -1); return; }
      const methods = { Home: () => controller.first(), End: () => controller.last() };
      if (!methods[event.key]) return; event.preventDefault(); change(methods[event.key]);
    });
    this.registerDomEvent(viewport, "wheel", (event) => {
      const horizontal = Math.abs(event.deltaX) > Math.abs(event.deltaY) || event.shiftKey;
      if (!horizontal || Math.abs(event.deltaX || event.deltaY) < 16) return;
      event.preventDefault(); move((event.deltaX || event.deltaY) > 0 ? 1 : -1);
    });
    let drag = null;
    this.registerDomEvent(viewport, "pointerdown", (event) => { drag = { x: event.clientX, y: event.clientY, id: event.pointerId }; controller.pause("drag"); if (viewport.setPointerCapture) viewport.setPointerCapture(event.pointerId); });
    this.registerDomEvent(viewport, "pointerup", (event) => {
      if (!drag) return; const dx = event.clientX - drag.x; const dy = event.clientY - drag.y;
      if (Math.abs(dx) > 34 && Math.abs(dx) > Math.abs(dy)) move(dx < 0 ? 1 : -1);
      drag = null; controller.resume("drag");
    });
    this.registerDomEvent(viewport, "pointercancel", () => { drag = null; controller.resume("drag"); });
    if (typeof IntersectionObserver !== "undefined") {
      observer = new IntersectionObserver((entries) => entries.forEach((entry) => entry.isIntersecting ? controller.resume("offscreen") : controller.pause("offscreen")), { threshold: 0.15 });
      observer.observe(section);
    }
    if (typeof document !== "undefined" && document.addEventListener) {
      const visibility = () => document.hidden ? controller.pause("hidden") : controller.resume("hidden");
      document.addEventListener("visibilitychange", visibility);
      var visibilityDisposer = () => document.removeEventListener("visibilitychange", visibility);
    }
    const resize = () => setPosition(false);
    if (typeof ResizeObserver !== "undefined") { resizeObserver = new ResizeObserver(resize); resizeObserver.observe(viewport); }
    else if (typeof window !== "undefined" && window.addEventListener) { window.addEventListener("resize", resize); var windowResizeDisposer = () => window.removeEventListener("resize", resize); }
    const timer = window.setInterval(() => { if (controller.canAutoplay()) move(1); }, 4400);
    setPosition(false); renderDetail();
    return { controller, viewport, setPosition, dispose: () => { if (resetHandle || transitionFallback) resetToCanonical(); window.clearInterval(timer); if (observer) observer.disconnect(); if (resizeObserver) resizeObserver.disconnect(); if (visibilityDisposer) visibilityDisposer(); if (windowResizeDisposer) windowResizeDisposer(); } };
  }

  renderGalleryCover(rail, entry, instanceId) {
    const { book, index, clone, pass } = entry;
    const card = rail.createEl("button", { cls: "weread-dashboard__gallery-cover", attr: { type: "button", "data-logical-index": String(index), "data-pass": String(pass), "aria-label": clone ? "" : `选择《${book.title}》` } });
    if (clone) { card.setAttr("aria-hidden", "true"); card.setAttr("inert", ""); card.tabIndex = -1; }
    else card.setAttr("aria-describedby", `${instanceId}-live`);
    const cover = card.createDiv({ cls: "weread-dashboard__cover weread-dashboard__cover--gallery" });
    this.appendCover(cover, book, clone ? "" : `${book.title}封面`);
    card.createSpan({ cls: "weread-dashboard__gallery-cover-title", text: book.title, attr: { "aria-hidden": "true" } });
    card.createSpan({ cls: "weread-dashboard__gallery-cover-meta", text: [book.kind === "audio" ? "听书" : "电子书", book.readingText].filter(Boolean).join(" · "), attr: { "aria-hidden": "true" } });
  }

  renderBookShelf(parent, book, instanceId) {
    const cover = parent.createDiv({ cls: "weread-dashboard__cover weread-dashboard__shelf-cover" });
    this.appendCover(cover, book, `${book.title}封面`);
    const copy = parent.createDiv({ cls: "weread-dashboard__shelf-copy" });
    copy.createEl("h4", { text: book.title, attr: { id: `${instanceId}-active-book` } });
    copy.createEl("p", { cls: "weread-dashboard__book-author", text: book.author || "作者信息待同步" });
    const facts = copy.createDiv({ cls: "weread-dashboard__book-facts", attr: { role: "list", "aria-label": `${book.title} 的阅读信息` } });
    [["类型", book.kind === "audio" ? "听书" : "电子书"], ["状态", book.finished ? "已读完" : "阅读中"], ["阅读", book.readingText || "阅读时长待同步"], ["最近", book.lastReadText || "最近阅读时间待同步"]].forEach(([label, value]) => {
      const fact = facts.createDiv({ attr: { role: "listitem" } }); fact.createSpan({ text: label }); fact.createEl("strong", { text: value });
    });
    if (book.progressKnown) { const progress = copy.createDiv({ cls: "weread-dashboard__progress", attr: { role: "progressbar", "aria-label": `${book.title}阅读进度`, "aria-valuemin": "0", "aria-valuemax": "100", "aria-valuenow": String(book.finished ? 100 : book.progressPercent) } }); const fill = progress.createSpan(); fill.style.setProperty("--weread-progress", `${book.finished ? 100 : book.progressPercent}%`); copy.createSpan({ cls: "weread-dashboard__progress-label", text: book.finished ? "已读完" : book.progressText }); }
    const noteBreakdown = copy.createDiv({ cls: "weread-dashboard__note-breakdown", attr: { role: "list", "aria-label": "笔记构成" } }); [["划线", book.noteBreakdown.highlights], ["想法", book.noteBreakdown.reviews], ["书签", book.noteBreakdown.bookmarks]].forEach(([label, value]) => noteBreakdown.createSpan({ text: `${label} ${formatNumber(value)}`, attr: { role: "listitem" } }));
    const actions = copy.createDiv({ cls: "weread-dashboard__book-actions" });
    const open = actions.createEl("button", { cls: "weread-dashboard__book-action is-primary", text: book.deepLink ? (book.finished ? "在微信读书查看" : "继续阅读") : "微信读书入口未同步", attr: { type: "button" } });
    if (book.deepLink) {
      this.registerDomEvent(open, "click", () => openSafeUrl(book.deepLink));
    } else { open.disabled = true; open.setAttr("title", "本次同步未提供微信读书链接"); }
    const resolvedNotePath = book.notePath || this.findExistingNotePath(book);
    const note = actions.createEl("button", { cls: "weread-dashboard__book-action", text: resolvedNotePath ? "打开 Obsidian 笔记" : "Obsidian 笔记未导出", attr: { type: "button" } });
    if (resolvedNotePath) {
      this.registerDomEvent(note, "click", () => this.app.workspace.openLinkText(resolvedNotePath, "", false));
    } else { note.disabled = true; note.setAttr("title", "尚未找到此书的本地笔记"); }
  }

  findExistingNotePath(book) { const path = `20-认知记录/阅读笔记/${safeExportNoteFilename(book.title, book.bookId)}`; try { return this.app.vault.getAbstractFileByPath && this.app.vault.getAbstractFileByPath(path) ? path : ""; } catch (_) { return ""; } }

  appendCover(parent, book, alt) {
    const url = this.resolveCoverUrl(book.coverRef);
    if (url) {
      const image = parent.createEl("img", { attr: { src: url, alt, loading: "lazy" } });
      this.registerDomEvent(image, "error", () => parent.addClass("is-missing"));
    } else parent.addClass("is-missing");
    const placeholder = parent.createDiv({ cls: "weread-dashboard__cover-placeholder", attr: { "aria-hidden": "true" } }); setIcon(placeholder, "book-open");
  }

  renderPeriodPanels(parent, dashboard, period, instanceId) {
    parent.empty();
    const trend = dashboard.periods[period] || dashboard.periods.monthly || dashboard.periods.weekly;
    const top = parent.createDiv({ cls: "weread-dashboard__analytics-top" });
    this.renderReadingCalendar(top, trend, period, instanceId);
    this.renderTrend(top, dashboard, trend, period, instanceId);
    const lower = parent.createDiv({ cls: "weread-dashboard__analytics-lower" });
    this.renderInsights(lower, dashboard, instanceId);
    this.renderNoteBooks(lower, dashboard.noteBooks, instanceId);
  }

  renderReadingCalendar(parent, trend, period, instanceId) {
    const section = parent.createEl("section", { cls: "weread-dashboard__surface weread-dashboard__calendar", attr: { "aria-labelledby": `${instanceId}-calendar` } });
    const heading = section.createDiv({ cls: "weread-dashboard__section-heading" }); heading.createEl("h3", { text: "阅读日历", attr: { id: `${instanceId}-calendar` } }); heading.createSpan({ cls: "weread-dashboard__unit", text: periodLabel(period) });
    const total = section.createDiv({ cls: "weread-dashboard__metric" }); total.createEl("strong", { text: formatNumber(trend.totalMinutes) }); total.createSpan({ text: "分钟" });
    section.createEl("p", { cls: "weread-dashboard__average", text: trend.readDays ? `${formatNumber(trend.readDays)} 天有阅读 · 日均 ${formatNumber(trend.averageMinutes)} 分钟` : "这段时间还没有阅读记录" });
    const days = trend.days.length ? trend.days : emptyDays(28);
    const max = Math.max(1, ...days.map((day) => day.minutes));
    const grid = section.createDiv({ cls: `weread-dashboard__heatmap${period === "annually" ? " is-annual" : ""}`, attr: { role: "list", "aria-label": "阅读日历" } });
    grid.style.setProperty("--weread-heatmap-count", String(days.length));
    days.forEach((day) => { const cell = grid.createDiv({ cls: "weread-dashboard__heatmap-cell", attr: { role: "listitem", "aria-label": `${day.label} ${formatNumber(day.minutes)} 分钟` } }); cell.style.setProperty("--weread-level", String(Math.min(4, Math.ceil((day.minutes / max) * 4)))); cell.createSpan({ text: day.shortLabel || day.label }); });
    if (trend.readStat.length || trend.preferTimeWord || trend.preferCategoryWord) { const strip = section.createDiv({ cls: "weread-dashboard__read-stat", attr: { role: "list", "aria-label": "本周期阅读摘要" } }); trend.readStat.forEach((item) => strip.createSpan({ text: `${item.label}${item.value ? ` ${item.value}` : ""}`, attr: { role: "listitem" } })); [trend.preferTimeWord, trend.preferCategoryWord].filter(Boolean).forEach((value) => strip.createSpan({ text: value, attr: { role: "listitem" } })); }
  }

  renderTrend(parent, dashboard, trend, period, instanceId) {
    const section = parent.createEl("section", { cls: "weread-dashboard__surface weread-dashboard__trend", attr: { "aria-labelledby": `${instanceId}-trend` } });
    const heading = section.createDiv({ cls: "weread-dashboard__section-heading" }); heading.createEl("h3", { text: period === "annually" ? "十二个月" : "阅读走势", attr: { id: `${instanceId}-trend` } }); heading.createSpan({ cls: "weread-dashboard__unit", text: "分钟" });
    const points = period === "annually" && dashboard.history.months.length ? dashboard.history.months : trend.days;
    const max = Math.max(1, ...points.map((point) => point.minutes));
    const chart = section.createDiv({ cls: "weread-dashboard__trend-chart", attr: { role: "list", "aria-label": "阅读时长走势" } });
    chart.style.setProperty("--weread-trend-count", String(points.length));
    points.forEach((point) => { const item = chart.createDiv({ cls: "weread-dashboard__trend-point", attr: { role: "listitem", "aria-label": `${point.label} ${formatNumber(point.minutes)} 分钟` } }); const bar = item.createDiv({ cls: "weread-dashboard__trend-bar" }); bar.style.setProperty("--weread-bar-height", `${Math.max(3, Math.round((point.minutes / max) * 100))}%`); item.createSpan({ text: point.shortLabel || point.label }); });
    if (!points.some((point) => point.minutes)) section.createEl("p", { cls: "weread-dashboard__quiet-copy", text: "同步后会逐渐形成阅读趋势。" });
  }

  renderInsights(parent, dashboard, instanceId) {
    const section = parent.createEl("section", { cls: "weread-dashboard__surface weread-dashboard__insights", attr: { "aria-labelledby": `${instanceId}-insights` } });
    section.createEl("h3", { text: "阅读习惯", attr: { id: `${instanceId}-insights` } });
    const body = section.createDiv({ cls: "weread-dashboard__insight-body" });
    const clock = body.createDiv({ cls: "weread-dashboard__clock", attr: { role: "img", "aria-label": dashboard.insights.readingClock.label } });
    dashboard.insights.readingClock.hours.forEach((value, index) => { const dot = clock.createSpan({ cls: "weread-dashboard__clock-dot" }); dot.style.setProperty("--weread-clock-level", String(value)); dot.style.setProperty("--weread-clock-index", String(index)); });
    const text = body.createDiv(); text.createEl("strong", { text: dashboard.insights.readingClock.label });
    const categories = dashboard.insights.categories;
    if (categories.length) { const list = text.createDiv({ cls: "weread-dashboard__categories", attr: { role: "list", "aria-label": "阅读分类" } }); categories.slice(0, 3).forEach((category) => list.createSpan({ text: `${category.name} ${formatNumber(category.minutes)} 分钟`, attr: { role: "listitem" } })); }
    const mix = dashboard.insights.mediaMix; text.createEl("p", { cls: "weread-dashboard__quiet-copy", text: mix.label });
  }

  renderNoteBooks(parent, noteBooks, instanceId) {
    const section = parent.createEl("section", { cls: "weread-dashboard__surface weread-dashboard__notes", attr: { "aria-labelledby": `${instanceId}-notes` } }); section.createEl("h3", { text: "最近的摘录", attr: { id: `${instanceId}-notes` } });
    if (!noteBooks.length) { section.createEl("p", { cls: "weread-dashboard__quiet-copy", text: "同步后会显示最近有摘录的书，而不会读取笔记正文。" }); return; }
    const list = section.createDiv({ cls: "weread-dashboard__note-list", attr: { role: "list", "aria-label": "最近有摘录的书" } });
    noteBooks.slice(0, 5).forEach((book) => { const item = list.createDiv({ cls: "weread-dashboard__note-listitem", attr: { role: "listitem" } }); const row = book.notePath ? item.createEl("button", { cls: "weread-dashboard__note", attr: { type: "button", "aria-label": `打开《${book.title}》的 Obsidian 笔记` } }) : item.createDiv({ cls: "weread-dashboard__note" }); const icon = row.createDiv({ cls: "weread-dashboard__note-icon", attr: { "aria-hidden": "true" } }); setIcon(icon, "highlighter"); const body = row.createDiv({ cls: "weread-dashboard__note-body" }); body.createEl("strong", { text: book.title }); body.createSpan({ text: book.author || "作者信息待同步" }); row.createSpan({ cls: "weread-dashboard__note-time", text: `${formatNumber(book.noteTotal)} 条` }); if (book.notePath) this.registerDomEvent(row, "click", () => this.app.workspace.openLinkText(book.notePath, "", false)); });
  }

  renderEmpty(root) { const empty = root.createEl("section", { cls: "weread-dashboard__empty", attr: { "aria-label": "暂无阅读数据" } }); const icon = empty.createDiv({ cls: "weread-dashboard__empty-icon", attr: { "aria-hidden": "true" } }); setIcon(icon, "book-open"); empty.createEl("h3", { text: "还没有可展示的阅读记录" }); empty.createEl("p", { text: "完成一次同步后，封面书廊、阅读日历与笔记摘要会显示在这里。" }); }
  renderError(root, error, path) { root.empty(); root.setAttr("data-weread-state", "error"); const section = root.createEl("section", { cls: "weread-dashboard__error", attr: { role: "alert" } }); const icon = section.createDiv({ cls: "weread-dashboard__error-icon", attr: { "aria-hidden": "true" } }); setIcon(icon, error && error.code === "ENOENT" ? "folder-search" : "circle-alert"); section.createEl("h3", { text: error && error.code === "ENOENT" ? "尚未找到阅读数据" : "阅读数据无法读取" }); section.createEl("p", { text: error && error.code === "ENOENT" ? `请先运行同步命令，生成 ${path}。` : "请检查 reading-board.json 格式后重新读取。已有笔记不会被修改。" }); const retry = this.iconButton("重新读取", "refresh-cw", "weread-dashboard__retry"); this.registerDomEvent(retry, "click", () => void this.renderDashboard(root.parentElement, path)); section.appendChild(retry); }
  iconButton(label, icon, cls) { const button = document.createElement("button"); button.type = "button"; button.className = cls; button.setAttribute("aria-label", label); const holder = document.createElement("span"); holder.setAttribute("aria-hidden", "true"); setIcon(holder, icon); button.appendChild(holder); return button; }
  resolveCoverUrl(reference) { if (!reference) return ""; if (reference.kind === "remote") return reference.value; if (reference.kind !== "vault" || !this.app.vault.adapter.getResourcePath) return ""; try { return this.app.vault.adapter.getResourcePath(reference.value); } catch (_) { return ""; } }
}

function normalizeDashboard(input) {
  const root = record(input); const sourcePeriods = record(root.periods); const isSample = Boolean(root.sample || root.isSample || root.source === "sample" || record(root.meta).sample);
  const periods = { weekly: normalizePeriod(sourcePeriods.weekly), monthly: normalizePeriod(sourcePeriods.monthly), annually: normalizePeriod(sourcePeriods.annually || sourcePeriods.annual, 366), overall: normalizePeriod(sourcePeriods.overall) };
  periods.today = normalizeToday(sourcePeriods.today, periods.monthly, periods.weekly, root.generatedAt, isSample);
  const shelf = record(root.shelf); const notebooks = record(root.notebooks); const notes = array(notebooks.books).map(normalizeNotebookBook).filter(Boolean); const noteMap = new Map(notes.map((book) => [book.bookId, book]));
  const progressMap = new Map(array(root.progress).map((entry) => [textValue(record(entry).bookId), record(entry)]));
  const ranked = chooseRankedItems(periods, shelf); const shelfItems = array(shelf.items).map(record).filter((item) => textValue(item.bookId) && textValue(item.title));
  const preferred = (ranked.length ? ranked : shelfItems).filter((item) => textValue(item.title));
  const bookMap = new Map(); preferred.concat(shelfItems).forEach((book) => { const id = textValue(book.bookId || book.id); if (id && !bookMap.has(id)) bookMap.set(id, book); });
  const books = Array.from(bookMap.values()).map((book, index) => normalizeBook(book, progressMap.get(textValue(book.bookId || book.id)), noteMap.get(textValue(book.bookId || book.id)), index, isSample)).sort((a, b) => b.rankSeconds - a.rankSeconds || b.lastReadAt - a.lastReadAt).slice(0, 12);
  const history = record(root.history);
  return { schemaVersion: numberValue(root.schemaVersion) || 1, updatedAt: unixDateValue(root.generatedAt || root.updatedAt), sample: isSample, periods, books, noteBooks: notes.sort((a, b) => b.recentAt - a.recentAt || b.noteTotal - a.noteTotal), history: { months: normalizeMonths(history.trailingMonths || history.months) }, insights: normalizeInsights(root, periods.monthly), summary: { completedBooks: shelfItems.filter((item) => item.finished === true || item.status === "finished").length, shelfCount: numberValue(shelf.totalEntries) || shelfItems.length, noteCount: numberValue(notebooks.totalNoteCount), noteBookCount: numberValue(notebooks.totalBookCount) } };
}

function chooseRankedItems(periods, shelf) { return array(periods.monthly.rankedItems).concat(array(periods.weekly.rankedItems), array(record(shelf).rankedItems)); }
function normalizePeriod(value, dayLimit = 31) { const source = record(value); const daily = source.dailyBuckets; const buckets = hasEntries(daily) ? daily : source.buckets; return { days: normalizeBuckets(buckets, dayLimit), totalMinutes: secondsToMinutes(source.totalReadSeconds || source.readSeconds), averageMinutes: secondsToMinutes(source.dayAverageReadSeconds || source.averageReadSeconds), readDays: numberValue(source.readDays), rankedItems: array(source.rankedItems).map(record), categories: array(source.categories).map(record), readingClock: source.readingClock, readStat: array(source.readStat).map((item) => ({ label: textValue(record(item).label), value: textValue(record(item).value), deepLink: safeDeepLink(record(item).deepLink) })).filter((item) => item.label || item.value), preferTimeWord: textValue(source.preferTimeWord), preferCategoryWord: textValue(source.preferCategoryWord), mediaMix: record(source.mediaMix), recordReadingSeconds: numberValue(source.recordReadingTime) }; }
function normalizeToday(value, monthly, weekly, generatedAt, isSample) { const direct = normalizePeriod(value); if (direct.days.length) return direct; const target = chinaDayKey(isSample && generatedAt ? Number(generatedAt) : Math.floor(Date.now() / 1000)); const all = monthly.days.concat(weekly.days); const day = all.find((item) => item.timestamp && chinaDayKey(item.timestamp) === target); return day ? { ...monthly, days: [day], totalMinutes: day.minutes, averageMinutes: day.minutes, readDays: day.minutes ? 1 : 0, rankedItems: [] } : { ...monthly, days: [{ label: target.slice(5), shortLabel: target.slice(-2), minutes: 0, timestamp: 0 }], totalMinutes: 0, averageMinutes: 0, readDays: 0, rankedItems: [] }; }
function normalizeBuckets(value, limit = 31) { const buckets = Array.isArray(value) ? value.reduce((out, item) => { const row = record(item); out[row.date || row.day || row.timestamp || row.key] = row.readSeconds || row.totalReadSeconds || row.seconds || row.value; return out; }, {}) : record(value); return Object.entries(buckets).sort(([a], [b]) => String(a).localeCompare(String(b), "zh-CN", { numeric: true })).slice(-limit).map(([key, seconds], index) => ({ label: bucketLabel(key, index), shortLabel: bucketShortLabel(key), minutes: secondsToMinutes(seconds), timestamp: numericTimestamp(key) })); }
function normalizeMonths(value) { return array(value).map((item, index) => { const row = record(item); const key = row.month || row.key || row.date || index; return { label: textValue(row.label) || bucketLabel(key, index), shortLabel: textValue(row.shortLabel) || bucketShortLabel(key), minutes: secondsToMinutes(row.readSeconds || row.totalReadSeconds || row.seconds || row.value) }; }); }
function normalizeBook(source, progress, note, index, isSample) { const title = textValue(source.title || source.bookName || source.name); const kind = textValue(source.kind) || "ebook"; const finished = source.finished === true || source.status === "finished" || (progress && progress.finished === true); const rawPercent = firstDefined(record(progress).progressPercent, record(progress).percent, source.progressPercent, source.progress); const percent = kind === "audio" ? 0 : numberValue(rawPercent); const progressKnown = kind !== "audio" && (rawPercent !== undefined && rawPercent !== null && rawPercent !== "" || finished); const breakdown = note ? note.noteBreakdown : record(source.noteBreakdown); const noteTotal = note ? note.noteTotal : numberValue(source.noteTotal); const readSeconds = numberValue(source.readSeconds || source.totalReadSeconds || source.recordReadingSeconds || (progress && progress.recordReadingSeconds)); const lastRead = numberValue(source.readUpdateTime || source.updatedAt || source.lastReadAt || (progress && progress.updatedAt)); return { bookId: textValue(source.bookId || source.id), title, author: textValue(source.author || source.authorName || source.creator), kind, coverRef: safeCoverReference(source.cover || source.coverUrl || source.coverURL || source.image) || (isSample ? sampleCoverReference(index) : null), deepLink: safeDeepLink(source.deepLink || source.url || source.link || source.weReadUrl), notePath: safeNotePath((note && note.notePath) || source.notePath || source.obsidianPath), finished, progressPercent: percent, progressKnown, progressText: finished ? "已读完" : progressKnown ? `${percent}% 已读` : "进度未同步", readingText: readSeconds ? `${formatNumber(secondsToMinutes(readSeconds))} 分钟` : "", lastReadText: lastRead ? dateText(lastRead) : "", noteText: noteTotal ? `${formatNumber(noteTotal)} 条摘录` : "", noteBreakdown: { highlights: numberValue(breakdown.highlights || (note && note.highlightCount) || source.highlightCount), reviews: numberValue(breakdown.reviews || (note && note.reviewCount) || source.reviewCount), bookmarks: numberValue(breakdown.bookmarks || (note && note.bookmarkCount) || source.bookmarkCount) }, rankSeconds: readSeconds, lastReadAt: lastRead }; }
function normalizeNotebookBook(value) { const source = record(value); const title = textValue(source.title || source.bookName || source.name); if (!title) return null; const breakdown = record(source.noteBreakdown || source.breakdown); return { bookId: textValue(source.bookId || source.id), title, author: textValue(source.author || source.authorName), notePath: safeNotePath(source.notePath || source.obsidianPath), noteTotal: numberValue(source.noteTotal || (numberValue(source.highlightCount || breakdown.highlights) + numberValue(source.reviewCount || breakdown.reviews) + numberValue(source.bookmarkCount || breakdown.bookmarks))), noteBreakdown: { highlights: numberValue(breakdown.highlights || source.highlightCount), reviews: numberValue(breakdown.reviews || source.reviewCount), bookmarks: numberValue(breakdown.bookmarks || source.bookmarkCount) }, recentAt: numberValue(source.recentNoteAt || source.updatedAt) }; }
function normalizeInsights(root, monthly) { const source = record(root.insights); const rawClock = source.readingClock || monthly.readingClock || root.readingClock; const clockSource = Array.isArray(rawClock) ? rawClock : array(record(rawClock).hours || record(rawClock).buckets); const byHour = Array.from({ length: 24 }, () => 0); clockSource.forEach((item, index) => { const row = record(item); const hour = Number.isFinite(Number(row.hour)) ? modulo(Number(row.hour), 24) : modulo(index + 6, 24); const seconds = typeof item === "object" ? row.readSeconds || row.seconds || row.value : item; byHour[hour] = Math.min(4, Math.ceil(secondsToMinutes(seconds) / 15)); }); const hours = Array.from({ length: 24 }, (_, index) => byHour[(index + 6) % 24]); const categories = array(source.categories || monthly.categories || root.categories).map((item) => { const row = record(item); return { name: textValue(row.name || row.title || row.category || row.label), minutes: secondsToMinutes(row.readSeconds || row.totalReadSeconds || row.seconds || row.value) }; }).filter((item) => item.name); const mix = record(source.mediaMix || monthly.mediaMix || root.mediaMix); const text = numberValue(mix.wrListenTime || mix.listenSeconds) ? `电子书 ${formatNumber(secondsToMinutes(mix.wrReadTime || mix.readSeconds))} 分钟 · 听书 ${formatNumber(secondsToMinutes(mix.wrListenTime || mix.listenSeconds))} 分钟` : "阅读时段与分类会在同步后逐渐完整"; return { readingClock: { hours, label: clockSource.length ? "24 小时阅读分布" : "阅读时段待同步" }, categories, mediaMix: { ...mix, label: text } }; }

function normalizeDashboardPath(value) { const candidate = String(value || DASHBOARD_PATH).trim().replace(/\\/g, "/"); return candidate === DASHBOARD_PATH ? candidate : DASHBOARD_PATH; }
function safeCoverReference(value) { const raw = String(value || "").trim(); if (!raw) return null; try { const url = new URL(raw); return (url.protocol === "https:" || url.protocol === "http:") && !url.username && !url.password ? { kind: "remote", value: url.href } : null; } catch (_) { const path = safeVaultCoverPath(raw); return path ? { kind: "vault", value: path } : null; } }
function safeVaultCoverPath(value) { const path = String(value || "").trim().replace(/\\/g, "/").replace(/^\/+/, ""); return path.startsWith(".weread/covers/") && !path.split("/").includes("..") && !path.includes("\0") && /\.(avif|gif|jpe?g|png|webp)$/i.test(path) ? path : ""; }
function safeNotePath(value) { const path = String(value || "").trim().replace(/\\/g, "/"); return path && !path.startsWith("/") && !path.split("/").includes("..") && !path.includes("\0") ? path.slice(0, 500) : ""; }
function safeExportNoteFilename(title, bookId) { const cleaned = String(title || "").split("").map((character) => /[<>:"/\\|?*]/.test(character) || character.charCodeAt(0) < 32 ? "_" : character).join("").trim().replace(/[. ]+$/, "").slice(0, 80) || "WeRead Notes"; const suffix = String(bookId || "").replace(/[^A-Za-z0-9_-]/g, "").slice(0, 32); return `${cleaned}-${suffix}.md`; }
function safeDeepLink(value) { try { const url = new URL(String(value)); return (url.protocol === "https:" && (url.hostname === "weread.qq.com" || url.hostname.endsWith(".weread.qq.com"))) || (url.protocol === "weread:" && !url.username && !url.password) ? url.href : ""; } catch (_) { return ""; } }
function openSafeUrl(url) { const safe = safeDeepLink(url); if (safe && typeof window !== "undefined" && window.open) window.open(safe, "_blank", "noopener,noreferrer"); }
function getDashboardState(dashboard) { if (!dashboard.books.length && !dashboard.noteBooks.length && dashboard.periods.weekly.totalMinutes === 0) return "empty"; if (dashboard.sample) return "sample"; return dashboard.updatedAt && Date.now() - dashboard.updatedAt.getTime() > STALE_AFTER_MS ? "stale" : "fresh"; }
function freshnessText(dashboard, state) { if (state === "sample") return "当前显示安全的示例数据"; if (!dashboard.updatedAt) return "同步时间待记录"; const delta = Math.max(0, Date.now() - dashboard.updatedAt.getTime()); return delta < 3600000 ? "最后同步：刚刚" : delta < 86400000 ? `最后同步：${Math.floor(delta / 3600000)} 小时前` : `最后同步：${dashboard.updatedAt.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" })}`; }
function bucketLabel(value, index) { const ts = numericTimestamp(value); if (ts) { const date = new Date(ts * 1000); return `${date.getMonth() + 1}/${date.getDate()}`; } const text = textValue(value); return text && text.length <= 10 ? text : `第 ${index + 1} 天`; }
function bucketShortLabel(value) { const ts = numericTimestamp(value); if (!ts) return textValue(value).slice(-3); const date = new Date(ts * 1000); return String(date.getDate()); }
function numericTimestamp(value) { const raw = Number(value); return Number.isFinite(raw) && raw > 1000000000 ? raw : 0; }
function chinaDayKey(timestamp) { return new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Shanghai", year: "numeric", month: "2-digit", day: "2-digit" }).format(new Date(Number(timestamp) * 1000)); }
function hasEntries(value) { return Array.isArray(value) ? value.length > 0 : Object.keys(record(value)).length > 0; }
function emptyDays(count) { return Array.from({ length: count }, (_, index) => ({ label: `${index + 1}`, shortLabel: `${index + 1}`, minutes: 0 })); }
function sampleCoverReference(index) { return { kind: "vault", value: `.weread/covers/sample-${String((Number(index) % 5) + 1).padStart(2, "0")}.webp` }; }
function dateText(value) { const date = unixDateValue(value); return date ? `${date.getMonth() + 1}月${date.getDate()}日` : ""; }
function periodLabel(value) { return (PERIODS.find((item) => item.id === value) || PERIODS[0]).label; }
function record(value) { return value && typeof value === "object" && !Array.isArray(value) ? value : {}; }
function array(value) { return Array.isArray(value) ? value : []; }
function firstDefined(...values) { return values.find((value) => value !== undefined && value !== null); }
function textValue(value) { return typeof value === "string" ? value.trim().slice(0, 500) : ""; }
function numberValue(value) { const number = Number(value); return Number.isFinite(number) && number > 0 ? Math.round(number) : 0; }
function secondsToMinutes(value) { const seconds = Number(value); return Number.isFinite(seconds) && seconds > 0 ? Math.round(seconds / 60) : 0; }
function unixDateValue(value) { const seconds = Number(value); const date = Number.isFinite(seconds) && seconds > 0 ? new Date(seconds * 1000) : null; return date && !Number.isNaN(date.getTime()) ? date : null; }
function formatNumber(value) { return new Intl.NumberFormat("zh-CN").format(numberValue(value)); }
function reducedMotion() { return typeof window !== "undefined" && window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches; }
function modulo(value, divisor) { return divisor ? ((value % divisor) + divisor) % divisor : 0; }

module.exports = WeReadReadingBoardPlugin;
module.exports.CircularGalleryController = CircularGalleryController;
module.exports.normalizeDashboard = normalizeDashboard;
module.exports.normalizeDashboardPath = normalizeDashboardPath;
