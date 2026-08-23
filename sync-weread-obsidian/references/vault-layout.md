# Vault layout and containment

Use this fixed, reviewable layout inside the selected vault. Human-facing notes stay in the vault's existing knowledge structure; machine state stays under one hidden `.weread` directory.

## Layout rules

- Install the dashboard at `00-首页/阅读看板.md` without replacing `00-首页/学习仪表盘.md` or any foreign file.
- Keep normalized state at `.weread/reading-board.json`, monthly snapshots at `.weread/snapshots/`, and synthetic offline covers at `.weread/covers/`.
- Install the renderer only at `.obsidian/plugins/weread-reading-board/` and preserve every other enabled plugin.
- Put explicitly requested per-book exports under `20-认知记录/阅读笔记/`.
- Make the dashboard a generated view. Do not require user-authored content inside it.
- Use stable IDs in generated filenames or metadata. Allow title text only as a readable suffix.
- Resolve the vault and destination paths before writing. Reject traversal components, unresolved locations, and destinations whose resolved path lies outside the vault.
- Never follow a symlink from any managed destination to a location outside the vault.

## Managed blocks

Use paired, named begin and end markers for machine-managed content. Give each block a stable record ID. Replace only the content between the exact pair.

- Preserve text before and after a valid pair byte-for-byte whenever practical.
- Abort on missing, inverted, ambiguous, or duplicated marker pairs.
- Do not rewrite a note merely to reformat user prose.
- Do not use a title as an identifier: title changes and duplicate editions are normal.

## Installation behavior

Create required folders and board assets only after `doctor` verifies containment and write permission. Change the Obsidian enabled-plugin list only as part of the explicitly requested board installation, preserving every existing entry.
