"""Timeline scope: without Obsidian a timeline links to notes anywhere in the
workspace (but the inboxes and hidden folders); an Obsidian vault keeps the
vault-only rule."""
from __future__ import annotations

import shutil

import support

CLOSE = "<!-- /pka:timeline -->"
PRIYA = "knowledge/personnel/priya/index.md"
JOINT = "knowledge/AI/northwind/2026-04-23-joint-partnership-meeting"
KICKOFF = "projects/widget/2026-05-04-kickoff.md"
STANDUP = "meeting-notes/2026-05-06-standup.md"


def meeting(date, attendees, title="Sync"):
    return "---\ntype: meeting\ndate: %s\nattendees: [%s]\n---\n\n# %s\n\nbody\n" % (
        date, ", ".join(attendees), title)


class Plain(support.ToolsCase):
    """The fixture vault without `.obsidian/`."""

    def setUp(self):
        super().setUp()
        shutil.rmtree(str(self.path("knowledge/.obsidian")))
        self.write(KICKOFF, meeting("2026-05-04", ["Priya"], "Widget kickoff"))
        self.write(STANDUP, meeting("2026-05-06", ["Priya"], "Standup"))

    def keys(self, slug="priya"):
        return [e["key"] for e in self.json("timeline", "list", slug)["entries"]]


class OutsideTheVault(Plain):
    def test_a_project_note_goes_on_the_timeline_with_a_relative_link(self):
        result = self.json("timeline", "add", KICKOFF)
        self.assertEqual([p["action"] for p in result["people"]], ["added"])
        self.assertIn("[Widget kickoff](../../../projects/widget/2026-05-04-kickoff.md)", self.text(PRIYA))
        self.assertIn("projects/widget/2026-05-04-kickoff", self.keys())
        self.assertEqual(self.json("timeline", "check")["problems"], [])

    def test_a_root_meeting_folder_is_reachable(self):
        self.json("timeline", "add", STANDUP)
        self.assertIn("meeting-notes/2026-05-06-standup", self.keys())

    def test_adding_twice_is_idempotent(self):
        self.json("timeline", "add", KICKOFF)
        again = self.json("timeline", "add", KICKOFF)
        self.assertEqual([p["action"] for p in again["people"]], ["present"])
        self.assertEqual(self.text(PRIYA).count("2026-05-04-kickoff"), 1)

    def test_the_inboxes_are_refused(self):
        self.write("owner-inbox/2026-05-07-sync.md", meeting("2026-05-07", ["Priya"]))
        code, _out, err = self.tool("timeline", "add", "owner-inbox/2026-05-07-sync.md")
        self.assertEqual(code, 64, err)
        self.assertIn("not filed yet", err)

    def test_hidden_folders_are_refused(self):
        self.write(".scratch/2026-05-07-sync.md", meeting("2026-05-07", ["Priya"]))
        code, _out, err = self.tool("timeline", "add", ".scratch/2026-05-07-sync.md")
        self.assertEqual(code, 64, err)
        self.assertIn("hidden folder", err)

    def test_vault_notes_still_work_and_keys_name_the_vault(self):
        self.json("timeline", "add", JOINT + ".md", "--person", "priya")
        self.assertIn(JOINT, self.keys())
        self.assertIn("](../../AI/northwind/2026-04-23-joint-partnership-meeting.md)", self.text(PRIYA))

    def test_hand_written_wikilinks_are_read_relative_to_the_vault(self):
        # A wikilink typed into a workspace without Obsidian still means what Obsidian would read.
        self.json("timeline", "add", KICKOFF)
        text = self.text(PRIYA).replace(
            CLOSE, "- 2026-04-23 · meeting · [[AI/northwind/2026-04-23-joint-partnership-meeting|Joint]]\n"
                   "- 2026-03-31 · 1on1 · [[2026-03-31-1-1-priya]]\n" + CLOSE)
        self.write(PRIYA, text)
        for note in (JOINT + ".md", "knowledge/personnel/priya/2026-03-31-1-1-priya.md"):
            result = self.json("timeline", "add", note, "--person", "priya")
            self.assertEqual([p["action"] for p in result["people"]], ["present"], note)
        self.assertEqual(self.json("timeline", "check")["problems"], [])


class Rename(Plain):
    def test_a_project_graduated_into_the_vault_is_followed(self):
        self.json("timeline", "add", KICKOFF)
        target = self.path("knowledge/reference/widget")
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(self.path("projects/widget")), str(target))
        result = self.json("timeline", "rename", "projects/widget", "knowledge/reference/widget", "--prefix")
        self.assertEqual(result["rewrites"], 1)
        self.assertIn("](../../reference/widget/2026-05-04-kickoff.md)", self.text(PRIYA))
        self.assertEqual(self.json("timeline", "check")["problems"], [])

    def test_a_vault_relative_path_still_works(self):
        self.json("timeline", "add", JOINT + ".md", "--person", "priya")
        old = self.path(JOINT + ".md")
        old.rename(old.with_name("2026-04-23-joint.md"))
        result = self.json("timeline", "rename", "AI/northwind/2026-04-23-joint-partnership-meeting",
                           "AI/northwind/2026-04-23-joint")
        self.assertEqual(result["rewrites"], 1)
        self.assertEqual(self.json("timeline", "check")["problems"], [])

    def test_pointers_rename_follows_a_note_outside_the_vault(self):
        self.json("timeline", "add", STANDUP)
        old = self.path(STANDUP)
        old.rename(old.with_name("2026-05-06-team-standup.md"))
        result = self.json("pointers", "rename", STANDUP, "meeting-notes/2026-05-06-team-standup.md")
        self.assertEqual(result["timeline_rewrites"], 1)
        self.assertIn("meeting-notes/2026-05-06-team-standup", self.keys())


