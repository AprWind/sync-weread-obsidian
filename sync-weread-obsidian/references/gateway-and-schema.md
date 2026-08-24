# Gateway and schema rules

Use the installed `weread-skills` instructions as the operational authority. This board does not implement an alternative WeChat Reading API. The source skill may change its version or request contract independently of this project.

## Request discipline and hard bounds

- Send the source skill's required version field on every request. Read that value from the installed source skill; do not hard-code this document's snapshot.
- Keep business fields at the JSON body root with the API name and version. Do not wrap them in a generic `params` object.
- Treat an upstream upgrade instruction as a hard stop: upgrade the official source skill, reread its relevant reference, then restart.
- A standard v2 live sync makes **at most five** `/readdata/detail` calls: current `weekly`, `monthly`, `annually`, and `overall`, plus one prior-year `annually` call to compose trailing 12-month history. Do not fan out into monthly requests.
- Make one shelf request and cursor-complete `/user/notebooks` requests with loop detection and a finite safety cap.
- Request `/book/getprogress` for at most five most recently active **public ebooks**. Never request audio progress. This bound is not a gallery limit.
- Do not call public reviews, recommendations, chapters, best bookmarks, book-info enrichment, or personal note-content endpoints during default sync.
- Default notebooks provide counts and recent activity only; a note body is requested only by an explicit single-book export.

## schemaVersion 2 local model

Write a normalized object with `schemaVersion: 2`, `generatedAt` (Unix seconds), and `source` (`live` or `sample`). New readers consume the following fields; readers may accept schema v1 as a read-only compatibility shape while all writes remain v2.

| Field | v2 shape and meaning |
| --- | --- |
| `periods.weekly`, `monthly`, `annually`, `overall` | Each contains `baseTime`, `totalReadSeconds`, `readDays`, `dayAverageReadSeconds`, optional `compare` and `recordReadingTime`, `buckets`, optional `dailyBuckets`, `rankedItems`, `categories`, `readingClock`, optional `mediaMix`, and source `readStat`. `topBooks` is retained only as a v1 compatibility projection of `rankedItems`. |
| `periods.*.rankedItems[]` | Public ebook or audio entries with stable `bookId` (`album:<id>` for audio), title, author, optional cover/deep link, `kind`, read seconds, recorded reading seconds, and tags when supplied. |
| `history.trailingMonths[]` | Exactly 12 chronological `{ month: "YYYY-MM", readSeconds }` entries derived from the current and prior annual responses plus the current monthly endpoint. |
| `insights` | Chosen category/clock insight plus optional media mix. When source reading-clock data is present, it is an ordered 24-item list from **06:00 through 05:00**, never midnight-first. `mediaMix` has optional `readRate`, `readSeconds`, and `listenSeconds`. |
| `shelf` | Public `items`, ebook/audio counts, `publicEntries`, the official-scope `totalEntries`, and aggregate `privateCount`. Private title, cover, author, ID, and other metadata are omitted. |
| `notebooks` | `totalBookCount`, `totalNoteCount`, and public/count-only book activity: stable ID, title/author/cover when provided, `noteBreakdown` (highlights, reviews, bookmarks), status, `recentNoteAt`, and derived total. No note body is present. |
| `progress[]` | At most five recent public ebook records: stable `bookId`, bounded `progressPercent`, `recordReadingSeconds`, and `updatedAt`. |

## Mapping and omission rules

- Count shelf entries using the official source skill's documented formula. `mp` and private entries may affect only aggregate totals; never expose their metadata.
- Treat documented duration fields as seconds. Calculate before formatting; absent optional values stay absent rather than becoming invented zeroes.
- Follow notebook cursor pagination exactly. Keep cursor state transient; do not publish it in notes or the repository.
- Map every record by stable upstream ID. Escape Markdown and YAML; derive readable filenames from titles only after collision-safe normalization.
- Preserve only deep links returned by source data. Never synthesize a WeRead deep link.
- The local renderer should read schema v1 defensively for existing boards, but any new sync or sample write must use schema v2.

## Sources

- Tencent WeChat Reading Skills repository: <https://github.com/Tencent/WeChatReading>
- Official key-management page linked by the source project: <https://weread.qq.com/r/weread-skills>
- Local source of truth after installation: installed `weread-skills/SKILL.md` and its capability documents.

The URLs identify upstream sources. The installed source skill controls live operational details.
