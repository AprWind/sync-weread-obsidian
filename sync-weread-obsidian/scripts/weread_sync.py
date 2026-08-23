#!/usr/bin/env python3
"""Secure, dependency-free synchronizer for WeRead's Agent Gateway and Obsidian.

This program intentionally never writes a credential to the vault or to a
configuration file.  The only optional persistence location is macOS Keychain,
and it is used only by the explicit ``configure-key`` command.
"""
from __future__ import annotations

import argparse
import datetime as dt
import getpass
import html
import json
import os
import subprocess
import sys
import tempfile
import time
import re
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


GATEWAY_URL = "https://i.weread.qq.com/api/agent/gateway"
FALLBACK_SKILL_VERSION = "1.0.4"
PLUGIN_ID = "weread-reading-board"
MODEL_VERSION = 1
DEFAULT_SERVICE = "weread-reading-board"
DEFAULT_ACCOUNT = "weread_api_key"
MANAGED_START = "<!-- weread-reading-board:begin -->"
MANAGED_END = "<!-- weread-reading-board:end -->"
DASHBOARD_PARTS = ("00-首页", "阅读看板.md")
NOTES_PARTS = ("20-认知记录", "阅读笔记")
DASHBOARD_SIGNATURE = b"<!-- weread-reading-board:dashboard -->"
CHINA_TZ = dt.timezone(dt.timedelta(hours=8), name="Asia/Shanghai")


class SyncError(RuntimeError):
    """A safe, human-readable operational error."""


class GatewayError(SyncError):
    """The official gateway rejected a request or requested an upgrade."""


def safe_int(value: Any, default: int = 0) -> int:
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def as_dict(value: Any) -> Dict[str, Any]:
    return value if isinstance(value, dict) else {}


def as_list(value: Any) -> List[Any]:
    return value if isinstance(value, list) else []


def validate_vault(value: str) -> Path:
    vault = Path(value).expanduser().resolve()
    if not vault.is_dir() or not (vault / ".obsidian").is_dir():
        raise SyncError("--vault 必须是包含 .obsidian 目录的 Obsidian 库。")
    return vault


def in_vault(vault: Path, *parts: str) -> Path:
    """Return a child path and reject all traversal, including symlink escapes."""
    vault = vault.resolve()
    target = (vault / Path(*parts)).resolve()
    try:
        target.relative_to(vault)
    except ValueError as exc:
        raise SyncError("拒绝写入 Obsidian 库外的路径。") from exc
    return target


def atomic_write_bytes(destination: Path, content: bytes) -> None:
    """Write atomically in the destination directory; old output survives errors."""
    destination.parent.mkdir(parents=True, exist_ok=True)
    fd, temporary = tempfile.mkstemp(prefix=".%s." % destination.name, dir=str(destination.parent))
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, destination)
    except BaseException:
        try:
            os.unlink(temporary)
        except FileNotFoundError:
            pass
        raise


def atomic_write_json(destination: Path, data: Dict[str, Any]) -> None:
    serialized = json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    atomic_write_bytes(destination, serialized.encode("utf-8"))


