"""The Obsidian mechanical retrofit, and the fixture-vault round trip."""
from __future__ import annotations

import os
import stat
import unittest

import support


def owned_change(name: str, removed, added) -> bool:
    """Is this line-level change one the tools are allowed to make?

    Allowed: pure insertions; a `tags:` line that gained an item; a pointer
    table row that gained entries; a final line that gained its newline.
    """
    if not removed:
        return True
    if len(removed) != 1 or not added:
        return False
    old = removed[0]
    new = added[0]
    old_body = old.rstrip("\r\n")
    new_body = new.rstrip("\r\n")
    if old_body == new_body and not old.endswith("\n"):
        return True                                        # only the missing newline was added
    if old_body.startswith("tags:") and new_body.startswith("tags:"):
        stem = old_body[: old_body.rfind("]")] if "]" in old_body else old_body
        return new_body.startswith(stem) and len(added) == 1
    if name.endswith("_MOC.md") and old_body.lstrip().startswith("|"):
        old_cells = [cell.strip() for cell in old_body.strip().strip("|").split(" | ")]
        new_cells = [cell.strip() for cell in new_body.strip().strip("|").split(" | ")]
        if len(old_cells) != len(new_cells) or old_cells[0] != new_cells[0]:
            return False
        return all(n == o or n.startswith(o) or o in ("—", "") for o, n in zip(old_cells, new_cells))
    return False


