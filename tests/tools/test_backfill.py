"""Phase 5: timeline backfill — plan, apply, verify, restore."""
from __future__ import annotations

import json
import os

import support

OPEN = "<!-- pka:timeline v1 — maintained by pka-tools; newest first; edit summaries freely, leave links alone -->"
CLOSE = "<!-- /pka:timeline -->"
PRIYA = "knowledge/personnel/priya/index.md"
ROBIN = "knowledge/personnel/robin-smith/index.md"
JOINT = "AI/northwind/2026-04-23-joint-partnership-meeting"


def meeting(date, attendees, title="Sync", extra=""):
    return "---\ntype: meeting\ndate: %s\nattendees: [%s]\n%s---\n\n# %s\n\nbody\n" % (
        date, ", ".join(attendees), extra, title)


class Backfill(support.ToolsCase):
    def plan(self, *args):
        result = self.json("timeline", "plan", *args)
        return result

    def apply(self, result, *args):
        return self.json("timeline", "apply", result["plan_file"], *args)

    def test_plan_writes_only_its_report_and_plan(self):
        before = self.snapshot()
        result = self.plan()
        self.assertEqual(self.changed(before, self.snapshot()), [])
        self.assertTrue(self.path(result["plan_file"]).is_file())
        report = self.text(result["report_file"])
        self.assertTrue(result["report_file"].startswith("owner-inbox/timeline-backfill-plan-"))
        for heading in ("## Entries per person", "## Sample of", "## Ambiguous names", "## Undated notes",
                        "## Large meetings", "## index.md stubs to create"):
            self.assertIn(heading, report)
        keys = {(e["slug"], e["key"]) for e in result["entries"]}
        self.assertIn(("priya", JOINT), keys)
        self.assertIn(("robin-smith", JOINT), keys)
        self.assertIn(("priya", "personnel/priya/2026-03-31-1-1-priya"), keys)
        self.assertEqual(result["stubs"], sorted(["knowledge/personnel/robin-smith/index.md",
                                                  "knowledge/personnel/zoë-åkesson/index.md"]))

    def test_apply_writes_timelines_only_and_is_repeatable(self):
        before = self.snapshot()
        result = self.plan()
        applied = self.apply(result)
        self.assertTrue(applied["verified"], applied)
        self.assertEqual(applied["problems"], [])
        changed = self.changed(before, self.snapshot())
        self.assertEqual(changed, sorted(set(e["index"] for e in result["entries"])))
        self.assertTrue(all(rel.endswith("/index.md") for rel in changed))
        priya = self.text(PRIYA)
        self.assertIn(OPEN, priya)
        self.assertLess(priya.index(JOINT), priya.index("2026-03-31-1-1-priya"))      # newest first
        self.assertIn("Something the owner wrote about Priya.", priya)                  # the rest kept
        self.assertEqual(self.json("timeline", "check")["problems"], [])
        again = self.plan()
        self.assertEqual(again["entries"], [])
        self.assertEqual(again["already_present"], len(result["entries"]))

    def test_hand_edited_lines_survive(self):
        self.ok("timeline", "add", "knowledge/" + JOINT + ".md", "--person", "priya")
        text = self.text(PRIYA).replace("Joint partnership meeting]]", "Joint partnership meeting]] — my own words")
        text = text.replace(CLOSE, "a note I typed inside the block\n" + CLOSE)
        self.write(PRIYA, text)
        result = self.plan()
        self.assertNotIn(("priya", JOINT), {(e["slug"], e["key"]) for e in result["entries"]})
        self.apply(result)
        after = self.text(PRIYA)
        self.assertIn("— my own words", after)
        self.assertIn("a note I typed inside the block", after)
        self.assertEqual(after.count(JOINT), 1)

    def test_refuses_when_a_page_changed_after_planning(self):
        result = self.plan()
        self.write(PRIYA, self.text(PRIYA) + "\nan edit after the plan\n")
        before = self.snapshot()
        code, out, err = self.tool("timeline", "apply", result["plan_file"], "--workspace", str(self.ws))
        self.assertEqual(code, 3, out + err)
        self.assertIn("changed since the plan", err)
        self.assertEqual(self.changed(before, self.snapshot()), [])

    def test_refuses_when_a_stub_appeared_after_planning(self):
        result = self.plan()
        self.write(ROBIN, "# Robin\n")
        code, _out, err = self.tool("timeline", "apply", result["plan_file"], "--workspace", str(self.ws))
        self.assertEqual(code, 3, err)

    def test_restore_puts_pages_back_and_removes_stubs(self):
        before = self.snapshot()
        applied = self.apply(self.plan())
        backup = applied["backup"].rsplit("/", 1)[-1]
        restored = self.json("timeline", "restore", backup)
        self.assertEqual(sorted(restored["restored"]), applied["files"])
        self.assertEqual(self.changed(before, self.snapshot()), [])
        self.assertFalse(self.path(ROBIN).exists())

    def test_restore_refuses_edits_made_after_the_apply(self):
        applied = self.apply(self.plan())
        backup = applied["backup"].rsplit("/", 1)[-1]
        self.write(PRIYA, self.text(PRIYA).replace("— ", "— ") + "\nlater edit\n")
        code, _out, err = self.tool("timeline", "restore", backup, "--workspace", str(self.ws))
        self.assertEqual(code, 3, err)
        self.assertIn("later edit", self.text(PRIYA))
        self.json("timeline", "restore", backup, "--force")
        self.assertNotIn("later edit", self.text(PRIYA))
        self.assertNotIn(OPEN, self.text(PRIYA))

    def test_old_backlink_sections_are_evidence(self):
        self.write("knowledge/AI/northwind/2026-04-10-kickoff.md", "# Kickoff\n\nNo attendee list.\n")
        self.write(PRIYA, self.text(PRIYA) + "\n## Mentioned in\n- [[AI/northwind/2026-04-10-kickoff]]\n")
        entries = {(e["slug"], e["key"]): e for e in self.plan()["entries"]}
        entry = entries[("priya", "AI/northwind/2026-04-10-kickoff")]
        self.assertIn("T2: listed under ## Mentioned in on their page", entry["evidence"])

    def test_report_lists_what_it_did_not_add(self):
        names = ["Priya", "Robin"]           # Robin is ambiguous once a second Robin exists
        os.makedirs(str(self.path("knowledge/personnel/robin-chen")), exist_ok=True)
        self.write("knowledge/leadership/2026-05-02-sync.md", meeting("2026-05-02", names))
        self.write("knowledge/leadership/undated-sync.md", "---\nattendees: [Priya]\n---\n\n# Undated\n")
        many = ["Person%d" % i for i in range(9)]
        for i in range(9):
            os.makedirs(str(self.path("knowledge/personnel/person%d" % i)), exist_ok=True)
        self.write("knowledge/leadership/2026-05-03-all-hands.md", meeting("2026-05-03", many, "All hands"))
        self.write("knowledge/leadership/2026-05-04-private.md", meeting("2026-05-04", ["Priya"], extra="no-backref: true\n"))
        for day in (5, 6, 7):
            self.write("knowledge/leadership/2026-05-0%d-ext.md" % day, meeting("2026-05-0%d" % day, ["Sam Ortiz"]))
        result = self.plan()
        self.assertIn({"text": "Robin", "candidates": ["robin-chen", "robin-smith"], "notes": 1}, result["ambiguous"])
        self.assertIn({"note": "knowledge/leadership/undated-sync.md", "people": ["priya"]}, result["undated"])
        self.assertIn({"note": "knowledge/leadership/2026-05-03-all-hands.md", "attendees": 9}, result["large_meetings"])
        self.assertIn("knowledge/leadership/2026-05-04-private.md", result["opted_out"])
        self.assertIn({"text": "Sam Ortiz", "notes": 3}, result["unmatched"])
        keys = {e["key"] for e in result["entries"]}
        self.assertNotIn("leadership/2026-05-03-all-hands", keys)
        self.assertNotIn("leadership/2026-05-04-private", keys)
        self.assertIn("leadership/2026-05-02-sync", keys)
        report = self.text(result["report_file"])
        self.assertIn("'Robin': robin-chen, robin-smith", report)
        self.assertIn("Sam Ortiz", report)

    def test_mocs_person_pages_and_wikis_are_not_candidates(self):
        self.write("knowledge/AI/agents/wiki.md", "---\nattendees: [Priya]\ndate: 2026-05-01\n---\n# Agents\n")
        self.write("knowledge/AI/agents/sources/2026-05-01-paper.md", "---\nattendees: [Priya]\n---\n# Paper\n")
        keys = {e["key"] for e in self.plan()["entries"]}
        self.assertFalse(any(k.startswith("AI/agents/") for k in keys), keys)
        self.assertFalse(any(k.endswith("_MOC") or k.endswith("/index") for k in keys), keys)

    def test_since_and_person(self):
        result = self.plan("--since", "2026-04-01", "--person", "priya")
        self.assertEqual({e["slug"] for e in result["entries"]}, {"priya"})
        self.assertTrue(all(e["date"] >= "2026-04-01" for e in result["entries"]))
        code, _out, _err = self.tool("timeline", "plan", "--person", "nobody", "--workspace", str(self.ws))
        self.assertEqual(code, 64)

    def test_unwritable_page_is_reported_and_left_out(self):
        self.write(PRIYA, self.text(PRIYA) + "\n```\nunclosed\n")
        result = self.plan()
        self.assertIn("priya", [s["slug"] for s in result["people_skipped"]])
        self.assertNotIn("priya", {e["slug"] for e in result["entries"]})

    def test_dry_run_and_no_write(self):
        before = self.snapshot()
        result = self.json("timeline", "plan", "--no-write")
        self.assertIsNone(result["plan_file"])
        self.assertFalse(self.path(".pka/backfill").exists())
        written = self.plan()
        dry = self.apply(written, "--dry-run")
        self.assertEqual(dry["entries"], len(written["entries"]))
        self.assertEqual(self.changed(before, self.snapshot()), [])

    def test_without_obsidian_links_are_relative(self):
        import shutil
        shutil.rmtree(str(self.path("knowledge/.obsidian")))
        applied = self.apply(self.plan())
        self.assertTrue(applied["verified"])
        self.assertIn("](../../AI/northwind/2026-04-23-joint-partnership-meeting.md)", self.text(PRIYA))
        self.assertEqual(self.json("timeline", "check")["problems"], [])

    def test_plan_made_with_obsidian_is_refused_without(self):
        import shutil
        result = self.plan()
        shutil.rmtree(str(self.path("knowledge/.obsidian")))
        code, _out, err = self.tool("timeline", "apply", result["plan_file"], "--workspace", str(self.ws))
        self.assertEqual(code, 3, err)

    def test_not_a_plan(self):
        self.write(".pka/backfill/junk.json", "[1, 2]\n")
        code, _out, _err = self.tool("timeline", "apply", ".pka/backfill/junk.json", "--workspace", str(self.ws))
        self.assertEqual(code, 64)


