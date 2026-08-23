# Privacy and recovery

Treat reading activity, highlights, personal thoughts, and shelf membership as private data.

## Exclusions by default

- Omit private shelf entries, account identifiers, raw responses, authorization material, diagnostics containing payloads, cached covers, and any data the user did not request.
- Do not commit or publish a populated vault, dashboard data, note exports, archive, log, or machine-local configuration.
- Use synthetic fixtures only for tests. Mark them synthetic and keep them distinct from live paths.

## Secret handling

- Do not read the clipboard, prompt for a key in conversation, read environment values for display, or include secrets in shell history, logs, examples, or tests.
- Direct the user to the interactive `configure-key` command. It must collect and store authorization outside the repository with restrictive file permissions.
- When authentication fails, report only the failure class and the next user action.

## Failure and recovery

- Fetch and validate before replacing an existing output.
- Write candidate output to a temporary sibling file, validate managed markers and IDs, then perform one atomic rename.
- Preserve the last known-good file when an operation fails. Do not erase a board to make an error look clean.
- Before a destructive recovery action, state the exact affected paths and obtain explicit approval.
- Offer export only after the user explicitly requests it; exported notes remain user-private and should not be scheduled automatically.

## Attribution

This project is independent and uses the official Tencent WeChat Reading Skills project only as its data-access source. It has no affiliation with Tencent, WeChat Reading, or Obsidian.
