---
name: sync-weread-obsidian
description: Connect official WeChat Reading data to an Obsidian vault and install, repair, sync, or verify a private reading board. Use for shelf, progress, reading statistics, note counts, authorization diagnosis, and safe single-book note exports without overwriting user writing.
---

# WeRead to Obsidian

Build and maintain a local, private Obsidian reading board from the official WeChat Reading skill. The board is a derived view: WeRead remains the source of account data, and ordinary text outside managed regions remains the user's work.

The board is gallery-first: a dense, logically seamless public-cover loop leads the view, then reveals the selected book and deeper reading history. It is independent software and is not affiliated with, endorsed by, or supported by Tencent, WeChat Reading, or Obsidian.

## Safety contract

- Use the installed official `weread-skills` source skill as the only account-data gateway. Read its relevant capability document before each gateway capability.
- Never inspect the clipboard. Never echo, log, commit, paste, or put a secret in a command line, repository file, frontmatter, fixture, screenshot, or response.
- When authorization is absent, expired, or returns `401`, ask the user to acquire a fresh official key and run the interactive `configure-key` action themselves. Do not enter the key on their behalf.
- `configure-key` stores authorization outside the repository and Vault (macOS Keychain). Do not request a key in chat or inspect environment values for display.
- Resolve an Obsidian vault before any write. Keep every destination inside the resolved vault, including symlink-resolved paths.
- Exclude private shelf metadata by default; preserve only the aggregate private count. Do not export public reviews, recommendations, account identifiers, raw API responses, or cover caches.
- Default synchronization never fetches note bodies. Single-book note export is opt-in, bounded to the named stable ID, and must preserve all non-managed writing.
- Do not create schedules, background jobs, launch agents, periodic refreshes, or note exports unless the user explicitly requests that action.

## Workflow

### 1. Preflight the source and vault

1. Confirm the official source skill is available. If missing, use the user-approved command `npx skills add Tencent/WeChatReading -g`, then reopen its `SKILL.md` and relevant references.
2. Read [gateway-and-schema.md](references/gateway-and-schema.md) before gateway work. The installed source skill is the authority for its version, endpoint, and request contract.
3. Resolve exactly one safe Vault. Refuse a filesystem root, home directory, or an unverified path outside the intended Vault.
4. Run `python3 scripts/weread_sync.py doctor --vault <vault-path>` before install, repair, or sync.
5. If credential status is missing or the gateway reports `401`, tell the user to obtain a fresh official key and run `python3 scripts/weread_sync.py configure-key --gui` in the local macOS secure dialog (or omit `--gui` for hidden terminal input). Resume only after `doctor` reports a credential is available; do not claim a live sync until it succeeds.

### 2. Install or repair the board

1. Read [vault-layout.md](references/vault-layout.md).
2. Run `python3 scripts/weread_sync.py install --vault <vault-path>` only after `doctor` confirms the intended Vault. Before writing, the installer preflights dashboard ownership, the renderer's integration-owned signature or marker, and `community-plugins.json`.
3. Let install create only documented board assets. Do not replace an existing user note, another dashboard, or a third-party Obsidian plugin.
4. For repair, run `doctor` first and use the least destructive fix. Do not invent a recovery copy or overwrite an unrecognized dashboard.

### 3. Manually synchronize and verify

1. Run `python3 scripts/weread_sync.py sync --vault <vault-path>` only for an explicitly requested manual sync.
2. Read the official source references for shelf, reading statistics, notebooks, and progress. Use stable upstream IDs; never key files or managed content only by title, author, index, or timestamp.
3. Respect the bounded v2 request plan in [gateway-and-schema.md](references/gateway-and-schema.md): at most five reading-statistics calls, one shelf call, cursor-complete notebooks, and at most five recent **public ebooks** for progress. Do not turn the gallery size into a request fan-out.
4. Build the full model before writing it. Each file uses a temporary sibling and atomic replacement; the board model and live monthly snapshot are applied as one rollback group. Fetch, parsing, pagination, or grouped-write failures must not leave a newly reported successful model.
5. Verify the board's source state, freshness, counts, safe links, managed-block integrity, keyboard interaction, and reduced-motion behavior without printing private content. If authorization is unavailable, stop after the secure handoff.
6. `python3 scripts/weread_sync.py sync --vault <disposable-test-vault> --sample` is only for an explicitly requested offline demonstration. It replaces board data with synthetic data and must not run in a populated Vault.

### 4. Export one book's notes only on request

1. Read [privacy-and-recovery.md](references/privacy-and-recovery.md) before exporting notes.
2. Ask for a single stable `book-id` if none was supplied.
3. Run `python3 scripts/weread_sync.py export-notes --vault <vault-path> --book-id <stable-id>` only for that explicit request.
4. Preserve user-authored text and replace only the exact paired managed markers. Keep upstream IDs in hidden metadata or markers so future merges remain stable.

## Diagnose before changing data

| Symptom | Required action |
| --- | --- |
| Source skill unavailable or outdated | Install or upgrade it, reread its current rules, then retry. |
| Gateway requests an upgrade | Stop immediately, upgrade the source skill, reread its capability file, and restart. |
| `401`, unauthorized, or expired authorization | Ask the user to obtain a fresh official key and run interactive `configure-key`; never inspect a key or clipboard. |
| Notebook page repeats or is incomplete | Check the documented cursor and flat-body rules before changing local data. |
| Board is stale | Run `doctor`, then a manual `sync`; report freshness only after live output succeeds. |
| Write path escapes the Vault | Stop and correct the Vault configuration. |
| Managed markers are missing or duplicated | Stop the update, create no replacement note, and explain recovery options. |

## Board contract

Read [board-ui.md](references/board-ui.md) before changing the bundled Obsidian view. Preserve its approved B-direction behavior: a dense logical cover loop, selected-book detail, period controls, history and insight views, and an iPhone-inspired but native Obsidian surface. Never fake live data or disguise a failed sync as fresh data.

## Completion checklist

- Confirm the official source skill and relevant current capability rules were read.
- Confirm `doctor`, requested install or repair, and requested manual live sync succeeded when authorization was available. Otherwise report only the remaining user-run authorization step.
- Confirm the schema v2 state stayed inside the selected Vault, private metadata and credentials stayed out, and no default note body was requested.
- Confirm progress requests were limited to at most five public ebooks and any note export was explicitly requested for one book.
- Confirm gallery controls work by pointer/touch, wheel, keyboard, pause/play, and reduced-motion preference; check selected-book detail and source/freshness states.
- Report the board location, action performed, verified freshness, and intentionally skipped optional actions.

## References

- Read [gateway-and-schema.md](references/gateway-and-schema.md) for v2 fields, request bounds, compatibility, pagination, and source semantics.
- Read [vault-layout.md](references/vault-layout.md) before install, repair, or path changes.
- Read [privacy-and-recovery.md](references/privacy-and-recovery.md) before export, recovery, or unusual writes.
- Read [board-ui.md](references/board-ui.md) before changing interaction or appearance.
