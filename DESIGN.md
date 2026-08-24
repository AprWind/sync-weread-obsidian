---
name: WeRead Reading Board 2
description: A gallery-first, living reading workspace for Obsidian.
concept_seed: "b94eec7a"
colors:
  accent: "var(--interactive-accent, #0a84ff)"
  accent-soft: "color-mix(in srgb, var(--interactive-accent, #0a84ff) 11%, var(--background-primary))"
  background: "var(--background-primary)"
  surface: "var(--background-primary-alt)"
  surface-quiet: "var(--background-secondary)"
  text: "var(--text-normal)"
  text-muted: "var(--text-muted)"
  separator: "var(--background-modifier-border)"
  error: "var(--text-error, #ff453a)"
typography:
  display: "clamp(30px, 4vw, 44px)/1.05 -apple-system, BlinkMacSystemFont, SF Pro Display, PingFang SC, sans-serif"
  headline: "700 24px/30px -apple-system, BlinkMacSystemFont, SF Pro Text, PingFang SC, sans-serif"
  title: "650 17px/22px -apple-system, BlinkMacSystemFont, SF Pro Text, PingFang SC, sans-serif"
  body: "400 15px/21px -apple-system, BlinkMacSystemFont, SF Pro Text, PingFang SC, sans-serif"
  metadata: "400 13px/18px -apple-system, BlinkMacSystemFont, SF Pro Text, PingFang SC, sans-serif"
rounded:
  cover: "10px"
  control: "12px"
  surface: "16px"
  pill: "999px"
spacing:
  xs: "4px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "24px"
  xxl: "32px"
  touch: "44px"
motion:
  focus: "260ms cubic-bezier(.22,.8,.22,1)"
  settle: "420ms cubic-bezier(.2,.78,.2,1)"
  autoplay: "4200ms"
---

# Design System: WeRead Reading Board 2

## Creative North Star

**The Living Bookshelf / 会流动的书架**

This is a personal reading workspace, not an analytics dashboard. The first viewport is a continuous belt of books: covers carry identity, the center book receives focus, and its real reading state unfolds immediately below. Statistics explain the habit only after the reader has encountered the books themselves.

The approved direction is **B · 连续封面画廊**. It independently preserves the reference skill's useful behavior—a dense, pure-cover horizontal gallery—while replacing its hard reset with a genuinely seamless logical loop and adding the interaction quality expected from iPhone system apps.

## Experience Hierarchy

1. **Living gallery:** the board shows up to twelve deduplicated local book records as a continuous library, with one active book and neighboring context.
2. **Book detail shelf:** progress, status, recent activity, reading time, note counts, and safe links all resolve from the active book id.
3. **Time structure:** month/week/today/year views expose calendar, buckets, and a trailing twelve-month rhythm without resetting the gallery.
4. **Reading intelligence:** reading clock, category/media preferences, notebook breakdown, and recent note activity add depth without becoming decorative KPI cards.
5. **Trust state:** source, freshness, sample/stale/error state, and refresh affordance are always legible but never compete with the books.

## Visual Grammar

- Translate Apple semantic hierarchy into the Obsidian pane; never draw a fake iPhone, fake sidebar, or separate app shell.
- Use the host's semantic background, label, separator, and accent variables rather than hard-coded light-only colors.
- Keep one system-blue action voice. Book covers may contain their own imagery, but UI chrome remains neutral.
- Use hairline separators and tonal grouping. A surface may use a border or a subtle shadow, never both.
- Use continuous 12–16px corners for controls and grouped surfaces; covers use a tighter 10px corner.
- Avoid gradients, glassmorphism, oversized marketing copy, floating pills for ordinary actions, and grids of interchangeable statistic cards.

## Gallery Contract

### Composition

- The gallery spans edge to edge within the board content width and appears before analytics.
- Covers are portrait-first, without attached horizontal info-card bodies. On desktop, enough neighboring books remain visible to read the collection as a belt.
- The active cover is modestly larger, fully opaque, and marked by a thin accent focus ring. Adjacent covers step down through scale and opacity; perspective is subtle, never theatrical.
- A compact control row provides previous, next, pause/play, position, and a textual drag hint. Controls retain 44px targets.

