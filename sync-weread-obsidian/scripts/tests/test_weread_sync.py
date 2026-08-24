import importlib.util
import json
import io
import tempfile
import unittest
from urllib.error import HTTPError
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stderr, redirect_stdout

SCRIPT = Path(__file__).parents[1] / "weread_sync.py"
SPEC = importlib.util.spec_from_file_location("weread_sync", SCRIPT)
weread_sync = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
SPEC.loader.exec_module(weread_sync)


class WereadSyncTest(unittest.TestCase):
    def vault(self):
        root = Path(tempfile.mkdtemp())
        (root / ".obsidian").mkdir()
        return root

    def test_sample_install_and_sync(self):
        vault = self.vault()
        (vault / ".obsidian" / "community-plugins.json").write_text('["calendar"]\n', encoding="utf-8")
        self.assertEqual(0, weread_sync.main(["install", "--vault", str(vault)]))
        self.assertEqual(0, weread_sync.main(["sync", "--vault", str(vault), "--sample"]))
        model = json.loads((vault / ".weread" / "reading-board.json").read_text(encoding="utf-8"))
        plugins = json.loads((vault / ".obsidian" / "community-plugins.json").read_text(encoding="utf-8"))
        self.assertEqual("sample", model["source"])
        self.assertTrue((vault / "00-首页" / "阅读看板.md").is_file())
        self.assertEqual(2, model["schemaVersion"])
        self.assertEqual(13, len(model["shelf"]["items"]))
        self.assertEqual(12, model["shelf"]["ebooks"])
        self.assertEqual(1, model["shelf"]["audiobooks"])
        self.assertEqual(15, model["shelf"]["totalEntries"])
        self.assertEqual(13, model["shelf"]["publicEntries"])
        self.assertEqual([".weread/covers/sample-%02d.webp" % number for number in range(1, 6)],
                         sorted(set(item["cover"] for item in model["shelf"]["items"])))
        self.assertEqual([40, 72, 15, 100, 5], [item["progressPercent"] for item in model["progress"]])
        self.assertTrue(all(not item["bookId"].startswith("album:") for item in model["progress"]))
        self.assertEqual(12, len(model["history"]["trailingMonths"]))
        self.assertEqual(24, len(model["insights"]["readingClock"]))
        self.assertTrue(all("deepLink" not in item for item in model["shelf"]["items"]))
        self.assertEqual(7, len(model["periods"]["weekly"]["buckets"]))
        self.assertGreater(len(model["periods"]["monthly"]["buckets"]), 7)
        for period in model["periods"].values():
            self.assertTrue(period["buckets"])
            self.assertEqual(period["totalReadSeconds"], sum(period["buckets"].values()))
        self.assertEqual(["sample-%02d.webp" % number for number in range(1, 6)],
                         sorted(path.name for path in (vault / ".weread" / "covers").iterdir()))
        self.assertIn("calendar", plugins)
        self.assertIn(weread_sync.PLUGIN_ID, plugins)

    def test_malicious_title_never_escapes_vault(self):
        vault = self.vault()
        filename = weread_sync.safe_note_filename("../../outside/evil", "id/../../x")
        target = weread_sync.in_vault(vault, *weread_sync.NOTES_PARTS, filename)
        self.assertTrue(str(target).startswith(str(vault.resolve())))
        self.assertNotIn("/..", filename)
        self.assertNotIn("/", filename)

    def test_atomic_failure_keeps_existing_json(self):
        vault = self.vault()
        output = vault / ".weread" / "reading-board.json"
        output.parent.mkdir()
        output.write_bytes(b"old-output")
        with patch.object(weread_sync.os, "replace", side_effect=OSError("disk error")):
            with self.assertRaises(OSError):
                weread_sync.atomic_write_bytes(output, b"new-output")
        self.assertEqual(b"old-output", output.read_bytes())

    def test_failed_live_collection_cannot_clobber_prior_model(self):
        vault = self.vault()
        output = vault / ".weread" / "reading-board.json"
        output.parent.mkdir()
        output.write_bytes(b'{"previous":true}\n')
        failing_gateway = type("Gateway", (), {"call": lambda self, *args, **kwargs: (_ for _ in ()).throw(weread_sync.GatewayError("offline"))})()
        with self.assertRaises(weread_sync.GatewayError):
            weread_sync.build_live_model(failing_gateway)
        self.assertEqual(b'{"previous":true}\n', output.read_bytes())

    def test_progress_is_percent_not_fraction_and_shelf_counts_audio_and_mp(self):
        fixture = Path(__file__).parent / "fixtures" / "gateway_shelf.json"
        shelf = weread_sync.normalize_shelf(json.loads(fixture.read_text(encoding="utf-8")))
        self.assertEqual(3, shelf["totalEntries"])
        self.assertEqual(2, shelf["privateCount"])
        self.assertEqual(1, shelf["publicEntries"])
        self.assertEqual("../../never-a-path", shelf["items"][0]["title"])
        self.assertEqual("weread://book?bookId=fixture-book-1", shelf["items"][0]["deepLink"])
        self.assertNotIn("Fixture audio", json.dumps(shelf, ensure_ascii=False))
        self.assertNotIn("deepLink", weread_sync.normalize_shelf({"books": [{"bookId": "no-link"}]})["items"][0])
        gateway = type("Gateway", (), {"call": lambda self, api, **kwargs: {"book": {"progress": 1, "recordReadingTime": 60}}})()
        # build_live_model has more endpoints, so assert the documented clamp directly via a mini pass.
        response = gateway.call("/book/getprogress", bookId="1")
        self.assertEqual(1, max(0, min(100, weread_sync.safe_int(response["book"]["progress"]))))

    def test_managed_block_replacement_preserves_surrounding_bytes(self):
        vault = self.vault()
        destination = vault.joinpath(*weread_sync.NOTES_PARTS, "Book-x.md")
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"prefix\\xff\n" + weread_sync.MANAGED_START.encode() + b"\nold\n" + weread_sync.MANAGED_END.encode() + b"\nsuffix\\xfe")
        block = weread_sync.managed_notes_block("x", {"book": {"title": "Book"}, "updated": []}, [])
        original = destination.read_bytes()
        start, end = original.find(weread_sync.MANAGED_START.encode()), original.find(weread_sync.MANAGED_END.encode())
        replacement = original[:start] + block.rstrip(b"\n") + original[end + len(weread_sync.MANAGED_END.encode()):]
        weread_sync.atomic_write_bytes(destination, replacement)
        self.assertTrue(destination.read_bytes().startswith(b"prefix\\xff\n"))
        self.assertTrue(destination.read_bytes().endswith(b"\nsuffix\\xfe"))

    def note_gateway(self):
        return type("Gateway", (), {"call": lambda self, api, **kwargs: {
            "/book/bookmarklist": {"book": {"title": "Book"}, "updated": []},
            "/review/list/mine": {"reviews": [], "hasMore": 0},
        }[api]})()

    def note_destination(self, vault):
        return vault / "20-认知记录" / "阅读笔记" / weread_sync.safe_note_filename("Book", "id")

    def test_export_new_note_has_exactly_one_managed_block(self):
        vault = self.vault()
        destination = weread_sync.export_notes(vault, self.note_gateway(), "id")
        exported = destination.read_bytes()
        self.assertEqual(1, exported.count(weread_sync.MANAGED_START.encode()))
        self.assertEqual(1, exported.count(weread_sync.MANAGED_END.encode()))

    def test_export_refuses_existing_note_without_markers(self):
        vault = self.vault()
        destination = self.note_destination(vault)
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"my untouched note\xff")
        with self.assertRaises(weread_sync.SyncError):
            weread_sync.export_notes(vault, self.note_gateway(), "id")
        self.assertEqual(b"my untouched note\xff", destination.read_bytes())

    def test_export_refuses_duplicate_or_misaligned_markers(self):
        for original in (
            weread_sync.MANAGED_START.encode() * 2 + weread_sync.MANAGED_END.encode(),
            weread_sync.MANAGED_END.encode() + weread_sync.MANAGED_START.encode(),
        ):
            vault = self.vault()
            destination = self.note_destination(vault)
            destination.parent.mkdir(parents=True)
            destination.write_bytes(original)
            with self.assertRaises(weread_sync.SyncError):
                weread_sync.export_notes(vault, self.note_gateway(), "id")
            self.assertEqual(original, destination.read_bytes())

    def test_export_replaces_only_the_unique_managed_block(self):
        vault = self.vault()
        destination = self.note_destination(vault)
        destination.parent.mkdir(parents=True)
        destination.write_bytes(b"prefix\xff\n" + weread_sync.MANAGED_START.encode() + b"\nold\n" + weread_sync.MANAGED_END.encode() + b"\nsuffix\xfe")
        weread_sync.export_notes(vault, self.note_gateway(), "id")
        exported = destination.read_bytes()
        self.assertTrue(exported.startswith(b"prefix\xff\n"))
        self.assertTrue(exported.endswith(b"\nsuffix\xfe"))
        self.assertEqual(1, exported.count(weread_sync.MANAGED_START.encode()))

    def test_doctor_reports_safe_paths_and_plugin_shape_without_writing(self):
        vault = self.vault()
        plugins = vault / ".obsidian" / "community-plugins.json"
        plugins.write_text(json.dumps([weread_sync.PLUGIN_ID]), encoding="utf-8")
        before = plugins.read_bytes()
        stream = io.StringIO()
        args = type("Args", (), {"keychain_service": "nonexistent", "keychain_account": "nonexistent"})()
        with redirect_stdout(stream):
            weread_sync.doctor(vault.resolve(), args)
        report = stream.getvalue()
        self.assertIn("Plugin enablement: enabled", report)
        self.assertIn("Expected state path: .weread/reading-board.json", report)
        self.assertIn("Expected plugin path: .obsidian/plugins/weread-reading-board", report)
        self.assertIn("Expected dashboard path: 00-首页/阅读看板.md", report)
        self.assertIn("WeRead skill version: ", report)
        self.assertEqual(before, plugins.read_bytes())

    def test_install_refuses_conflicting_dashboard_before_any_write(self):
        vault = self.vault()
        target = vault / "00-首页" / "阅读看板.md"
        target.parent.mkdir()
        target.write_bytes(b"user-owned dashboard")
        with self.assertRaises(weread_sync.SyncError):
            weread_sync.install(vault)
        self.assertEqual(b"user-owned dashboard", target.read_bytes())
        self.assertFalse((vault / ".weread").exists())
        self.assertFalse((vault / ".obsidian" / "plugins" / weread_sync.PLUGIN_ID).exists())
        self.assertFalse((vault / ".obsidian" / "community-plugins.json").exists())

    def test_malformed_community_plugins_preflight_leaves_no_partial_install(self):
        vault = self.vault()
        config = vault / ".obsidian" / "community-plugins.json"
        config.write_bytes(b"{not-json")
        with self.assertRaises(weread_sync.SyncError):
            weread_sync.install(vault)
        self.assertEqual(b"{not-json", config.read_bytes())
        self.assertFalse((vault / ".weread").exists())
        self.assertFalse((vault / "00-首页" / "阅读看板.md").exists())
        self.assertFalse((vault / ".obsidian" / "plugins" / weread_sync.PLUGIN_ID).exists())

    def test_install_transaction_rolls_back_prior_owned_file_after_later_failure(self):
        vault = self.vault()
        first, second = vault / ".weread" / "first", vault / ".weread" / "second"
        first.parent.mkdir()
        first.write_bytes(b"old-first")
        second.write_bytes(b"old-second")
        original_writer = weread_sync.atomic_write_bytes
        calls = []

        def fail_second(destination, content):
            calls.append(destination)
            if len(calls) == 2:
                raise OSError("simulated failure")
            original_writer(destination, content)

        with patch.object(weread_sync, "atomic_write_bytes", side_effect=fail_second):
            with self.assertRaises(OSError):
                weread_sync.apply_installation([(first, b"new-first"), (second, b"new-second")])
        self.assertEqual(b"old-first", first.read_bytes())
        self.assertEqual(b"old-second", second.read_bytes())

    def test_failed_transaction_cleans_new_empty_parents_but_keeps_existing_directory(self):
        vault = self.vault()
        existing = vault / "already-here"
        existing.mkdir()
        destination = existing / "new-parent" / "deeper" / "file.json"

        def create_parent_then_fail(path, content):
            path.parent.mkdir(parents=True, exist_ok=True)
            raise OSError("simulated write failure")

        with patch.object(weread_sync, "atomic_write_bytes", side_effect=create_parent_then_fail):
            with self.assertRaises(OSError):
                weread_sync.apply_installation([(destination, b"new")])
        self.assertTrue(existing.is_dir())
        self.assertFalse((existing / "new-parent").exists())

    def test_live_model_and_snapshot_are_one_transaction_on_second_write_failure(self):
        vault = self.vault()
        output = vault / ".weread" / "reading-board.json"
        snapshot = vault / ".weread" / "snapshots" / "2024-08.json"
        snapshot.parent.mkdir(parents=True)
        output.write_bytes(b'{"schemaVersion":1,"old":true}\n')
        snapshot.write_bytes(b'{"oldSnapshot":true}\n')
        old_output, old_snapshot = output.read_bytes(), snapshot.read_bytes()
        base = int(__import__("datetime").datetime(2024, 8, 1, tzinfo=weread_sync.CHINA_TZ).timestamp())
        model = {"schemaVersion": 2, "generatedAt": base, "source": "live", "periods": {"monthly": {"baseTime": base}}}
        original_writer = weread_sync.atomic_write_bytes
        writes = []

        def fail_snapshot(path, content):
            writes.append(path)
            if len(writes) == 2:
                raise OSError("snapshot disk failure")
            original_writer(path, content)

        with patch.object(weread_sync, "atomic_write_bytes", side_effect=fail_snapshot):
            with self.assertRaises(OSError):
                weread_sync.write_model(vault, model)
        self.assertEqual(old_output, output.read_bytes())
        self.assertEqual(old_snapshot, snapshot.read_bytes())

    def test_install_refuses_foreign_plugin_and_leaves_everything_unchanged(self):
        vault = self.vault()
        plugin = vault / ".obsidian" / "plugins" / weread_sync.PLUGIN_ID
        plugin.mkdir(parents=True)
        manifest = {"id": weread_sync.PLUGIN_ID, "name": "WeChat Reading Board", "author": "Independent local integration"}
        (plugin / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (plugin / "main.js").write_text("module.exports = class ForeignPlugin {};", encoding="utf-8")
        (plugin / "styles.css").write_text(".foreign {}", encoding="utf-8")
        before = {path.name: path.read_bytes() for path in plugin.iterdir()}
        with self.assertRaises(weread_sync.SyncError):
            weread_sync.install(vault)
        self.assertEqual(before, {path.name: path.read_bytes() for path in plugin.iterdir()})
        self.assertFalse((vault / ".weread").exists())
        self.assertFalse((vault / "00-首页" / "阅读看板.md").exists())
        self.assertFalse((vault / ".obsidian" / "community-plugins.json").exists())

    def test_install_upgrades_recognized_pre_marker_plugin_and_adds_owner_marker(self):
        vault = self.vault()
        plugin = vault / ".obsidian" / "plugins" / weread_sync.PLUGIN_ID
        plugin.mkdir(parents=True)
        source = SCRIPT.parents[1] / "assets" / "obsidian-plugin"
        for name in ("main.js", "styles.css", "manifest.json"):
            (plugin / name).write_bytes((source / name).read_bytes())
        self.assertFalse((plugin / weread_sync.PLUGIN_OWNER_FILENAME).exists())
        weread_sync.install(vault)
        self.assertEqual(weread_sync.PLUGIN_OWNER_MARKER, (plugin / weread_sync.PLUGIN_OWNER_FILENAME).read_bytes())
        for name in ("main.js", "styles.css", "manifest.json"):
            self.assertEqual((source / name).read_bytes(), (plugin / name).read_bytes())

    def test_install_upgrades_audited_v1_signature(self):
        vault = self.vault()
        plugin = vault / ".obsidian" / "plugins" / weread_sync.PLUGIN_ID
        plugin.mkdir(parents=True)
        manifest = {"id": weread_sync.PLUGIN_ID, "name": "WeChat Reading Board", "version": "1.0.0",
                    "description": "Render a local WeChat Reading board from .weread/reading-board.json.",
                    "author": "Independent local integration"}
        legacy_main = '''const { Plugin } = require("obsidian");
/* THESIS: 让本周阅读节奏先于书架信息进入视线，拒绝把 Obsidian 伪装成另一台手机。 */
const DASHBOARD_PATH = ".weread/reading-board.json";
class WeReadReadingBoardPlugin extends Plugin {}
module.exports = WeReadReadingBoardPlugin;
'''
        (plugin / "manifest.json").write_text(json.dumps(manifest), encoding="utf-8")
        (plugin / "main.js").write_text(legacy_main, encoding="utf-8")
        (plugin / "styles.css").write_text(".weread-dashboard {}", encoding="utf-8")
        weread_sync.install(vault)
        self.assertEqual(weread_sync.PLUGIN_OWNER_MARKER, (plugin / weread_sync.PLUGIN_OWNER_FILENAME).read_bytes())

    def test_sync_command_returns_failure_when_transaction_write_fails(self):
        vault = self.vault()
        stderr = io.StringIO()
        with patch.object(weread_sync, "write_model", side_effect=OSError("disk failure")), redirect_stderr(stderr):
            result = weread_sync.main(["sync", "--vault", str(vault), "--sample"])
        self.assertEqual(2, result)
        self.assertIn("本地写入失败", stderr.getvalue())
        self.assertNotIn("disk failure", stderr.getvalue())

    def test_resolve_skill_version_uses_installed_metadata_or_explicit_fallback(self):
        root = Path(tempfile.mkdtemp())
        skill = root / "SKILL.md"
        skill.write_text("---\nname: weread-skills\nversion: 2.3.4\n---\n", encoding="utf-8")
        self.assertEqual(("2.3.4", str(skill)), weread_sync.resolve_skill_version([skill]))
        self.assertEqual((weread_sync.FALLBACK_SKILL_VERSION, "fallback (no installed weread-skills/SKILL.md found)"),
                         weread_sync.resolve_skill_version([root / "missing.md"]))

    def test_configure_key_uses_stdin_and_never_process_arguments_or_output(self):
        secret = "fixture-secret-that-must-not-leak"
        args = type("Args", (), {"keychain_service": "fixture-service", "keychain_account": "fixture-account"})()
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(weread_sync.sys, "platform", "darwin"), \
             patch.object(weread_sync.getpass, "getpass", return_value=secret), \
             patch.object(weread_sync, "delete_keychain_secret") as delete, \
             patch.object(weread_sync, "store_keychain_secret", return_value=True) as store, \
             patch.object(weread_sync, "load_keychain", return_value=secret), \
             redirect_stdout(stdout), redirect_stderr(stderr):
            weread_sync.configure_key(args)
        delete.assert_not_called()
        store.assert_called_once_with("fixture-service", "fixture-account", secret)
        self.assertNotIn(secret, stdout.getvalue())
        self.assertNotIn(secret, stderr.getvalue())

    def test_configure_key_gui_never_reads_clipboard_or_exposes_secret(self):
        secret = "fixture-gui-secret-that-must-not-leak"
        args = type("Args", (), {"keychain_service": "fixture-service", "keychain_account": "fixture-account", "gui": True})()
        stdout, stderr = io.StringIO(), io.StringIO()
        with patch.object(weread_sync.sys, "platform", "darwin"), \
             patch.object(weread_sync, "prompt_key_gui", return_value=secret) as prompt, \
             patch.object(weread_sync.getpass, "getpass") as terminal_prompt, \
             patch.object(weread_sync, "delete_keychain_secret") as delete, \
             patch.object(weread_sync, "store_keychain_secret", return_value=True) as store, \
             patch.object(weread_sync, "load_keychain", return_value=secret), \
             redirect_stdout(stdout), redirect_stderr(stderr):
            weread_sync.configure_key(args)
        prompt.assert_called_once_with()
        terminal_prompt.assert_not_called()
        delete.assert_not_called()
        store.assert_called_once_with("fixture-service", "fixture-account", secret)
        self.assertNotIn(secret, stdout.getvalue())
        self.assertNotIn(secret, stderr.getvalue())

    def test_native_gui_prompt_keeps_returned_secret_out_of_process_arguments(self):
        secret = "fixture-native-dialog-secret"
        completed = type("Completed", (), {"returncode": 0, "stdout": secret + "\n", "stderr": ""})()
        with patch.object(weread_sync.subprocess, "run", return_value=completed) as run:
            self.assertEqual(secret, weread_sync.prompt_key_gui())
        positional, keywords = run.call_args
        self.assertEqual("/usr/bin/osascript", positional[0][0])
        self.assertNotIn(secret, " ".join(positional[0]))
        self.assertIn("hidden answer", positional[0][-1])
        self.assertTrue(keywords["capture_output"])
        self.assertTrue(keywords["text"])
        self.assertEqual(weread_sync.GUI_PROMPT_TIMEOUT_SECONDS, keywords["timeout"])

    def test_native_gui_prompt_cancel_returns_empty_secret(self):
        completed = type("Completed", (), {"returncode": 1, "stdout": "not-used", "stderr": "not-used"})()
        with patch.object(weread_sync.subprocess, "run", return_value=completed):
            self.assertEqual("", weread_sync.prompt_key_gui())

    def test_native_gui_prompt_timeout_is_safe_sync_error(self):
        secret = "fixture-timeout-secret"
        failure = weread_sync.subprocess.TimeoutExpired(["/usr/bin/osascript"], 1, output=secret, stderr=secret)
        with patch.object(weread_sync.subprocess, "run", side_effect=failure):
            with self.assertRaises(weread_sync.SyncError) as raised:
                weread_sync.prompt_key_gui()
        self.assertNotIn(secret, str(raised.exception))
        self.assertIn("超时", str(raised.exception))

    def test_native_gui_prompt_os_error_is_safe_sync_error(self):
        secret = "fixture-os-error-secret"
        with patch.object(weread_sync.subprocess, "run", side_effect=OSError(secret)):
            with self.assertRaises(weread_sync.SyncError) as raised:
                weread_sync.prompt_key_gui()
        self.assertNotIn(secret, str(raised.exception))
        self.assertIn("无法打开", str(raised.exception))

    def _keychain_store_fakes(self, update_status, add_status=0):
        events, dictionaries = [], []

        class Security:
            def SecItemUpdate(self, query, attributes):
                events.append(("update", query, attributes))
                return update_status

            def SecItemAdd(self, attributes, result):
                events.append(("add", attributes, result))
                return add_status

        class Core:
            def CFRelease(self, reference):
                events.append(("release", reference))

        security, core = Security(), Core()

        def create_string(_ctypes, _core, value):
            return "string:%s" % value

        def create_data(_ctypes, _core, value):
            return "data:%s" % value.decode("utf-8")

        def create_dictionary(_ctypes, _core, _key_callbacks, _value_callbacks, pairs):
            reference = "dictionary:%d" % len(dictionaries)
            dictionaries.append((reference, list(pairs)))
            return reference

        return security, core, events, dictionaries, create_string, create_data, create_dictionary

    def test_keychain_store_updates_exact_item_and_releases_all_references(self):
        security, core, events, dictionaries, create_string, create_data, create_dictionary = self._keychain_store_fakes(0)
        with patch.object(weread_sync, "_keychain_runtime", return_value=(object(), security, core, 1, 2)), \
             patch.object(weread_sync, "_security_constant", side_effect=lambda _ctypes, _security, name: name), \
             patch.object(weread_sync, "_cf_string", side_effect=create_string), \
             patch.object(weread_sync, "_cf_data", side_effect=create_data), \
             patch.object(weread_sync, "_cf_dictionary", side_effect=create_dictionary):
            self.assertTrue(weread_sync.store_keychain_secret("fixture-service", "fixture-account", "fixture-secret"))
        self.assertEqual(["update"], [event[0] for event in events if event[0] in ("update", "add")])
        query_pairs = dictionaries[0][1]
        self.assertIn(("kSecUseAuthenticationUI", "kSecUseAuthenticationUIFail"), query_pairs)
        self.assertEqual(["dictionary:1", "dictionary:0", "data:fixture-secret", "string:fixture-account", "string:fixture-service"],
                         [event[1] for event in events if event[0] == "release"])

    def test_keychain_store_adds_only_after_item_not_found(self):
        security, core, events, dictionaries, create_string, create_data, create_dictionary = self._keychain_store_fakes(
            weread_sync.ERR_SEC_ITEM_NOT_FOUND)
        with patch.object(weread_sync, "_keychain_runtime", return_value=(object(), security, core, 1, 2)), \
             patch.object(weread_sync, "_security_constant", side_effect=lambda _ctypes, _security, name: name), \
             patch.object(weread_sync, "_cf_string", side_effect=create_string), \
             patch.object(weread_sync, "_cf_data", side_effect=create_data), \
             patch.object(weread_sync, "_cf_dictionary", side_effect=create_dictionary):
            self.assertTrue(weread_sync.store_keychain_secret("fixture-service", "fixture-account", "fixture-secret"))
        self.assertEqual(["update", "add"], [event[0] for event in events if event[0] in ("update", "add")])
        self.assertEqual(["dictionary:2", "dictionary:1", "dictionary:0", "data:fixture-secret", "string:fixture-account", "string:fixture-service"],
                         [event[1] for event in events if event[0] == "release"])
        self.assertIn(("kSecValueData", "data:fixture-secret"), dictionaries[2][1])

    def test_keychain_store_does_not_add_when_interaction_is_not_allowed(self):
        security, core, events, dictionaries, create_string, create_data, create_dictionary = self._keychain_store_fakes(-25308)
        with patch.object(weread_sync, "_keychain_runtime", return_value=(object(), security, core, 1, 2)), \
             patch.object(weread_sync, "_security_constant", side_effect=lambda _ctypes, _security, name: name), \
             patch.object(weread_sync, "_cf_string", side_effect=create_string), \
             patch.object(weread_sync, "_cf_data", side_effect=create_data), \
             patch.object(weread_sync, "_cf_dictionary", side_effect=create_dictionary):
            self.assertFalse(weread_sync.store_keychain_secret("fixture-service", "fixture-account", "fixture-secret"))
        self.assertEqual(["update"], [event[0] for event in events if event[0] in ("update", "add")])

    def test_keychain_store_returns_false_for_update_or_add_failures(self):
        for update_status, add_status in ((-25293, 0), (weread_sync.ERR_SEC_ITEM_NOT_FOUND, -25293)):
            with self.subTest(update_status=update_status, add_status=add_status):
                security, core, events, dictionaries, create_string, create_data, create_dictionary = self._keychain_store_fakes(
                    update_status, add_status)
                with patch.object(weread_sync, "_keychain_runtime", return_value=(object(), security, core, 1, 2)), \
                     patch.object(weread_sync, "_security_constant", side_effect=lambda _ctypes, _security, name: name), \
                     patch.object(weread_sync, "_cf_string", side_effect=create_string), \
                     patch.object(weread_sync, "_cf_data", side_effect=create_data), \
                     patch.object(weread_sync, "_cf_dictionary", side_effect=create_dictionary):
                    self.assertFalse(weread_sync.store_keychain_secret("fixture-service", "fixture-account", "fixture-secret"))
                calls = [event[0] for event in events if event[0] in ("update", "add")]
                self.assertEqual(["update"] if update_status != weread_sync.ERR_SEC_ITEM_NOT_FOUND else ["update", "add"], calls)

    def test_live_gateway_refuses_fallback_version_metadata(self):
        with patch.object(weread_sync, "resolve_skill_version",
                          return_value=(weread_sync.FALLBACK_SKILL_VERSION, "fallback (no installed weread-skills/SKILL.md found)")):
            with self.assertRaises(weread_sync.GatewayError):
                weread_sync.Gateway("not-a-real-key")

    def test_export_escapes_malicious_remote_markdown_and_html(self):
        block = weread_sync.managed_notes_block("book-1--><img", {
            "book": {"title": "<img src=x onerror=alert(1)>"},
            "updated": [{"bookmarkId": "bm-1--><script", "markText": "![x](https://bad.example) # heading | `code` - + . ~"}],
        }, [{"reviewId": "top-2--><img", "review": {"reviewId": "nested-wrong", "abstract": "> quote", "content": "<img onerror=1> [link](https://bad.example)"}}])
        rendered = block.decode("utf-8")
        self.assertNotIn("<img", rendered)
        self.assertNotIn("![x]", rendered)
        self.assertNotIn("[link](", rendered)
        self.assertIn("&lt;img", rendered)
        self.assertIn("\\!\\[x\\]\\(https://bad\\.example\\)", rendered)
        self.assertIn("\\- \\+ \\. \\~", rendered)
        self.assertIn("- Book ID: `book-1--img`", rendered)
        self.assertIn("<!-- weread-reading-board:bookmark id=bm-1--script -->", rendered)
        self.assertIn("<!-- weread-reading-board:review id=top-2--img -->", rendered)

    def test_live_monthly_snapshot_uses_china_natural_month(self):
        vault = self.vault()
        china_midnight = int(__import__("datetime").datetime(2024, 8, 1, 0, 0, tzinfo=weread_sync.CHINA_TZ).timestamp())
        model = {"schemaVersion": 1, "generatedAt": china_midnight, "source": "live", "periods": {"monthly": {"baseTime": china_midnight}}}
        weread_sync.write_model(vault, model)
        self.assertTrue((vault / ".weread" / "snapshots" / "2024-08.json").is_file())
        self.assertFalse((vault / ".weread" / "snapshots" / "2024-07.json").exists())

    def test_period_normalizes_mixed_rankings_clock_and_optional_media_mix(self):
        raw = {"baseTime": 1704067200, "totalReadTime": 3600, "readDays": 2, "dayAverageReadTime": 1800,
               "readTimes": {"1704067200": 3600}, "dailyReadTimes": {"1704067200": 3600},
               "readLongest": [
                   {"book": {"bookId": "ebook-1", "title": "电子书", "author": "作者", "cover": "cover-a"}, "readTime": 1200, "tags": ["笔记最多"]},
                   {"albumInfo": {"albumId": "audio-1", "name": "有声书", "authorName": "讲述者", "cover": "cover-b"}, "readTime": 2400, "recordReadingTime": 30},
               ], "preferTime": list(range(24)), "preferTimeWord": "偏好夜间阅读", "preferCategoryWord": "偏好阅读文学",
               "recordReadingTime": 77, "readStat": [{"stat": "读过", "counts": "2本", "scheme": "weread://stats"}],
               "preferCategory": [{"categoryId": 1, "categoryTitle": "文学", "readingTime": 3000, "readingCount": 2, "val": 1}]}
        normalized = weread_sync.period(raw)
        self.assertEqual(["ebook", "audio"], [item["kind"] for item in normalized["rankedItems"]])
        self.assertEqual("album:audio-1", normalized["rankedItems"][1]["bookId"])
        self.assertEqual([6, 7, 8], [item["hour"] for item in normalized["readingClock"][:3]])
        self.assertEqual(["06:00", "05:00"], [normalized["readingClock"][0]["label"], normalized["readingClock"][-1]["label"]])
        self.assertEqual("1", normalized["categories"][0]["categoryId"])
        self.assertEqual({"label": "读过", "value": "2本", "deepLink": "weread://stats"}, normalized["readStat"][0])
        self.assertEqual("偏好阅读文学", normalized["preferCategoryWord"])
        self.assertEqual("偏好夜间阅读", normalized["preferTimeWord"])
        self.assertEqual(77, normalized["recordReadingTime"])
        self.assertNotIn("mediaMix", normalized)
        with_mix = weread_sync.period(dict(raw, readRate=70, wrReadTime=2500, wrListenTime=1100))
        self.assertEqual({"readRate": 70, "readSeconds": 2500, "listenSeconds": 1100}, with_mix["mediaMix"])

    def test_trailing_history_crosses_year_without_monthly_fanout(self):
        def timestamp(year, month):
            return str(int(__import__("datetime").datetime(year, month, 1, tzinfo=weread_sync.CHINA_TZ).timestamp()))
        current = {"baseTime": int(__import__("datetime").datetime(2024, 1, 1, tzinfo=weread_sync.CHINA_TZ).timestamp()),
                   "readTimes": {timestamp(2024, 1): 10, timestamp(2024, 2): 20, timestamp(2024, 12): 0}}
        previous = {"readTimes": {timestamp(2023, month): month for month in range(1, 13)}}
        current_monthly = {"baseTime": int(__import__("datetime").datetime(2024, 2, 1, tzinfo=weread_sync.CHINA_TZ).timestamp())}
        history = weread_sync.trailing_month_history(current, previous, current_monthly)
        self.assertEqual("2023-03", history[0]["month"])
        self.assertEqual("2024-02", history[-1]["month"])
        self.assertEqual(12, len(history))
        self.assertEqual(3, history[0]["readSeconds"])

    def test_live_model_uses_five_statistics_calls_public_ebooks_only_and_no_note_content(self):
        class Gateway:
            def __init__(self):
                self.calls = []
            def call(self, api, **kwargs):
                self.calls.append((api, kwargs))
                if api == "/readdata/detail":
                    mode = kwargs["mode"]
                    if mode == "annually":
                        base = kwargs.get("baseTime")
                        year = 2023 if base else 2024
                        months = {str(int(__import__("datetime").datetime(year, month, 1, tzinfo=weread_sync.CHINA_TZ).timestamp())): month * 10 for month in range(1, 13)}
                        return {"baseTime": int(__import__("datetime").datetime(year, 1, 1, tzinfo=weread_sync.CHINA_TZ).timestamp()), "totalReadTime": sum(months.values()), "readTimes": months,
                                "dailyReadTimes": months, "preferTime": list(range(24)), "preferCategory": [{"categoryId": "lit", "categoryTitle": "文学"}],
                                "readLongest": [{"book": {"bookId": "ebook-1", "title": "公开电子书", "author": "A", "cover": "c"}, "readTime": 100},
                                                {"albumInfo": {"albumId": "audio-1", "name": "公开有声书", "authorName": "B", "cover": "a"}, "readTime": 90}]}
                    return {"baseTime": 1704067200, "totalReadTime": 100, "readTimes": {"1704067200": 100}}
                if api == "/shelf/sync":
                    return {"books": [{"bookId": "ebook-1", "title": "公开电子书", "author": "A", "cover": "c", "readUpdateTime": 3},
                                      {"bookId": "private-1", "title": "PRIVATE CONTENT MUST NOT LEAK", "secret": 1}],
                            "albums": [{"albumInfo": {"albumId": "audio-1", "name": "公开有声书"}, "albumInfoExtra": {"lectureReadUpdateTime": 4}}], "mp": {"count": 3}}
                if api == "/user/notebooks":
                    return {"totalBookCount": 1, "totalNoteCount": 3, "hasMore": 0,
                            "books": [{"bookId": "ebook-1", "book": {"title": "公开电子书", "author": "A", "cover": "c"}, "noteCount": 1, "reviewCount": 1, "bookmarkCount": 1, "markedStatus": 0, "sort": 9}]}
                if api == "/book/getprogress":
                    if kwargs["bookId"] != "ebook-1":
                        raise AssertionError("audio/private book reached progress endpoint")
                    return {"book": {"progress": 55, "recordReadingTime": 60, "updateTime": 7}}
                raise AssertionError("unexpected endpoint: " + api)
        gateway = Gateway()
        model = weread_sync.build_live_model(gateway)
        stats = [call for call in gateway.calls if call[0] == "/readdata/detail"]
        self.assertEqual(5, len(stats))
        self.assertEqual({"weekly", "monthly", "annually", "overall"}, {call[1]["mode"] for call in stats})
        self.assertEqual(12, len(model["history"]["trailingMonths"]))
        self.assertEqual(["ebook-1"], [item["bookId"] for item in model["progress"]])
        self.assertEqual(4, model["shelf"]["totalEntries"])
        self.assertEqual(2, model["shelf"]["publicEntries"])
        serialized = json.dumps(model, ensure_ascii=False)
        self.assertNotIn("PRIVATE CONTENT", serialized)
        self.assertNotIn("/book/bookmarklist", [call[0] for call in gateway.calls])
        self.assertNotIn("/review/list/mine", [call[0] for call in gateway.calls])
        self.assertEqual({"highlights": 1, "reviews": 1, "bookmarks": 1}, model["notebooks"]["books"][0]["noteBreakdown"])

    def test_gateway_401_is_clear_without_exposing_server_body(self):
        with patch.object(weread_sync, "urlopen", side_effect=HTTPError("https://example.invalid", 401, "LOGIN ERR secret", {}, None)):
            gateway = weread_sync.Gateway("not-a-real-key", retries=0, skill_version="1.0.4")
            with self.assertRaisesRegex(weread_sync.GatewayError, "configure-key") as raised:
                gateway.call("/_list")
        self.assertNotIn("LOGIN ERR", str(raised.exception))

    def test_gateway_payload_is_flat_and_contains_resolved_skill_version(self):
        class Response:
            def __enter__(self):
                return self
            def __exit__(self, *args):
                return False
            def read(self):
                return b'{"errcode":0}'
        with patch.object(weread_sync, "urlopen", return_value=Response()) as opened:
            gateway = weread_sync.Gateway("not-a-real-key", retries=0, skill_version="9.8.7")
            gateway.call("/readdata/detail", mode="monthly", baseTime=123)
        request = opened.call_args.args[0]
        payload = json.loads(request.data.decode("utf-8"))
        self.assertEqual({"api_name": "/readdata/detail", "mode": "monthly", "baseTime": 123, "skill_version": "9.8.7"}, payload)
        self.assertTrue({"params", "data", "body"}.isdisjoint(payload))


if __name__ == "__main__":
    unittest.main()
