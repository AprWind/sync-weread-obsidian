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
import hmac
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
PLUGIN_OWNER_FILENAME = ".sync-weread-obsidian-owner.json"
PLUGIN_OWNER_MARKER = b'{"format":1,"id":"weread-reading-board","owner":"sync-weread-obsidian"}\n'
MODEL_VERSION = 2
DEFAULT_SERVICE = "weread-reading-board"
DEFAULT_ACCOUNT = "weread_api_key"
ERR_SEC_ITEM_NOT_FOUND = -25300
GUI_PROMPT_TIMEOUT_SECONDS = 120
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


def _keychain_runtime() -> tuple[Any, Any, Any, int, int]:
    """Load the native Security/CoreFoundation calls used for secret storage."""
    import ctypes

    security = ctypes.CDLL("/System/Library/Frameworks/Security.framework/Security")
    core = ctypes.CDLL("/System/Library/Frameworks/CoreFoundation.framework/CoreFoundation")
    pointer, index = ctypes.c_void_p, ctypes.c_long
    core.CFStringCreateWithCString.argtypes = [pointer, ctypes.c_char_p, ctypes.c_uint32]
    core.CFStringCreateWithCString.restype = pointer
    core.CFDataCreate.argtypes = [pointer, ctypes.POINTER(ctypes.c_ubyte), index]
    core.CFDataCreate.restype = pointer
    core.CFDictionaryCreate.argtypes = [pointer, ctypes.POINTER(pointer), ctypes.POINTER(pointer), index, pointer, pointer]
    core.CFDictionaryCreate.restype = pointer
    core.CFDataGetLength.argtypes = [pointer]
    core.CFDataGetLength.restype = index
    core.CFDataGetBytePtr.argtypes = [pointer]
    core.CFDataGetBytePtr.restype = ctypes.POINTER(ctypes.c_ubyte)
    core.CFRelease.argtypes = [pointer]
    core.CFRelease.restype = None
    security.SecItemUpdate.argtypes = [pointer, pointer]
    security.SecItemUpdate.restype = ctypes.c_int32
    security.SecItemAdd.argtypes = [pointer, ctypes.POINTER(pointer)]
    security.SecItemAdd.restype = ctypes.c_int32
    security.SecItemCopyMatching.argtypes = [pointer, ctypes.POINTER(pointer)]
    security.SecItemCopyMatching.restype = ctypes.c_int32
    security.SecItemDelete.argtypes = [pointer]
    security.SecItemDelete.restype = ctypes.c_int32
    key_callbacks = ctypes.addressof(ctypes.c_byte.in_dll(core, "kCFTypeDictionaryKeyCallBacks"))
    value_callbacks = ctypes.addressof(ctypes.c_byte.in_dll(core, "kCFTypeDictionaryValueCallBacks"))
    return ctypes, security, core, key_callbacks, value_callbacks


def _security_constant(ctypes: Any, security: Any, name: str) -> int:
    return ctypes.c_void_p.in_dll(security, name).value


def _cf_string(ctypes: Any, core: Any, value: str) -> Any:
    return core.CFStringCreateWithCString(None, value.encode("utf-8"), 0x08000100)


def _cf_data(ctypes: Any, core: Any, value: bytes) -> Any:
    buffer = (ctypes.c_ubyte * len(value)).from_buffer_copy(value)
    return core.CFDataCreate(None, buffer, len(value))


def _cf_dictionary(ctypes: Any, core: Any, key_callbacks: int, value_callbacks: int,
                   pairs: List[tuple[int, Any]]) -> Any:
    pointer = ctypes.c_void_p
    keys = (pointer * len(pairs))(*(key for key, _value in pairs))
    values = (pointer * len(pairs))(*(_value for _key, _value in pairs))
    return core.CFDictionaryCreate(None, keys, values, len(pairs), key_callbacks, value_callbacks)


