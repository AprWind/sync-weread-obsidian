const { Plugin, setIcon } = require("obsidian");

/*
THESIS: 让本周阅读节奏先于书架信息进入视线，拒绝把 Obsidian 伪装成另一台手机。
OWN-WORLD: 以 Obsidian 语义表面和系统蓝为唯一行动色，采用 16px 分组面与 10px 控件。
STORY: 读者一眼确认同步新鲜度和阅读状态，再查看继续阅读的书与笔记较多的书。
FIRST VIEWPORT: 左侧是七日时长与主数值，右侧三条状态摘要，下方是一条可直接拖动的书籍画廊，刷新在标题右侧。
FORM: Trends-first composition, seed 697b06cb.
FINISH: unreviewed and undocumented is unfinished; this build ends with the finish review, the verdict, and DESIGN.md
*/

const DASHBOARD_PATH = ".weread/reading-board.json";
const STALE_AFTER_MS = 36 * 60 * 60 * 1000;
const PERIODS = [
  { id: "weekly", label: "本周" },
  { id: "monthly", label: "本月" },
  { id: "overall", label: "全部" },
];

class WeReadReadingBoardPlugin extends Plugin {
  onload() {
    this.unloaded = false;
    this.register(() => {
      this.unloaded = true;
    });

    this.registerMarkdownCodeBlockProcessor("weread-dashboard", (source, el) => {
      const requestedPath = source.trim().split(/\r?\n/)[0] || DASHBOARD_PATH;
      void this.renderDashboard(el, requestedPath);
    });
  }

  onunload() {
    this.unloaded = true;
  }

  async renderDashboard(container, requestedPath) {
    const path = normalizeDashboardPath(requestedPath);
    const view = this.createRoot(container, "loading");
    this.renderLoading(view);

    try {
      const data = await this.readDashboard(path);
      if (this.unloaded || !view.isConnected) return;
      this.renderReady(view, data, path);
    } catch (error) {
      if (this.unloaded || !view.isConnected) return;
      this.renderError(view, error, path);
    }
  }

  createRoot(container, state) {
    container.empty();
    const root = container.createDiv({ cls: "weread-dashboard" });
    root.setAttr("data-weread-state", state);
    root.setAttr("aria-live", "polite");
    return root;
  }

  async readDashboard(path) {
    if (!this.app.vault.adapter.exists || !(await this.app.vault.adapter.exists(path))) {
      const missing = new Error("找不到数据文件");
      missing.code = "ENOENT";
      throw missing;
    }
    const raw = await this.app.vault.adapter.read(path);
    return normalizeDashboard(JSON.parse(raw));
  }

  renderLoading(root) {
    root.empty();
    root.setAttr("data-weread-state", "loading");
    const header = root.createDiv({ cls: "weread-dashboard__header weread-dashboard__skeleton-header" });
    header.createDiv({ cls: "weread-dashboard__skeleton weread-dashboard__skeleton--title" });
    header.createDiv({ cls: "weread-dashboard__skeleton weread-dashboard__skeleton--action" });
    const upper = root.createDiv({ cls: "weread-dashboard__upper" });
    upper.createDiv({ cls: "weread-dashboard__skeleton weread-dashboard__skeleton--chart" });
    upper.createDiv({ cls: "weread-dashboard__skeleton weread-dashboard__skeleton--rows" });
    root.createDiv({ cls: "weread-dashboard__skeleton weread-dashboard__skeleton--rail" });
  }

