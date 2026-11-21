"""`pka-tools commit` (a deprecated stub that never touches git) and `pka-tools actions`."""
from __future__ import annotations

import os
import unittest

import support


class CommitStub(support.ToolsCase):
    """`commit` is kept so role files written for earlier releases do not
    fail, but it must not touch git: nothing staged, nothing committed."""

    def setUp(self):
        super().setUp()
        self.repo = self.init_repo("knowledge")

    def head(self):
        return self.git(self.repo, "rev-parse", "HEAD").strip()

    def test_does_nothing_and_exits_0(self):
        before = self.head()
        self.write("knowledge/AI/x.md", "x\n")
        code, out, _err = self.tool("commit", "-m", "Librarian: Route x.md to AI/", "--body", "b", "knowledge/AI/x.md")
        self.assertEqual(code, 0)
        self.assertIn("no longer commits", out)
        self.assertEqual(self.head(), before)
        self.assertEqual(self.git(self.repo, "status", "--porcelain").strip(), "?? AI/x.md")

    def test_stage_only_stages_nothing(self):
        self.write("knowledge/AI/x.md", "x\n")
        result = self.json("commit", "--stage-only", "knowledge/AI/x.md")
        self.assertEqual((result["committed"], result["reason"], result["deprecated"]), (False, "removed", True))
        self.assertEqual(self.git(self.repo, "status", "--porcelain").strip(), "?? AI/x.md")

    def test_any_arguments_an_old_role_file_might_pass_are_accepted(self):
        for args in (("commit", "-m", "x"),
                     ("commit", "-m", "x", "--", "knowledge/AI/x.md", "knowledge/AI/_MOC.md"),
                     ("commit", "-m", "x", "no/such/file.md"),
                     ("commit",)):
            code, _out, _err = self.tool(*args)
            self.assertEqual(code, 0, args)

    def test_works_without_git_and_outside_a_repository(self):
        (self.base / "empty-bin").mkdir()
        self.env["PATH"] = str(self.base / "empty-bin")      # no git to be found
        code, out, _err = self.tool("commit", "-m", "x", "projects/orion/CLAUDE.md")
        self.assertEqual(code, 0)
        self.assertIn("no longer commits", out)


class SymlinkedVault(support.ToolsCase):
    """knowledge/ is a symbolic link to a vault kept elsewhere (an iCloud or
    Dropbox folder, say). Paths are still given through the workspace."""

    def setUp(self):
        super().setUp()
        real = self.base / "elsewhere" / "vault"
        real.parent.mkdir()
        os.rename(str(self.path("knowledge")), str(real))
        os.symlink(str(real), str(self.path("knowledge")))
        self.real = real

    def test_commands_work_through_the_link(self):
        self.ok("db", "init")
        self.assertGreater(self.json("index")["added"], 15)
        summary = self.json("obsidian", "bootstrap")
        self.assertIn("(vault root)", summary["moc_created"])
        self.assertTrue((self.real / "_MOC.md").is_file())
        result = self.json("pointers", "add", "knowledge/AI/Vendor landscape, 2026.md")
        self.assertEqual(result["changed"], ["knowledge/AI/_MOC.md"])
        self.ok("index", "knowledge/AI/_MOC.md")
        self.assertTrue(self.json("search", "vendor-landscape-2026")["results"][0]["is_pointer"])
        self.assertGreaterEqual(self.json("actions", "--all-dates")["open"], 3)