def load_keychain(service: str = DEFAULT_SERVICE, account: str = DEFAULT_ACCOUNT) -> Optional[str]:
    """Read with Security.framework without exposing a secret to a child process."""
    if sys.platform != "darwin":
        return None
    references: List[Any] = []
    try:
        ctypes, security, core, key_callbacks, value_callbacks = _keychain_runtime()
        service_ref, account_ref = _cf_string(ctypes, core, service), _cf_string(ctypes, core, account)
        references.extend([service_ref, account_ref])
        query = _cf_dictionary(ctypes, core, key_callbacks, value_callbacks, [
            (_security_constant(ctypes, security, "kSecClass"), _security_constant(ctypes, security, "kSecClassGenericPassword")),
            (_security_constant(ctypes, security, "kSecAttrService"), service_ref),
            (_security_constant(ctypes, security, "kSecAttrAccount"), account_ref),
            (_security_constant(ctypes, security, "kSecReturnData"), ctypes.c_void_p.in_dll(core, "kCFBooleanTrue").value),
            (_security_constant(ctypes, security, "kSecMatchLimit"), _security_constant(ctypes, security, "kSecMatchLimitOne")),
            (_security_constant(ctypes, security, "kSecUseAuthenticationUI"), _security_constant(ctypes, security, "kSecUseAuthenticationUIFail")),
        ])
        references.append(query)
        result = ctypes.c_void_p()
        if security.SecItemCopyMatching(query, ctypes.byref(result)) != 0 or not result.value:
            return None
        references.append(result)
        length = core.CFDataGetLength(result)
        if length <= 0:
            return None
        raw = bytes(core.CFDataGetBytePtr(result)[:length])
        return raw.decode("utf-8") or None
    except (AttributeError, OSError, UnicodeDecodeError, ValueError):
        return None
    finally:
        if "core" in locals():
            for reference in reversed(references):
                if reference:
                    core.CFRelease(reference)


def resolve_api_key(args: argparse.Namespace) -> str:
    key = os.environ.get("WEREAD_API_KEY") or load_keychain(args.keychain_service, args.keychain_account)
    if not key:
        raise SyncError("未找到 WEREAD_API_KEY；请设置环境变量，或先运行 configure-key。")
    return key


def prompt_key_gui() -> str:
    """Collect a key in a native hidden-answer dialog without reading clipboard state."""
    script = '''
tell application "System Events"
    activate
    set answerRecord to display dialog "请粘贴刚从微信读书官方页面重新生成的 key。内容只会写入 macOS Keychain。" default answer "" with hidden answer buttons {"取消", "安全保存"} default button "安全保存" cancel button "取消" with title "微信读书安全连接"
    return text returned of answerRecord
end tell
'''
    try:
        completed = subprocess.run(
            ["/usr/bin/osascript", "-e", script],
            capture_output=True,
            text=True,
            check=False,
            timeout=GUI_PROMPT_TIMEOUT_SECONDS,
        )
    except subprocess.TimeoutExpired as exc:
        raise SyncError("安全输入窗口超时，未做任何更改。") from exc
    except OSError as exc:
        raise SyncError("无法打开安全输入窗口，未做任何更改。") from exc
    if completed.returncode != 0:
        return ""
    return completed.stdout.strip()


def store_keychain_secret(service: str, account: str, key: str) -> bool:
    """Update the exact Keychain item, adding only if it does not yet exist."""
    references: List[Any] = []
    try:
        ctypes, security, core, key_callbacks, value_callbacks = _keychain_runtime()
        service_ref, account_ref = _cf_string(ctypes, core, service), _cf_string(ctypes, core, account)
        secret_ref = _cf_data(ctypes, core, key.encode("utf-8"))
        references.extend([service_ref, account_ref, secret_ref])
        identity = [
            (_security_constant(ctypes, security, "kSecClass"), _security_constant(ctypes, security, "kSecClassGenericPassword")),
            (_security_constant(ctypes, security, "kSecAttrService"), service_ref),
            (_security_constant(ctypes, security, "kSecAttrAccount"), account_ref),
        ]
        query = _cf_dictionary(ctypes, core, key_callbacks, value_callbacks, identity + [
            (_security_constant(ctypes, security, "kSecUseAuthenticationUI"), _security_constant(ctypes, security, "kSecUseAuthenticationUIFail")),
        ])
        update = _cf_dictionary(ctypes, core, key_callbacks, value_callbacks, [
            (_security_constant(ctypes, security, "kSecValueData"), secret_ref),
        ])
        references.extend([query, update])
        status = security.SecItemUpdate(query, update)
        if status == 0:
            return True
        if status != ERR_SEC_ITEM_NOT_FOUND:
            return False
        addition = _cf_dictionary(ctypes, core, key_callbacks, value_callbacks, identity + [
            (_security_constant(ctypes, security, "kSecValueData"), secret_ref),
        ])
        references.append(addition)
        return security.SecItemAdd(addition, None) == 0
    except (AttributeError, OSError, ValueError):
        return False
    finally:
        if "core" in locals():
            for reference in reversed(references):
                if reference:
                    core.CFRelease(reference)


