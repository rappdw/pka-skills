"""Regression tests for bugs found in review of the first toolkit build.

Each test names the promise it protects. They all run the vendored tool.
"""
from __future__ import annotations

import json
import os
import sqlite3
import stat
import unittest
from contextlib import closing

import support

from pka_tools import frontmatter
from pka_tools.textio import split_lines

HEADER = "| Topic | Entities | Files |\n|---|---|---|\n"


def running_as_root() -> bool:
    return hasattr(os, "geteuid") and os.geteuid() == 0


class Frontmatter(unittest.TestCase):
    def merge(self, text):
        lines = split_lines(text)
        fm = frontmatter.parse(lines)
        if not fm.usable:
            return None, fm.error
        out, status = frontmatter.merge_tag(lines, fm, "ai", "\n")
        return "".join(out), status

    def test_trailing_comma_in_a_flow_list_stays_valid_yaml(self):
        self.assertEqual(self.merge("---\ntags: [a, b,]\n---\n")[0], "---\ntags: [a, b, ai]\n---\n")
        self.assertEqual(self.merge("---\ntags: [a, ]\n---\n")[0], "---\ntags: [a, ai]\n---\n")

    def test_comment_after_an_empty_tags_key_is_kept(self):
        self.assertEqual(self.merge("---\ntags: # my tags\n---\n")[0], "---\ntags: [ai]  # my tags\n---\n")

    def test_unbalanced_brackets_are_malformed_not_edited(self):
        out, error = self.merge("---\ntags: [a]]\n---\n")
        self.assertIsNone(out)
        self.assertIn("closing ]", error)

    def test_nested_brackets_are_fine(self):
        self.assertEqual(self.merge("---\ntags: [a]\nattendees: [[priya]]\n---\n")[1], "added")


class ReadOnlyAndLinks(support.ToolsCase):
    def test_read_only_moc_is_skipped_by_add_and_rename(self):
        if running_as_root():
            self.skipTest("root ignores file permissions")
        rel = "knowledge/AI/_MOC.md"
        os.chmod(str(self.path(rel)), stat.S_IRUSR | stat.S_IRGRP | stat.S_IROTH)
        before = self.read(rel)
        result = self.json("pointers", "add", "knowledge/AI/Vendor landscape, 2026.md")
        self.assertEqual(result["mocs"][0]["action"], "skipped")
        self.assertIn("read-only", result["mocs"][0]["problem"])
        self.assertEqual(result["changed"], [])
        renamed = self.json("pointers", "rename", "AI/ai-adoption-research", "AI/renamed")
        self.assertEqual((renamed["rewrites"], renamed["skipped"]), (0, [rel]))
        self.assertEqual(self.read(rel), before)

    def test_symlinked_moc_is_written_through_not_replaced(self):
        rel = "knowledge/AI/_MOC.md"
        real = self.base / "shared-moc.md"
        os.rename(str(self.path(rel)), str(real))
        os.symlink(str(real), str(self.path(rel)))
        self.ok("pointers", "add", "knowledge/AI/Vendor landscape, 2026.md")
        self.assertTrue(self.path(rel).is_symlink())
        self.assertIn("vendor-landscape-2026", real.read_text(encoding="utf-8"))

    def test_read_only_folder_is_reported_not_a_traceback(self):
        if running_as_root():
            self.skipTest("root ignores folder permissions")
        folder = self.path("knowledge/reference")
        os.chmod(str(folder), stat.S_IRUSR | stat.S_IXUSR)
        try:
            code, out, err = self.tool("obsidian", "bootstrap", "--json")
        finally:
            os.chmod(str(folder), 0o755)
        self.assertEqual(code, 0, err)
        self.assertNotIn("Traceback", err)
        skipped = "\n".join(json.loads(out)["skipped"])
        self.assertIn("reference/_MOC.md: could not write", skipped)
        self.assertTrue(self.path("knowledge/lab-notebook/_MOC.md").is_file())   # the rest still happened


