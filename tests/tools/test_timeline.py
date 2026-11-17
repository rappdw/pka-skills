"""Phase 4: the people registry and person timelines."""
from __future__ import annotations

import os
import shutil

import support

OPEN = "<!-- pka:timeline v1 — maintained by pka-tools; newest first; edit summaries freely, leave links alone -->"
CLOSE = "<!-- /pka:timeline -->"
JOINT = "knowledge/AI/northwind/2026-04-23-joint-partnership-meeting.md"
PRIYA_1ON1 = "knowledge/personnel/priya/2026-03-31-1-1-priya.md"
PRIYA = "knowledge/personnel/priya/index.md"


def meeting(date, attendees, title="Sync"):
    return "---\ntype: meeting\ndate: %s\nattendees: [%s]\n---\n\n# %s\n\nbody\n" % (date, ", ".join(attendees), title)


class Resolve(support.ToolsCase):
    def setUp(self):
        super().setUp()
        self.write("knowledge/personnel/priya/index.md", self.text(PRIYA).replace(
            "tags: [person]", "aliases: [PJ]\ntags: [person]"))
        for slug in ("robin-smith", "robin-chen", "sam-ortiz"):
            os.makedirs(str(self.path("knowledge/personnel/" + slug)), exist_ok=True)

    def resolve(self, *names):
        return {r["text"]: r for r in self.json("people", "resolve", *names)["results"]}

    def test_high_confidence_forms(self):
        found = self.resolve("Priya", "priya", "Priya Nair", "PJ", "@Priya", "Dr. Priya Nair", "Ortiz Sam",
                             "sam-ortiz", "[[personnel/robin-smith/index|Robin]]", "[Robin](../personnel/robin-chen/)",
                             "Zoe", "zoë-åkesson")
        expect = {"Priya": "priya", "priya": "priya", "Priya Nair": "priya", "PJ": "priya", "@Priya": "priya",
                  "Dr. Priya Nair": "priya", "Ortiz Sam": "sam-ortiz", "sam-ortiz": "sam-ortiz",
                  "[[personnel/robin-smith/index|Robin]]": "robin-smith",
                  "[Robin](../personnel/robin-chen/)": "robin-chen", "Zoe": "zoë-åkesson", "zoë-åkesson": "zoë-åkesson"}
        for text, slug in expect.items():
            self.assertEqual((found[text]["status"], found[text]["slug"]), ("high", slug), text)

    def test_never_guessed(self):
        found = self.resolve("Robin", "Smith", "Nair", "Priyanka", "Priya Shah", "Bobby", "[[AI/brief]]", "")
        self.assertEqual(found["Robin"]["status"], "ambiguous")             # two Robins
        self.assertEqual(found["Robin"]["candidates"], ["robin-chen", "robin-smith"])
        self.assertEqual(found["Smith"]["status"], "ambiguous")             # last name only
        self.assertEqual(found["Nair"]["status"], "ambiguous")              # last name of a `name`
        for text in ("Priyanka", "Priya Shah", "Bobby", "[[AI/brief]]", ""):
            self.assertEqual(found[text]["status"], "none", text)
        self.assertEqual(found["Priya Shah"]["candidates"], ["priya"])     # offered, not chosen

    def test_alias_is_recorded_and_then_resolves(self):
        result = self.json("people", "alias", "sam-ortiz", "Sammy")
        self.assertEqual(result["action"], "created-index")
        self.assertIn("aliases: [Sammy]", self.text("knowledge/personnel/sam-ortiz/index.md"))
        self.assertEqual(self.resolve("Sammy")["Sammy"]["slug"], "sam-ortiz")
        self.assertEqual(self.json("people", "alias", "sam-ortiz", "sammy")["action"], "noop")
        before = self.text(PRIYA)
        self.json("people", "alias", "priya", "Pri")
        self.assertEqual(self.text(PRIYA), before.replace("aliases: [PJ]", "aliases: [PJ, Pri]"))

    def test_alias_that_already_means_someone_else_is_refused(self):
        code, _out, err = self.tool("people", "alias", "sam-ortiz", "Priya")
        self.assertEqual(code, 64)
        self.assertIn("already means priya", err)

    def test_no_people_folder(self):
        shutil.rmtree(str(self.path("knowledge/personnel")))
        claude = self.text("CLAUDE.md").replace("people-home", "")
        self.write("CLAUDE.md", claude)
        self.assertEqual(self.tool("people", "resolve", "Priya")[0], 3)


