"""Phase 3: the pointer layer opt-in, `moc add-link`, `post-route` and `log`."""
from __future__ import annotations

import os
import shutil
import subprocess
import unittest

import support

TRAILER = "Co-Authored-By: Claude <noreply@anthropic.com>"
HEADER = "| Topic | Entities | Files |\n|---|---|---|\n"


def note(lines, body="body\n"):
    return "---\n" + "\n".join(lines) + "\n---\n\n" + body


class Plain(support.ToolsCase):
    """A plain-markdown vault (no .obsidian/)."""

    def setUp(self):
        super().setUp()
        shutil.rmtree(str(self.path("knowledge/.obsidian")))


class OptIn(Plain):
    def test_no_moc_is_created_without_obsidian(self):
        self.write("knowledge/planning/2026-06-01-roadmap.md", note(["topic: roadmap-review", "tags: [ai]"]))
        before = self.snapshot()
        result = self.json("pointers", "add", "knowledge/planning/2026-06-01-roadmap.md")
        self.assertEqual([(m["moc"], m["action"]) for m in result["mocs"]],
                         [("knowledge/planning/_MOC.md", "no-moc"), ("knowledge/AI/_MOC.md", "appended")])
        after = self.snapshot()
        self.assertFalse(self.path("knowledge/planning/_MOC.md").exists())
        self.assertEqual(self.changed(before, after), ["knowledge/AI/_MOC.md"])   # the existing MOC got the row

    def test_text_output_says_how_to_opt_in(self):
        self.write("knowledge/planning/x.md", "x\n")
        out = self.ok("pointers", "add", "knowledge/planning/x.md")
        self.assertIn("pointers init", out)

    def test_init_creates_stubs_only_where_missing(self):
        before_ai = self.read("knowledge/AI/_MOC.md")
        result = self.json("pointers", "init")
        self.assertIn("knowledge/lab-notebook/_MOC.md", result["created"])
        self.assertIn("knowledge/AI/_MOC.md", result["already_present"])
        self.assertEqual(self.read("knowledge/AI/_MOC.md"), before_ai)
        stub = self.text("knowledge/lab-notebook/_MOC.md")
        self.assertTrue(stub.endswith("| Topic | Entities | Files |\n|---|---|---|\n"))
        self.ok("pointers", "add", "knowledge/lab-notebook/2026-04-22.md")
        self.assertTrue(self.text("knowledge/lab-notebook/_MOC.md").endswith(
            "|---|---|---|\n| 2026-04-22 |  | [[lab-notebook/2026-04-22]] |\n"))
        self.assertEqual(self.json("pointers", "init")["created"], [])          # idempotent

    def test_init_named_folders_and_capture_directories(self):
        self.write("knowledge/meetings-raw/2026-01-05_sync/meeting.json", "{}\n")
        result = self.json("pointers", "init", "knowledge/reference")
        self.assertEqual(result["created"], ["knowledge/reference/_MOC.md"])
        self.write("knowledge/2026-01-06_sync/meeting.json", "{}\n")
        result = self.json("pointers", "init")
        self.assertIn("knowledge/meetings-raw/_MOC.md", result["created"])
        self.assertNotIn("knowledge/2026-01-06_sync/_MOC.md", result["created"])   # a capture directory
        self.assertFalse(self.path("knowledge/2026-01-06_sync/_MOC.md").exists())

    def test_create_flag_and_explicit_moc(self):
        self.write("knowledge/planning/x.md", "x\n")
        self.ok("pointers", "add", "knowledge/planning/x.md", "--create-moc")
        self.assertTrue(self.path("knowledge/planning/_MOC.md").is_file())
        self.write("knowledge/other/y.md", "y\n")
        self.ok("pointers", "add", "knowledge/other/y.md", "--moc", "knowledge/extra/_MOC.md")
        self.assertTrue(self.path("knowledge/extra/_MOC.md").is_file())
        self.assertFalse(self.path("knowledge/other/_MOC.md").exists())

    def test_no_create_flag_in_an_obsidian_vault(self):
        os.mkdir(str(self.path("knowledge/.obsidian")))
        self.write("knowledge/planning/x.md", "x\n")
        result = self.json("pointers", "add", "knowledge/planning/x.md", "--no-create-moc")
        self.assertEqual(result["mocs"][0]["action"], "no-moc")
        self.assertFalse(self.path("knowledge/planning/_MOC.md").exists())