class Bootstrap(support.ToolsCase):
    def test_refuses_without_an_obsidian_vault(self):
        os.rename(str(self.path("knowledge/.obsidian")), str(self.path("knowledge/obsidian-off")))
        before = self.snapshot()
        code, _out, err = self.tool("obsidian", "bootstrap")
        self.assertEqual(code, 3)
        self.assertIn("No Obsidian vault detected", err)
        self.assertEqual(self.snapshot(), before)

    def test_summary_counts_and_skips(self):
        summary = self.json("obsidian", "bootstrap")
        self.assertEqual(summary["moc_already_present"], ["AI", "leadership"])
        self.assertEqual(summary["moc_created"],
                         ["(vault root)", "AI/northwind", "archived", "lab-notebook", "personnel", "reference"])
        self.assertEqual(summary["person_indexes_created"], ["personnel/robin-smith", "personnel/zoë-åkesson"])
        self.assertEqual(summary["person_indexes_already_present"], ["personnel/priya"])
        skipped = "\n".join(summary["skipped"])
        self.assertIn("leadership/2026-05-06-budget review.md: line 3: unquoted colon", skipped)
        self.assertIn("reference/latin1.md: not valid UTF-8", skipped)
        self.assertEqual(len(summary["skipped"]), 2)
        self.assertEqual(summary["warnings"],
                         ["lab-notebook/2026-04-23.md: tags are not a simple list; domain tag not added"])

    def test_existing_files_are_only_added_to(self):
        before = self.snapshot()
        self.ok("obsidian", "bootstrap")
        after = self.snapshot()
        for name in before:
            self.assertIn(name, after)
        untouched = [
            "knowledge/AI/_MOC.md", "knowledge/leadership/_MOC.md",       # existing MOCs are never edited
            "knowledge/personnel/priya/index.md",                          # existing person index
            "knowledge/leadership/2026-05-06-budget review.md",            # malformed frontmatter
            "knowledge/reference/latin1.md",                               # not UTF-8
            "knowledge/lab-notebook/2026-04-23.md",                        # scalar tags
            "knowledge/reference/report.pdf", "knowledge/reference/report.pdf.txt",
        ]
        for name in untouched:
            self.assertEqual(before[name], after[name], name)
        for name in self.changed(before, after):
            if name not in before:
                self.assertTrue(name.endswith("/_MOC.md") or name.endswith("/index.md"), name)
                continue
            for removed, added in support.removed_and_added(before[name], after[name]):
                self.assertTrue(owned_change(name, removed, added), "%s: %r -> %r" % (name, removed, added))

    def test_bodies_are_carried_through_byte_for_byte(self):
        before = self.snapshot()
        self.ok("obsidian", "bootstrap")
        after = self.snapshot()
        for name in ("knowledge/leadership/2026-04-22-slt-meeting.md",      # CRLF, no frontmatter
                     "knowledge/lab-notebook/2026-04-22.md",                # no final newline
                     "knowledge/AI/Vendor landscape, 2026.md",
                     "knowledge/AI/northwind/Übersicht – Zürich.md",
                     "knowledge/reference/code-fence.md"):
            self.assertTrue(after[name].endswith(before[name]), name)
            self.assertNotEqual(after[name], before[name], name)
        crlf = after["knowledge/leadership/2026-04-22-slt-meeting.md"]
        self.assertTrue(crlf.startswith(b"---\r\ntype: meeting\r\ndate: 2026-04-22\r\ntopic: slt-meeting\r\n"
                                        b"attendees: []\r\ntags: [meeting, leadership]\r\n---\r\n\r\n# SLT meeting\r\n"))
        self.assertEqual(crlf.count(b"\n"), crlf.count(b"\r\n"))

    def test_bom_stays_first_and_only_the_tags_line_changes(self):
        name = "knowledge/leadership/2026-04-29-slt-meeting.md"
        before = self.read(name)
        self.ok("obsidian", "bootstrap")
        after = self.read(name)
        self.assertTrue(after.startswith(b"\xef\xbb\xbf---\n"))
        self.assertEqual(after, before.replace(b"tags: [meeting]\n", b"tags: [meeting, leadership]\n"))

    def test_block_list_tags_comments_and_inline_comments_survive(self):
        self.ok("obsidian", "bootstrap")
        text = self.text("knowledge/AI/ai-adoption-research.md")
        self.assertIn("# a comment the owner left here\n", text)
        self.assertIn("tags:\n  - research\n  - strategy\n  - ai\n---\n", text)
        joint = self.text("knowledge/AI/northwind/2026-04-23-joint-partnership-meeting.md")
        self.assertIn("tags: [meeting, ai, leadership]   # inline comment\n", joint)   # already had `ai`

    def test_patterns(self):
        self.ok("obsidian", "bootstrap")
        self.assertTrue(self.text("knowledge/personnel/priya/2026-03-31-1-1-priya.md").startswith(
            '---\ntype: 1on1\ndate: 2026-03-31\nperson: "[[personnel/priya/index]]"\ntags: [1on1, personnel]\n---\n\n'))
        self.assertTrue(self.text("knowledge/personnel/zoë-åkesson/2026-05-01-1on1.md").startswith(
            '---\ntype: 1on1\ndate: 2026-05-01\nperson: "[[personnel/zoë-åkesson/index]]"\n'))
        self.assertTrue(self.text("knowledge/lab-notebook/2026-04-22.md").startswith(
            "---\ndate: 2026-04-22\ntags: [daily, lab-notebook]\n---\n\n"))
        self.assertTrue(self.text("knowledge/AI/Vendor landscape, 2026.md").startswith("---\ntags: [ai]\n---\n\n"))
        index = self.text("knowledge/personnel/zoë-åkesson/index.md")
        self.assertIn('name: "Zoë Åkesson"\n', index)
        self.assertIn("# Zoë Åkesson\n", index)
        self.assertIn("- [[personnel/zoë-åkesson/2026-05-01-1on1|2026-05-01-1on1]]\n", index)
        self.assertIn("name: Robin Smith\n", self.text("knowledge/personnel/robin-smith/index.md"))

    def test_moc_stub_lists_files_and_subdomains_but_not_people(self):
        self.ok("obsidian", "bootstrap")
        root = self.text("knowledge/_MOC.md")
        self.assertIn("- [[AI/_MOC|AI]]\n", root)
        self.assertIn("- [[personnel/_MOC|personnel]]\n", root)
        people = self.text("knowledge/personnel/_MOC.md")
        self.assertNotIn("Subdomains", people)
        sub = self.text("knowledge/AI/northwind/_MOC.md")
        self.assertIn("- [[AI/northwind/northwind_partnership_proposal|northwind_partnership_proposal]]\n", sub)
        self.assertFalse(self.path("knowledge/personnel/priya/_MOC.md").exists())

    def test_second_run_changes_nothing(self):
        self.ok("obsidian", "bootstrap")
        before = self.snapshot()
        summary = self.json("obsidian", "bootstrap")
        self.assertEqual(self.snapshot(), before)
        self.assertEqual(summary["touched"], [])

    def test_dry_run_reports_and_writes_nothing(self):
        before = self.snapshot()
        summary = self.json("obsidian", "bootstrap", "--dry-run")
        self.assertGreater(len(summary["touched"]), 10)
        self.assertEqual(self.snapshot(), before)

    def test_read_only_note_is_left_alone(self):
        name = "knowledge/AI/Vendor landscape, 2026.md"
        os.chmod(str(self.path(name)), stat.S_IRUSR | stat.S_IRGRP)
        if os.access(str(self.path(name)), os.W_OK):
            self.skipTest("running as a user for whom read-only files are writable")
        before = self.read(name)
        summary = self.json("obsidian", "bootstrap")
        self.assertEqual(self.read(name), before)
        self.assertIn("AI/Vendor landscape, 2026.md: read-only", summary["skipped"])

    def test_meeting_home_comes_from_the_repo_map_tag(self):
        # `planning/` is not one of the fallback folder names; the tag makes it a meeting home.
        self.write("knowledge/planning/2026-06-01-roadmap review.md", "notes\n")
        claude = self.text("CLAUDE.md").replace(
            "| `knowledge/reference/`", "| `knowledge/planning/` | Planning meetings | by date | Active | active | High | meeting-home |\n| `knowledge/reference/`")
        self.write("CLAUDE.md", claude)
        self.ok("obsidian", "bootstrap")
        self.assertTrue(self.text("knowledge/planning/2026-06-01-roadmap review.md").startswith(
            "---\ntype: meeting\ndate: 2026-06-01\ntopic: roadmap review\nattendees: []\ntags: [meeting, planning]\n---\n"))

    def test_commit_flag_commits_exactly_the_touched_files(self):
        repo = self.init_child_repo("knowledge")
        self.write("knowledge/AI/half-written.txt", "the owner is in the middle of this\n")
        summary = self.json("obsidian", "bootstrap", "--commit")
        self.assertTrue(summary["commit"]["committed"])
        subject = self.git(repo, "log", "-1", "--format=%s").strip()
        self.assertEqual(subject, "Bootstrap (obsidian): 6 MOCs, 2 person indexes, 13 frontmatter additions")
        self.assertIn("Co-Authored-By: Claude <noreply@anthropic.com>", self.git(repo, "log", "-1", "--format=%B"))
        status = self.git(repo, "status", "--porcelain").strip()
        self.assertEqual(status, "?? AI/half-written.txt")