class VaultShapes(support.ToolsCase):
    def test_capture_directory_inside_the_vault_is_left_alone(self):
        capture = "knowledge/leadership/2026-01-05_090000_sync"
        self.write(capture + "/meeting.json", "{}\n")
        self.write(capture + "/narrative.md", "The narrative.\n")
        self.write(capture + "/notes.md", "- [ ] a machine note, not an action item\n")
        self.ok("obsidian", "bootstrap")
        self.assertFalse(self.path(capture + "/_MOC.md").exists())
        self.assertEqual(self.text(capture + "/narrative.md"), "The narrative.\n")
        self.assertEqual(self.text(capture + "/notes.md"), "- [ ] a machine note, not an action item\n")
        items = self.json("actions", "--all-dates", "--include-undated")["items"]
        self.assertFalse([item for item in items if "machine note" in item["text"]])
        # ... while its narrative is still indexed in place
        self.ok("db", "init")
        self.ok("index")
        self.assertEqual(self.json("search", "narrative")["results"][0]["path"], capture + "/narrative.md")

    def test_names_a_wikilink_cannot_express_get_no_row(self):
        for name in ("C# notes.md", "plan [draft].md", "a^b.md"):
            self.write("knowledge/AI/" + name, "x\n")
            before = self.read("knowledge/AI/_MOC.md")
            for _ in range(2):
                code, out, err = self.tool("pointers", "add", "knowledge/AI/" + name, "--json")
                self.assertEqual(code, 0, err)
                result = json.loads(out)
                self.assertIn("wikilink cannot express", result["problem"])
                self.assertEqual(result["changed"], [])
            self.assertEqual(self.read("knowledge/AI/_MOC.md"), before)
        self.assertEqual(self.json("pointers", "check")["broken"], [])

    def test_bootstrap_stubs_do_not_link_what_they_cannot_name(self):
        self.write("knowledge/planning/C# notes.md", "x\n")
        self.write("knowledge/planning/plain.md", "x\n")
        self.ok("obsidian", "bootstrap")
        stub = self.text("knowledge/planning/_MOC.md")
        self.assertIn("- [[planning/plain|plain]]\n", stub)
        self.assertNotIn("C#", stub)

    def test_moc_with_an_unclosed_fence_is_skipped(self):
        text = "# AI\n\n```\nsnippet\n"
        self.write("knowledge/AI/_MOC.md", text)
        for _ in range(2):
            result = self.json("pointers", "add", "knowledge/AI/Vendor landscape, 2026.md")
            self.assertEqual(result["mocs"][0]["action"], "skipped")
            self.assertIn("never closed", result["mocs"][0]["problem"])
        self.assertEqual(self.text("knowledge/AI/_MOC.md"), text)

    def test_bare_carriage_return_files_are_left_alone(self):
        note = b"---\rtags: [a]\r---\rbody\r"
        self.write("knowledge/AI/old-mac.md", note)
        moc = b"# Reference\r\r## Pointers\r\r| Topic | Entities | Files |\r|---|---|---|\r| a-b | x | [[reference/x]] |\r"
        self.write("knowledge/reference/_MOC.md", moc)
        summary = self.json("obsidian", "bootstrap")
        self.assertIn("AI/old-mac.md: uses bare carriage returns as line endings", summary["skipped"])
        self.assertEqual(self.read("knowledge/AI/old-mac.md"), note)
        result = self.json("pointers", "add", "knowledge/reference/code-fence.md")
        self.assertEqual(result["mocs"][0]["action"], "skipped")
        self.assertEqual(self.read("knowledge/reference/_MOC.md"), moc)

    def test_person_folder_with_quotes_round_trips(self):
        self.write('knowledge/personnel/robin "rob" orion/2026-05-01-1on1.md', "x\n")
        self.ok("obsidian", "bootstrap")
        text = self.text('knowledge/personnel/robin "rob" orion/2026-05-01-1on1.md')
        self.assertIn('person: "[[personnel/robin \\"rob\\" orion/index]]"\n', text)
        again = self.json("obsidian", "bootstrap")
        self.assertEqual((again["touched"], [s for s in again["skipped"] if "orion" in s]), ([], []))

    def test_rename_leaves_code_comments_and_escaped_links(self):
        text = ("# AI\n\n- [[AI/old]]\n- `[[AI/old]]` is how you would write it\n"
                "- <!-- [[AI/old]] --> and \\[[AI/old]] stay\n")
        self.write("knowledge/planning/_MOC.md", text)
        result = self.json("pointers", "rename", "AI/old", "AI/new")
        self.assertEqual(result["rewrites"], 1)
        self.assertEqual(self.text("knowledge/planning/_MOC.md"), text.replace("- [[AI/old]]\n", "- [[AI/new]]\n", 1))

    def test_existing_entities_written_as_links_or_names_are_not_duplicated(self):
        self.write("knowledge/planning/_MOC.md", "## Pointers\n\n" + HEADER +
                   "| roadmap-review | [[personnel/priya/index\\|Priya]], Robin Smith | [[planning/a]] |\n")
        self.write("knowledge/planning/b.md", "---\ntopic: roadmap-review\nattendees: [priya, robin-smith]\n---\n")
        self.ok("pointers", "add", "knowledge/planning/b.md")
        row = self.text("knowledge/planning/_MOC.md").splitlines()[-1]
        self.assertEqual(row, "| roadmap-review | [[personnel/priya/index\\|Priya]], Robin Smith | "
                              "[[planning/a]], [[planning/b]] |")

    def test_topic_with_nothing_to_slug_is_a_usage_error(self):
        code, _out, err = self.tool("pointers", "add", "knowledge/AI/ai-adoption-research.md", "--topic", "!!!")
        self.assertEqual(code, 64)

    def test_moc_flag_cannot_leave_the_vault_through_a_link(self):
        outside = self.base / "outside"
        outside.mkdir()
        os.symlink(str(outside), str(self.path("knowledge/AI/link")))
        code, _out, err = self.tool("pointers", "add", "knowledge/AI/ai-adoption-research.md",
                                    "--moc", "knowledge/AI/link/_MOC.md")
        self.assertEqual(code, 64)
        self.assertEqual(list(outside.iterdir()), [])

    def test_repo_map_row_pointing_outside_is_ignored(self):
        (self.base / "outside").mkdir()
        (self.base / "outside" / "secret.md").write_text("not ours\n")
        claude = self.text("CLAUDE.md") + "| `../outside/` | elsewhere | flat | Active | active | High | meeting-home |\n"
        self.write("CLAUDE.md", claude)
        status = self.json("status")
        self.assertFalse([root for root in status["index_roots"] if "outside" in root])
        self.assertFalse([root for root in status["meeting_homes"] if "outside" in root])


