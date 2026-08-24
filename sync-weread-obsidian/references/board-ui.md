# Board UI behavior

Design the board as a calm, iPhone-inspired reading surface inside Obsidian, not a generic analytics dashboard. The approved B direction is **gallery first**: dense book covers set the rhythm; personal reading detail unfolds below them.

## Information order

1. Show the local freshness timestamp and compact 本月 / 本周 / 今天 / 年度 period controls. The `overall` source period is normalized for compatibility but has no selectable board control.
2. Show the public-cover gallery as the first substantial reading content.
3. Show the selected book's title, creator, completion/progress, reading time, recent activity, note count, safe WeRead link when supplied, and local exported-note link when present.
4. Follow with the selected period's calendar or daily buckets, 12-month history, `06:00 → 05:00` reading clock, categories, media mix, and count-only recent notebook activity.

Avoid generic KPI-card grids and any claim that a local refresh is a network refresh. The in-board refresh only rereads `.weread/reading-board.json`.

## Gallery interaction contract

- Render up to twelve deduplicated local book records, combining monthly and weekly ranked records with shelf records and sorting by recorded reading activity. A five-book cap applies only to upstream ebook progress lookups, never to the gallery.
- Maintain a logical selected index. The visual rail may use cloned or virtualized edge items, but must map all actions back to one real public-book record.
- Loop without a visible end jump. If the implementation repositions a scroller after crossing a clone boundary, do it between frames and retain the same selected record and focus intent.
- Provide explicit previous, next, and pause/play controls with accessible names and visible focus. Play state must be textually conveyed, not color-only.
- Support pointer and touch drag, horizontal scrolling, mouse-wheel/trackpad motion, and Left/Right/Home/End on the focused gallery viewport without trapping focus.
- Selecting a cover updates the selected-book detail. A missing external deep link disables only the external-open action; it must not prevent selection.
- Pause automatic movement on hover, focus within the gallery, pointer/touch drag, invisible/offscreen state, document hidden state, and any interaction that would make a moving target hard to use. Resume only when playback is enabled and no pause reason remains.
- Respect `prefers-reduced-motion`: start paused, never auto-advance, and use immediate or minimal transitions. The pause/play control may still allow deliberate stepwise navigation.
- Do not use a fake 3D carousel, cover-only text substitutes, abruptly resetting scroll position, or a loop that makes keyboard focus disappear.

## Accessibility and state

- Use real buttons and links, 44 px minimum touch targets where practical, semantic labels, logical tab order, visible focus, and keyboard-operable actions.
- Announce selected-book changes succinctly in a bounded live region. Do not place the entire board in an `aria-live` container.
- Keep cover images decorative when title/creator is adjacent; otherwise provide meaningful alternative text. Do not reveal private titles or metadata.
- Make sample, empty, loading, and error states visible in words as well as color, and show the local freshness timestamp without representing it as a network refresh. Never display a future timestamp as current.
- State why a section is empty: no eligible public data, first sync not completed, authorization required, or fetch error.
- Read only the local board JSON and use source-supplied links that pass the renderer's safe-link check. Do not construct deep links.

## Visual language

- Use Obsidian semantic colors, Apple system-font fallbacks, one restrained accent, and quiet surfaces that work in both themes.
- Favor reading texture—covers, timeline marks, concise labels—over ornamental charts. Keep motion as subtle feedback, not a competing visual layer.
- Use readable type hierarchy and comfortable spacing; keep text in the selected-book detail selectable and unclipped.

## Design references

- Apple Human Interface Guidelines, foundations: <https://developer.apple.com/design/human-interface-guidelines/foundations>
- Obsidian plugin developer documentation: <https://docs.obsidian.md/Plugins/Getting+started/Build+a+plugin>

These are design guidance only and do not imply affiliation or endorsement.