class RoundTrip(support.ToolsCase):
    """Acceptance test for the toolkit: run every mutating command over the
    fixture vault; nothing changes outside the lines the tools own, and a
    second pass changes nothing at all."""

    def everything(self):
        self.ok("obsidian", "bootstrap")
        for rel in ("knowledge/AI/northwind/2026-04-23-joint-partnership-meeting.md",
                    "knowledge/leadership/2026-04-29-slt-meeting.md",
                    "knowledge/leadership/2026-04-22-slt-meeting.md",
                    "knowledge/AI/Vendor landscape, 2026.md",
                    "knowledge/AI/northwind/Übersicht – Zürich.md",
                    "knowledge/reference/report.pdf"):
            self.ok("pointers", "add", rel)
        self.ok("pointers", "rename", "knowledge/AI/does-not-exist.md", "knowledge/AI/still-not.md")
        self.ok("index")

    def test_round_trip(self):
        self.ok("db", "init")
        before = self.snapshot()
        self.everything()
        after = self.snapshot()
        for name, data in before.items():
            self.assertIn(name, after, "a file disappeared: %s" % name)
            if data == after[name]:
                continue
            for removed, added in support.removed_and_added(data, after[name]):
                self.assertTrue(owned_change(name, removed, added),
                                "%s: unowned change\n  removed: %r\n  added:   %r" % (name, removed, added))
        for name in after:
            if name not in before:
                self.assertTrue(name.endswith("/_MOC.md") or name.endswith("/index.md"), name)
        self.assertEqual(self.json("pointers", "check")["broken"], [])
        self.everything()
        self.assertEqual(self.snapshot(), after, "the second pass changed something")
        outside = self.snapshot("projects")
        self.assertEqual(sorted(outside), ["projects/orion/CLAUDE.md", "projects/orion/src/main.rs"])


if __name__ == "__main__":
    unittest.main()
