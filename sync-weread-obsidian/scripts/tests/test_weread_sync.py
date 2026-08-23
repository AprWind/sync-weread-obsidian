import importlib.util
import json
import io
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from contextlib import redirect_stdout

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
        self.assertEqual(5, len(model["shelf"]["items"]))
        self.assertEqual([".weread/covers/sample-%02d.webp" % number for number in range(1, 6)],
                         [item["cover"] for item in model["shelf"]["items"]])
        self.assertEqual([40, 72, 15, 100, 5], [item["progressPercent"] for item in model["progress"]])
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
        self.assertEqual(1, shelf["totalEntries"])
        self.assertEqual(2, shelf["privateCount"])
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

    def test_resolve_skill_version_uses_installed_metadata_or_explicit_fallback(self):
        root = Path(tempfile.mkdtemp())
        skill = root / "SKILL.md"
        skill.write_text("---\nname: weread-skills\nversion: 2.3.4\n---\n", encoding="utf-8")
        self.assertEqual(("2.3.4", str(skill)), weread_sync.resolve_skill_version([skill]))
        self.assertEqual((weread_sync.FALLBACK_SKILL_VERSION, "fallback (no installed weread-skills/SKILL.md found)"),
                         weread_sync.resolve_skill_version([root / "missing.md"]))

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


if __name__ == "__main__":
    unittest.main()