class Timeline(support.ToolsCase):
    def lines(self, rel):
        return self.text(rel).split("\n")

    def block(self, rel):
        lines = self.lines(rel)
        return lines[lines.index(OPEN) + 1: lines.index(CLOSE)]

    def test_meeting_goes_on_each_attendee_timeline(self):
        result = self.json("timeline", "add", JOINT, "--summary-for", "priya=Owns the architecture comparison")
        self.assertEqual({p["slug"]: p["action"] for p in result["people"]},
                         {"priya": "added", "robin-smith": "created-index"})
        self.assertEqual(result["unresolved"], ["jamie-lin"])
        self.assertEqual(self.block(PRIYA), [
            "- 2026-04-23 · meeting · [[AI/northwind/2026-04-23-joint-partnership-meeting|Joint partnership meeting]]"
            " — Owns the architecture comparison"])
        robin = self.text("knowledge/personnel/robin-smith/index.md")
        self.assertTrue(robin.startswith("---\ntype: person\nname: Robin Smith\n"))
        self.assertTrue(robin.endswith("## Timeline\n%s\n- 2026-04-23 · meeting · [[AI/northwind/2026-04-23-joint-"
                                       "partnership-meeting|Joint partnership meeting]]\n%s\n" % (OPEN, CLOSE)))

    def test_existing_index_is_only_appended_to(self):
        before = self.text(PRIYA)
        self.ok("timeline", "add", PRIYA_1ON1, "--summary", "Adapter spike")
        after = self.text(PRIYA)
        self.assertTrue(after.startswith(before))
        self.assertEqual(after[len(before):], "\n## Timeline\n%s\n- 2026-03-31 · 1on1 · "
                         "[[personnel/priya/2026-03-31-1-1-priya|1-1]] — Adapter spike\n%s\n" % (OPEN, CLOSE))

    def test_newest_first_and_same_date_keeps_existing_order(self):
        for date, name in (("2026-05-01", "b"), ("2026-03-01", "a"), ("2026-06-01", "c"), ("2026-05-01", "d")):
            self.write("knowledge/leadership/%s-%s.md" % (date, name), meeting(date, ["priya"]))
            self.ok("timeline", "add", "knowledge/leadership/%s-%s.md" % (date, name))
        dates = [line.split(" · ")[0][2:] + line.split("|")[0][-1] for line in self.block(PRIYA)]
        self.assertEqual(dates, ["2026-06-01c", "2026-05-01b", "2026-05-01d", "2026-03-01a"])

    def test_filing_twice_changes_nothing(self):
        self.ok("timeline", "add", JOINT)
        snap = self.snapshot()
        result = self.json("timeline", "add", JOINT, "--summary", "a different summary")
        self.assertEqual({p["action"] for p in result["people"]}, {"present"})
        self.assertEqual(self.snapshot(), snap)

    def test_hand_edited_summary_and_stray_text_survive_ten_routes(self):
        self.ok("timeline", "add", JOINT, "--summary", "tool summary")
        edited = self.text(PRIYA).replace("— tool summary", "— my own words, edited by hand")
        edited = edited.replace(CLOSE, "a note I typed inside the block\n" + CLOSE)
        self.write(PRIYA, edited)
        for _ in range(10):
            self.ok("post-route", JOINT, "--summary", "tool summary again")
        self.assertEqual(self.text(PRIYA), edited)

    def test_rename_updates_every_timeline(self):
        self.ok("timeline", "add", JOINT)
        new = "knowledge/AI/northwind/2026-04-23-partnership-kickoff.md"
        os.rename(str(self.path(JOINT)), str(self.path(new)))
        result = self.json("pointers", "rename", JOINT, new)
        self.assertEqual(sorted(result["timeline_changed"]), [PRIYA, "knowledge/personnel/robin-smith/index.md"])
        for rel in (PRIYA, "knowledge/personnel/robin-smith/index.md"):
            block = "\n".join(self.block(rel))
            self.assertIn("[[AI/northwind/2026-04-23-partnership-kickoff|Joint partnership meeting]]", block)
            self.assertNotIn("joint-partnership-meeting", block)
        self.assertEqual(self.json("timeline", "check")["problems"], [])
        # and the note is still "present": refiling it adds nothing
        self.assertEqual({p["action"] for p in self.json("timeline", "add", new)["people"]}, {"present"})

    def test_large_meeting_adds_no_attendees(self):
        for n in range(9):
            os.makedirs(str(self.path("knowledge/personnel/person-%d" % n)))
        rel = "knowledge/leadership/2026-06-01-all-hands.md"
        self.write(rel, meeting("2026-06-01", ["person-%d" % n for n in range(9)], "All hands"))
        result = self.json("timeline", "add", rel)
        self.assertEqual((result["people"], result["large_skipped"], result["attendees"]), ([], True, 9))
        result = self.json("timeline", "add", rel, "--include-large")
        self.assertEqual(len(result["people"]), 9)
        # the person the note is filed under still gets it
        rel = "knowledge/personnel/priya/2026-06-02-all-hands-notes.md"
        self.write(rel, meeting("2026-06-02", ["person-%d" % n for n in range(9)]))
        self.assertEqual([p["slug"] for p in self.json("timeline", "add", rel)["people"]], ["priya"])

    def test_evidence_tiers(self):
        self.write("knowledge/leadership/2026-06-03-sync-with-robin-smith.md", "No frontmatter.\n")
        found = self.json("timeline", "who", "knowledge/leadership/2026-06-03-sync-with-robin-smith.md")
        self.assertEqual([p["slug"] for p in found["people"]], ["robin-smith"])     # filename words
        self.write("knowledge/leadership/2026-06-04-review.md",
                   "# Review\n\n## Attendees\n- [Priya](../personnel/priya/) — matched\n- Pat Doe — no personnel folder\n\n"
                   "Robin said something.\n")
        found = self.json("timeline", "who", "knowledge/leadership/2026-06-04-review.md")
        self.assertEqual([p["slug"] for p in found["people"]], ["priya"])            # body mention of Robin: no
        self.assertEqual(self.json("timeline", "who", PRIYA_1ON1)["people"][0]["tier"], "T1")

    def test_no_backref_opts_a_note_out(self):
        rel = "knowledge/leadership/2026-06-06-private.md"
        self.write(rel, "---\ndate: 2026-06-06\nattendees: [priya]\nno-backref: true\n---\n")
        result = self.json("timeline", "add", rel)
        self.assertEqual((result["people"], result["opted_out"]), ([], True))

    def test_ambiguous_attendee_is_reported_not_added(self):
        os.makedirs(str(self.path("knowledge/personnel/robin-chen")))
        rel = "knowledge/leadership/2026-06-05-sync.md"
        self.write(rel, meeting("2026-06-05", ["Robin", "priya"]))
        result = self.json("timeline", "add", rel)
        self.assertEqual([p["slug"] for p in result["people"]], ["priya"])
        self.assertEqual(result["ambiguous"][0]["candidates"], ["robin-chen", "robin-smith"])

    def test_without_obsidian_links_are_relative_markdown(self):
        shutil.rmtree(str(self.path("knowledge/.obsidian")))
        self.ok("timeline", "add", JOINT)
        self.assertEqual(self.block(PRIYA), [
            "- 2026-04-23 · meeting · [Joint partnership meeting](../../AI/northwind/2026-04-23-joint-partnership-meeting.md)"])
        self.assertEqual({p["action"] for p in self.json("timeline", "add", JOINT)["people"]}, {"present"})
        new = "knowledge/AI/2026-04-23-kickoff notes.md"
        os.rename(str(self.path(JOINT)), str(self.path(new)))
        self.ok("timeline", "rename", JOINT, new)
        self.assertEqual(self.block(PRIYA), [
            "- 2026-04-23 · meeting · [Joint partnership meeting](<../../AI/2026-04-23-kickoff notes.md>)"])
        self.assertEqual(self.json("timeline", "check")["problems"], [])

    def test_crlf_index_and_unreadable_blocks(self):
        self.write(PRIYA, self.read(PRIYA).replace(b"\n", b"\r\n"))
        self.ok("timeline", "add", JOINT)
        data = self.read(PRIYA)
        self.assertEqual(data.count(b"\n"), data.count(b"\r\n"))
        broken = self.text(PRIYA).replace(CLOSE, "")
        self.write(PRIYA, broken)
        result = self.json("timeline", "add", PRIYA_1ON1)
        self.assertEqual(result["people"][0]["action"], "skipped")
        self.assertIn("markers", result["people"][0]["problem"])
        self.assertEqual(self.text(PRIYA), broken)

    def test_no_date_is_a_usage_error(self):
        self.write("knowledge/personnel/priya/undated.md", "x\n")
        self.assertEqual(self.tool("timeline", "add", "knowledge/personnel/priya/undated.md")[0], 64)
        self.assertEqual(self.json("timeline", "add", "knowledge/personnel/priya/undated.md",
                                   "--date", "2026-01-02")["date"], "2026-01-02")

    def test_strip_restores_the_file(self):
        before = self.text(PRIYA)
        self.ok("timeline", "add", JOINT)
        self.ok("timeline", "add", PRIYA_1ON1)
        self.ok("timeline", "strip")
        self.assertEqual(self.text(PRIYA), before)
        robin = self.text("knowledge/personnel/robin-smith/index.md")
        self.assertNotIn("Timeline", robin)

    def test_check_reports(self):
        self.ok("timeline", "add", JOINT)
        os.remove(str(self.path(JOINT)))
        problems = self.json("timeline", "check")["problems"]
        self.assertEqual(len(problems), 2)
        self.assertTrue(all("does not exist" in p["problem"] for p in problems))

    def test_dry_run_writes_nothing(self):
        snap = self.snapshot()
        result = self.json("timeline", "add", JOINT, "--dry-run")
        self.assertEqual(len(result["people"]), 2)
        self.assertEqual(self.snapshot(), snap)