class NoTracebacks(support.ToolsCase):
    def assertClean(self, code, err, expected):
        self.assertEqual(code, expected, err)
        self.assertNotIn("Traceback", err)

    def test_a_file_that_is_not_a_database(self):
        self.write(".pka/knowledge.db", "this is not sqlite\n" * 50)
        for args in (("status",), ("db", "schema"), ("db", "migrate"), ("db", "init"), ("index",), ("search", "x")):
            code, _out, err = self.tool(*args)
            self.assertClean(code, err, 1)
            self.assertIn("could not be read", err)

    def test_manifest_that_is_not_an_object(self):
        self.write(".pka/manifest.json", "[]\n")
        code, _out, err = self.tool("status")
        self.assertClean(code, err, 0)

    def test_bad_pkaignore_pattern_is_ignored(self):
        self.write(".pkaignore", "[z-a]\n*.log\n")
        self.ok("db", "init")
        code, out, err = self.tool("index", "--json")
        self.assertClean(code, err, 0)
        self.assertGreater(json.loads(out)["added"], 10)

    def test_filename_that_is_not_utf8(self):
        raw = os.fsencode(str(self.path("knowledge/AI"))) + b"/caf\xe9.md"
        try:
            with open(raw, "wb") as handle:
                handle.write(b"x\n")
        except OSError:
            self.skipTest("this filesystem does not allow such a name")
        self.ok("db", "init")
        code, out, err = self.tool("index", "--json")
        self.assertClean(code, err, 0)
        report = json.loads(out)
        self.assertEqual(report["unreadable_names"], 1)
        self.assertGreater(report["added"], 10)
        code, _out, err = self.tool("obsidian", "bootstrap")
        self.assertClean(code, err, 0)

    def test_strict_dates_on_every_python(self):
        code, _out, err = self.tool("actions", "--since", "20261101")
        self.assertClean(code, err, 64)


