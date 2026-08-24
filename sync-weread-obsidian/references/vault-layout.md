# Vault layout and containment

Use this fixed, reviewable layout inside the selected Vault. Human-facing notes stay in the existing knowledge structure; machine state stays under one hidden `.weread` directory.

## Layout rules

- Install the dashboard at `00-首页/阅读看板.md` without replacing `00-首页/学习仪表盘.md` or any foreign file.
- Keep schema v2 normalized state at `.weread/reading-board.json`, monthly snapshots at `.weread/snapshots/`, and synthetic offline covers at `.weread/covers/`.
- Install the renderer only at `.obsidian/plugins/weread-reading-board/` and preserve every other enabled plugin.
- Put explicitly requested single-book exports under `20-认知记录/阅读笔记/`.
- Make the dashboard a generated view. Do not require user-authored content inside it.
- Use stable IDs in generated filenames or metadata. Allow title text only as a readable suffix.
- Resolve the Vault and destination paths before writing. Reject traversal components, unresolved locations, and destinations whose resolved path lies outside the Vault.
- Never follow a symlink from any managed destination to a location outside the Vault.

## Managed blocks

Use paired, named begin and end markers for machine-managed content. Give each block a stable record ID. Replace only the content between the exact pair.

- Preserve text before and after a valid pair byte-for-byte whenever practical.
- Abort on missing, inverted, ambiguous, or duplicated marker pairs.
- Do not rewrite a note merely to reformat user prose.
- Do not use a title as an identifier: title changes and duplicate editions are normal.

## Installation behavior

Run `doctor` before installation to confirm the intended Vault and report the current board paths. Before creating board assets, the installer validates Vault containment and preflights dashboard ownership, the renderer's integration-owned legacy signature or stable marker, and `community-plugins.json`. It refuses unknown contents in the same plugin directory, changes the enabled-plugin list only during the explicitly requested installation, and preserves every existing entry.
