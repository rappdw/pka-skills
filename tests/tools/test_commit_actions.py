"""`pka-tools commit` (path-scoped, child repos only) and `pka-tools actions`."""
from __future__ import annotations

import os
import unittest

import support

TRAILER = "Co-Authored-By: Claude <noreply@anthropic.com>"


class Commit(support.ToolsCase):
    def setUp(self):
        super().setUp()
        self.repo = self.init_child_repo("knowledge")

    def head(self):
        return self.git(self.repo, "rev-parse", "HEAD").strip()

    def test_commits_exactly_the_named_paths(self):
        # the owner's own work in progress: one modified, one staged, one untracked
        self.write("knowledge/AI/ai-adoption-research.md", "owner is editing this\n")
        self.write("knowledge/AI/staged-by-owner.md", "staged\n")
        self.git(self.repo, "add", "AI/staged-by-owner.md")
        self.write("knowledge/AI/untracked.md", "untracked\n")
        # the routing's files
        self.write("knowledge/leadership/2026-06-01-new-meeting.md", "routed\n")
        self.write("knowledge/leadership/_MOC.md", self.text("knowledge/leadership/_MOC.md") + "- added\r\n")
        result = self.json("commit", "-m", "Librarian: Route 2026-06-01-new-meeting.md to leadership/", "--",
                           "knowledge/leadership/2026-06-01-new-meeting.md", "knowledge/leadership/_MOC.md")
        self.assertTrue(result["committed"])
        self.assertEqual(result["repo"], "knowledge")
        self.assertEqual(result["sha"], self.head())
        names = self.git(self.repo, "show", "--name-only", "--format=", "HEAD").split()
        self.assertEqual(sorted(names), ["leadership/2026-06-01-new-meeting.md", "leadership/_MOC.md"])
        message = self.git(self.repo, "log", "-1", "--format=%B")
        self.assertTrue(message.startswith("Librarian: Route 2026-06-01-new-meeting.md to leadership/\n\n"))
        self.assertEqual(message.strip().splitlines()[-1], TRAILER)
        status = self.git(self.repo, "status", "--porcelain").splitlines()
        self.assertEqual(sorted(status), [" M AI/ai-adoption-research.md", "?? AI/untracked.md", "A  AI/staged-by-owner.md"])

    def test_body_goes_between_subject_and_trailer(self):
        self.write("knowledge/AI/x.md", "x\n")
        self.ok("commit", "-m", "Librarian: Route x.md to AI/", "--body", "Side effects: none.", "knowledge/AI/x.md")
        lines = self.git(self.repo, "log", "-1", "--format=%B").strip().splitlines()
        self.assertEqual(lines, ["Librarian: Route x.md to AI/", "", "Side effects: none.", "", TRAILER])

    def test_no_changes_means_no_commit(self):
        before = self.head()
        result = self.json("commit", "-m", "Librarian: nothing", "knowledge/AI/ai-adoption-research.md")
        self.assertEqual((result["committed"], result["reason"]), (False, "no-changes"))
        self.assertEqual(self.head(), before)

    def test_a_deleted_path_can_be_committed(self):
        self.path("knowledge/AI/northwind/northwind_partnership_proposal.md").unlink()
        result = self.json("commit", "-m", "Librarian: Remove proposal",
                           "knowledge/AI/northwind/northwind_partnership_proposal.md")
        self.assertTrue(result["committed"])
        self.assertEqual(self.git(self.repo, "status", "--porcelain").strip(), "")

    def test_root_repo_is_never_committed(self):
        self.git(self.ws, "init", "-q", "-b", "main")
        self.write(".gitignore", "knowledge/\n")
        result = self.json("commit", "-m", "Should not happen", "CLAUDE.md")
        self.assertEqual((result["committed"], result["reason"]), (False, "root-repo"))
        self.assertEqual(self.git(self.ws, "status", "--porcelain", "CLAUDE.md").strip(), "?? CLAUDE.md")
        staged = self.json("commit", "--stage-only", "CLAUDE.md")
        self.assertEqual((staged["committed"], staged["reason"]), (False, "staged"))
        self.assertEqual(self.git(self.ws, "status", "--porcelain", "CLAUDE.md").strip(), "A  CLAUDE.md")
        code, out, _err = self.git_rc(self.ws, "rev-parse", "--verify", "HEAD")
        self.assertNotEqual(code, 0, "the root repo must still have no commit")

    def git_rc(self, repo, *args):
        import subprocess
        proc = subprocess.run(["git", "-C", str(repo)] + list(args), env=self.env,
                              stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        return proc.returncode, proc.stdout, proc.stderr

    def test_no_repository_is_a_reported_no_op(self):
        result = self.json("commit", "-m", "x", "projects/orion/CLAUDE.md")
        self.assertEqual((result["committed"], result["reason"]), (False, "no-repo"))

    def test_paths_in_two_repositories_are_refused(self):
        self.init_child_repo("projects/orion")
        code, _out, err = self.tool("commit", "-m", "x", "knowledge/AI/x.md", "projects/orion/CLAUDE.md")
        self.assertEqual(code, 64)
        self.assertIn("more than one repository", err)

    def test_failed_commit_exits_1_and_leaves_the_files_staged(self):
        hook = self.repo / ".git" / "hooks" / "pre-commit"
        hook.parent.mkdir(exist_ok=True)
        hook.write_text("#!/bin/sh\necho 'hook says no' >&2\nexit 1\n")
        os.chmod(str(hook), 0o755)
        before = self.head()
        self.write("knowledge/AI/x.md", "x\n")
        code, _out, err = self.tool("commit", "-m", "Librarian: Route x.md to AI/", "knowledge/AI/x.md")
        self.assertEqual(code, 1)
        self.assertIn("git commit failed", err)
        self.assertIn("hook says no", err)
        self.assertEqual(self.head(), before)
        self.assertEqual(self.git(self.repo, "status", "--porcelain").strip(), "A  AI/x.md")

    def test_missing_identity_is_reported_not_swallowed(self):
        os.remove(self.env["GIT_CONFIG_GLOBAL"])
        self.env["GIT_CONFIG_GLOBAL"] = os.path.join(self.env["HOME"], "empty-gitconfig")
        open(self.env["GIT_CONFIG_GLOBAL"], "w").close()
        self.git(self.repo, "config", "user.useConfigOnly", "true")
        before = self.head()
        self.write("knowledge/AI/x.md", "x\n")
        code, _out, err = self.tool("commit", "-m", "Librarian: Route x.md to AI/", "knowledge/AI/x.md")
        self.assertEqual(code, 1)
        self.assertIn("identity", err)
        self.assertEqual(self.head(), before)

    def test_usage_errors(self):
        for args in (("commit", "-m", "two\nlines", "knowledge/AI/x.md"),
                     ("commit", "-m", "", "knowledge/AI/x.md"),
                     ("commit", "-m", "x"),
                     ("commit", "-m", "x", "../outside")):
            code, _out, _err = self.tool(*args)
            self.assertEqual(code, 64, args)


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

    def test_commit_through_the_link_is_a_child_repo_commit(self):
        self.git(self.real, "init", "-q", "-b", "main")
        self.git(self.real, "add", "-A")
        self.git(self.real, "commit", "-q", "-m", "baseline")
        self.write("knowledge/AI/x.md", "x\n")
        result = self.json("commit", "-m", "Librarian: Route x.md to AI/", "knowledge/AI/x.md")
        self.assertEqual((result["committed"], result["repo"], result["paths"]), (True, "knowledge", ["AI/x.md"]))
        self.assertEqual(self.git(self.real, "status", "--porcelain").strip(), "")


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
        import datetime
        today = datetime.date.today()
        recent = (today - datetime.timedelta(days=2)).isoformat()
        old = (today - datetime.timedelta(days=30)).isoformat()
        self.write("knowledge/leadership/%s-standup.md" % recent, "- [ ] recent item\n")
        self.write("knowledge/leadership/%s-standup.md" % old, "- [ ] old item\n")
        self.assertEqual([item["text"] for item in self.json("actions")["items"]], ["recent item"])

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
