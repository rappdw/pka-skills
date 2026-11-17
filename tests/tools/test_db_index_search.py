"""db init / migrate / backup, index and search, through the vendored CLI."""
from __future__ import annotations

import os
import sqlite3
import unittest
from contextlib import closing

import support


class DbCase(support.ToolsCase):
    def db(self):
        conn = sqlite3.connect(str(self.path(".pka/knowledge.db")))
        conn.row_factory = sqlite3.Row
        return conn

    def rows(self, sql, *params):
        with closing(self.db()) as conn:
            return conn.execute(sql, params).fetchall()

    def scalar(self, sql, *params):
        return self.rows(sql, *params)[0][0]


class Init(DbCase):
    def test_init_creates_schema_version_1(self):
        out = self.json("db", "init")
        self.assertEqual(out["action"], "created")
        self.assertEqual(self.scalar("PRAGMA user_version"), 1)
        names = {row["name"] for row in self.rows("SELECT name FROM sqlite_master")}
        for name in ("file_index", "search_fts", "project_lifecycle", "pka_meta", "file_index_path_uq"):
            self.assertIn(name, names)

    def test_path_is_unique(self):
        self.ok("db", "init")
        with closing(self.db()) as conn:
            conn.execute("INSERT INTO file_index(path, folder, filename) VALUES('a.md', '', 'a.md')")
            with self.assertRaises(sqlite3.IntegrityError):
                conn.execute("INSERT INTO file_index(path, folder, filename) VALUES('a.md', '', 'a.md')")

    def test_init_twice_is_a_no_op(self):
        self.ok("db", "init")
        before = self.read(".pka/knowledge.db")
        self.assertEqual(self.json("db", "init")["action"], "already-initialized")
        self.assertEqual(self.read(".pka/knowledge.db"), before)

    def test_commands_without_an_index_exit_3(self):
        for args in (("index",), ("search", "x"), ("db", "schema"), ("db", "backup"), ("db", "migrate")):
            code, _out, err = self.tool(*args)
            self.assertEqual(code, 3, args)
            self.assertIn("no index", err)

    def test_outside_a_workspace_exits_3(self):
        code, _out, err = self.tool("status", cwd=self.base)
        self.assertEqual(code, 3)
        self.assertIn("no PKA workspace", err)


LEGACY_SCHEMA = """
CREATE TABLE file_index (
    id INTEGER PRIMARY KEY, path TEXT NOT NULL, folder TEXT NOT NULL, filename TEXT NOT NULL,
    file_type TEXT, size_bytes INTEGER, modified_at TEXT, inferred_topic TEXT, tags TEXT,
    ocr_text TEXT, indexed_at TEXT, status TEXT
);
CREATE VIRTUAL TABLE search_fts USING fts5(path, filename, folder, content, tokenize = 'porter unicode61');
CREATE TABLE personnel_index (person_slug TEXT, note_type TEXT, excerpt TEXT);
"""