class Actions(support.ToolsCase):
    def test_open_items_in_the_date_window(self):
        result = self.json("actions", "--since", "2026-04-01", "--until", "2026-04-30")
        found = [(item["path"], item["text"]) for item in result["items"]]
        self.assertEqual(found, [
            ("knowledge/leadership/2026-04-22-slt-meeting.md", "Review the Q2 budget proposal @Sam"),
            ("knowledge/leadership/2026-04-22-slt-meeting.md", "Circulate minutes"),
        ])
        self.assertEqual(result["scope"], ["knowledge/leadership", "knowledge/personnel"])
        self.assertEqual(result["items"][0]["owners"], ["Sam"])
        self.assertEqual(result["closed"], 1)

    def test_scope_all_finds_notes_outside_meeting_homes(self):
        result = self.json("actions", "--since", "2026-04-01", "--until", "2026-04-30", "--scope", "all")
        item = [i for i in result["items"] if i["path"].endswith("joint-partnership-meeting.md")][0]
        self.assertEqual(item["text"], "Send Priya the architecture comparison @Sam by 2026-05-01")
        self.assertEqual((item["owners"], item["due"], item["date"]), (["Sam"], "2026-05-01", "2026-04-23"))

    def test_person_folder_notes_are_in_the_default_scope(self):
        result = self.json("actions", "--since", "2026-03-01", "--until", "2026-03-31")
        self.assertEqual([item["path"] for item in result["items"]],
                         ["knowledge/personnel/priya/2026-03-31-1-1-priya.md"])

    def test_checkboxes_inside_code_fences_are_not_action_items(self):
        result = self.json("actions", "--all-dates", "--include-undated", "--scope", "all")
        self.assertFalse([i for i in result["items"] if "not a real action item" in i["text"]])
        self.assertGreaterEqual(result["open"], 4)

    def test_ticking_the_box_closes_the_item(self):
        name = "knowledge/leadership/2026-04-22-slt-meeting.md"
        self.write(name, self.read(name).replace(b"- [ ] Review", b"- [x] Review"))
        result = self.json("actions", "--since", "2026-04-01", "--until", "2026-04-30")
        self.assertEqual([item["text"] for item in result["items"]], ["Circulate minutes"])

    def test_default_window_is_the_last_seven_days(self):
        # The day is pinned, so the test does not depend on when it runs.
        self.env["PKA_ACTIONS_TODAY"] = "2026-11-20"
        for day, text in (("2026-11-20", "today"), ("2026-11-18", "recent item"), ("2026-11-13", "seven days back"),
                          ("2026-11-12", "eight days back"), ("2026-10-21", "old item")):
            self.write("knowledge/leadership/%s-standup.md" % day, "- [ ] %s\n" % text)
        result = self.json("actions")
        self.assertEqual([item["text"] for item in result["items"]], ["seven days back", "recent item", "today"])
        self.assertEqual((result["since"], result["until"]), ("2026-11-13", None))
        self.assertIn("since 2026-11-13,", self.ok("actions"))
        # An explicit window does not look at the day at all.
        self.env["PKA_ACTIONS_TODAY"] = "1999-01-01"
        self.assertEqual(len(self.json("actions", "--since", "2026-11-12", "--until", "2026-11-18")["items"]), 3)

    def test_without_the_override_the_window_ends_today(self):
        import datetime
        self.env.pop("PKA_ACTIONS_TODAY", None)
        expected = (datetime.date.today() - datetime.timedelta(days=7)).isoformat()
        self.assertIn(self.json("actions")["since"], (expected, (datetime.date.today() - datetime.timedelta(days=8)).isoformat()))

    def test_a_bad_override_is_a_usage_error(self):
        for value in ("tomorrow", "2026-13-45", "20261120", "2026-11-20T09:00:00Z"):
            self.env["PKA_ACTIONS_TODAY"] = value
            code, _out, err = self.tool("actions")
            self.assertEqual(code, 64, value)
            self.assertIn("PKA_ACTIONS_TODAY must be a date like 2026-11-20", err)
            self.assertEqual(len(err.strip().split("\n")), 1, err)
            self.assertEqual(self.tool("actions", "--all-dates")[0], 0, "not read when there is no default window")

    def test_frontmatter_date_is_used_when_the_filename_has_none(self):
        self.write("knowledge/leadership/offsite.md", "---\ndate: 2026-04-10\n---\n- [ ] book venue\n")
        result = self.json("actions", "--since", "2026-04-09", "--until", "2026-04-11")
        self.assertEqual([item["text"] for item in result["items"]], ["book venue"])

    def test_bad_date_is_a_usage_error(self):
        code, _out, _err = self.tool("actions", "--since", "last tuesday")
        self.assertEqual(code, 64)

    def test_works_without_an_index(self):
        self.assertFalse(self.path(".pka/knowledge.db").exists())
        self.assertEqual(self.tool("actions", "--all-dates")[0], 0)


if __name__ == "__main__":
    unittest.main()