class MocLink(support.ToolsCase):
    def lines(self, rel):
        return support.split_lines(self.text(rel))

    def test_appends_to_the_files_section_and_is_idempotent(self):
        rel = "knowledge/AI/_MOC.md"
        before = self.lines(rel)
        self.write("knowledge/AI/new-brief.md", "x\n")
        result = self.json("moc", "add-link", "knowledge/AI/new-brief.md")
        self.assertEqual((result["moc"], result["action"]), (rel, "added"))
        after = self.lines(rel)
        index = before.index("- [[AI/Vendor landscape, 2026]]\n")
        self.assertEqual(after, before[:index + 1] + ["- [[AI/new-brief]]\n"] + before[index + 1:])
        self.assertEqual(self.json("moc", "add-link", "knowledge/AI/new-brief.md")["action"], "noop")
        self.assertEqual(self.lines(rel), after)

    def test_a_link_in_the_prose_counts_but_a_pointer_row_does_not(self):
        rel = "knowledge/AI/_MOC.md"
        # ai-adoption-research is listed under ## Files already
        self.assertEqual(self.json("moc", "add-link", "knowledge/AI/ai-adoption-research.md")["action"], "noop")
        # a note named only in a pointer row and in inline code still gets a bullet
        self.write("knowledge/AI/proposal.md", "x\n")
        moc = self.text(rel).replace("[[AI/northwind/northwind_partnership_proposal\\|the proposal]]",
                                     "[[AI/proposal\\|the proposal]]")
        moc += "\n`[[AI/proposal]]` in code does not count\n"
        self.write(rel, moc)
        self.assertEqual(self.json("moc", "add-link", "knowledge/AI/proposal.md")["action"], "added")

    def test_unsorted_section_when_there_is_no_files_section(self):
        self.write("knowledge/planning/_MOC.md", "# Planning\n\n## Themes\n- [[planning/a]]")
        self.write("knowledge/planning/b.md", "x\n")
        self.ok("moc", "add-link", "knowledge/planning/b.md")
        self.assertEqual(self.text("knowledge/planning/_MOC.md"),
                         "# Planning\n\n## Themes\n- [[planning/a]]\n\n## Unsorted\n- [[planning/b]]\n")
        self.write("knowledge/planning/c.md", "x\n")
        self.ok("moc", "add-link", "knowledge/planning/c.md")
        self.assertTrue(self.text("knowledge/planning/_MOC.md").endswith("## Unsorted\n- [[planning/b]]\n- [[planning/c]]\n"))

    def test_named_section(self):
        self.write("knowledge/planning/_MOC.md", "# Planning\n\n## Themes\n- [[planning/a]]\n\n## Files\n- [[planning/z]]\n")
        self.write("knowledge/planning/b.md", "x\n")
        self.ok("moc", "add-link", "knowledge/planning/b.md", "--section", "Themes")
        self.assertEqual(self.text("knowledge/planning/_MOC.md"),
                         "# Planning\n\n## Themes\n- [[planning/a]]\n- [[planning/b]]\n\n## Files\n- [[planning/z]]\n")
        code, _out, err = self.tool("moc", "add-link", "knowledge/planning/b.md", "--section", "Nope")
        self.assertEqual(code, 0)          # already linked: nothing to do, no error
        self.write("knowledge/planning/c.md", "x\n")
        code, _out, err = self.tool("moc", "add-link", "knowledge/planning/c.md", "--section", "Nope")
        self.assertEqual(code, 64)
        self.assertIn("no `## Nope` heading", err)

    def test_nearest_moc_then_the_domain_moc_then_a_new_one(self):
        # AI/northwind/ has no MOC: the link goes to the domain's MOC
        result = self.json("moc", "add-link", "knowledge/AI/northwind/northwind_partnership_proposal.md")
        self.assertEqual((result["moc"], result["action"]), ("knowledge/AI/_MOC.md", "added"))
        # once the subfolder has its own MOC, that one is used
        self.write("knowledge/AI/northwind/_MOC.md", "# Northwind\n\n## Files\n")
        result = self.json("moc", "add-link", "knowledge/AI/northwind/2026-04-23-joint-partnership-meeting.md")
        self.assertEqual(result["moc"], "knowledge/AI/northwind/_MOC.md")
        self.assertEqual(self.text("knowledge/AI/northwind/_MOC.md"),
                         "# Northwind\n\n## Files\n- [[AI/northwind/2026-04-23-joint-partnership-meeting]]\n")
        # a domain with no MOC at all gets one (Obsidian vault)
        result = self.json("moc", "add-link", "knowledge/lab-notebook/2026-04-22.md")
        self.assertEqual((result["moc"], result["action"]), ("knowledge/lab-notebook/_MOC.md", "created-moc"))
        self.assertTrue(self.text("knowledge/lab-notebook/_MOC.md").endswith("## Files\n- [[lab-notebook/2026-04-22]]\n"))

    def test_crlf_moc_and_nearest_moc(self):
        self.write("knowledge/leadership/sub/2026-06-01-x.md", "x\n")
        result = self.json("moc", "add-link", "knowledge/leadership/sub/2026-06-01-x.md")
        self.assertEqual(result["moc"], "knowledge/leadership/_MOC.md")
        data = self.read("knowledge/leadership/_MOC.md")
        self.assertIn(b"- [[leadership/2026-04-22-slt-meeting]]\r\n- [[leadership/sub/2026-06-01-x]]\r\n", data)
        self.assertEqual(data.count(b"\n"), data.count(b"\r\n"))

    def test_skips(self):
        self.write("knowledge/planning/_MOC.md", "# P\n\n```\nopen fence\n")
        self.write("knowledge/planning/b.md", "x\n")
        result = self.json("moc", "add-link", "knowledge/planning/b.md")
        self.assertEqual(result["action"], "skipped")
        self.write("knowledge/planning/C# notes.md", "x\n")
        self.assertIn("wikilink cannot express",
                      self.json("moc", "add-link", "knowledge/planning/C# notes.md")["problem"])