class Migrate(DbCase):
    def make_legacy(self, schema=LEGACY_SCHEMA):
        with closing(self.db()) as conn:
            conn.executescript(schema)
            conn.execute("INSERT INTO file_index(path, folder, filename, status) VALUES('knowledge/a.md','knowledge','a.md','old')")
            conn.execute("INSERT INTO file_index(path, folder, filename, status) VALUES('knowledge/a.md','knowledge','a.md','new')")
            conn.execute("INSERT INTO file_index(path, folder, filename) VALUES('knowledge/b.pdf','knowledge','b.pdf')")
            conn.execute("INSERT INTO search_fts(path, filename, folder, content) VALUES('knowledge/b.pdf','b.pdf','knowledge','text a role extracted from the pdf')")
            conn.execute("INSERT INTO personnel_index VALUES('priya','1on1','hello')")
            conn.commit()

    def test_plan_changes_nothing(self):
        self.make_legacy()
        before = self.read(".pka/knowledge.db")
        plan = self.json("db", "migrate")
        self.assertEqual(plan["action"], "planned")
        self.assertEqual((plan["from"], plan["to"]), (0, 1))
        joined = "\n".join(plan["steps"])
        self.assertIn("content_hash", joined)
        self.assertIn("1 duplicate", joined)
        self.assertIn("unique index", joined)
        self.assertIn("rebuild search_fts", joined)
        self.assertEqual(self.read(".pka/knowledge.db"), before)
        self.assertFalse(self.path(".pka/db-backups").exists())

    def test_apply_backs_up_then_migrates_and_keeps_data(self):
        self.make_legacy()
        before = self.read(".pka/knowledge.db")
        result = self.json("db", "migrate", "--apply")
        self.assertEqual(result["action"], "migrated")
        backup = self.path(result["backup"])
        self.assertTrue(backup.is_file())
        with closing(sqlite3.connect(str(backup))) as conn:
            self.assertEqual(conn.execute("SELECT COUNT(*) FROM file_index").fetchone()[0], 3)
            self.assertEqual(conn.execute("PRAGMA user_version").fetchone()[0], 0)
        self.assertEqual(self.text(".pka/db-backups/.gitignore"), "*\n")
        self.assertEqual(self.scalar("PRAGMA user_version"), 1)
        # the newest duplicate survives; nothing else is lost
        kept = self.rows("SELECT status FROM file_index WHERE path = 'knowledge/a.md'")
        self.assertEqual([row["status"] for row in kept], ["new"])
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM file_index"), 2)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM personnel_index"), 1)
        # text a role had extracted is still searchable, now with is_pointer
        hit = self.rows("SELECT path, is_pointer FROM search_fts WHERE search_fts MATCH '\"extracted\"'")
        self.assertEqual([(row["path"], row["is_pointer"]) for row in hit], [("knowledge/b.pdf", 0)])
        self.assertNotEqual(self.read(".pka/knowledge.db"), before)

    def test_migrate_is_idempotent(self):
        self.make_legacy()
        self.ok("db", "migrate", "--apply")
        self.assertEqual(self.json("db", "migrate", "--apply")["action"], "none")
        self.assertEqual(len(list(self.path(".pka/db-backups").glob("*.db"))), 1)

    def test_commands_refuse_an_unmigrated_index(self):
        self.make_legacy()
        code, _out, err = self.tool("index")
        self.assertEqual(code, 3)
        self.assertIn("db migrate", err)
        code, _out, err = self.tool("search", "anything")
        self.assertEqual(code, 3)

    def test_unrecognised_fts_layout_is_kept_under_another_name(self):
        with closing(self.db()) as conn:
            conn.executescript("CREATE TABLE file_index (path TEXT);\nCREATE TABLE search_fts (body TEXT);")
            conn.execute("INSERT INTO search_fts VALUES('whatever a role stored here')")
            conn.commit()
        self.ok("db", "migrate", "--apply")
        names = {row["name"] for row in self.rows("SELECT name FROM sqlite_master")}
        self.assertIn("search_fts_legacy_v0", names)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM search_fts_legacy_v0"), 1)
        self.assertEqual(self.scalar("PRAGMA user_version"), 1)
        self.ok("index")
        self.assertGreater(self.scalar("SELECT COUNT(*) FROM search_fts"), 10)

    def test_file_index_without_path_is_refused_untouched(self):
        with closing(self.db()) as conn:
            conn.executescript("CREATE TABLE file_index (name TEXT);")
        before = self.read(".pka/knowledge.db")
        code, _out, err = self.tool("db", "migrate", "--apply")
        self.assertEqual(code, 3)
        self.assertIn("Nothing was changed", err)
        self.assertEqual(self.read(".pka/knowledge.db"), before)

    def test_a_failing_step_rolls_everything_back(self):
        from pka_tools import db as db_mod
        from pka_tools.errors import ToolError
        from pka_tools.workspace import Workspace
        self.make_legacy()
        good = db_mod._CREATE_LIFECYCLE
        db_mod._CREATE_LIFECYCLE = "CREATE TABLE project_lifecycle (this is not sql"
        try:
            with self.assertRaises(ToolError) as caught:
                db_mod.migrate(Workspace(self.ws), apply=True)
        finally:
            db_mod._CREATE_LIFECYCLE = good
        self.assertIn("rolled back", caught.exception.message)
        self.assertEqual(self.scalar("PRAGMA user_version"), 0)
        columns = [row["name"] for row in self.rows("PRAGMA table_info(file_index)")]
        self.assertNotIn("content_hash", columns)
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM file_index"), 3)
        self.assertEqual(len(list(self.path(".pka/db-backups").glob("*.db"))), 1)

    def test_backup_command(self):
        self.ok("db", "init")
        first = self.json("db", "backup")["backup"]
        second = self.json("db", "backup")["backup"]
        self.assertNotEqual(first, second)
        self.assertTrue(self.path(first).is_file() and self.path(second).is_file())


