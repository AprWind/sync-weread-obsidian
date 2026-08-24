# Privacy and recovery

Treat reading activity, highlights, personal thoughts, and shelf membership as private data.

## Exclusions by default

- Omit private shelf metadata, account identifiers, raw responses, authorization material, payload-bearing diagnostics, cached covers, and any data the user did not request.
- Private shelf entries contribute only an aggregate count; their titles, authors, covers, IDs, and statuses never enter the dashboard state.
- Do not commit or publish a populated Vault, state file, note export, archive, log, or machine-local configuration.
- Use synthetic fixtures only for tests. Mark them synthetic and keep them separate from live paths.
- Default synchronization may collect notebook counts and recent activity, but never fetches or renders note bodies. Public reviews, recommendations, chapters, and content endpoints are out of scope by default.

## Secret handling

- Do not read the clipboard, prompt for a key in conversation, read environment values for display, or include secrets in shell history, logs, examples, tests, screenshots, or command arguments.
- Direct the user to interactive `configure-key`. It stores authorization outside the repository and Vault in macOS Keychain; an environment variable is a user-managed alternative. Existing Keychain credentials are updated in place, so a failed native write does not first delete the last credential.
- If the gateway returns `401`, report the authorization failure class only. Ask the user to acquire a fresh official key, rerun `configure-key`, then run `doctor` and their requested sync.

## Failure and recovery

- Complete fetch, parsing, and normalization before replacing state. Each state file uses a temporary sibling and atomic rename; the board model and live monthly snapshot share rollback semantics.
- Preserve the last known-good board when an operation fails. Do not erase a board to make an error look clean.
- Before a destructive recovery action, state the exact affected paths and obtain explicit approval.
- Export notes only after the user explicitly asks for one stable book ID. Exported notes remain user-private and must not be scheduled automatically.

## Attribution

This independent project uses the official Tencent WeChat Reading Skills project only as a data-access source. Its gallery-first behavior is independently implemented; it does not copy external code, text, styles, or assets. It has no affiliation with Tencent, WeChat Reading, or Obsidian.