  renderReady(root, dashboard, path) {
    root.empty();
    const state = getDashboardState(dashboard);
    root.setAttr("data-weread-state", state);

    const header = root.createDiv({ cls: "weread-dashboard__header" });
    const heading = header.createDiv({ cls: "weread-dashboard__heading" });
    heading.createEl("h2", { text: "阅读看板" });
    const freshness = heading.createEl("p", { cls: "weread-dashboard__freshness" });
    freshness.createSpan({ text: freshnessText(dashboard, state) });
    if (state === "stale") freshness.createSpan({ cls: "weread-dashboard__state-tag", text: "待刷新" });
    if (state === "sample") freshness.createSpan({ cls: "weread-dashboard__state-tag", text: "示例数据" });

    const refresh = this.iconButton("读取本地数据", "refresh-cw", "weread-dashboard__refresh");
    refresh.setAttr("aria-label", "读取本地 reading-board.json 数据，不会同步网络");
    refresh.setAttr("title", "读取本地 reading-board.json 数据，不会同步网络");
    const refreshText = document.createElement("span");
    refreshText.className = "weread-dashboard__refresh-text";
    refreshText.textContent = "读取本地数据";
    refresh.appendChild(refreshText);
    this.registerDomEvent(refresh, "click", () => void this.renderDashboard(root.parentElement, path));
    header.appendChild(refresh);

    if (state === "empty") {
      this.renderEmpty(root, path);
      return;
    }

    const selectedPeriod = "weekly";
    const controls = root.createDiv({ cls: "weread-dashboard__periods", attr: { role: "radiogroup", "aria-label": "阅读数据时间范围" } });
    const content = root.createDiv({ cls: "weread-dashboard__content" });
    const updatePeriod = (nextPeriod) => {
      controls.querySelectorAll("button").forEach((button) => {
        const selected = button.dataset.period === nextPeriod;
        button.setAttr("aria-checked", String(selected));
        button.toggleClass("is-selected", selected);
        button.tabIndex = selected ? 0 : -1;
      });
      this.renderPeriodContent(content, dashboard, nextPeriod);
    };

    PERIODS.forEach((period, index) => {
      const button = controls.createEl("button", {
        cls: `weread-dashboard__period${index === 0 ? " is-selected" : ""}`,
        text: period.label,
        attr: { type: "button", role: "radio", "aria-checked": String(index === 0), "data-period": period.id },
      });
      button.tabIndex = index === 0 ? 0 : -1;
      this.registerDomEvent(button, "click", () => updatePeriod(period.id));
      this.registerDomEvent(button, "keydown", (event) => {
        if (!["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
        event.preventDefault();
        const current = PERIODS.findIndex((item) => item.id === period.id);
        const next = event.key === "Home" ? 0 : event.key === "End" ? PERIODS.length - 1 : (current + (event.key === "ArrowRight" ? 1 : PERIODS.length - 1)) % PERIODS.length;
        updatePeriod(PERIODS[next].id);
        controls.querySelector(`[data-period="${PERIODS[next].id}"]`).focus();
      });
    });
    updatePeriod(selectedPeriod);
  }

  renderPeriodContent(content, dashboard, period) {
    content.empty();
    const trend = dashboard.periods[period] || dashboard.periods.weekly;
    const upper = content.createDiv({ cls: "weread-dashboard__upper" });
    this.renderTrend(upper, trend, period);
    this.renderSummary(upper, dashboard, period);
    this.renderGallery(content, dashboard.books);
    const lower = content.createDiv({ cls: "weread-dashboard__lower" });
    this.renderRhythm(lower, trend);
    this.renderNoteBooks(lower, dashboard.noteBooks);
  }

  renderTrend(parent, trend, period) {
    const section = parent.createEl("section", { cls: "weread-dashboard__surface weread-dashboard__trend", attr: { "aria-labelledby": "weread-trend-title" } });
    const heading = section.createDiv({ cls: "weread-dashboard__section-heading" });
    heading.createEl("h3", { text: "阅读时长", attr: { id: "weread-trend-title" } });
    heading.createSpan({ text: period === "weekly" ? "分钟" : "累计分钟", cls: "weread-dashboard__unit" });
    const number = section.createDiv({ cls: "weread-dashboard__metric" });
    number.createEl("strong", { text: formatNumber(trend.totalMinutes) });
    number.createSpan({ text: "分钟" });
    section.createEl("p", { cls: "weread-dashboard__average", text: trend.averageMinutes ? `日均 ${formatNumber(trend.averageMinutes)} 分钟` : "尚无阅读时长" });
    const max = Math.max(1, ...trend.days.map((day) => day.minutes));
    const needsHorizontalScroll = trend.days.length > 7;
    const chartViewport = section.createDiv({ cls: `weread-dashboard__chart-viewport${needsHorizontalScroll ? " is-scrollable" : ""}` });
    const chart = chartViewport.createDiv({ cls: `weread-dashboard__chart${needsHorizontalScroll ? " is-scrollable" : ""}`, attr: { role: "list", "aria-label": "每日阅读时长" } });
    if (needsHorizontalScroll) chart.style.setProperty("--weread-day-count", String(trend.days.length));
    trend.days.forEach((day) => {
      const item = chart.createDiv({ cls: "weread-dashboard__bar-item", attr: { role: "listitem", "aria-label": `${day.label} ${formatNumber(day.minutes)} 分钟` } });
      const value = item.createEl("span", { cls: "weread-dashboard__bar-value", text: formatNumber(day.minutes) });
      value.setAttr("aria-hidden", "true");
      const barTrack = item.createDiv({ cls: "weread-dashboard__bar-track" });
      const bar = barTrack.createDiv({ cls: "weread-dashboard__bar" });
      bar.style.setProperty("--weread-bar-height", `${Math.max(4, Math.round((day.minutes / max) * 100))}%`);
      barTrack.setAttr("aria-hidden", "true");
      item.createEl("span", { cls: "weread-dashboard__bar-label", text: day.label });
    });
  }

  renderSummary(parent, dashboard, period) {
    const section = parent.createEl("section", { cls: "weread-dashboard__surface weread-dashboard__summary", attr: { "aria-label": "阅读摘要" } });
    const periodData = dashboard.periods[period] || dashboard.periods.weekly;
    const items = [
      ["calendar-days", "阅读天数", `${formatNumber(periodData.readDays)} 天`, PERIODS.find((item) => item.id === period).label],
      ["book-open", "读完", `${formatNumber(dashboard.summary.completedBooks)} 本`, `书架共 ${formatNumber(dashboard.summary.shelfCount)} 本`],
      ["file-text", "笔记", `${formatNumber(dashboard.summary.noteCount)} 条`, `涉及 ${formatNumber(dashboard.summary.noteBookCount)} 本`],
    ];
    items.forEach(([icon, label, value, detail]) => {
      const row = section.createDiv({ cls: "weread-dashboard__summary-row" });
      const iconHolder = row.createDiv({ cls: "weread-dashboard__summary-icon" });
      setIcon(iconHolder, icon);
      row.createEl("span", { cls: "weread-dashboard__summary-label", text: label });
      const values = row.createDiv({ cls: "weread-dashboard__summary-values" });
      values.createEl("strong", { text: value });
      values.createSpan({ text: detail });
    });
  }

  renderGallery(parent, books) {
    const section = parent.createEl("section", { cls: "weread-dashboard__gallery", attr: { "aria-labelledby": "weread-gallery-title" } });
    const sectionHeader = section.createDiv({ cls: "weread-dashboard__gallery-header" });
    sectionHeader.createEl("h3", { text: "继续阅读", attr: { id: "weread-gallery-title" } });
    const actions = sectionHeader.createDiv({ cls: "weread-dashboard__gallery-actions" });
    const previous = this.iconButton("上一册", "chevron-left", "weread-dashboard__gallery-button");
    const next = this.iconButton("下一册", "chevron-right", "weread-dashboard__gallery-button");
    actions.append(previous, next);
    const rail = section.createDiv({ cls: "weread-dashboard__book-rail", attr: { role: "list", "aria-label": "继续阅读书籍" } });
    this.registerDomEvent(previous, "click", () => rail.scrollBy({ left: -Math.max(240, rail.clientWidth * 0.8), behavior: reducedMotion() ? "auto" : "smooth" }));
    this.registerDomEvent(next, "click", () => rail.scrollBy({ left: Math.max(240, rail.clientWidth * 0.8), behavior: reducedMotion() ? "auto" : "smooth" }));
    books.forEach((book) => {
      const item = rail.createDiv({ cls: "weread-dashboard__book-item", attr: { role: "listitem" } });
      const card = item.createEl("button", { cls: "weread-dashboard__book", attr: { type: "button", "aria-label": `打开《${book.title}》` } });
      const cover = card.createDiv({ cls: "weread-dashboard__cover" });
      const coverUrl = this.resolveCoverUrl(book.coverRef);
      if (coverUrl) {
        const image = cover.createEl("img", { attr: { src: coverUrl, alt: `${book.title}封面`, loading: "lazy" } });
        this.registerDomEvent(image, "error", () => cover.addClass("is-missing"));
      } else {
        cover.addClass("is-missing");
      }
      const placeholder = cover.createDiv({ cls: "weread-dashboard__cover-placeholder", attr: { "aria-hidden": "true" } });
      setIcon(placeholder, "book-open");
      const copy = card.createDiv({ cls: "weread-dashboard__book-copy" });
      copy.createEl("strong", { text: book.title });
      copy.createSpan({ text: book.author || "作者信息待同步" });
      const progressText = book.progressText || "进度待同步";
      copy.createSpan({ cls: "weread-dashboard__book-progress", text: progressText });
      if (book.url) this.registerDomEvent(card, "click", () => openSafeUrl(book.url));
      else card.disabled = true;
    });
  }

  renderRhythm(parent, trend) {
    const section = parent.createEl("section", { cls: "weread-dashboard__surface weread-dashboard__rhythm", attr: { "aria-labelledby": "weread-rhythm-title" } });
    section.createEl("h3", { text: "阅读节奏", attr: { id: "weread-rhythm-title" } });
    const days = trend.days;
    const max = Math.max(1, ...days.map((day) => day.minutes));
    const grid = section.createDiv({ cls: "weread-dashboard__rhythm-grid", attr: { role: "list", "aria-label": "阅读节奏记录" } });
    days.slice(-14).forEach((day) => {
      const cell = grid.createDiv({ cls: "weread-dashboard__rhythm-cell", attr: { role: "listitem", "aria-label": `${day.label} ${formatNumber(day.minutes)} 分钟` } });
      cell.style.setProperty("--weread-rhythm-level", String(Math.min(4, Math.ceil((day.minutes / max) * 4))));
      cell.createSpan({ text: day.label });
      cell.createEl("strong", { text: formatNumber(day.minutes) });
    });
  }

  renderNoteBooks(parent, noteBooks) {
    const section = parent.createEl("section", { cls: "weread-dashboard__surface weread-dashboard__notes", attr: { "aria-labelledby": "weread-notes-title" } });
    section.createEl("h3", { text: "笔记较多的书", attr: { id: "weread-notes-title" } });
    if (!noteBooks.length) {
      section.createEl("p", { cls: "weread-dashboard__quiet-copy", text: "同步后会显示笔记数量较多的书籍。" });
      return;
    }
    const list = section.createDiv({ cls: "weread-dashboard__note-list", attr: { role: "list", "aria-label": "笔记较多的书" } });
    noteBooks.slice(0, 5).forEach((book) => {
      const row = list.createDiv({ cls: "weread-dashboard__note", attr: { role: "listitem", "aria-label": `${book.title}，${formatNumber(book.noteTotal)} 条笔记` } });
      const icon = row.createDiv({ cls: "weread-dashboard__note-icon", attr: { "aria-hidden": "true" } });
      setIcon(icon, "file-text");
      const body = row.createDiv({ cls: "weread-dashboard__note-body" });
      body.createEl("strong", { text: book.title });
      body.createSpan({ text: book.author || "作者信息待同步" });
      row.createSpan({ cls: "weread-dashboard__note-time", text: `${formatNumber(book.noteTotal)} 条` });
    });
  }

  renderEmpty(root) {
    const empty = root.createEl("section", { cls: "weread-dashboard__empty", attr: { "aria-label": "暂无阅读数据" } });
    const icon = empty.createDiv({ cls: "weread-dashboard__empty-icon", attr: { "aria-hidden": "true" } });
    setIcon(icon, "book-open");
    empty.createEl("h3", { text: "还没有可展示的阅读记录" });
    empty.createEl("p", { text: "完成一次同步后，阅读进度、节奏和笔记较多的书会显示在这里。" });
  }

  renderError(root, error, path) {
    root.empty();
    root.setAttr("data-weread-state", "error");
    const errorSection = root.createEl("section", { cls: "weread-dashboard__error", attr: { role: "alert" } });
    const icon = errorSection.createDiv({ cls: "weread-dashboard__error-icon", attr: { "aria-hidden": "true" } });
    setIcon(icon, error && error.code === "ENOENT" ? "folder-search" : "circle-alert");
    errorSection.createEl("h3", { text: error && error.code === "ENOENT" ? "尚未找到阅读数据" : "阅读数据无法读取" });
    errorSection.createEl("p", { text: error && error.code === "ENOENT" ? `请先运行同步命令，生成 ${path}。` : "请检查 reading-board.json 的格式，然后重新读取。已有笔记不会被修改。" });
    const retry = this.iconButton("重新读取", "refresh-cw", "weread-dashboard__retry");
    this.registerDomEvent(retry, "click", () => void this.renderDashboard(root.parentElement, path));
    errorSection.appendChild(retry);
  }

  iconButton(label, icon, cls) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = cls;
    button.setAttribute("aria-label", label);
    const iconHolder = document.createElement("span");
    iconHolder.setAttribute("aria-hidden", "true");
    setIcon(iconHolder, icon);
    button.appendChild(iconHolder);
    return button;
  }

  resolveCoverUrl(reference) {
    if (!reference) return "";
    if (reference.kind === "remote") return reference.value;
    if (reference.kind !== "vault" || !this.app.vault.adapter.getResourcePath) return "";
    try {
      return this.app.vault.adapter.getResourcePath(reference.value);
    } catch (_) {
      return "";
    }
  }
}

function normalizeDashboardPath(value) {
  const candidate = String(value || DASHBOARD_PATH).trim().replace(/\\/g, "/");
  return candidate === DASHBOARD_PATH ? candidate : DASHBOARD_PATH;
}

function normalizeDashboard(input) {
  const root = record(input);
  const isSample = Boolean(root.sample || root.isSample || root.source === "sample" || record(root.meta).sample);
  const sourcePeriods = record(root.periods);
  const periods = {
    weekly: normalizeCanonicalPeriod(sourcePeriods.weekly),
    monthly: normalizeCanonicalPeriod(sourcePeriods.monthly),
    overall: normalizeCanonicalPeriod(sourcePeriods.overall),
  };
  const progressByBookId = new Map(array(root.progress).map((entry) => [textValue(record(entry).bookId), record(entry)]));
  const shelf = record(root.shelf);
  const shelfItems = array(shelf.items).map(record).filter((item) => textValue(item.bookId) && textValue(item.title));
  const books = shelfItems.slice().sort((left, right) => numberValue(right.readUpdateTime) - numberValue(left.readUpdateTime)).slice(0, 5).map((book, index) => normalizeCanonicalBook(book, progressByBookId.get(textValue(book.bookId)), index, isSample));
  const notebooks = record(root.notebooks);
  const noteBooks = array(notebooks.books).map(normalizeNotebookBook).filter(Boolean);
  return {
    updatedAt: unixDateValue(root.generatedAt),
    sample: isSample,
    periods,
    books,
    noteBooks,
    summary: {
      completedBooks: shelfItems.filter((item) => item.finished === true).length,
      shelfCount: numberValue(shelf.totalEntries) || shelfItems.length,
      noteCount: numberValue(notebooks.totalNoteCount),
      noteBookCount: numberValue(notebooks.totalBookCount),
    },
  };
}

function normalizeCanonicalPeriod(value) {
  const source = record(value);
  return {
    days: normalizeBuckets(source.buckets),
    totalMinutes: secondsToMinutes(source.totalReadSeconds),
    averageMinutes: secondsToMinutes(source.dayAverageReadSeconds),
    readDays: numberValue(source.readDays),
  };
}

function normalizeBuckets(value) {
  const buckets = record(value);
  const entries = Object.entries(buckets).sort(([left], [right]) => left.localeCompare(right, "zh-CN", { numeric: true })).slice(-31);
  const labels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
  return entries.length ? entries.map(([key, seconds], index) => ({ label: bucketLabel(key, index), minutes: secondsToMinutes(seconds) })) : emptyWeek();
}

function bucketLabel(value, index) {
  const numeric = Number(value);
  if (Number.isFinite(numeric) && numeric > 1000000000) {
    const date = new Date(numeric * 1000);
    if (!Number.isNaN(date.getTime())) return `${date.getMonth() + 1}/${date.getDate()}`;
  }
  const text = textValue(value);
  if (text && text.length <= 8) return text;
  const labels = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"];
  return labels[index % labels.length];
}

function emptyWeek() {
  return ["周一", "周二", "周三", "周四", "周五", "周六", "周日"].map((label) => ({ label, minutes: 0 }));
}

function normalizeCanonicalBook(source, progressEntry, index, isSample) {
  const title = textValue(source.title || source.bookName || source.name);
  const progress = numberValue(progressEntry && progressEntry.progressPercent);
  const progressText = progressEntry ? `${progress}% 已读` : source.finished === true ? "已读完" : "进度未同步";
  return {
    title,
    author: textValue(source.author || source.authorName),
    coverRef: safeCoverReference(source.cover || source.coverUrl || source.coverURL || source.image) || (isSample ? sampleCoverReference(index) : null),
    url: safeDeepLink(source.url || source.link || source.deepLink || source.weReadUrl),
    progressText,
  };
}

function sampleCoverReference(index) {
  const number = String((Number(index) % 5) + 1).padStart(2, "0");
  return { kind: "vault", value: `.weread/covers/sample-${number}.webp` };
}

function normalizeNotebookBook(value) {
  const source = record(value);
  const title = textValue(source.title || source.bookName || source.name);
  if (!title) return null;
  return {
    title,
    author: textValue(source.author),
    noteTotal: numberValue(source.noteTotal || numberValue(source.highlightCount) + numberValue(source.reviewCount) + numberValue(source.bookmarkCount)),
  };
}

function getDashboardState(dashboard) {
  if (!dashboard.books.length && !dashboard.noteBooks.length && dashboard.periods.weekly.totalMinutes === 0) return "empty";
  if (dashboard.sample) return "sample";
  if (dashboard.updatedAt && Date.now() - dashboard.updatedAt.getTime() > STALE_AFTER_MS) return "stale";
  return "fresh";
}

function freshnessText(dashboard, state) {
  if (state === "sample") return "当前显示安全的示例数据";
  if (!dashboard.updatedAt) return "同步时间待记录";
  const delta = Math.max(0, Date.now() - dashboard.updatedAt.getTime());
  if (delta < 60 * 60 * 1000) return "最后同步：刚刚";
  if (delta < 24 * 60 * 60 * 1000) return `最后同步：${Math.floor(delta / (60 * 60 * 1000))} 小时前`;
  return `最后同步：${dashboard.updatedAt.toLocaleDateString("zh-CN", { month: "numeric", day: "numeric" })}`;
}

function safeCoverReference(value) {
  const raw = String(value || "").trim();
  if (!raw) return null;
  try {
    const url = new URL(raw);
    if ((url.protocol === "https:" || url.protocol === "http:") && !url.username && !url.password) return { kind: "remote", value: url.href };
  } catch (_) {
    const path = safeVaultCoverPath(raw);
    if (path) return { kind: "vault", value: path };
  }
  return null;
}

function safeVaultCoverPath(value) {
  const path = String(value || "").trim().replace(/\\/g, "/").replace(/^\/+/, "");
  const allowedExtension = /\.(avif|gif|jpe?g|png|webp)$/i;
  return path.startsWith(".weread/covers/") && !path.split("/").includes("..") && !path.includes("\0") && allowedExtension.test(path) ? path : "";
}

function safeDeepLink(value) {
  try {
    const url = new URL(String(value));
    if (url.protocol === "https:" && (url.hostname === "weread.qq.com" || url.hostname.endsWith(".weread.qq.com"))) return url.href;
    if (url.protocol === "weread:" && !url.username && !url.password) return url.href;
  } catch (_) {
    return "";
  }
  return "";
}

function openSafeUrl(url) {
  const safe = safeDeepLink(url);
  if (safe) window.open(safe, "_blank", "noopener,noreferrer");
}

function record(value) {
  return value && typeof value === "object" && !Array.isArray(value) ? value : {};
}

function array(value) {
  return Array.isArray(value) ? value : [];
}

function textValue(value) {
  return typeof value === "string" ? value.trim().slice(0, 500) : "";
}

function numberValue(value) {
  const number = Number(value);
  return Number.isFinite(number) && number > 0 ? Math.round(number) : 0;
}

function secondsToMinutes(value) {
  const seconds = Number(value);
  return Number.isFinite(seconds) && seconds > 0 ? Math.round(seconds / 60) : 0;
}

function unixDateValue(value) {
  const seconds = Number(value);
  const date = Number.isFinite(seconds) && seconds > 0 ? new Date(seconds * 1000) : null;
  return date && !Number.isNaN(date.getTime()) ? date : null;
}

function formatNumber(value) {
  return new Intl.NumberFormat("zh-CN").format(numberValue(value));
}

function reducedMotion() {
  return typeof window !== "undefined" && window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
}

module.exports = WeReadReadingBoardPlugin;
