# Board UI behavior

Design the board as an iPhone-inspired reading surface, not a generic analytics dashboard. Favor clear content hierarchy and calm touch feedback over decorative widgets.

## Visual and interaction rules

- Use semantic system-like colors, readable type scale, consistent rounded surfaces, and generous touch targets.
- Put the reading summary first, then shelf and current-progress content, then note activity. Use real empty states rather than placeholder metrics.
- Make the last successful synchronization time visible. Distinguish fresh, stale, sample, empty, and error states in words as well as color.
- Label the in-board action as a local data read. It rereads `.weread/reading-board.json`; it does not imply a network synchronization.
- Use accessible labels for controls, preserve keyboard navigation, and respect reduced-motion preferences.
- Keep external links visibly external and use only links returned by the source data. Do not construct deep links.

## Data integrity in UI

- Render only validated local data. Never display a future timestamp or stale data as current.
- State why a section is empty: no eligible data, first sync not completed, authorization required, or fetch error.
- Never expose raw gateway payloads, stable account identifiers, or private-item labels in the dashboard.

## Design references

- Apple Human Interface Guidelines, foundations: <https://developer.apple.com/design/human-interface-guidelines/foundations>
- Obsidian plugin developer documentation: <https://docs.obsidian.md/Plugins/Getting+started/Build+a+plugin>

Apply these as design guidance. They do not imply affiliation or endorsement.