class PostRoute(support.ToolsCase):
    """In a hybrid monorepo with an index: the whole pipeline."""

    def setUp(self):
        super().setUp()
        self.git(self.ws, "init", "-q", "-b", "main")
        self.write(".gitignore", "knowledge/\nprojects/\n")
        self.write(".meta", '{"projects": {}}\n')
        self.repo = self.init_child_repo("knowledge")
        self.ok("db", "init")
        self.ok("index")

    def head(self, repo=None):
        return self.git(repo or self.repo, "rev-parse", "HEAD").strip()

    def file_note(self, rel, text):
        self.write(rel, text)
        return self.json("post-route", rel, "--role", "Meetings")

    def steps(self, result):
        return {step["step"]: step["action"] for step in result["steps"]}

    def test_a_meeting_note_gets_everything_in_one_commit(self):
        rel = "knowledge/leadership/2026-06-02-roadmap-review.md"
        self.write("knowledge/AI/owner-draft.md", "the owner's work in progress\n")
        result = self.file_note(rel, note(["type: meeting", "topic: roadmap-review", "attendees: [priya]",
                                           "tags: [meeting, ai]"], "# Roadmap\n- [ ] Draft plan @Sam\n"))
        self.assertEqual(self.steps(result), {"frontmatter": "merged", "moc-link": "added", "pointers": "written",
                                              "index": "indexed", "commit": "committed"})
        names = sorted(self.git(self.repo, "show", "--name-only", "--format=", "HEAD").split())
        self.assertEqual(names, ["AI/_MOC.md", "leadership/2026-06-02-roadmap-review.md", "leadership/_MOC.md"])
        message = self.git(self.repo, "log", "-1", "--format=%B").strip().splitlines()
        self.assertEqual((message[0], message[-1]),
                         ("Meetings: Route 2026-06-02-roadmap-review.md to leadership/", TRAILER))
        self.assertEqual(self.git(self.repo, "status", "--porcelain").strip(), "?? AI/owner-draft.md")
        text = self.text(rel)
        self.assertIn("date: 2026-06-02\n", text)
        self.assertIn("tags: [meeting, ai, leadership]\n", text)
        self.assertIn("- [[leadership/2026-06-02-roadmap-review]]", self.text("knowledge/leadership/_MOC.md"))
        hits = self.json("search", "roadmap-review")["results"]
        self.assertTrue(hits and hits[0]["is_pointer"])
        # second run: nothing changes, no commit
        head = self.head()
        snap = self.snapshot()
        again = self.json("post-route", rel, "--role", "Meetings")
        self.assertEqual(self.steps(again)["commit"], "no-changes")
        self.assertEqual(self.head(), head)
        self.assertEqual(self.snapshot(), snap)

    def test_same_result_as_a_librarian_route(self):
        """Phase 3 acceptance: a note filed by pka-meetings and one routed by
        the librarian end up the same, apart from the commit prefix."""
        text = note(["type: meeting", "topic: roadmap-review", "tags: [meeting]"], "x\n")
        self.write("knowledge/leadership/2026-06-02-a.md", text)
        self.write("knowledge/leadership/2026-06-02-b.md", text)
        a = self.json("post-route", "knowledge/leadership/2026-06-02-a.md", "--role", "Meetings")
        b = self.json("post-route", "knowledge/leadership/2026-06-02-b.md")
        self.assertEqual(self.steps(a), self.steps(b))
        self.assertEqual(self.text("knowledge/leadership/2026-06-02-a.md"), self.text("knowledge/leadership/2026-06-02-b.md"))
        subjects = self.git(self.repo, "log", "-2", "--format=%s").splitlines()
        self.assertEqual(subjects, ["Librarian: Route 2026-06-02-b.md to leadership/",
                                    "Meetings: Route 2026-06-02-a.md to leadership/"])

    def test_moved_note_commits_the_old_location_too(self):
        old = "knowledge/AI/ai-adoption-research.md"
        new = "knowledge/AI/research/ai-adoption-research.md"
        os.makedirs(str(self.path("knowledge/AI/research")))
        os.rename(str(self.path(old)), str(self.path(new)))
        self.ok("pointers", "rename", old, new)
        result = self.json("post-route", new, "--also", old, "--also", "knowledge/AI/_MOC.md",
                           "-m", "Librarian: Move ai-adoption-research.md to AI/research/")
        self.assertEqual(self.steps(result)["commit"], "committed")
        self.assertEqual(self.git(self.repo, "status", "--porcelain").strip(), "")
        self.assertEqual(self.json("search", "Body text")["results"][0]["path"], new)

    def test_failed_commit_exits_1_after_the_other_steps(self):
        hook = self.repo / ".git" / "hooks" / "pre-commit"
        hook.parent.mkdir(exist_ok=True)
        hook.write_text("#!/bin/sh\necho no >&2\nexit 1\n")
        os.chmod(str(hook), 0o755)
        self.write("knowledge/AI/x.md", "x\n")
        code, out, err = self.tool("post-route", "knowledge/AI/x.md", "--json")
        self.assertEqual(code, 1, err)
        import json
        result = json.loads(out)
        steps = {step["step"]: step for step in result["steps"]}
        self.assertEqual(steps["commit"]["action"], "failed")
        self.assertEqual(steps["pointers"]["action"], "written")
        self.assertIn("- [[AI/x]]", self.text("knowledge/AI/_MOC.md"))

    def test_no_commit_and_dry_run(self):
        self.write("knowledge/AI/x.md", "x\n")
        snap = self.snapshot()
        head = self.head()
        result = self.json("post-route", "knowledge/AI/x.md", "--dry-run")
        self.assertEqual(self.snapshot(), snap)
        self.assertEqual(self.steps(result)["commit"], "dry-run")
        result = self.json("post-route", "knowledge/AI/x.md", "--no-commit")
        self.assertEqual(self.steps(result)["commit"], "not-requested")
        self.assertEqual(self.head(), head)

    def test_project_file_is_indexed_and_committed_without_vault_steps(self):
        project = self.init_child_repo("projects/orion")
        self.write("projects/orion/notes.md", "orion planning notes\n")
        result = self.json("post-route", "projects/orion/notes.md", "-m", "Librarian: Add notes.md to orion")
        self.assertEqual(self.steps(result), {"frontmatter": "not-applicable", "moc-link": "not-applicable",
                                              "pointers": "not-applicable", "index": "indexed", "commit": "committed"})
        self.assertEqual(self.git(project, "log", "-1", "--format=%s").strip(), "Librarian: Add notes.md to orion")

    def test_refusals(self):
        self.write("knowledge/leadership/2026-01-05_sync/meeting.json", "{}\n")
        self.write("knowledge/leadership/2026-01-05_sync/narrative.md", "n\n")
        for args in (("post-route", "knowledge/leadership/2026-01-05_sync/narrative.md"),
                     ("post-route", "knowledge/AI/_MOC.md"),
                     ("post-route", ".pka/session-log.md"),
                     ("post-route", "knowledge/AI/nope.md"),
                     ("post-route", "knowledge/AI/ai-adoption-research.md", "-m", "two\nlines")):
            code, _out, err = self.tool(*args)
            self.assertEqual(code, 64, (args, err))
        code, _out, err = self.tool("post-route", "knowledge/leadership/2026-01-05_sync/narrative.md")
        self.assertIn("capture directory", err)


