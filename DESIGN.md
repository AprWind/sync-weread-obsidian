---
name: WeRead Reading Board
description: A calm, trends-first reading dashboard for Obsidian.
colors:
  action-blue: "var(--interactive-accent, #0a84ff)"
  action-blue-soft: "color-mix(in srgb, var(--interactive-accent, #0a84ff) 12%, var(--background-primary))"
  surface: "var(--background-primary-alt)"
  surface-quiet: "var(--background-secondary)"
  text: "var(--text-normal)"
  text-muted: "var(--text-muted)"
  separator: "var(--background-modifier-border)"
  error: "var(--text-error, #ff453a)"
typography:
  display:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, PingFang SC, Hiragino Sans GB, Microsoft YaHei, sans-serif"
    fontSize: "clamp(40px, 6vw, 58px)"
    fontWeight: 700
    lineHeight: 1
    letterSpacing: "-0.04em"
  headline:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, PingFang SC, Hiragino Sans GB, Microsoft YaHei, sans-serif"
    fontSize: "28px"
    fontWeight: 700
    lineHeight: "34px"
    letterSpacing: "-0.02em"
  title:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, PingFang SC, Hiragino Sans GB, Microsoft YaHei, sans-serif"
    fontSize: "17px"
    fontWeight: 650
    lineHeight: "22px"
    letterSpacing: "-0.01em"
  body:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, PingFang SC, Hiragino Sans GB, Microsoft YaHei, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: "21px"
  metadata:
    fontFamily: "-apple-system, BlinkMacSystemFont, SF Pro Text, PingFang SC, Hiragino Sans GB, Microsoft YaHei, sans-serif"
    fontSize: "13px"
    fontWeight: 400
    lineHeight: "18px"
rounded:
  control: "10px"
  icon: "14px"
  surface: "16px"
  pill: "999px"
spacing:
  xs: "2px"
  sm: "8px"
  md: "12px"
  lg: "16px"
  xl: "20px"
  touch: "44px"
components:
  action-button:
    backgroundColor: "transparent"
    textColor: "{colors.action-blue}"
    typography: "{typography.body}"
    rounded: "{rounded.control}"
    padding: "0 10px"
    size: "44px"
  period-selected:
    backgroundColor: "{colors.action-blue}"
    textColor: "#fff"
    typography: "{typography.body}"
    rounded: "{rounded.pill}"
    height: "44px"
  grouped-surface:
    backgroundColor: "{colors.surface}"
    rounded: "{rounded.surface}"
    padding: "20px"
---

# Design System: WeRead Reading Board

## Overview

**Creative North Star: "The Quiet Reading Pulse"**

This is an Operate surface: it lets a reader understand this week's reading rhythm before asking them to browse a shelf. A large trend and one dominant total lead the view; three plain status rows confirm the state; a directly scrollable cover rail and compact follow-up sections support the next action. It borrows the calm grouping and touch clarity of system interfaces while remaining an Obsidian content pane, never a simulated phone or separate application shell.

The interface is deliberately quiet, concise, and data-led. It adapts to the host theme through semantic variables, keeps a single blue action voice, and gives status copy, labels, and controls equal responsibility for meaning. The system rejects decorative dashboard chrome, forced carousels, and color-only explanations.

**Key Characteristics:**

- Trends first; shelf content follows.
- Native-theme surfaces, separators, and system typography.
- One action accent; dense information with generous touch geometry.
- Direct horizontal browsing, explicit data state, and calm feedback.

## Colors

The palette is owned by the Obsidian theme so the board belongs in both light and dark workspaces; its only branded behavioral signal is the system action blue.

### Primary

- **System Action Blue:** use for the selected period, the reading total, interactive icons, focus treatment, and progress/data marks. Keep it sparse so an action or selected state is immediately legible.
- **Action Blue Wash:** reserve for hover fills and icon wells; it supports, rather than competes with, the primary action.

### Neutral

- **Host Surface:** the grouped card background; it carries the dashboard without impersonating a new application background.
- **Quiet Surface:** segmented-control tracks, icon wells, cover fallbacks, skeletons, and low-priority rhythm cells.
- **Primary and Muted Text:** primary text carries titles and numbers; muted text carries freshness, units, metadata, and supporting copy.
- **Host Separator:** defines group boundaries and chart baselines. It is the default depth cue.

### Tertiary

- **System Error:** use only for failed reads and their icon well. Error copy must state the recovery action as well as using this signal.

**The One Blue Voice Rule.** Do not introduce competing accents for books, metrics, or categories. Blue communicates selection, action, progress, and emphasis; all other color comes from the host's semantic theme.

## Typography

**Display Font:** the platform system stack, with SF Pro Text and Chinese system fallbacks.

**Character:** compact, highly legible, and native to the host. Large numeric metrics feel decisive; headings and metadata remain restrained enough for a reader's notes to stay central.

### Hierarchy

- **Display:** the trend total only; use tabular-looking, tightly tracked numerals as the visual anchor.
- **Headline:** the dashboard title; keep it leading and left aligned.
- **Title:** section headers, summary labels, and book titles; semibold without turning every label into a heading.
- **Body:** action labels, supporting sentences, and average reading copy.
- **Metadata:** timestamps, authors, units, detail lines, and chart labels.

