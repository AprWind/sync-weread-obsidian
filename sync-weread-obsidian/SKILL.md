---
name: sync-weread-obsidian
description: Connect official WeChat Reading data to an Obsidian vault and install, repair, sync, or verify a private reading board. Use for shelf, progress, reading-statistics, highlights, and personal-note synchronization; stale-data or authorization diagnosis; and safe updates to managed book-note blocks without overwriting user writing.
---

# WeRead to Obsidian

Build and maintain a local, private Obsidian reading board from the official WeChat Reading skill. Treat the board as a derived view: WeRead remains the source of account data, while ordinary text outside managed regions remains the user's work.

This project is independent software. It is not affiliated with, endorsed by, or supported by Tencent, WeChat Reading, or Obsidian.

## Safety contract

- Use the installed official `weread-skills` source skill as the only account-data gateway. Read its capability document before each gateway capability.
- Never inspect the clipboard. Never echo, log, commit, paste, or put a secret in a command line, repository file, frontmatter, fixture, screenshot, or response.
- Ask the user to run the interactive `configure-key` action themselves when authorization is absent or invalid. Do not enter the key on their behalf.
- Resolve an Obsidian vault before any write. Keep every destination inside the resolved vault, including symlink-resolved paths.
- Exclude private shelf items by default. Do not export public reviews, recommendations, account identifiers, raw API responses, or cover caches unless the user explicitly asks.
- Do not create schedules, background jobs, launch agents, periodic refreshes, or note exports unless the user explicitly requests that exact action.
- Preserve pre-existing files and all text outside a marked managed block. Stop rather than overwrite an unrecognized or malformed managed block.

## Workflow

### 1. Preflight the source and vault

1. Confirm the official source skill is available. If it is missing, install it with the user-approved command `npx skills add Tencent/WeChatReading -g`, then reopen its `SKILL.md` and applicable capability references.
2. Read [gateway-and-schema.md](references/gateway-and-schema.md) before gateway work. Use the source skill's current version, endpoint, and request rules, never a hard-coded copy.
3. Ask for the vault path if no vault is supplied or exactly one safe vault cannot be inferred. Refuse a filesystem root, home directory, or path outside the user's intended vault.
4. Run `python3 scripts/weread_sync.py doctor --vault <vault-path>` and act on its diagnostics before installation or synchronization.
5. If authentication is missing, tell the user to run `python3 scripts/weread_sync.py configure-key`. Resume only after a new `doctor` succeeds. Do not ask them to paste a key into chat.

### 2. Install or repair the board

1. Read [vault-layout.md](references/vault-layout.md).
2. Run `python3 scripts/weread_sync.py install --vault <vault-path>` only after `doctor` resolves a contained Obsidian vault and reports no configuration conflict.
3. Let install create only the documented board assets. Do not replace an existing user note or third-party Obsidian plugin.
4. For a repair request, run `doctor` first and use the least destructive fix. Keep a timestamped recovery copy only where the script says it is safe to do so.

### 3. Synchronize and inspect

1. Run `python3 scripts/weread_sync.py sync --vault <vault-path>` for an explicitly requested manual sync.
2. Use the source skill's current shelf, progress, reading-statistics, and notebook semantics. Do not infer totals from field names.
3. Use stable upstream IDs for books, albums, highlights, and reviews. Never key files or managed content solely by a title, author, index, or timestamp.
4. Write files atomically: render to a temporary sibling, validate, then replace. If fetch, parsing, or validation fails, retain the last known-good board.
5. Confirm the resulting board reports a live source and a current successful refresh. Verify counts, links, and managed-block integrity without printing private content. If authorization is unavailable, stop after the secure `configure-key` handoff and do not claim that live synchronization succeeded.
6. Use `python3 scripts/weread_sync.py sync --vault <disposable-test-vault> --sample` only for an explicitly requested offline demonstration. It replaces board data with synthetic data and must not run in a user's populated vault.

### 4. Export book notes only on request

1. Read [privacy-and-recovery.md](references/privacy-and-recovery.md) before exporting notes.
2. Ask for a specific book if the user did not identify one. Keep export opt-in and bounded to that book.
3. Run `python3 scripts/weread_sync.py export-notes --vault <vault-path> --book-id <stable-id>` only for that explicit request.
4. Preserve the user-authored area and replace only the exact paired managed markers. Keep upstream item IDs in hidden metadata or markers so merges are repeatable.

## Diagnose before changing data

| Symptom | Required action |
| --- | --- |
| Source skill unavailable or outdated | Install or upgrade it, reread its current rules, then retry. |
| Gateway response requests an upgrade | Stop immediately, upgrade the source skill, and restart the operation. |
| Unauthorized or expired authorization | Ask the user to run `configure-key`; do not inspect environment values or secrets. |
| A page repeats or is incomplete | Check the gateway's cursor and flat-body requirements before changing local data. |
| Board is stale | Run `doctor`, then a manual `sync`; report the verified freshness time only after a live output succeeds. |
| Write path escapes the vault | Stop and correct the vault configuration. |
| Managed markers are missing or duplicated | Stop the update, create no replacement note, and explain recovery options. |

## Interface expectations

Read [board-ui.md](references/board-ui.md) when changing the bundled Obsidian view. Preserve an iPhone-inspired reading surface: calm hierarchy, system-like navigation, legible native controls, semantic colors, and visible refresh state. Show empty, loading, stale, and error states. Do not fake live data or disguise a failed sync as fresh data.

## Completion checklist

- Confirm the official source skill was read and its current version rules were applied.
- Confirm `doctor`, install or repair if needed, and one requested manual live sync succeeded when authorization was available. Otherwise report the exact remaining user-run authorization step. Record any separate synthetic sample only as an offline test.
- Confirm data stayed inside the selected vault and no private items or credentials entered the repository.
- Confirm book-note exports occurred only when explicitly requested and retained user-authored text.
- Report the board location, action performed, verified freshness, and any intentionally skipped optional action.

## References

- Read [gateway-and-schema.md](references/gateway-and-schema.md) for gateway versioning, flat request bodies, pagination, and source semantics.
- Read [vault-layout.md](references/vault-layout.md) before install, repair, or path changes.
- Read [privacy-and-recovery.md](references/privacy-and-recovery.md) before export, recovery, or any unusual write.
- Read [board-ui.md](references/board-ui.md) before changing the Obsidian board's interaction or appearance.