class PostRoutePlain(Plain):
    def test_plain_vault_without_git_or_index(self):
        self.write("knowledge/planning/x.md", "x\n")
        result = self.json("post-route", "knowledge/planning/x.md")
        steps = {step["step"]: (step["action"], step["detail"]) for step in result["steps"]}
        self.assertEqual(steps["frontmatter"][0], "not-applicable")
        self.assertEqual(steps["moc-link"][0], "not-applicable")
        self.assertEqual(steps["pointers"][0], "no MOC, pointer row not written")
        self.assertEqual(steps["index"][0], "not-applicable")
        self.assertEqual(steps["commit"], ("not-applicable", "not a hybrid monorepo"))
        self.assertEqual(self.text("knowledge/planning/x.md"), "x\n")
        self.assertFalse(self.path("knowledge/planning/_MOC.md").exists())


class SessionLog(support.ToolsCase):
    def log(self):
        return self.text(".pka/session-log.md")

    def test_add_writes_one_well_formed_line(self):
        before = self.log()
        result = self.json("log", "add", "--role", "pka-meetings", "--summary", "Filed SLT sync → leadership/",
                           "--open", "Send Priya the doc | by Friday", "--at", "2026-11-17 09:30")
        self.assertEqual(result["entry"],
                         "## 2026-11-17 09:30 | pka-meetings | Filed SLT sync → leadership/ | "
                         "Send Priya the doc \\| by Friday | —")
        self.assertEqual(self.log(), before + result["entry"] + "\n")
        opened = self.json("log", "open")["open"]
        self.assertEqual(opened[0]["open"], "Send Priya the doc | by Friday")
        self.assertEqual(self.json("log", "check")["malformed"], [])

    def test_whitespace_is_flattened(self):
        result = self.json("log", "add", "--role", "librarian", "--summary", "two\nlines  here", "--at", "2026-11-17 09:30")
        self.assertEqual(result["entry"], "## 2026-11-17 09:30 | librarian | two lines here | — | —")

    def test_crlf_and_missing_final_newline_are_respected(self):
        self.write(".pka/session-log.md", b"# Session log\r\n\r\n## 2026-11-01 | bootstrap | init | \xe2\x80\x94 | \xe2\x80\x94")
        self.ok("log", "add", "--role", "librarian", "--summary", "s", "--at", "2026-11-17 09:30")
        self.assertEqual(self.read(".pka/session-log.md"),
                         "# Session log\r\n\r\n## 2026-11-01 | bootstrap | init | — | —\r\n"
                         "## 2026-11-17 09:30 | librarian | s | — | —\r\n".encode("utf-8"))

    def test_open_lists_newest_first_and_ignores_empty(self):
        for at, open_ in (("2026-11-10 09:00", "older thread"), ("2026-11-11 09:00", ""), ("2026-11-12 09:00", "newer thread")):
            self.ok("log", "add", "--role", "r", "--summary", "s", "--open", open_, "--at", at)
        self.assertEqual([item["open"] for item in self.json("log", "open")["open"]], ["newer thread", "older thread"])
        self.assertEqual([item["open"] for item in self.json("log", "open", "--last", "1")["open"]], ["newer thread"])

    def test_check_reports_without_rewriting(self):
        bad = ("## 2026-11-01 | bootstrap | PKA initialized | — | —\n"
               "## 2026-04-05 HH:MM | pka-wiki | Ingested | 3 claims | —\n"
               "## 2026-11-02 | owner | Updated owner profile\n")
        self.write(".pka/session-log.md", bad)
        result = self.json("log", "check")
        self.assertEqual([item["line"] for item in result["malformed"]], [2, 3])
        self.assertEqual(self.log(), bad)
        self.assertEqual(self.tool("log", "check", "--strict")[0], 1)

    def test_usage_errors(self):
        for args in (("log", "add", "--role", "r", "--summary", "s", "--at", "yesterday"),
                     ("log", "add", "--role", " ", "--summary", "s"),
                     ("log", "open", "--last", "0")):
            self.assertEqual(self.tool(*args)[0], 64, args)