**The Numbers Lead Rule.** Give a primary metric a single clear visual level; do not enlarge every count in a section or use display type for ordinary status rows.

## Layout

The desktop frame is centered with a capped reading width and a light top/bottom margin. Header and segmented period control establish context before a 7:3 upper grid: the reading trend receives most of the width and the three-row summary receives a stable, readable minimum. The cover rail spans beneath it; the lower rhythm and note groups use a near-even two-column grid.

Use the existing spacing scale for all gaps and grouped-surface insets. The trend surface has more vertical room than ordinary groups because the chart must remain readable. Keep the visible clipped next cover as an invitation to drag; do not replace the rail with pagination or automatic movement. Rails and overlong day charts scroll horizontally with containment and scroll snap, while the document keeps normal vertical scrolling.

At narrow widths, the upper and lower grids stack; grouped insets tighten, covers and rail cards shrink modestly, and arrow buttons disappear because direct touch scrolling is the control. Preserve the full-width segmented control, readable chart labels, and the visible continuation of the rail. Do not compress a multi-column summary until its labels or values collide.

## Elevation & Depth

This is a flat, tonal system. Grouped surfaces use a host surface plus a separator, and inner summary rows use separators only. There are no ambient card shadows. The selected segment, soft action wash, border baseline, and clipped scroll content supply hierarchy without visual weight.

**The One Depth Cue Rule.** A surface uses either a separator or subtle elevation, never both. The shipped board uses separators; preserve that choice unless a future host integration makes a tonal elevation necessary.

## Shapes

Grouped cards, galleries, empty states, and error states use the surface corner language. Controls, covers, compact tags, and rhythm cells use the tighter control language; icon wells use the intermediate icon corner. Only the three-way period selector is fully pill-shaped. Bar tops are gently rounded while their bases remain grounded on the chart baseline.

Borders are quiet host separators, not decorative outlines. Covers clip their image and fallback within the same compact control form. Avoid arbitrary radii, floating pills for ordinary actions, gradients, or device-frame silhouettes.

## Components

### Actions and Focus

Action buttons are text-and-icon or icon-only controls with minimum touch geometry. Their resting surface is transparent; hover receives the action wash, press gives a small scale response, and keyboard focus uses a clearly offset blue outline. The refresh label must describe a local data read, not imply a network sync.

### Period Selector

The selector is one three-option grouped control, not three unrelated buttons. It is full-width up to its readable cap, uses the quiet track and a single blue selected segment, and preserves roving focus with arrow, Home, and End keys. Keep a real checked/selected state for assistive technology.

### Trend and Summary Groups

The trend group contains a section title, unit, primary total, supporting average, and bars with visible text values and labels. The neighboring summary is exactly three calm rows with host icons, label, value, and qualifying detail. Use the same grouped surface geometry and separator logic; do not turn either into a decorative analytics widget.

### Continue-Reading Rail

Each book is a button-sized reading item with an image or clear fallback, a two-line-safe title, author, and progress. The rail has mandatory horizontal snapping and optional previous/next controls on larger screens. It never loops or moves by itself. Disabled books visibly remain non-actionable.

### Rhythm and Note Rows

Rhythm cells pair level, date, and number so intensity is never conveyed by color alone. Note rows are compact list items with icon, title, book metadata, and count/time; truncate only after preserving the primary title. Separators, not card stacking, organize the list.

### States

Loading uses skeletons matched to final header, trend, summary, and rail geometry. Empty, stale, sample, and error states are named in text as well as visually differentiated. An error has a retry control and recovery copy; prior safe content must not be represented as fresh when data cannot be read.

### Motion and Accessibility

Motion is limited to press feedback, smooth intentional rail scrolling, and a low-key skeleton pulse. With reduced motion enabled, scrolling becomes immediate and animation/transition duration collapses. Every interactive control has a visible focus state and a minimum touch target; imagery receives a useful cover label or a non-decorative fallback. Retain semantic headings, lists, radio-group behavior, live status updates, and text equivalents for charts and rhythm data.

## Do's and Don'ts

### Do:

- **Do** lead with the period, trend total, and visible freshness state before shelf information.
- **Do** use the host semantic variables so the board tracks the current Obsidian theme.
- **Do** keep action controls and selected states blue, with visible keyboard focus and text labels for state.
- **Do** make horizontal content directly scrollable with snap alignment and preserve ordinary vertical page scrolling.
- **Do** keep loading, empty, sample, stale, and error states structurally close to their ready-state geometry.

### Don't:

- **Don't** create a faux iPhone, persistent app shell, gradient dashboard, or decorative chart treatment.
- **Don't** add competing accent colors, gratuitous shadows, or a border-and-shadow combination on one surface.
- **Don't** autoplay or loop the book rail, trap scrolling, or hide the touch path on small screens.
- **Don't** use color as the sole indication of progress, status, selection, or error.
- **Don't** replace local-read wording with language that promises a network synchronization.