def load_keychain(service: str = DEFAULT_SERVICE, account: str = DEFAULT_ACCOUNT) -> Optional[str]:
    """Read a key from Keychain without exposing it to stdout, stderr, or logs."""
    if sys.platform != "darwin":
        return None
    result = subprocess.run(
        ["security", "find-generic-password", "-s", service, "-a", account, "-w"],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return None
    key = result.stdout.rstrip("\r\n")
    return key or None


def resolve_api_key(args: argparse.Namespace) -> str:
    key = os.environ.get("WEREAD_API_KEY") or load_keychain(args.keychain_service, args.keychain_account)
    if not key:
        raise SyncError("未找到 WEREAD_API_KEY；请设置环境变量，或先运行 configure-key。")
    return key


def configure_key(args: argparse.Namespace) -> None:
    if sys.platform != "darwin":
        raise SyncError("configure-key 仅支持 macOS Keychain；请改用 WEREAD_API_KEY 环境变量。")
    key = getpass.getpass("WeRead API key (不会显示或写入 vault): ").strip()
    if not key:
        raise SyncError("未输入 API key，未做任何更改。")
    result = subprocess.run(
        ["security", "add-generic-password", "-U", "-s", args.keychain_service,
         "-a", args.keychain_account, "-w", key],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise SyncError("无法写入 macOS Keychain。")
    print("API key 已存入 macOS Keychain。")


def resolve_skill_version(paths: Optional[Iterable[Path]] = None) -> tuple[str, str]:
    """Use the installed official skill version, with an explicit safe fallback."""
    candidates = list(paths) if paths is not None else [
        Path.home() / ".agents" / "skills" / "weread-skills" / "SKILL.md",
        Path.home() / ".codex" / "skills" / "weread-skills" / "SKILL.md",
    ]
    for candidate in candidates:
        try:
            match = re.search(r"^version:\s*([0-9]+(?:\.[0-9]+)*)\s*$", candidate.read_text(encoding="utf-8"), re.MULTILINE)
        except OSError:
            continue
        if match:
            return match.group(1), str(candidate)
    return FALLBACK_SKILL_VERSION, "fallback (no installed weread-skills/SKILL.md found)"


class Gateway:
    def __init__(self, api_key: str, timeout: float = 15.0, retries: int = 2, skill_version: Optional[str] = None) -> None:
        self.api_key = api_key
        self.timeout = timeout
        self.retries = retries
        resolved, source = resolve_skill_version()
        if source.startswith("fallback"):
            raise GatewayError("未找到已安装的官方 weread-skills 版本信息，拒绝发起实时同步。")
        self.skill_version = skill_version or resolved
        self.skill_version_source = "explicit" if skill_version else source

    def call(self, api_name: str, **business_args: Any) -> Dict[str, Any]:
        # The gateway requires a flat request body. Never nest business args.
        body = {"api_name": api_name, **business_args, "skill_version": self.skill_version}
        encoded = json.dumps(body, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        request = Request(
            GATEWAY_URL,
            data=encoded,
            headers={"Authorization": "Bearer " + self.api_key, "Content-Type": "application/json"},
            method="POST",
        )
        last_error: Optional[BaseException] = None
        for attempt in range(self.retries + 1):
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                if not isinstance(payload, dict):
                    raise GatewayError("微信读书返回了无效数据。")
                if payload.get("upgrade_info") is not None:
                    message = as_dict(payload.get("upgrade_info")).get("message")
                    raise GatewayError("微信读书要求升级，请先升级 skill。" + (" " + str(message) if message else ""))
                if safe_int(payload.get("errcode")) != 0:
                    raise GatewayError("微信读书接口返回错误（errcode %s）。" % safe_int(payload.get("errcode")))
                return payload
            except GatewayError:
                raise
            except HTTPError as exc:
                last_error = exc
                if exc.code not in (408, 425, 429) and not (500 <= exc.code < 600):
                    break
            except (URLError, TimeoutError, ValueError) as exc:
                last_error = exc
            if attempt < self.retries:
                time.sleep(0.25 * (2 ** attempt))
        raise GatewayError("微信读书接口暂时不可用，请稍后重试。") from last_error


def period(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize documented semantics: all duration fields are seconds."""
    return {
        "baseTime": safe_int(raw.get("baseTime")),
        "totalReadSeconds": safe_int(raw.get("totalReadTime")),
        "readDays": safe_int(raw.get("readDays")),
        "dayAverageReadSeconds": safe_int(raw.get("dayAverageReadTime")),
        "compare": raw.get("compare"),
        "buckets": {str(k): safe_int(v) for k, v in as_dict(raw.get("readTimes")).items()},
        "topBooks": [
            {"bookId": str(as_dict(item.get("book")).get("bookId", "")),
             "title": as_dict(item.get("book")).get("title", ""),
             "author": as_dict(item.get("book")).get("author", ""),
             "readSeconds": safe_int(item.get("readTime"))}
            for item in as_list(raw.get("readLongest")) if isinstance(item, dict)
        ],
    }


def normalize_shelf(raw: Dict[str, Any]) -> Dict[str, Any]:
    books: List[Dict[str, Any]] = []
    private_count = 0
    for item in as_list(raw.get("books")):
        if not isinstance(item, dict):
            continue
        book_id = item.get("bookId")
        if book_id is None:
            continue
        if safe_int(item.get("secret")) == 1:
            private_count += 1
            continue
        normalized = {"bookId": str(book_id), "title": item.get("title", ""), "author": item.get("author", ""),
                      "cover": item.get("cover", ""), "category": item.get("category", ""),
                      "readUpdateTime": safe_int(item.get("readUpdateTime")), "finished": safe_int(item.get("finishReading")) == 1,
                      "kind": "ebook"}
        # Deep links are supplied by WeRead. Do not synthesize one when absent.
        if "deepLink" in item:
            normalized["deepLink"] = item["deepLink"]
        books.append(normalized)
    albums: List[Dict[str, Any]] = []
    for item in as_list(raw.get("albums")):
        if not isinstance(item, dict):
            continue
        info = as_dict(item.get("albumInfo"))
        extra = as_dict(item.get("albumInfoExtra"))
        album_id = info.get("albumId")
        if album_id is None:
            continue
        if safe_int(extra.get("secret")) == 1:
            private_count += 1
            continue
        albums.append({"bookId": "album:" + str(album_id), "title": info.get("name", ""), "author": info.get("authorName", ""),
                       "cover": info.get("cover", ""), "readUpdateTime": safe_int(extra.get("lectureReadUpdateTime")),
                       "finished": safe_int(info.get("finish")) == 1, "kind": "audio"})
    has_mp = bool(raw.get("mp"))
    # Article favourites are private-only in WeRead, so expose only their count.
    private_count += int(has_mp)
    return {"items": books + albums, "ebooks": len(books), "audiobooks": len(albums),
            "totalEntries": len(books) + len(albums), "privateCount": private_count}


def fetch_notebooks(gateway: Gateway, page_size: int = 100) -> Dict[str, Any]:
    entries: List[Dict[str, Any]] = []
    last_sort: Optional[int] = None
    total_book_count = total_note_count = 0
    # Guard cursor loops. A broken response cannot consume unbounded requests.
    for _ in range(100):
        args: Dict[str, Any] = {"count": page_size}
        if last_sort is not None:
            args["lastSort"] = last_sort
        payload = gateway.call("/user/notebooks", **args)
        total_book_count = safe_int(payload.get("totalBookCount"), total_book_count)
        total_note_count = safe_int(payload.get("totalNoteCount"), total_note_count)
        page = [item for item in as_list(payload.get("books")) if isinstance(item, dict)]
        for item in page:
            book = as_dict(item.get("book"))
            book_id = item.get("bookId") or book.get("bookId")
            if book_id is None:
                continue
            entries.append({"bookId": str(book_id), "title": book.get("title", ""), "author": book.get("author", ""),
                            "highlightCount": safe_int(item.get("noteCount")), "reviewCount": safe_int(item.get("reviewCount")),
                            "bookmarkCount": safe_int(item.get("bookmarkCount")), "readingProgress": safe_int(item.get("readingProgress")),
                            "sort": safe_int(item.get("sort"))})
        if safe_int(payload.get("hasMore")) != 1:
            break
        if not page or safe_int(page[-1].get("sort")) == last_sort:
            raise GatewayError("笔记分页游标无效，已安全停止同步。")
        last_sort = safe_int(page[-1].get("sort"))
    else:
        raise GatewayError("笔记分页超过安全上限，已停止同步。")
    for entry in entries:
        entry["noteTotal"] = entry["highlightCount"] + entry["reviewCount"] + entry["bookmarkCount"]
    entries.sort(key=lambda item: (-item["noteTotal"], str(item["bookId"])))
    return {"totalBookCount": total_book_count, "totalNoteCount": total_note_count, "books": entries}


def build_live_model(gateway: Gateway) -> Dict[str, Any]:
    periods = {mode: period(gateway.call("/readdata/detail", mode=mode)) for mode in ("weekly", "monthly", "overall")}
    shelf = normalize_shelf(gateway.call("/shelf/sync"))
    notebooks = fetch_notebooks(gateway)
    latest = sorted((item for item in shelf["items"] if item["kind"] == "ebook"),
                    key=lambda item: (-item["readUpdateTime"], item["bookId"]))[:5]
    progress: List[Dict[str, Any]] = []
    for item in latest:
        response = gateway.call("/book/getprogress", bookId=item["bookId"])
        book = as_dict(response.get("book"))
        progress.append({"bookId": item["bookId"], "progressPercent": max(0, min(100, safe_int(book.get("progress")))),
                         "recordReadingSeconds": safe_int(book.get("recordReadingTime")),
                         "updatedAt": safe_int(book.get("updateTime"))})
    return {"schemaVersion": MODEL_VERSION, "generatedAt": int(time.time()), "source": "live",
            "periods": periods, "shelf": shelf, "notebooks": notebooks, "progress": progress}


def sample_model() -> Dict[str, Any]:
    # Deliberately benign synthetic data. It enables a complete offline demo.
    return {"schemaVersion": MODEL_VERSION, "generatedAt": 1704038400, "source": "sample",
            "periods": {"weekly": {"baseTime": 1704038400, "totalReadSeconds": 7200, "readDays": 6,
                                      "dayAverageReadSeconds": 1028, "compare": 0.12,
                                      "buckets": {1704038400: 480, 1704124800: 900, 1704211200: 600, 1704297600: 1200, 1704384000: 0, 1704470400: 1620, 1704556800: 2400}, "topBooks": []},
                        "monthly": {"baseTime": 1704038400, "totalReadSeconds": 21600, "readDays": 11,
                                       "dayAverageReadSeconds": 720, "compare": None,
                                       "buckets": {1704038400: 600, 1704124800: 1200, 1704211200: 0, 1704297600: 900, 1704384000: 1800, 1704470400: 1500, 1704556800: 300, 1704643200: 2100, 1704729600: 1200, 1704816000: 2400, 1704902400: 3300, 1704988800: 6300}, "topBooks": []},
                        "overall": {"baseTime": 0, "totalReadSeconds": 86400, "readDays": 24,
                                      "dayAverageReadSeconds": 3600, "compare": None,
                                      "buckets": {1640966400: 14400, 1672502400: 28800, 1704038400: 43200}, "topBooks": []}},
            "shelf": {"items": [{"bookId": "sample-book-1", "title": "示例阅读", "author": "示例作者", "cover": ".weread/covers/sample-01.webp", "category": "", "readUpdateTime": 1704067200, "finished": False, "kind": "ebook"}, {"bookId": "sample-book-2", "title": "第二本示例书", "author": "示例作者", "cover": ".weread/covers/sample-02.webp", "category": "", "readUpdateTime": 1703980800, "finished": False, "kind": "ebook"}, {"bookId": "sample-book-3", "title": "漫游的文字", "author": "合成作者", "cover": ".weread/covers/sample-03.webp", "category": "", "readUpdateTime": 1703894400, "finished": False, "kind": "ebook"}, {"bookId": "sample-book-4", "title": "城市与记忆", "author": "合成作者", "cover": ".weread/covers/sample-04.webp", "category": "", "readUpdateTime": 1703808000, "finished": True, "kind": "ebook"}, {"bookId": "sample-book-5", "title": "安静的科学", "author": "合成作者", "cover": ".weread/covers/sample-05.webp", "category": "", "readUpdateTime": 1703721600, "finished": False, "kind": "ebook"}], "ebooks": 5, "audiobooks": 0, "totalEntries": 5, "privateCount": 0},
            "notebooks": {"totalBookCount": 1, "totalNoteCount": 2, "books": [{"bookId": "sample-book-1", "title": "示例阅读", "author": "示例作者", "highlightCount": 1, "reviewCount": 1, "bookmarkCount": 0, "readingProgress": 40, "sort": 1704067200, "noteTotal": 2}]},
            "progress": [{"bookId": "sample-book-1", "progressPercent": 40, "recordReadingSeconds": 3600, "updatedAt": 1704067200}, {"bookId": "sample-book-2", "progressPercent": 72, "recordReadingSeconds": 7200, "updatedAt": 1703980800}, {"bookId": "sample-book-3", "progressPercent": 15, "recordReadingSeconds": 900, "updatedAt": 1703894400}, {"bookId": "sample-book-4", "progressPercent": 100, "recordReadingSeconds": 12600, "updatedAt": 1703808000}, {"bookId": "sample-book-5", "progressPercent": 5, "recordReadingSeconds": 300, "updatedAt": 1703721600}]}


def restore_installation(written: List[tuple[Path, Optional[bytes]]]) -> None:
    """Best-effort transaction rollback for files owned by this integration."""
    for destination, previous in reversed(written):
        try:
            if previous is None:
                destination.unlink(missing_ok=True)
            else:
                atomic_write_bytes(destination, previous)
        except OSError:
            # Preserve the original error. Atomic writes keep a previous file
            # intact for the common single-file failure case.
            pass


def apply_installation(operations: List[tuple[Path, bytes]]) -> None:
    """Apply a fully preflighted install and restore already-written files on error."""
    written: List[tuple[Path, Optional[bytes]]] = []
    try:
        for destination, content in operations:
            previous = destination.read_bytes() if destination.exists() else None
            atomic_write_bytes(destination, content)
            written.append((destination, previous))
    except BaseException:
        restore_installation(written)
        raise


def install(vault: Path) -> None:
    """Install only owned files after every conflict and JSON preflight passes."""
    root = Path(__file__).resolve().parents[1]
    source_plugin = root / "assets" / "obsidian-plugin"
    source_note = root / "assets" / "dashboard-note.md"
    source_covers = root / "assets" / "sample-covers"
    dashboard = in_vault(vault, *DASHBOARD_PARTS)
    plugin_list = in_vault(vault, ".obsidian", "community-plugins.json")
    source_dashboard = source_note.read_bytes() if source_note.is_file() else None
    # Preflight *before* creating .weread or writing any plugin file.
    if dashboard.exists() and source_dashboard is not None:
        existing_dashboard = dashboard.read_bytes()
        if existing_dashboard != source_dashboard and DASHBOARD_SIGNATURE not in existing_dashboard:
            raise SyncError("阅读看板已存在且不是本集成受管文件，未修改任何文件。")
    existing: List[Any] = []
    if plugin_list.exists():
        try:
            loaded = json.loads(plugin_list.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError) as exc:
            raise SyncError("community-plugins.json 无法解析，未修改任何文件。") from exc
        if not isinstance(loaded, list):
            raise SyncError("community-plugins.json 格式错误，未修改任何文件。")
        existing = loaded
    operations: List[tuple[Path, bytes]] = []
    if source_plugin.is_dir():
        for source in source_plugin.rglob("*"):
            if source.is_file():
                relative = source.relative_to(source_plugin)
                destination = in_vault(vault, ".obsidian", "plugins", PLUGIN_ID, *relative.parts)
                operations.append((destination, source.read_bytes()))
    if source_dashboard is not None and (not dashboard.exists() or dashboard.read_bytes() != source_dashboard):
        operations.append((dashboard, source_dashboard))
    if source_covers.is_dir():
        for source in sorted(source_covers.glob("sample-*.webp")):
            if source.is_file():
                operations.append((in_vault(vault, ".weread", "covers", source.name), source.read_bytes()))
    if PLUGIN_ID not in existing:
        operations.append((plugin_list, (json.dumps(existing + [PLUGIN_ID], ensure_ascii=False, indent=2) + "\n").encode("utf-8")))
    apply_installation(operations)


def write_model(vault: Path, model: Dict[str, Any]) -> Path:
    output = in_vault(vault, ".weread", "reading-board.json")
    atomic_write_json(output, model)
    monthly = as_dict(model.get("periods")).get("monthly")
    if model.get("source") == "live" and isinstance(monthly, dict):
        timestamp = safe_int(monthly.get("baseTime"))
        month = dt.datetime.fromtimestamp(timestamp or time.time(), tz=CHINA_TZ).strftime("%Y-%m")
        # Snapshot contains only the normalized month view, not the full export.
        atomic_write_json(in_vault(vault, ".weread", "snapshots", month + ".json"),
                          {"schemaVersion": MODEL_VERSION, "capturedAt": model["generatedAt"], "monthly": monthly})
    return output


def markdown_text(value: Any) -> str:
    """Render untrusted remote prose as readable Markdown text, never markup."""
    raw = str(value if value is not None else "").replace("\r", "").replace("\n", " ")
    escaped = html.escape(raw, quote=True)
    controls = "\\`*_{}[]()#>!|+-.~"
    return "".join("\\" + character if character in controls else character for character in escaped)


def managed_id(value: Any) -> str:
    """Stable note identifiers are comments only, never paths or account data."""
    return "".join(character for character in str(value or "") if character.isascii() and (character.isalnum() or character in "._-"))[:128]


def managed_notes_block(book_id: str, bookmarks: Dict[str, Any], reviews: Iterable[Dict[str, Any]]) -> bytes:
    book = as_dict(bookmarks.get("book"))
    lines = [MANAGED_START, "## 微信读书同步笔记", "", "- Book ID: `" + (managed_id(book_id) or "unknown") + "`",
             "- 标题: " + markdown_text(book.get("title", "")), ""]
    for item in as_list(bookmarks.get("updated")):
        if isinstance(item, dict):
            bookmark_id = managed_id(item.get("bookmarkId"))
            if bookmark_id:
                lines.append("<!-- weread-reading-board:bookmark id=" + bookmark_id + " -->")
            lines.extend(["> " + markdown_text(item.get("markText", "")), ""])
    for item in reviews:
        review = as_dict(item.get("review"))
        review_id = managed_id(item.get("reviewId") or review.get("reviewId"))
        if review_id:
            lines.append("<!-- weread-reading-board:review id=" + review_id + " -->")
        abstract = review.get("abstract")
        if abstract:
            lines.append("> " + markdown_text(abstract))
        content = markdown_text(review.get("content", ""))
        if content:
            lines.extend([content, ""])
    lines.append(MANAGED_END)
    return ("\n".join(lines) + "\n").encode("utf-8")


def safe_note_filename(title: Any, book_id: str) -> str:
    cleaned = "".join("_" if char in '<>:"/\\|?*' or ord(char) < 32 else char for char in str(title or "")).strip(" .")
    cleaned = cleaned[:80] or "WeRead Notes"
    suffix = "-" + "".join(ch for ch in str(book_id) if ch.isalnum() or ch in "-_")[:32]
    return cleaned + suffix + ".md"


def export_notes(vault: Path, gateway: Gateway, book_id: str) -> Path:
    bookmarks = gateway.call("/book/bookmarklist", bookId=book_id)
    reviews: List[Dict[str, Any]] = []
    sync_key = 0
    for _ in range(100):
        page = gateway.call("/review/list/mine", bookid=book_id, synckey=sync_key, count=100)
        reviews.extend(item for item in as_list(page.get("reviews")) if isinstance(item, dict))
        if safe_int(page.get("hasMore")) != 1:
            break
        next_key = safe_int(page.get("synckey"))
        if next_key == sync_key:
            raise GatewayError("想法分页游标无效，已安全停止导出。")
        sync_key = next_key
    else:
        raise GatewayError("想法分页超过安全上限，已停止导出。")
    title = as_dict(bookmarks.get("book")).get("title", "WeRead Notes")
    destination = in_vault(vault, *NOTES_PARTS, safe_note_filename(title, book_id))
    block = managed_notes_block(book_id, bookmarks, reviews)
    if destination.exists():
        original = destination.read_bytes()
        start_marker, end_marker = MANAGED_START.encode(), MANAGED_END.encode()
        starts = [index for index in range(len(original)) if original.startswith(start_marker, index)]
        ends = [index for index in range(len(original)) if original.startswith(end_marker, index)]
        if len(starts) != 1 or len(ends) != 1 or starts[0] >= ends[0]:
            raise SyncError("目标笔记不是唯一有效的受管区块，未修改原文件。")
        end = ends[0] + len(end_marker)
        replacement = original[:starts[0]] + block.rstrip(b"\n") + original[end:]
    else:
        replacement = ("# " + markdown_text(title) + "\n\n").encode("utf-8") + block
    atomic_write_bytes(destination, replacement)
    return destination


def doctor(vault: Path, args: argparse.Namespace) -> int:
    state_path = in_vault(vault, ".weread", "reading-board.json")
    plugin_path = in_vault(vault, ".obsidian", "plugins", PLUGIN_ID)
    dashboard_path = in_vault(vault, *DASHBOARD_PARTS)
    plugin_list = in_vault(vault, ".obsidian", "community-plugins.json")
    if not plugin_list.exists():
        plugin_status = "missing community-plugins.json"
    else:
        try:
            enabled = json.loads(plugin_list.read_text(encoding="utf-8"))
            plugin_status = "enabled" if isinstance(enabled, list) and PLUGIN_ID in enabled else ("disabled" if isinstance(enabled, list) else "invalid shape (expected JSON array)")
        except (OSError, json.JSONDecodeError):
            plugin_status = "invalid JSON"
    print("Vault: " + str(vault))
    print("Obsidian: ok")
    print("Plugin enablement: " + plugin_status)
    print("Plugin files: " + ("present" if plugin_path.is_dir() else "missing"))
    print("State directory: " + ("ok" if state_path.parent.is_dir() else "not installed"))
    print("Expected state path: " + state_path.relative_to(vault).as_posix())
    print("Expected plugin path: " + plugin_path.relative_to(vault).as_posix())
    print("Expected dashboard path: " + dashboard_path.relative_to(vault).as_posix())
    version, version_source = resolve_skill_version()
    print("WeRead skill version: " + version + " (" + version_source + ")")
    print("Credential: " + ("available" if (os.environ.get("WEREAD_API_KEY") or load_keychain(args.keychain_service, args.keychain_account)) else "missing"))
    return 0


def parser() -> argparse.ArgumentParser:
    result = argparse.ArgumentParser(description="同步微信读书数据到 Obsidian 阅读看板。")
    sub = result.add_subparsers(dest="command", required=True)
    for name in ("doctor", "install", "sync", "export-notes"):
        command = sub.add_parser(name)
        command.add_argument("--vault", required=(name != "configure-key"), help="Obsidian vault 路径")
        command.add_argument("--keychain-service", default=DEFAULT_SERVICE, help=argparse.SUPPRESS)
        command.add_argument("--keychain-account", default=DEFAULT_ACCOUNT, help=argparse.SUPPRESS)
        if name == "sync":
            command.add_argument("--sample", action="store_true", help="离线写入合成示例数据")
        if name == "export-notes":
            command.add_argument("--book-id", required=True)
    configure = sub.add_parser("configure-key", help="交互式保存 API key 到 macOS Keychain")
    configure.add_argument("--keychain-service", default=DEFAULT_SERVICE, help=argparse.SUPPRESS)
    configure.add_argument("--keychain-account", default=DEFAULT_ACCOUNT, help=argparse.SUPPRESS)
    return result


def main(argv: Optional[List[str]] = None) -> int:
    args = parser().parse_args(argv)
    try:
        if args.command == "configure-key":
            configure_key(args)
            return 0
        vault = validate_vault(args.vault)
        if args.command == "doctor":
            return doctor(vault, args)
        if args.command == "install":
            install(vault)
            print("已安装 WeRead Reading Board 到: " + str(vault))
            return 0
        if args.command == "sync":
            model = sample_model() if args.sample else build_live_model(Gateway(resolve_api_key(args)))
            output = write_model(vault, model)
            print("同步完成: " + str(output))
            return 0
        if args.command == "export-notes":
            output = export_notes(vault, Gateway(resolve_api_key(args)), args.book_id)
            print("笔记已导出: " + str(output))
            return 0
        raise SyncError("未知命令。")
    except SyncError as exc:
        print("错误: " + str(exc), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