### Logical Loop

- Maintain one canonical array and an `activeIndex`; all input methods call the same modular navigation method.
- Visual clones or a virtual window may provide continuity, but clones are `aria-hidden`, inert, and never focusable.
- Crossing either boundary must not expose an empty gap or visible jump. After the transition, restore the equivalent canonical position without animation.
- Period changes update analysis only and preserve the active book.

### Input and Motion

- Support previous/next buttons, Left/Right/Home/End, horizontal wheel intent, pointer drag, and touch swipe.
- Autoplay is an optional ambient affordance, not the only way to navigate. It pauses on hover, focus-within, drag, offscreen state, hidden document, and explicit pause.
- `prefers-reduced-motion: reduce` disables autoplay and smooth transitions. Manual navigation remains complete.
- Do not trap vertical scroll: only consume a wheel/pointer gesture once horizontal intent is clear.
- A short isolated live region announces the active title and position; never make the whole dashboard live.

## Active Book Shelf

- The selected book remains selectable even when it has no official deep link; only that external action becomes unavailable.
- Resolve title, creator, kind, cover, progress, status, last activity, accumulated reading time, and notebook counts by stable content id.
- Completed books use `已读完` and, when a safe source link exists, a `在微信读书查看` action; unfinished books may use `继续阅读`. Audio items never display invented page progress.
- Present official WeRead and local Obsidian-note actions separately. Disabled actions retain explanatory text.
- Remote values enter the DOM through text APIs. Never interpolate titles, URLs, or note metadata into HTML.

## Analysis Panels

### Period Navigation

- Use one grouped segment with 本月 / 本周 / 今天 / 年度. Selection is both visibly and programmatically expressed.
- Arrow, Home, and End keys move selection. Switching panels must not reconstruct the gallery controller.

### Reading Calendar and Trend

- Monthly/day buckets are text-readable as well as color-scaled. Each cell exposes its date and duration.
- The twelve-month trend is a compact continuous plot or bars with explicit month values and no chart junk.
- Empty or unavailable historical data renders an honest quiet state; it is never fabricated from unrelated totals.

### Preferences and Notes

- Reading-clock buckets follow the official 06:00 through 05:00 order when the source provides them.
- Categories and media mix are small grouped distributions, not decorative tags with invented values.
- Notebook activity distinguishes highlights, personal reviews, and bookmarks. It stores and displays counts by default, not personal note bodies.

## Responsive Behavior

- At wide widths, the gallery shows a dense belt and the lower panels use two coordinated columns.
- At 700px and below, retain one centered active cover with adjacent peeks; detail facts wrap into a readable list and lower panels stack.
- Primary controls retain 44px targets. Text scales with `clamp` and host zoom; long Chinese book titles truncate rather than expanding the cover shelf.
- Cover motion uses transforms rather than layout churn. The document preserves ordinary vertical scrolling.

## States

- Loading skeletons match gallery, active shelf, and lower-panel geometry.
- Sample data is visibly labeled and uses only synthetic covers/metadata.
- A state file older than the stale threshold remains readable as the last serialized model; the displayed timestamp must not imply a network refresh.
- Authorization recovery belongs to the sync CLI; the local renderer never echoes response bodies or secrets.
- Empty shelf, missing cover, missing progress, missing note link, and missing deep link are all independent branches.

## Accessibility and Quality Floor

- Semantic headings, buttons, lists, tabs/radios, visible focus, and AA contrast are mandatory.
- The active canonical book has one accessible name. Neighboring decorative repetitions and all clones stay outside the accessibility tree.
- Charts include text summaries; color is never the sole carrier of quantity or state.
- Preserve light/dark host themes, reduced motion, keyboard-only use, touch use, and multiple dashboard instances with unique ids.
- Validate a mid-transition frame, both loop boundaries, narrow width, and reduced-motion mode before release.

## Explicit Rejections

- No trends-first hero.
- No five-card horizontal information rail.
- No end-of-track hard jump.
- No forced animation under reduced motion.
- No generic KPI-card dashboard.
- No copied code, CSS, copy, or theme assets from the unlicensed reference repository.
