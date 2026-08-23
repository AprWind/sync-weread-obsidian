# Gateway and schema rules

Use the current local `weread-skills` instructions as the authority. This board does not implement an alternative WeChat Reading API.

## Request discipline

- Send the source skill's required version field on every gateway request. Obtain the value from the installed source skill rather than this document.
- Keep business fields at the JSON body root with the API name and version. Do not nest them in a generic parameter wrapper.
- Treat a returned upgrade instruction as a hard stop: upgrade the source skill, reread its current capability file, then restart.
- Read the relevant source reference before calling a capability: shelf for shelf data, reading-data for statistics, notes for highlights and personal notes, and book data for progress.

## Local mapping rules

- Count shelf entries with the source skill's documented formula. Do not substitute a server-side count with a different scope.
- Treat reading durations as seconds when the source documentation says so; format only after calculating.
- Follow cursor pagination exactly. Store a cursor only in transient process state, not in published notes or the repository.
- Map each record by its stable upstream ID. Escape Markdown and YAML values; derive readable filenames from titles only after collision-safe normalization.
- Treat absent optional fields as absent, not zero. Do not manufacture progress, notes, ratings, links, or dates.

## Sources

- Tencent WeChat Reading Skills repository: <https://github.com/Tencent/WeChatReading>
- Official key-management page linked by the source project: <https://weread.qq.com/r/weread-skills>
- Local source of truth after installation: the installed `weread-skills/SKILL.md` and its capability documents.

The URLs identify upstream sources. The local installed source skill controls operational details because the gateway can change independently of this board.