class PostRouteTimeline(support.ToolsCase):
    def setUp(self):
        super().setUp()
        self.git(self.ws, "init", "-q", "-b", "main")
        self.write(".gitignore", "knowledge/\nprojects/\n")
        self.write(".meta", '{"projects": {}}\n')
        self.repo = self.init_child_repo("knowledge")

    def committed(self):
        return sorted(self.git(self.repo, "show", "--name-only", "--format=", "HEAD").split())

    def test_timeline_lines_ride_in_the_note_commit(self):
        rel = "knowledge/leadership/2026-06-10-roadmap.md"
        self.write(rel, meeting("2026-06-10", ["priya", "Robin"], "Roadmap"))
        result = self.json("post-route", rel, "--role", "Meetings", "--summary-for", "priya=Owns the roadmap draft")
        steps = {s["step"]: s["action"] for s in result["steps"]}
        self.assertEqual(steps["timeline"], "written")
        self.assertIn("personnel/priya/index.md", self.committed())
        self.assertIn("personnel/robin-smith/index.md", self.committed())
        self.assertEqual(self.git(self.repo, "status", "--porcelain").strip(), "")
        head = self.git(self.repo, "rev-parse", "HEAD")
        again = self.json("post-route", rel, "--role", "Meetings")
        self.assertEqual({s["step"]: s["action"] for s in again["steps"]}["timeline"], "noop")
        self.assertEqual(self.git(self.repo, "rev-parse", "HEAD"), head)

    def test_a_timeline_line_left_by_an_earlier_run_is_committed(self):
        rel = "knowledge/leadership/2026-06-11-sync.md"
        self.write(rel, meeting("2026-06-11", ["priya"]))
        self.ok("post-route", rel, "--no-commit")
        self.ok("post-route", rel)
        self.assertEqual(self.git(self.repo, "status", "--porcelain").strip(), "")

    def test_options(self):
        rel = "knowledge/AI/brief.md"
        self.write(rel, "---\ndate: 2026-06-12\n---\n# Brief\n")
        result = self.json("post-route", rel, "--person", "priya", "--summary", "Reviewed the brief", "--no-commit")
        self.assertEqual({s["step"]: s["action"] for s in result["steps"]}["timeline"], "written")
        self.assertIn("· doc · [[AI/brief|Brief]] — Reviewed the brief", self.text(PRIYA))
        result = self.json("post-route", "knowledge/AI/ai-adoption-research.md", "--no-timeline", "--no-commit")
        self.assertEqual({s["step"]: s["action"] for s in result["steps"]}["timeline"], "not-requested")
        for args in (("--person", "nobody"), ("--summary-for", "nobody=x"), ("--summary-for", "no-equals")):
            code, _out, _err = self.tool("post-route", rel, *args)
            self.assertEqual(code, 64, args)

    def test_person_index_itself_is_not_timelined(self):
        result = self.json("post-route", PRIYA, "--no-commit")
        self.assertEqual({s["step"]: s["action"] for s in result["steps"]}["timeline"], "not-applicable")