class IndexEdges(support.ToolsCase):
    def setUp(self):
        super().setUp()
        self.ok("db", "init")
        self.ok("index")

    def db(self):
        return sqlite3.connect(str(self.path(".pka/knowledge.db")))

    def test_prune_keeps_text_stored_under_an_old_path_form_for_a_file_that_exists(self):
        with closing(self.db()) as conn:
            conn.execute("INSERT INTO search_fts(path, filename, folder, content, is_pointer) VALUES"
                         "('./knowledge/reference/scan.pdf', 'scan.pdf', 'reference', 'role extracted marigold', 0)")
            conn.execute("INSERT INTO search_fts(path, filename, folder, content, is_pointer) VALUES"
                         "('./knowledge/reference/gone.pdf', 'gone.pdf', 'reference', 'orphan text', 0)")
            conn.commit()
        report = self.json("index", "--prune")
        self.assertEqual(report["pruned"], 1)
        with closing(self.db()) as conn:
            paths = [row[0] for row in conn.execute("SELECT path FROM search_fts WHERE path LIKE './%'")]
        self.assertEqual(paths, ["./knowledge/reference/scan.pdf"])

    def test_explicitly_indexed_note_outside_the_roots_survives_a_plain_index(self):
        rel = "meeting-notes/2026-11-11-loose-notes.md"
        self.assertEqual(self.json("index", rel)["added"], 1)
        report = self.json("index")
        self.assertEqual(report["removed"], 0)
        self.path(rel).unlink()
        self.assertEqual(self.json("index")["removed"], 1)

    def test_extra_required_column_is_flagged_in_the_plan(self):
        os.remove(str(self.path(".pka/knowledge.db")))
        with closing(self.db()) as conn:
            conn.executescript("CREATE TABLE file_index (path TEXT, owner TEXT NOT NULL);")
        plan = self.json("db", "migrate")
        self.assertTrue([step for step in plan["steps"] if step.startswith("NOTE:") and "owner" in step])


class InstallEdges(support.ToolsCase):
    def test_manifest_keys_cannot_reach_outside_dot_pka(self):
        import hashlib
        note = "knowledge/AI/ai-adoption-research.md"
        digest = hashlib.sha256(self.read(note)).hexdigest()
        manifest = json.loads(self.text(".pka/manifest.json"))
        manifest["files"]["../" + note] = {"sha256": digest, "component": "core"}
        manifest["files"]["/etc/hosts"] = {"sha256": "0" * 64, "component": "core"}
        self.write(".pka/manifest.json", json.dumps(manifest))
        code, out, err = self.plugin("install", "--workspace", str(self.ws), "--json")
        self.assertEqual(code, 0, err)
        report = json.loads(out)
        self.assertEqual((report["obsolete_moved"], report["obsolete_kept"]), ([], []))
        self.assertTrue(self.path(note).is_file())
        self.assertNotIn("../" + note, json.loads(self.text(".pka/manifest.json"))["files"])


if __name__ == "__main__":
    unittest.main()