def delete_keychain_secret(service: str, account: str) -> bool:
    """Delete only the exact integration item, without allowing an auth prompt."""
    references: List[Any] = []
    try:
        ctypes, security, core, key_callbacks, value_callbacks = _keychain_runtime()
        service_ref, account_ref = _cf_string(ctypes, core, service), _cf_string(ctypes, core, account)
        references.extend([service_ref, account_ref])
        query = _cf_dictionary(ctypes, core, key_callbacks, value_callbacks, [
            (_security_constant(ctypes, security, "kSecClass"), _security_constant(ctypes, security, "kSecClassGenericPassword")),
            (_security_constant(ctypes, security, "kSecAttrService"), service_ref),
            (_security_constant(ctypes, security, "kSecAttrAccount"), account_ref),
            (_security_constant(ctypes, security, "kSecUseAuthenticationUI"), _security_constant(ctypes, security, "kSecUseAuthenticationUIFail")),
        ])
        references.append(query)
        return security.SecItemDelete(query) in (0, ERR_SEC_ITEM_NOT_FOUND)
    except (AttributeError, OSError, ValueError):
        return False
    finally:
        if "core" in locals():
            for reference in reversed(references):
                if reference:
                    core.CFRelease(reference)


def configure_key(args: argparse.Namespace) -> None:
    if sys.platform != "darwin":
        raise SyncError("configure-key 仅支持 macOS Keychain；请改用 WEREAD_API_KEY 环境变量。")
    key = (prompt_key_gui() if getattr(args, "gui", False)
           else getpass.getpass("WeRead API key (不会显示或写入 vault): ")).strip()
    if not key:
        raise SyncError("未输入 API key，未做任何更改。")
    if not store_keychain_secret(args.keychain_service, args.keychain_account, key):
        raise SyncError("无法写入 macOS Keychain。")
    stored = load_keychain(args.keychain_service, args.keychain_account)
    if not stored or not hmac.compare_digest(stored, key):
        raise SyncError("Keychain 写入后暂时无法回读验证；请稍后运行 doctor，勿立即重复保存。")
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
                # A gateway 401 is an invalid/expired bearer credential.  Do
                # not read the response body: it can contain server details
                # and is neither useful nor safe to echo in a local vault log.
                if exc.code == 401:
                    raise GatewayError("微信读书授权已失效或 API key 无效，请重新运行 configure-key 后再同步。") from exc
                if exc.code not in (408, 425, 429) and not (500 <= exc.code < 600):
                    break
            except (URLError, TimeoutError, ValueError) as exc:
                last_error = exc
            if attempt < self.retries:
                time.sleep(0.25 * (2 ** attempt))
        raise GatewayError("微信读书接口暂时不可用，请稍后重试。") from last_error


def _official_link(item: Dict[str, Any]) -> Optional[Any]:
    """Return only a link supplied by WeRead; never construct a deep link."""
    for key in ("deepLink", "scheme"):
        if key in item and item[key] is not None:
            return item[key]
    return None