class Index(DbCase):
    def setUp(self):
        super().setUp()
        self.ok("db", "init")

    def paths(self):
        return {row["path"] for row in self.rows("SELECT path FROM file_index")}

    def test_first_pass_covers_roots_and_respects_ignores(self):
        report = self.json("index")
        paths = self.paths()
        self.assertEqual(report["added"], len(paths))
        self.assertIn("knowledge/AI/Vendor landscape, 2026.md", paths)
        self.assertIn("knowledge/AI/northwind/Übersicht – Zürich.md", paths)
        self.assertIn("knowledge/reference/report.pdf", paths)
        self.assertIn("projects/orion/CLAUDE.md", paths)
        self.assertIn("meeting-notes/2026-11-10_140000_slt-sync/narrative.md", paths)
        for absent in (
            "knowledge/reference/report.pdf.txt",                      # sidecar: attached to its source
            "knowledge/archived/old-plan.md",                           # Archive priority
            "knowledge/AI/build.log",                                   # .pkaignore
            "projects/orion/src/main.rs",                               # shallow project index
            "meeting-notes/2026-11-10_140000_slt-sync/transcript.md",   # capture: narrative only
            "meeting-notes/2026-11-10_140000_slt-sync/audio.wav",
            "meeting-notes/2026-11-11-loose-notes.md",                  # unrouted
            "knowledge/.obsidian/app.json",
        ):
            self.assertNotIn(absent, paths)
        self.assertEqual(report["needs_text"], ["knowledge/reference/scan.pdf"])
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM file_index WHERE content_hash IS NULL"), 0)

    def test_second_pass_changes_nothing(self):
        self.ok("index")
        before = self.rows("SELECT path, content_hash, indexed_at FROM file_index ORDER BY path")
        report = self.json("index")
        self.assertEqual((report["added"], report["updated"], report["removed"]), (0, 0, 0))
        after = self.rows("SELECT path, content_hash, indexed_at FROM file_index ORDER BY path")
        self.assertEqual([tuple(r) for r in before], [tuple(r) for r in after])

    def test_sidecar_text_is_searchable_under_the_source_path(self):
        self.ok("index")
        hits = self.json("search", "quarterly lighthouse")["results"]
        self.assertEqual([hit["path"] for hit in hits], ["knowledge/reference/report.pdf"])
        self.assertEqual(self.scalar("SELECT ocr_text FROM file_index WHERE path = 'knowledge/reference/report.pdf'"),
                         "Extracted text: quarterly lighthouse report.\n")

    def test_new_sidecar_is_picked_up_without_touching_the_source(self):
        self.ok("index")
        self.write("knowledge/reference/scan.pdf.txt", "freshly recognised words\n")
        report = self.json("index")
        self.assertEqual(report["updated"], 1)
        self.assertEqual(report["needs_text"], [])
        self.assertEqual(self.json("search", "recognised")["results"][0]["path"], "knowledge/reference/scan.pdf")

    def test_change_add_remove(self):
        self.ok("index")
        self.write("knowledge/AI/ai-adoption-research.md", "# Rewritten\n\nzeppelin\n")
        self.write("knowledge/AI/new-note.md", "# New\n\nxylophone\n")
        self.path("knowledge/AI/northwind/northwind_partnership_proposal.md").unlink()
        report = self.json("index")
        self.assertEqual((report["added"], report["updated"], report["removed"]), (1, 1, 1))
        self.assertEqual(self.json("search", "zeppelin")["count"], 1)
        self.assertEqual(self.json("search", "xylophone")["count"], 1)
        self.assertEqual(self.json("search", "Draft")["count"], 0)
        self.assertNotIn("knowledge/AI/northwind/northwind_partnership_proposal.md", self.paths())
        # exactly one body row per file: no duplicates left behind by the update
        dupes = self.rows("SELECT path, COUNT(*) c FROM search_fts WHERE is_pointer = 0 GROUP BY path HAVING c > 1")
        self.assertEqual(dupes, [])

    def test_explicit_paths_index_only_those(self):
        report = self.json("index", "knowledge/AI/ai-adoption-research.md", "knowledge/leadership")
        self.assertIn("knowledge/AI/ai-adoption-research.md", self.paths())
        self.assertNotIn("knowledge/AI/Vendor landscape, 2026.md", self.paths())
        self.assertGreater(report["added"], 2)

    def test_missing_explicit_path_removes_its_row_and_is_reported(self):
        self.ok("index")
        self.path("knowledge/AI/new.md").write_text("x\n")
        self.ok("index", "knowledge/AI/new.md")
        self.path("knowledge/AI/new.md").unlink()
        report = self.json("index", "knowledge/AI/new.md")
        self.assertEqual(report["removed"], 1)
        self.assertEqual(report["not_found"], ["knowledge/AI/new.md"])

    def test_moc_pointer_rows_are_separate_flagged_rows(self):
        self.ok("index")
        rows = self.rows("SELECT content FROM search_fts WHERE is_pointer = 1 AND path = 'knowledge/AI/_MOC.md' ORDER BY rowid")
        self.assertEqual(len(rows), 2)
        self.assertTrue(rows[0]["content"].startswith("northwind-partnership-2026 sasha-ortega, taylor-brooks"))
        body = self.scalar("SELECT content FROM search_fts WHERE is_pointer = 0 AND path = 'knowledge/AI/_MOC.md'")
        self.assertIn("Hand-written introduction", body)
        self.assertNotIn("sasha-ortega", body)
        # the table inside the code fence is an example, not a pointer row
        self.assertEqual(self.scalar("SELECT COUNT(*) FROM search_fts WHERE is_pointer = 1 AND content LIKE '%example-inside-a-fence%'"), 0)

    def test_text_a_role_inserted_for_a_pdf_survives_reindexing(self):
        self.ok("index")
        with closing(self.db()) as conn:
            conn.execute("INSERT INTO search_fts(path, filename, folder, content, is_pointer) "
                         "VALUES('knowledge/reference/scan.pdf', 'scan.pdf', 'knowledge/reference', 'pdfplumber output marigold', 0)")
            conn.commit()
        self.ok("index")
        self.ok("index", "--rebuild")
        self.assertEqual(self.json("search", "marigold")["results"][0]["path"], "knowledge/reference/scan.pdf")
        # ... until the file changes, when it is reported as stale
        self.write("knowledge/reference/scan.pdf", b"%PDF-1.4 different bytes\n")
        self.assertEqual(self.json("index")["stale_text"], ["knowledge/reference/scan.pdf"])

    def test_rows_outside_scope_are_counted_and_pruned_only_on_request(self):
        self.ok("index")
        with closing(self.db()) as conn:
            conn.execute("INSERT INTO file_index(path, folder, filename) VALUES('./AI/old-form.md', 'AI', 'old-form.md')")
            conn.execute("INSERT INTO file_index(path, folder, filename) VALUES('gone-folder/x.md', 'gone-folder', 'x.md')")
            conn.commit()
        report = self.json("index")
        self.assertEqual(report["stale_elsewhere"], 2)
        self.assertIn("gone-folder/x.md", self.paths())
        report = self.json("index", "--prune")
        self.assertEqual(report["pruned"], 2)
        self.assertNotIn("gone-folder/x.md", self.paths())

    def test_dry_run_writes_nothing(self):
        before = self.read(".pka/knowledge.db")
        report = self.json("index", "--dry-run")
        self.assertGreater(report["added"], 10)
        self.assertEqual(self.read(".pka/knowledge.db"), before)

    def test_frontmatter_tags_and_topic_are_recorded(self):
        self.ok("index")
        row = self.rows("SELECT tags, inferred_topic FROM file_index WHERE path = 'knowledge/AI/ai-adoption-research.md'")[0]
        self.assertEqual((row["tags"], row["inferred_topic"]), ("research, strategy", "ai-adoption-research"))

    def test_non_utf8_file_is_indexed_not_fatal(self):
        self.ok("index")
        self.assertIn("knowledge/reference/latin1.md", self.paths())
        self.assertEqual(self.json("search", "lait")["count"], 1)

    def test_paths_inside_pka_are_refused(self):
        code, _out, err = self.tool("index", ".pka/session-log.md")
        self.assertEqual(code, 64)