class BackfillHybrid(support.ToolsCase):
    def setUp(self):
        super().setUp()
        self.git(self.ws, "init", "-q", "-b", "main")
        self.write(".gitignore", "knowledge/\nprojects/\n")
        self.write(".meta", '{"projects": {}}\n')
        self.repo = self.init_child_repo("knowledge")

    def test_one_commit_with_exactly_the_person_pages(self):
        self.write("knowledge/scratch.md", "uncommitted work of the user\n")
        result = self.json("timeline", "plan")
        applied = self.json("timeline", "apply", result["plan_file"])
        self.assertTrue(applied["commit"]["committed"], applied)
        files = self.git(self.repo, "-c", "core.quotepath=off", "show", "--name-only", "--format=", "HEAD").split()
        self.assertEqual(sorted(files), sorted(f[len("knowledge/"):] for f in applied["files"]))
        self.assertIn("?? scratch.md", self.git(self.repo, "status", "--porcelain"))
        subject = self.git(self.repo, "log", "-1", "--format=%s").strip()
        self.assertTrue(subject.startswith("Timelines: backfill"), subject)


class BackfillVerification(support.ToolsCase):
    """A failed verification puts every page back."""

    def test_unexpected_change_is_rolled_back(self):
        import sys
        sys.path.insert(0, str(support.ASSETS / "tools"))
        from pka_tools import backfill, timeline
        from pka_tools.workspace import Workspace
        ws = Workspace(self.ws)
        result = backfill.plan(ws)
        before = self.snapshot()
        original = timeline.place

        def sneaky(*args, **kwargs):
            (self.ws / "knowledge" / "AI" / "ai-adoption-research.md").write_text("changed\n", encoding="utf-8")
            return original(*args, **kwargs)

        timeline.place = sneaky
        try:
            applied = backfill.apply(ws, result["plan_file"])
        finally:
            timeline.place = original
        self.assertFalse(applied["verified"])
        self.assertTrue(applied["restored"])
        self.assertTrue(any("ai-adoption-research.md" in p for p in applied["problems"]), applied["problems"])
        changed = self.changed(before, self.snapshot())
        self.assertEqual(changed, ["knowledge/AI/ai-adoption-research.md"])     # the person pages are back
        record = json.loads((self.ws / applied["backup"] / "backup.json").read_text(encoding="utf-8"))
        self.assertEqual(record["state"], "rolled-back")