class Backfill(Plain):
    def test_plan_and_apply_reach_project_and_root_meeting_notes(self):
        self.write("owner-inbox/2026-05-07-unfiled.md", meeting("2026-05-07", ["Priya"]))
        self.write("projects/widget/node_modules/pkg/2026-05-08-readme.md", meeting("2026-05-08", ["Priya"]))
        result = self.json("timeline", "plan")
        keys = {e["key"] for e in result["entries"] if e["slug"] == "priya"}
        self.assertIn("projects/widget/2026-05-04-kickoff", keys)
        self.assertIn("meeting-notes/2026-05-06-standup", keys)
        self.assertFalse([k for k in keys if k.startswith("owner-inbox/") or "node_modules" in k])
        applied = self.json("timeline", "apply", result["plan_file"])
        self.assertTrue(applied["verified"], applied["problems"])
        self.assertEqual(self.json("timeline", "check")["problems"], [])

    def test_a_project_note_edited_after_the_plan_is_refused(self):
        result = self.json("timeline", "plan")
        before = self.text(PRIYA)
        # A stray edit in projects/ after the plan is caught as a stale note, not written over.
        self.write(KICKOFF, self.text(KICKOFF) + "\nedited\n")
        code, _out, err = self.tool("timeline", "apply", result["plan_file"])
        self.assertEqual(code, 3, err)
        self.assertEqual(self.text(PRIYA), before)


class PostRoute(Plain):
    def test_post_route_writes_the_timeline_for_a_project_note(self):
        result = self.json("post-route", KICKOFF, "--no-commit")
        steps = {s["step"]: s for s in result["steps"]}
        self.assertEqual(steps["timeline"]["action"], "written", steps["timeline"])
        self.assertEqual(steps["moc-link"]["action"], "not-applicable")
        self.assertIn("2026-05-04-kickoff", self.text(PRIYA))

    def test_post_route_reports_an_inbox_note(self):
        self.write("owner-inbox/2026-05-07-sync.md", meeting("2026-05-07", ["Priya"]))
        result = self.json("post-route", "owner-inbox/2026-05-07-sync.md", "--no-commit")
        steps = {s["step"]: s for s in result["steps"]}
        self.assertEqual(steps["timeline"]["action"], "not-applicable")
        self.assertIn("not filed yet", steps["timeline"]["detail"])


class PostRouteHybrid(Plain):
    """A project in its own repository: the note and the person page are
    committed in their own repositories."""

    def setUp(self):
        super().setUp()
        self.git(self.ws, "init", "-q", "-b", "main")
        self.write(".gitignore", "knowledge/\nprojects/\n")
        self.write(".meta", '{"projects": {"projects/widget": "x"}}\n')
        self.repo = self.init_child_repo("knowledge")
        self.project = self.path("projects/widget")
        self.git(self.project, "init", "-q", "-b", "main")
        self.git(self.project, "commit", "-q", "--allow-empty", "-m", "baseline")

    def test_one_commit_in_each_repository(self):
        result = self.json("post-route", KICKOFF)
        self.assertFalse(result["failed"], result["steps"])
        commits = [s for s in result["steps"] if s["step"] == "commit"]
        self.assertEqual([s["action"] for s in commits], ["committed", "committed"], commits)
        self.assertEqual(self.git(self.project, "show", "--name-only", "--format=", "HEAD").split(),
                         ["2026-05-04-kickoff.md"])
        self.assertEqual(self.git(self.repo, "show", "--name-only", "--format=", "HEAD").split(),
                         ["personnel/priya/index.md"])


class ObsidianVault(support.ToolsCase):
    def test_a_note_outside_the_vault_is_refused(self):
        self.write(KICKOFF, meeting("2026-05-04", ["Priya"]))
        code, _out, err = self.tool("timeline", "add", KICKOFF)
        self.assertEqual(code, 64, err)
        self.assertIn("outside the vault", err)

    def test_backfill_stays_in_the_vault(self):
        self.write(KICKOFF, meeting("2026-05-04", ["Priya"]))
        result = self.json("timeline", "plan")
        self.assertFalse([e for e in result["entries"] if e["key"].startswith("projects/")])
        self.assertTrue([e for e in result["entries"] if e["key"] == "AI/northwind/2026-04-23-joint-partnership-meeting"])

    def test_post_route_reports_outside_the_vault(self):
        self.write(KICKOFF, meeting("2026-05-04", ["Priya"]))
        result = self.json("post-route", KICKOFF, "--no-commit")
        steps = {s["step"]: s for s in result["steps"]}
        self.assertEqual(steps["timeline"]["action"], "not-applicable")
        self.assertIn("outside the vault", steps["timeline"]["detail"])


if __name__ == "__main__":
    import unittest
    unittest.main()