class Search(DbCase):
    def setUp(self):
        super().setUp()
        self.ok("db", "init")
        self.ok("index")

    def test_slugs_and_punctuation_do_not_break_the_query(self):
        for query in ("northwind-partnership-2026", "what did we decide about pricing?", "AI/ML notes",
                      'say "hello"', "NOT AND OR NEAR", "col:value", "c++ -flag [x]", "(unbalanced"):
            code, _out, err = self.tool("search", query)
            self.assertEqual(code, 0, "%r: %s" % (query, err))

    def test_pointer_row_outranks_body_matches(self):
        result = self.json("search", "northwind")
        self.assertGreaterEqual(result["count"], 3)
        top = result["results"][0]
        self.assertTrue(top["is_pointer"])
        self.assertEqual(top["topic"], "northwind-partnership-2026")
        self.assertEqual(top["files"][0]["path"], "knowledge/AI/northwind/northwind_partnership_proposal.md")
        self.assertTrue(top["files"][0]["exists"])

    def test_all_terms_then_any(self):
        both = self.json("search", "lighthouse", "quarterly")
        self.assertEqual(both["mode"], "all")
        self.assertEqual(both["match"], '"lighthouse" "quarterly"')
        fallback = self.json("search", "lighthouse", "zzzznotaword")
        self.assertEqual(fallback["mode"], "any")
        self.assertGreaterEqual(fallback["count"], 1)

    def test_nothing_to_search_for_is_a_usage_error(self):
        code, _out, err = self.tool("search", "???", "--")
        self.assertEqual(code, 64)

    def test_non_ascii_terms(self):
        self.assertEqual(self.json("search", "Zürich")["results"][0]["path"],
                         "knowledge/AI/northwind/Übersicht – Zürich.md")

    def test_limit(self):
        self.assertEqual(self.json("search", "the", "--any", "--limit", "2")["count"], 2)


if __name__ == "__main__":
    unittest.main()