def normalize_ranked_item(item: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    """Normalize a documented ebook or album entry from ``readLongest``."""
    book = as_dict(item.get("book"))
    album = as_dict(item.get("albumInfo"))
    if book.get("bookId") is not None:
        normalized: Dict[str, Any] = {
            "bookId": str(book.get("bookId")), "title": book.get("title", ""),
            "author": book.get("author", ""), "cover": book.get("cover", ""),
            "kind": "ebook", "readSeconds": safe_int(item.get("readTime")),
            "recordReadingSeconds": safe_int(item.get("recordReadingTime")),
            "tags": [str(tag) for tag in as_list(item.get("tags")) if isinstance(tag, (str, int, float))],
        }
        link = _official_link(item)
        if link is not None:
            normalized["deepLink"] = link
        return normalized
    if album.get("albumId") is not None:
        normalized = {
            "bookId": "album:" + str(album.get("albumId")), "title": album.get("name", ""),
            "author": album.get("authorName", album.get("author", "")), "cover": album.get("cover", ""),
            "kind": "audio", "readSeconds": safe_int(item.get("readTime")),
            "recordReadingSeconds": safe_int(item.get("recordReadingTime")),
            "tags": [str(tag) for tag in as_list(item.get("tags")) if isinstance(tag, (str, int, float))],
        }
        link = _official_link(item)
        if link is not None:
            normalized["deepLink"] = link
        return normalized
    return None


def normalize_categories(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    return [{
        "categoryId": str(item.get("categoryId", "")),
        "title": item.get("categoryTitle", ""),
        "parentCategoryId": str(item.get("parentCategoryId", "")),
        "parentTitle": item.get("parentCategoryTitle", ""),
        "weight": item.get("val"), "readSeconds": safe_int(item.get("readingTime")),
        "readingCount": safe_int(item.get("readingCount")), "categoryType": safe_int(item.get("categoryType")),
    } for item in as_list(raw.get("preferCategory")) if isinstance(item, dict)]


def normalize_reading_clock(raw: Dict[str, Any]) -> List[Dict[str, Any]]:
    """``preferTime`` is documented as 06:00 through 05:00, never 00:00 first."""
    values = as_list(raw.get("preferTime"))
    return [{"hour": (index + 6) % 24, "label": "%02d:00" % ((index + 6) % 24),
             "readSeconds": safe_int(values[index]) if index < len(values) else 0}
            for index in range(24)] if values else []


def normalize_media_mix(raw: Dict[str, Any]) -> Optional[Dict[str, Any]]:
    keys = ("readRate", "wrReadTime", "wrListenTime")
    if not any(key in raw for key in keys):
        return None
    return {"readRate": raw.get("readRate"), "readSeconds": safe_int(raw.get("wrReadTime")),
            "listenSeconds": safe_int(raw.get("wrListenTime"))}


def period(raw: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize documented semantics: all duration fields are seconds."""
    ranked = [normalized for item in as_list(raw.get("readLongest")) if isinstance(item, dict)
              for normalized in [normalize_ranked_item(item)] if normalized is not None]
    normalized: Dict[str, Any] = {
        "baseTime": safe_int(raw.get("baseTime")),
        "totalReadSeconds": safe_int(raw.get("totalReadTime")),
        "readDays": safe_int(raw.get("readDays")),
        "dayAverageReadSeconds": safe_int(raw.get("dayAverageReadTime")),
        "compare": raw.get("compare"),
        "buckets": {str(k): safe_int(v) for k, v in as_dict(raw.get("readTimes")).items()},
        "dailyBuckets": {str(k): safe_int(v) for k, v in as_dict(raw.get("dailyReadTimes")).items()},
        "rankedItems": ranked,
        # v1 clients used this field. Keep it as a compatibility projection.
        "topBooks": ranked,
        "categories": normalize_categories(raw),
        "readingClock": normalize_reading_clock(raw),
        "readStat": [{"label": item.get("stat", ""), "value": item.get("counts", "")}
                     for item in as_list(raw.get("readStat")) if isinstance(item, dict)],
    }
    for source_key, target_key in (("preferCategoryWord", "preferCategoryWord"), ("preferTimeWord", "preferTimeWord")):
        if source_key in raw:
            normalized[target_key] = raw[source_key]
    for source, normalized_stat in zip((item for item in as_list(raw.get("readStat")) if isinstance(item, dict)), normalized["readStat"]):
        link = _official_link(source)
        if link is not None:
            normalized_stat["deepLink"] = link
    if "recordReadingTime" in raw:
        normalized["recordReadingTime"] = safe_int(raw.get("recordReadingTime"))
    media_mix = normalize_media_mix(raw)
    if media_mix is not None:
        normalized["mediaMix"] = media_mix
    return normalized


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
        link = _official_link(item)
        if link is not None:
            normalized["deepLink"] = link
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
        normalized = {"bookId": "album:" + str(album_id), "title": info.get("name", ""), "author": info.get("authorName", ""),
                      "cover": info.get("cover", ""), "readUpdateTime": safe_int(extra.get("lectureReadUpdateTime")),
                      "finished": safe_int(info.get("finish")) == 1, "kind": "audio"}
        link = _official_link(item)
        if link is not None:
            normalized["deepLink"] = link
        albums.append(normalized)
    mp_count = int(bool(raw.get("mp")))
    # ``mp`` is one aggregate/private shelf entry, even when the service
    # attaches a nested count. Its contents and metadata never leave this
    # boundary. The official shelf total is raw books + raw albums + mp.
    private_count += mp_count
    public_entries = len(books) + len(albums)
    return {"items": books + albums, "ebooks": len(books), "audiobooks": len(albums),
            "publicEntries": public_entries, "totalEntries": len(as_list(raw.get("books"))) + len(as_list(raw.get("albums"))) + mp_count,
            "privateCount": private_count}


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
            highlights, reviews, bookmarks = (safe_int(item.get("noteCount")), safe_int(item.get("reviewCount")),
                                               safe_int(item.get("bookmarkCount")))
            entry = {"bookId": str(book_id), "title": book.get("title", ""), "author": book.get("author", ""),
                     "cover": book.get("cover", ""), "highlightCount": highlights, "reviewCount": reviews,
                     "bookmarkCount": bookmarks, "noteBreakdown": {"highlights": highlights, "reviews": reviews, "bookmarks": bookmarks},
                     "readingProgress": safe_int(item.get("readingProgress")), "markedStatus": safe_int(item.get("markedStatus")),
                     "status": "finished" if safe_int(item.get("markedStatus")) == 1 else "reading",
                     "sort": safe_int(item.get("sort")), "recentNoteAt": safe_int(item.get("sort"))}
            entries.append(entry)
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


def annual_base_year(raw: Dict[str, Any]) -> int:
    """Find the annual response's natural year without relying on wall-clock time."""
    base = safe_int(raw.get("baseTime"))
    if base:
        return dt.datetime.fromtimestamp(base, tz=CHINA_TZ).year
    bucket_times = [safe_int(key) for key in as_dict(raw.get("readTimes")).keys() if safe_int(key)]
    if bucket_times:
        return dt.datetime.fromtimestamp(max(bucket_times), tz=CHINA_TZ).year
    return dt.datetime.now(CHINA_TZ).year


def trailing_month_history(current_annual: Dict[str, Any], previous_annual: Dict[str, Any], current_monthly: Dict[str, Any]) -> List[Dict[str, Any]]:
    """Compose exactly twelve chronological months from two annual responses."""
    current_year = annual_base_year(current_annual)
    current_buckets = as_dict(current_annual.get("readTimes"))
    previous_buckets = as_dict(previous_annual.get("readTimes"))
    monthly_base = safe_int(current_monthly.get("baseTime"))
    all_current_times = [safe_int(key) for key in current_buckets if safe_int(key)]
    # ``readTimes`` can include future zero buckets. The monthly response is
    # the authoritative normalized current period endpoint, so it determines
    # the trailing window's end rather than a potentially padded annual map.
    end = (dt.datetime.fromtimestamp(monthly_base, tz=CHINA_TZ) if monthly_base else
           dt.datetime.fromtimestamp(max(all_current_times), tz=CHINA_TZ) if all_current_times else
           dt.datetime(current_year, 1, 1, tzinfo=CHINA_TZ))
    end_year, end_month = end.year, end.month
    source: Dict[str, int] = {}
    for buckets in (previous_buckets, current_buckets):
        for timestamp, seconds in buckets.items():
            value = safe_int(timestamp)
            if value:
                stamp = dt.datetime.fromtimestamp(value, tz=CHINA_TZ)
                source[stamp.strftime("%Y-%m")] = safe_int(seconds)
    history: List[Dict[str, Any]] = []
    for offset in range(11, -1, -1):
        month_index = end_year * 12 + (end_month - 1) - offset
        year, month_zero = divmod(month_index, 12)
        label = "%04d-%02d" % (year, month_zero + 1)
        history.append({"month": label, "readSeconds": source.get(label, 0)})
    return history


def build_live_model(gateway: Gateway) -> Dict[str, Any]:
    # Exactly five statistics requests: four current views plus the prior year
    # needed for a 12-month trend. Never fan out into twelve monthly calls.
    weekly_raw = gateway.call("/readdata/detail", mode="weekly")
    monthly_raw = gateway.call("/readdata/detail", mode="monthly")
    annually_raw = gateway.call("/readdata/detail", mode="annually")
    overall_raw = gateway.call("/readdata/detail", mode="overall")
    previous_year = annual_base_year(annually_raw) - 1
    previous_base = int(dt.datetime(previous_year, 6, 1, tzinfo=CHINA_TZ).timestamp())
    previous_annual_raw = gateway.call("/readdata/detail", mode="annually", baseTime=previous_base)
    periods = {"weekly": period(weekly_raw), "monthly": period(monthly_raw),
               "annually": period(annually_raw), "overall": period(overall_raw)}
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
    insight_period = periods["overall"] if (periods["overall"]["categories"] or periods["overall"]["readingClock"]) else periods["annually"]
    insights: Dict[str, Any] = {"categories": insight_period["categories"], "readingClock": insight_period["readingClock"]}
    if "mediaMix" in insight_period:
        insights["mediaMix"] = insight_period["mediaMix"]
    return {"schemaVersion": MODEL_VERSION, "generatedAt": int(time.time()), "source": "live",
            "periods": periods, "history": {"trailingMonths": trailing_month_history(annually_raw, previous_annual_raw, monthly_raw)},
            "insights": insights, "shelf": shelf, "notebooks": notebooks, "progress": progress}


def sample_model() -> Dict[str, Any]:
    """Deliberately benign synthetic data for a deep offline board preview."""
    generated = 1706745600  # 2024-02-01 00:00 China
    titles = ["缓慢生长", "第二座图书馆", "海边的算法", "城市与记忆", "安静的科学", "一间自己的房间", "未寄出的信", "风从北方来", "纸上旅行", "微小的秩序", "夜航船", "山月记"]
    shelf_items: List[Dict[str, Any]] = []
    for index, title in enumerate(titles, start=1):
        item: Dict[str, Any] = {"bookId": "sample-book-%d" % index, "title": title, "author": "合成作者 %d" % ((index - 1) % 4 + 1),
                                "cover": ".weread/covers/sample-%02d.webp" % ((index - 1) % 5 + 1), "category": "阅读", "readUpdateTime": generated - index * 7200,
                                "finished": index in (4, 8, 12), "kind": "ebook"}
        shelf_items.append(item)
    shelf_items.append({"bookId": "album:sample-audio-1", "title": "合成声音书", "author": "合成讲述者", "cover": ".weread/covers/sample-03.webp",
                        "category": "听书", "readUpdateTime": generated - 13 * 7200, "finished": False, "kind": "audio"})
    ranked = [{"bookId": item["bookId"], "title": item["title"], "author": item["author"], "cover": item["cover"], "kind": item["kind"],
               "readSeconds": 3600 * (14 - index), "recordReadingSeconds": 0, "tags": (["笔记最多"] if index == 1 else [])}
              for index, item in enumerate(shelf_items[:10], start=1)]
    month_starts = [int(dt.datetime(2023 if month >= 3 else 2024, month, 1, tzinfo=CHINA_TZ).timestamp()) for month in list(range(3, 13)) + [1, 2]]
    monthly_buckets = {str(int(dt.datetime(2024, 1, day, tzinfo=CHINA_TZ).timestamp())): (day % 5) * 420 for day in range(1, 32)}
    annual_buckets = {str(timestamp): (index + 1) * 1800 for index, timestamp in enumerate(month_starts[-2:])}
    daily_buckets = {str(int(dt.datetime(2024, 1, day, tzinfo=CHINA_TZ).timestamp())): (day % 6) * 360 for day in range(1, 32)}
    categories = [{"categoryId": "1", "title": "文学", "parentCategoryId": "0", "parentTitle": "", "weight": 1, "readSeconds": 21600, "readingCount": 6, "categoryType": 0},
                  {"categoryId": "2", "title": "社科", "parentCategoryId": "0", "parentTitle": "", "weight": 0.68, "readSeconds": 14400, "readingCount": 4, "categoryType": 0},
                  {"categoryId": "3", "title": "科学", "parentCategoryId": "0", "parentTitle": "", "weight": 0.42, "readSeconds": 9000, "readingCount": 3, "categoryType": 0}]
    clock = [{"hour": (index + 6) % 24, "label": "%02d:00" % ((index + 6) % 24), "readSeconds": (index % 7) * 300} for index in range(24)]
    def sample_period(base: int, buckets: Dict[str, int], *, annual: bool = False) -> Dict[str, Any]:
        total = sum(buckets.values())
        result: Dict[str, Any] = {"baseTime": base, "totalReadSeconds": total, "readDays": sum(1 for value in buckets.values() if value),
                                  "dayAverageReadSeconds": total // max(1, len(buckets)), "compare": 0.12, "buckets": buckets,
                                  "dailyBuckets": daily_buckets if annual else {}, "rankedItems": ranked, "topBooks": ranked,
                                  "categories": categories, "readingClock": clock, "mediaMix": {"readRate": 76, "readSeconds": total * 3 // 4, "listenSeconds": total // 4}}
        result.update({"readStat": [{"label": "读过", "value": "12本"}, {"label": "笔记", "value": "19条"}],
                       "preferCategoryWord": "偏好阅读文学", "preferTimeWord": "偏好夜间阅读", "recordReadingTime": total // 10})
        return result
    weekly_buckets = {str(int(dt.datetime(2024, 1, day, tzinfo=CHINA_TZ).timestamp())): day * 180 for day in range(1, 8)}
    annually = sample_period(int(dt.datetime(2024, 1, 1, tzinfo=CHINA_TZ).timestamp()), annual_buckets, annual=True)
    history = [{"month": dt.datetime.fromtimestamp(stamp, tz=CHINA_TZ).strftime("%Y-%m"), "readSeconds": (index + 1) * 1800}
               for index, stamp in enumerate(month_starts)]
    notebooks = [{"bookId": "sample-book-1", "title": "缓慢生长", "author": "合成作者 1", "cover": ".weread/covers/sample-01.webp",
                  "highlightCount": 8, "reviewCount": 3, "bookmarkCount": 2, "noteBreakdown": {"highlights": 8, "reviews": 3, "bookmarks": 2},
                  "readingProgress": 40, "markedStatus": 0, "status": "reading", "sort": generated, "recentNoteAt": generated, "noteTotal": 13},
                 {"bookId": "sample-book-4", "title": "城市与记忆", "author": "合成作者 4", "cover": ".weread/covers/sample-04.webp",
                  "highlightCount": 4, "reviewCount": 1, "bookmarkCount": 1, "noteBreakdown": {"highlights": 4, "reviews": 1, "bookmarks": 1},
                  "readingProgress": 100, "markedStatus": 1, "status": "finished", "sort": generated - 86400, "recentNoteAt": generated - 86400, "noteTotal": 6}]
    progress = [{"bookId": item["bookId"], "progressPercent": [40, 72, 15, 100, 5][index], "recordReadingSeconds": 900 * (index + 1), "updatedAt": item["readUpdateTime"]}
                for index, item in enumerate(shelf_items[:5])]
    return {"schemaVersion": MODEL_VERSION, "generatedAt": generated, "source": "sample",
            "periods": {"weekly": sample_period(generated, weekly_buckets), "monthly": sample_period(generated, monthly_buckets), "annually": annually,
                        "overall": sample_period(0, {str(int(dt.datetime(2022 + index, 1, 1, tzinfo=CHINA_TZ).timestamp())): 14400 * (index + 1) for index in range(3)})},
            "history": {"trailingMonths": history}, "insights": {"categories": categories, "readingClock": clock, "mediaMix": {"readRate": 76, "readSeconds": 50400, "listenSeconds": 16800}},
            "shelf": {"items": shelf_items, "ebooks": 12, "audiobooks": 1, "publicEntries": 13, "totalEntries": 15, "privateCount": 2},
            "notebooks": {"totalBookCount": 2, "totalNoteCount": 19, "books": notebooks}, "progress": progress}


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


def missing_parent_directories(destination: Path) -> List[Path]:
    """Return absent parents, nearest first, stopping at the first existing one."""
    missing: List[Path] = []
    current = destination.parent
    while not current.exists():
        missing.append(current)
        if current == current.parent:
            break
        current = current.parent
    return missing


def cleanup_empty_directories(directories: Iterable[Path]) -> None:
    """Best-effort cleanup of directories created by a failed transaction."""
    for directory in sorted(set(directories), key=lambda item: len(item.parts), reverse=True):
        try:
            directory.rmdir()
        except OSError:
            # Never remove a non-empty directory or obscure the write error.
            pass


def apply_installation(operations: List[tuple[Path, bytes]]) -> None:
    """Apply a fully preflighted install and restore already-written files on error."""
    written: List[tuple[Path, Optional[bytes]]] = []
    created_directories: List[Path] = []
    try:
        for destination, content in operations:
            created_directories.extend(missing_parent_directories(destination))
            previous = destination.read_bytes() if destination.exists() else None
            atomic_write_bytes(destination, content)
            written.append((destination, previous))
    except BaseException:
        restore_installation(written)
        cleanup_empty_directories(created_directories)
        raise


def preflight_plugin_ownership(plugin_dir: Path) -> None:
    """Reject overwriting a foreign plugin, while recognizing audited v1/v2 installs."""
    if not plugin_dir.exists():
        return
    if plugin_dir.is_symlink() or not plugin_dir.is_dir():
        raise SyncError("插件目标路径不是本集成受管目录，未修改任何文件。")
    allowed = {"main.js", "styles.css", "manifest.json", PLUGIN_OWNER_FILENAME}
    entries = list(plugin_dir.iterdir())
    if any(entry.is_dir() or entry.name not in allowed for entry in entries):
        raise SyncError("现有插件目录包含未知内容，无法确认所有权，未修改任何文件。")
    marker = plugin_dir / PLUGIN_OWNER_FILENAME
    manifest_path, main_path, styles_path = (plugin_dir / "manifest.json", plugin_dir / "main.js", plugin_dir / "styles.css")
    try:
        manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
        main = main_path.read_text(encoding="utf-8")
        styles = styles_path.read_text(encoding="utf-8")
    except (OSError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SyncError("现有插件无法验证为本集成所有，未修改任何文件。") from exc
    if not isinstance(manifest, dict) or manifest.get("id") != PLUGIN_ID or manifest.get("name") != "WeChat Reading Board" or manifest.get("author") != "Independent local integration":
        raise SyncError("现有插件身份与本集成不符，未修改任何文件。")
    if marker.exists():
        try:
            marker_matches = marker.read_bytes() == PLUGIN_OWNER_MARKER
        except OSError as exc:
            raise SyncError("现有插件所有权标记无法读取，未修改任何文件。") from exc
        if not marker_matches:
            raise SyncError("现有插件所有权标记无效，未修改任何文件。")
    else:
        # Audited upgrade bridge for our pre-marker releases only. v1 is
        # identified by its exact thesis line; v2 by its circular controller.
        known_v1 = "THESIS: 让本周阅读节奏先于书架信息进入视线" in main
        known_v2 = "class CircularGalleryController" in main and "module.exports.normalizeDashboard" in main
        common = ('const DASHBOARD_PATH = ".weread/reading-board.json";' in main and
                  "class WeReadReadingBoardPlugin extends Plugin" in main and
                  "module.exports = WeReadReadingBoardPlugin;" in main and ".weread-dashboard" in styles)
        if not common or not (known_v1 or known_v2):
            raise SyncError("现有插件没有可信的本项目旧版签名，未修改任何文件。")


def install(vault: Path) -> None:
    """Install only owned files after every conflict and JSON preflight passes."""
    root = Path(__file__).resolve().parents[1]
    source_plugin = root / "assets" / "obsidian-plugin"
    source_note = root / "assets" / "dashboard-note.md"
    source_covers = root / "assets" / "sample-covers"
    dashboard = in_vault(vault, *DASHBOARD_PARTS)
    plugin_list = in_vault(vault, ".obsidian", "community-plugins.json")
    plugin_dir = in_vault(vault, ".obsidian", "plugins", PLUGIN_ID)
    source_dashboard = source_note.read_bytes() if source_note.is_file() else None
    # Preflight *before* creating .weread or writing any plugin file.
    preflight_plugin_ownership(plugin_dir)
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
        operations.append((in_vault(vault, ".obsidian", "plugins", PLUGIN_ID, PLUGIN_OWNER_FILENAME), PLUGIN_OWNER_MARKER))
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
    operations = [(output, (json.dumps(model, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8"))]
    monthly = as_dict(model.get("periods")).get("monthly")
    if model.get("source") == "live" and isinstance(monthly, dict):
        timestamp = safe_int(monthly.get("baseTime"))
        month = dt.datetime.fromtimestamp(timestamp or time.time(), tz=CHINA_TZ).strftime("%Y-%m")
        # Snapshot contains only the normalized month view, not the full export.
        snapshot = {"schemaVersion": MODEL_VERSION, "capturedAt": model["generatedAt"], "monthly": monthly}
        operations.append((in_vault(vault, ".weread", "snapshots", month + ".json"),
                           (json.dumps(snapshot, ensure_ascii=False, indent=2, sort_keys=True) + "\n").encode("utf-8")))
    apply_installation(operations)
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
    configure.add_argument("--gui", action="store_true", help="使用 macOS 本地安全输入框")
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
    except OSError:
        # Atomic/transaction helpers have already attempted rollback. Keep the
        # CLI failure concise and never expose local file contents.
        print("错误: 本地写入失败，同步未完成；请检查磁盘空间和目录权限。", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