class ReviewFindings(support.ToolsCase):
    """Regression tests for the review of the first Phase 3 build."""

    def hybrid(self):
        self.git(self.ws, "init", "-q", "-b", "main")
        self.write(".gitignore", "knowledge/\nprojects/\n")
        self.write(".meta", '{"projects": {}}\n')
        self.repo = self.init_child_repo("knowledge")

    def status(self):
        return self.git(self.repo, "status", "--porcelain").strip()

    # high: frontmatter written into non-markdown files
    def test_frontmatter_only_for_markdown(self):
        for rel, data in (("knowledge/AI/scores.csv", "name,score\nPriya,3\n"),
                          ("knowledge/AI/board.canvas", '{"nodes": []}\n'),
                          ("knowledge/reference/report.pdf.txt", None)):
            if data is not None:
                self.write(rel, data)
            before = self.read(rel)
            result = self.json("post-route", rel)
            steps = {step["step"]: step["action"] for step in result["steps"]}
            self.assertEqual(steps["frontmatter"], "not-applicable", rel)
            self.assertEqual(self.read(rel), before, rel)

    # medium: exit 64 after files were already edited
    def test_bad_section_or_topic_touches_nothing(self):
        self.write("knowledge/reference/orion.md", "x\n")
        self.write("knowledge/AI/orion2.md", "x\n")
        before = self.snapshot()
        for args in (("post-route", "knowledge/reference/orion.md", "--section", "Links"),
                     ("post-route", "knowledge/AI/orion2.md", "--section", "Links"),
                     ("post-route", "knowledge/AI/orion2.md", "--topic", "!!!")):
            code, _out, err = self.tool(*args)
            self.assertEqual(code, 64, (args, err))
        self.assertEqual(self.snapshot(), before)

    def test_bad_also_touches_nothing(self):
        self.hybrid()
        self.write("knowledge/AI/northwind-a.md", "x\n")
        before = self.snapshot()
        for also in ("knowledge/reference", "knowledge/AI/gone.md", ".meta"):
            code, _out, err = self.tool("post-route", "knowledge/AI/northwind-a.md", "--also", also)
            self.assertEqual(code, 64, (also, err))
        self.assertEqual(self.snapshot(), before)

    def test_a_later_run_commits_what_an_earlier_run_left(self):
        self.hybrid()
        self.write("knowledge/AI/northwind-a.md", "x\n")
        self.ok("post-route", "knowledge/AI/northwind-a.md", "--no-commit")
        self.assertIn("M AI/_MOC.md", self.status().splitlines()[0] + "\n" + self.status())
        self.ok("post-route", "knowledge/AI/northwind-a.md")
        self.assertEqual(self.status(), "")
        names = sorted(self.git(self.repo, "show", "--name-only", "--format=", "HEAD").split())
        self.assertEqual(names, ["AI/_MOC.md", "AI/northwind-a.md"])

    def test_rerun_after_a_move_is_a_no_op(self):
        self.hybrid()
        os.rename(str(self.path("knowledge/AI/ai-adoption-research.md")), str(self.path("knowledge/AI/moved.md")))
        args = ("post-route", "knowledge/AI/moved.md", "--also", "knowledge/AI/ai-adoption-research.md")
        self.ok(*args)
        head = self.git(self.repo, "rev-parse", "HEAD")
        result = self.json(*args)
        self.assertEqual(result["notes"], ["knowledge/AI/ai-adoption-research.md: already committed as removed"])
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), head)

    # medium: moc add-link
    def test_bullet_not_hidden_in_a_comment_or_under_a_subsection(self):
        self.write("knowledge/planning/_MOC.md", "## Files\n- [[planning/a]]\n<!--\n## Old\n-->\n")
        self.write("knowledge/planning/b.md", "x\n")
        self.ok("moc", "add-link", "knowledge/planning/b.md")
        self.assertEqual(self.text("knowledge/planning/_MOC.md"),
                         "## Files\n- [[planning/a]]\n- [[planning/b]]\n<!--\n## Old\n-->\n")
        self.write("knowledge/planning/_MOC.md", "## Files\n- [[planning/a]]\n\n### Archived\n- [[planning/z]]\n")
        self.write("knowledge/planning/c.md", "x\n")
        self.ok("moc", "add-link", "knowledge/planning/c.md")
        self.assertEqual(self.text("knowledge/planning/_MOC.md"),
                         "## Files\n- [[planning/a]]\n- [[planning/c]]\n\n### Archived\n- [[planning/z]]\n")

    def test_setext_heading_and_bom(self):
        self.write("knowledge/planning/_MOC.md", "## Files\n- [[planning/a]]\n\nOther\n-----\ntext\n")
        self.write("knowledge/planning/b.md", "x\n")
        self.ok("moc", "add-link", "knowledge/planning/b.md")
        self.assertEqual(self.text("knowledge/planning/_MOC.md"),
                         "## Files\n- [[planning/a]]\n- [[planning/b]]\n\nOther\n-----\ntext\n")
        self.write("knowledge/planning/_MOC.md", "﻿## Files\n- [[planning/a]]\n")
        self.write("knowledge/planning/c.md", "x\n")
        self.ok("moc", "add-link", "knowledge/planning/c.md")
        self.assertEqual(self.text("knowledge/planning/_MOC.md"), "﻿## Files\n- [[planning/a]]\n- [[planning/c]]\n")

    def test_short_name_and_markdown_links_count(self):
        self.write("knowledge/Orion/plan.md", "x\n")
        self.write("knowledge/Orion/_MOC.md", "## Files\n- [[plan]]\n")
        self.assertEqual(self.json("moc", "add-link", "knowledge/Orion/plan.md")["action"], "noop")
        self.write("knowledge/Orion/_MOC.md", "## Files\n- [Plan](plan.md)\n")
        self.assertEqual(self.json("moc", "add-link", "knowledge/Orion/plan.md")["action"], "noop")
        # a bare name that two files share is ambiguous: it does not count
        self.write("knowledge/AI/plan.md", "y\n")
        self.write("knowledge/Orion/_MOC.md", "## Files\n- [[plan]]\n")
        self.assertEqual(self.json("moc", "add-link", "knowledge/Orion/plan.md")["action"], "added")
        # a link only inside a comment does not count
        self.write("knowledge/Orion/_MOC.md", "## Files\n<!--\n- [[Orion/plan]]\n-->\n")
        self.assertEqual(self.json("moc", "add-link", "knowledge/Orion/plan.md")["action"], "added")

    def test_init_refuses_captures_dot_folders_and_ignored(self):
        self.write("knowledge/leadership/2026-05-01-orion-sync/meeting.json", "{}\n")
        os.makedirs(str(self.path("knowledge/.trash")))
        for folder in ("knowledge/leadership/2026-05-01-orion-sync", "knowledge/.trash"):
            code, _out, _err = self.tool("pointers", "init", folder)
            self.assertEqual(code, 64, folder)
        self.assertFalse(self.path("knowledge/leadership/2026-05-01-orion-sync/_MOC.md").exists())
        self.assertFalse(self.path("knowledge/.trash/_MOC.md").exists())

    # low: rename --notes
    def test_rename_notes_edge_cases(self):
        self.write("knowledge/AI/a.md", "<!--\n[[AI/foo]]\n-->\n[[ AI/foo ]] [[./AI/foo|F]] [[AI/foo-bar]]\n")
        self.write("knowledge/AI/b.md", "```\nopen fence [[AI/foo]]\n")
        self.write("knowledge/AI/c.md", "[[AI/foo]]\n")
        os.chmod(str(self.path("knowledge/AI/c.md")), 0o444)
        result = self.json("pointers", "rename", "AI/foo", "AI/bar", "--notes")
        self.assertEqual(self.text("knowledge/AI/a.md"),
                         "<!--\n[[AI/foo]]\n-->\n[[ AI/bar ]] [[./AI/bar|F]] [[AI/foo-bar]]\n")
        self.assertEqual(self.text("knowledge/AI/b.md"), "```\nopen fence [[AI/foo]]\n")
        reasons = result["skip_reasons"]
        self.assertIn("never closed", reasons["knowledge/AI/b.md"])
        if not (hasattr(os, "geteuid") and os.geteuid() == 0):
            self.assertEqual(reasons["knowledge/AI/c.md"], "read-only")
            self.assertEqual(self.text("knowledge/AI/c.md"), "[[AI/foo]]\n")

    # low: session log
    def test_log_bom_and_strict_at(self):
        self.write(".pka/session-log.md", "﻿## 2026-11-01 09:00 | r | s | Orion open | —\n")
        self.assertEqual([item["open"] for item in self.json("log", "open")["open"]], ["Orion open"])
        self.assertEqual(self.json("log", "check")["entries"], 1)
        for at in ("2026-99-99 77:77", "2026-11-17"):
            self.assertEqual(self.tool("log", "add", "--role", "r", "--summary", "s", "--at", at)[0], 64, at)


class RefreshSectionValidation(support.ToolsCase):
    fixture = False

    def test_unknown_section_is_an_error_listing_the_choices(self):
        import subprocess
        import sys
        (self.ws / ".pka" / "roles").mkdir(parents=True)
        self.write(".pka/roles/librarian.md", "# @librarian\n\n## Output Conventions\n- x\n")
        proc = subprocess.run([sys.executable, str(self.path(".pka/upgrade-roles.py")), "--workspace", str(self.ws),
                               "--refresh", "--refresh-section", "librarian.md:## Output Conventions"],
                              env=self.env, capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0)
        self.assertIn("is not a seeded section", proc.stdout + proc.stderr)
        self.assertIn("## Pointer-row maintenance", proc.stdout + proc.stderr)

if __name__ == "__main__":
    unittest.main()