class ReviewFindings(support.ToolsCase):
    """Regression tests for the review of the first Phase 5 build."""

    def module(self):
        import sys
        sys.path.insert(0, str(support.ASSETS / "tools"))
        from pka_tools import backfill, timeline
        from pka_tools.workspace import Workspace
        return backfill, timeline, Workspace(self.ws)

    def code(self, *args):
        code, _out, err = self.tool(*args, "--workspace", str(self.ws))
        return code, err

    def test_interrupt_mid_apply_puts_everything_back(self):          # high
        backfill, timeline, ws = self.module()
        result = backfill.plan(ws)
        before = self.snapshot()
        original = timeline.place
        seen = set()

        def boom(ws_, index, *args, **kwargs):
            seen.add(index)
            if len(seen) > 1:
                raise KeyboardInterrupt
            return original(ws_, index, *args, **kwargs)

        timeline.place = boom
        try:
            with self.assertRaises(KeyboardInterrupt):
                backfill.apply(ws, result["plan_file"])
        finally:
            timeline.place = original
        self.assertEqual(self.changed(before, self.snapshot()), [])
        backup = sorted(os.listdir(str(self.path(".pka/backups"))))[-1]
        self.assertEqual(self.code("timeline", "restore", backup)[0], 3)        # rolled back: nothing to restore

    def test_restore_refuses_a_page_whose_state_after_apply_is_unknown(self):
        backfill, _timeline, ws = self.module()
        applied = backfill.apply(ws, backfill.plan(ws)["plan_file"])
        path = self.ws / applied["backup"] / "backup.json"
        record = json.loads(path.read_text(encoding="utf-8"))
        for info in record["files"].values():
            info["after"] = None                         # as if the run died before recording it
        path.write_text(json.dumps(record), encoding="utf-8")
        code, err = self.code("timeline", "restore", applied["backup"].rsplit("/", 1)[-1])
        self.assertEqual(code, 3, err)
        self.assertIn(OPEN, self.text(PRIYA))

    def test_restore_after_a_failed_verification_is_refused(self):     # medium
        backfill, timeline, ws = self.module()
        result = backfill.plan(ws)
        original = timeline.place

        def sneaky(*args, **kwargs):
            (self.ws / "knowledge" / "AI" / "ai-adoption-research.md").write_text("changed\n", encoding="utf-8")
            return original(*args, **kwargs)

        timeline.place = sneaky
        try:
            applied = backfill.apply(ws, result["plan_file"])
        finally:
            timeline.place = original
        self.write(PRIYA, self.text(PRIYA) + "\nimportant later edit\n")
        code, err = self.code("timeline", "restore", applied["backup"].rsplit("/", 1)[-1])
        self.assertEqual(code, 3, err)
        self.assertIn("important later edit", self.text(PRIYA))

    def test_a_name_a_link_cannot_carry_is_left_out_not_fatal(self):    # medium
        self.write("knowledge/leadership/2026-05-02-Sync.MD", meeting("2026-05-02", ["Priya"]))
        result = self.json("timeline", "plan")
        self.assertIn("knowledge/leadership/2026-05-02-Sync.MD", result["unlinkable"])
        self.assertNotIn("leadership/2026-05-02-Sync", {e["key"] for e in result["entries"]})
        self.assertTrue(self.json("timeline", "apply", result["plan_file"])["verified"])

    def test_angle_brackets_without_obsidian(self):
        import shutil
        shutil.rmtree(str(self.path("knowledge/.obsidian")))
        self.write("knowledge/leadership/2026-05-02-a>b.md", meeting("2026-05-02", ["Priya"]))
        result = self.json("timeline", "plan")
        self.assertIn("knowledge/leadership/2026-05-02-a>b.md", result["unlinkable"])
        self.assertTrue(self.json("timeline", "apply", result["plan_file"])["verified"])

    def test_ids_never_collide(self):                                   # medium
        backfill, _timeline, ws = self.module()
        first = backfill.plan(ws, person="priya")
        second = backfill.plan(ws, person="robin-smith")
        self.assertNotEqual(first["plan_file"], second["plan_file"])
        self.assertNotEqual(first["report_file"], second["report_file"])
        self.assertEqual(json.loads(self.text(first["plan_file"]))["options"]["person"], "priya")
        one = backfill.apply(ws, first["plan_file"], commit=False)
        two = backfill.apply(ws, second["plan_file"], commit=False)
        self.assertNotEqual(one["backup"], two["backup"])

    def test_obsidian_writing_its_own_files_does_not_fail_the_apply(self):    # medium
        backfill, timeline, ws = self.module()
        result = backfill.plan(ws)
        original = timeline.place

        def obsidian(*args, **kwargs):
            (self.ws / "knowledge" / ".obsidian" / "workspace.json").write_text('{"active": "x"}', encoding="utf-8")
            return original(*args, **kwargs)

        timeline.place = obsidian
        try:
            applied = backfill.apply(ws, result["plan_file"])
        finally:
            timeline.place = original
        self.assertTrue(applied["verified"], applied["problems"])

    def test_a_note_changed_after_planning_makes_the_plan_stale(self):   # medium
        self.write("knowledge/leadership/2026-05-02-sync.md", meeting("2026-05-02", ["Priya"]))
        result = self.json("timeline", "plan")
        self.write("knowledge/leadership/2026-05-02-sync.md", meeting("2026-05-02", ["Priya"], extra="no-backref: true\n"))
        code, err = self.code("timeline", "apply", result["plan_file"])
        self.assertEqual(code, 3, err)
        self.assertIn("2026-05-02-sync.md", err)
        self.assertNotIn("2026-05-02-sync", self.text(PRIYA))

    def test_restore_refuses_when_a_person_folder_moved(self):          # medium/low
        applied = self.json("timeline", "apply", self.json("timeline", "plan")["plan_file"])
        backup = applied["backup"].rsplit("/", 1)[-1]
        os.rename(str(self.path("knowledge/personnel/priya")), str(self.path("knowledge/personnel/priya-old")))
        for extra in ((), ("--force",)):
            code, err = self.code("timeline", "restore", backup, *extra)
            self.assertEqual(code, 3, err)
        self.assertTrue(self.path(ROBIN).exists())      # all or nothing: nothing was touched

    def test_a_foreign_plan_cannot_reach_outside_person_pages(self):    # low/medium
        backfill, _timeline, ws = self.module()
        outside = self.base / "secret.txt"
        outside.write_text("outside the workspace\n", encoding="utf-8")
        from pka_tools.textio import sha256_file
        plan = backfill.plan(ws, write=False)
        plan["targets"]["../secret.txt"] = {"slug": "priya", "sha256": sha256_file(outside), "created": False}
        self.write(".pka/backfill/evil.json", json.dumps(plan))
        self.assertEqual(self.code("timeline", "apply", ".pka/backfill/evil.json")[0], 64)
        plan = backfill.plan(ws, write=False)
        plan["entries"][0]["line"] = "- 2026-01-01 · doc · [[AI/ai-adoption-research|x]]"
        self.write(".pka/backfill/evil2.json", json.dumps(plan))
        self.assertEqual(self.code("timeline", "apply", ".pka/backfill/evil2.json")[0], 64)
        self.assertFalse(self.path(".pka/backups").exists())

    def test_a_foreign_backup_record_cannot_delete_notes(self):
        self.write(".pka/backups/zz/backup.json", json.dumps(
            {"version": 1, "files": {"knowledge/AI/ai-adoption-research.md": {"existed": False, "before": None,
                                                                              "after": None}}}))
        self.assertEqual(self.code("timeline", "restore", "zz")[0], 3)
        self.assertEqual(self.code("timeline", "restore", "../../knowledge")[0], 64)
        self.assertTrue(self.path("knowledge/AI/ai-adoption-research.md").exists())

    def test_malformed_plans_are_usage_errors(self):                    # low
        for body in ({"version": 1, "entries": [], "obsidian": True},
                     {"version": 1, "entries": [{"slug": "priya"}], "targets": {}, "obsidian": True},
                     {"version": 1, "entries": [], "targets": {"x": "y"}, "obsidian": True}):
            self.write(".pka/backfill/bad.json", json.dumps(body))
            code, err = self.code("timeline", "apply", ".pka/backfill/bad.json")
            self.assertEqual(code, 64, err)
            self.assertNotIn("Traceback", err)

    def test_a_wiki_high_up_does_not_hide_its_subfolders(self):         # low
        self.write("knowledge/AI/wiki.md", "# AI wiki\n")
        keys = {e["key"] for e in self.plan_entries()}
        self.assertIn("AI/northwind/2026-04-23-joint-partnership-meeting", keys)

    def plan_entries(self):
        return self.json("timeline", "plan")["entries"]


class ReviewFindingsHybrid(BackfillHybrid):
    def test_a_failed_commit_exits_1(self):                             # low
        result = self.json("timeline", "plan")
        hooks = self.repo / ".git" / "hooks"
        hooks.mkdir(exist_ok=True)
        (hooks / "pre-commit").write_text("#!/bin/sh\nexit 1\n", encoding="utf-8")
        os.chmod(str(hooks / "pre-commit"), 0o755)
        code, err = self.tool("timeline", "apply", result["plan_file"], "--workspace", str(self.ws))[::2]
        self.assertEqual(code, 1, err)

    def test_the_users_uncommitted_page_edits_are_not_committed(self):
        self.write(PRIYA, self.text(PRIYA) + "\nmy own unfinished thought\n")
        result = self.json("timeline", "plan")
        applied = self.json("timeline", "apply", result["plan_file"])
        self.assertTrue(applied["verified"])
        self.assertFalse(applied["commit"]["committed"])
        self.assertIn("uncommitted changes", applied["commit"]["reason"])
        self.assertEqual(self.git(self.repo, "log", "--format=%s").strip().splitlines()[0], "baseline")


if __name__ == "__main__":
    import unittest
    unittest.main()
