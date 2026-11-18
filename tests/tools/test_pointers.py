"""Pointer-layer maintenance: cluster rule, line-by-line edits, rename, check."""
from __future__ import annotations

import unittest

import support

TWO_ROWS = """\
# Northwind

## Pointers

Compact retrieval rows maintained by the librarian.

| Topic | Entities | Files |
|---|---|---|
| northwind-partnership-2026 | sasha-ortega, taylor-brooks | [[northwind/northwind_partnership_proposal]] |
| lighthouse-research | atlas-model, victor-hale | [[northwind/revised_lighthouse]] |
"""


def note(frontmatter_lines, body="body\n"):
    if not frontmatter_lines:
        return body
    return "---\n" + "\n".join(frontmatter_lines) + "\n---\n\n" + body


class Blank(support.ToolsCase):
    """An empty Obsidian vault: knowledge/.obsidian/ and nothing else.
    (Without Obsidian, MOCs are not created; see test_postroute.OptIn.)"""
    fixture = False

    def setUp(self):
        super().setUp()
        (self.ws / "knowledge" / ".obsidian").mkdir(parents=True)

    def add(self, rel, *extra):
        return self.json("pointers", "add", rel, *extra)

    def lines(self, rel):
        return support.split_lines(self.text(rel))


class ClusterRule(Blank):
    def test_new_domain_creates_moc_with_one_row(self):
        self.write("knowledge/northwind/2026-04-23-joint-partnership-meeting.md", note([
            "type: meeting", "date: 2026-04-23", "topic: northwind-partnership-2026",
            "attendees: [sasha-ortega, jamie-lin, taylor-brooks]", "tags: [meeting, ai]"]))
        result = self.add("knowledge/northwind/2026-04-23-joint-partnership-meeting.md")
        self.assertEqual(result["mocs"][0]["action"], "created-moc")
        moc = self.text("knowledge/northwind/_MOC.md")
        self.assertIn("## Pointers", moc)
        self.assertIn("| Topic | Entities | Files |", moc)
        self.assertIn("| northwind-partnership-2026 | sasha-ortega, jamie-lin, taylor-brooks | "
                      "[[northwind/2026-04-23-joint-partnership-meeting]] |", moc)

    def test_the_spec_scenario_that_jaccard_failed(self):
        """Finding B2: the PR2 fixture scores 0.33 under Jaccard and coined a
        duplicate row. Topic equality is the first rule now."""
        self.write("knowledge/northwind/_MOC.md", TWO_ROWS)
        self.write("knowledge/northwind/2026-04-23-joint-partnership-meeting.md", note([
            "type: meeting", "date: 2026-04-23", "topic: northwind-partnership-2026",
            "attendees: [jamie-lin, casey-dunn]", "tags: [meeting, ai]"]))
        before = self.lines("knowledge/northwind/_MOC.md")
        result = self.add("knowledge/northwind/2026-04-23-joint-partnership-meeting.md")
        self.assertEqual(result["mocs"][0]["action"], "extended")
        after = self.lines("knowledge/northwind/_MOC.md")
        self.assertEqual(len(after), len(before))                      # no new row
        changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
        self.assertEqual(changed, [8])                                 # only the matched row
        self.assertEqual(
            after[8],
            "| northwind-partnership-2026 | sasha-ortega, taylor-brooks, jamie-lin, casey-dunn | "
            "[[northwind/northwind_partnership_proposal]], [[northwind/2026-04-23-joint-partnership-meeting]] |\n")
        # idempotent
        again = self.add("knowledge/northwind/2026-04-23-joint-partnership-meeting.md")
        self.assertEqual(again["mocs"][0]["action"], "noop")
        self.assertEqual(again["changed"], [])
        self.assertEqual(self.lines("knowledge/northwind/_MOC.md"), after)

    def test_without_a_topic_two_distinctive_tokens_must_all_match(self):
        self.write("knowledge/northwind/_MOC.md", TWO_ROWS)
        # filename + folder supply {northwind, partnership}: joins the first row
        self.write("knowledge/northwind/partnership-term-sheet.md", "x\n")
        self.assertEqual(self.add("knowledge/northwind/partnership-term-sheet.md")["mocs"][0]["topic"],
                         "northwind-partnership-2026")
        # shares one token ("research") with lighthouse-research: must NOT merge
        self.write("knowledge/northwind/research-plan.md", "x\n")
        result = self.add("knowledge/northwind/research-plan.md")
        self.assertEqual(result["mocs"][0]["action"], "appended")
        self.assertEqual(result["mocs"][0]["topic"], "research-plan")
        self.assertEqual(self.lines("knowledge/northwind/_MOC.md")[-1],
                         "| research-plan |  | [[northwind/research-plan]] |\n")

    def test_single_token_slug_never_matches_by_tokens_but_is_idempotent(self):
        self.write("knowledge/AI/_MOC.md", "# AI\n\n## Pointers\n\n| Topic | Entities | Files |\n|---|---|---|\n"
                                            "| strategy | — | [[AI/old]] |\n")
        self.write("knowledge/AI/strategy-offsite.md", note(["tags: [ai]"]))
        result = self.add("knowledge/AI/strategy-offsite.md")
        self.assertEqual(result["mocs"][0]["topic"], "strategy-offsite")   # a new cluster, not "strategy"
        self.write("knowledge/AI/roadmap.md", "x\n")
        self.assertEqual(self.add("knowledge/AI/roadmap.md")["mocs"][0]["action"], "appended")
        self.assertEqual(self.add("knowledge/AI/roadmap.md")["mocs"][0]["action"], "noop")
        self.assertEqual(self.text("knowledge/AI/_MOC.md").count("| roadmap |"), 1)

    def test_most_specific_row_wins(self):
        self.write("knowledge/AI/_MOC.md", "# AI\n\n## Pointers\n\n| Topic | Entities | Files |\n|---|---|---|\n"
                                            "| vendor-landscape | — | [[AI/a]] |\n"
                                            "| vendor-landscape-pricing | — | [[AI/b]] |\n")
        self.write("knowledge/AI/vendor-landscape-pricing-notes.md", "x\n")
        self.assertEqual(self.add("knowledge/AI/vendor-landscape-pricing-notes.md")["mocs"][0]["topic"],
                         "vendor-landscape-pricing")

    def test_explicit_topic_is_a_decision(self):
        self.write("knowledge/northwind/_MOC.md", TWO_ROWS)
        self.write("knowledge/northwind/partnership-term-sheet.md", "x\n")
        # would match row 1 by tokens; the caller says otherwise
        result = self.add("knowledge/northwind/partnership-term-sheet.md", "--topic", "Legal Review 2026")
        self.assertEqual((result["mocs"][0]["action"], result["mocs"][0]["topic"]), ("appended", "legal-review-2026"))
        # and an explicit topic that names an existing row joins it
        self.write("knowledge/northwind/misc.md", "x\n")
        result = self.add("knowledge/northwind/misc.md", "--topic", "lighthouse-research")
        self.assertEqual(result["mocs"][0]["action"], "extended")

    def test_coined_slug_falls_back_to_tag_and_type_then_stem(self):
        self.write("knowledge/AI/x1.md", note(["type: brief", "tags: [brief, ai]"]))
        self.assertEqual(self.add("knowledge/AI/x1.md")["coined_slug"], "ai-brief")
        self.write("knowledge/AI/2026-05-01 Vendor Review.md", "x\n")
        self.assertEqual(self.add("knowledge/AI/2026-05-01 Vendor Review.md")["coined_slug"], "vendor-review")

    def test_entities_come_from_frontmatter_people_and_the_flag(self):
        self.write("knowledge/AI/e.md", note([
            'person: "[[personnel/priya/index]]"',
            'attendees: ["[[personnel/robin-smith/index|Robin]]", Jamie Lin]',
            "related:", '  - "[[AI/atlas-model.md]]"', "tags: [ai, strategy]"]))
        result = self.add("knowledge/AI/e.md", "--entities", "Northwind, Atlas Model")
        self.assertEqual(result["entities"], ["robin-smith", "jamie-lin", "priya", "atlas-model", "northwind"])

    def test_body_is_never_read(self):
        self.write("knowledge/AI/secret.md", "northwind partnership lighthouse research\n")
        self.write("knowledge/AI/_MOC.md", TWO_ROWS.replace("# Northwind", "# AI"))
        self.assertEqual(self.add("knowledge/AI/secret.md")["mocs"][0]["action"], "appended")


class Surgical(support.ToolsCase):
    """Edits against the fixture vault's hand-written MOCs."""

    def test_padded_table_with_an_extra_column(self):
        rel = "knowledge/AI/_MOC.md"
        before = support.split_lines(self.text(rel))
        self.ok("pointers", "add", "knowledge/AI/northwind/2026-04-23-joint-partnership-meeting.md")
        after = support.split_lines(self.text(rel))
        changed = [i for i, (a, b) in enumerate(zip(before, after)) if a != b]
        self.assertEqual(len(after), len(before))
        self.assertEqual(len(changed), 1)
        row = after[changed[0]]
        self.assertIn("[[AI/northwind/northwind_partnership_proposal\\|the proposal]], "
                      "[[AI/northwind/2026-04-23-joint-partnership-meeting]]", row)
        self.assertIn("sasha-ortega, taylor-brooks, priya, robin-smith, jamie-lin", row)
        self.assertTrue(row.rstrip("\n").endswith("| keep me |"))
        self.assertTrue(row.startswith("| northwind-partnership-2026 |"))

    def test_new_row_goes_after_the_last_row_and_fills_extra_columns(self):
        rel = "knowledge/AI/_MOC.md"
        before = support.split_lines(self.text(rel))
        self.ok("pointers", "add", "knowledge/AI/Vendor landscape, 2026.md")
        after = support.split_lines(self.text(rel))
        self.assertEqual(len(after), len(before) + 1)
        index = before.index("| ai-adoption-research       | —                           | "
                             "[[AI/ai-adoption-research]]                                    |         |\n")
        self.assertEqual(after[index + 1], "| vendor-landscape-2026 |  | [[AI/Vendor landscape, 2026]] |  |\n")
        self.assertEqual(after[:index + 1], before[:index + 1])
        self.assertEqual(after[index + 2:], before[index + 1:])

    def test_placeholder_entity_cell_is_replaced_not_appended_to(self):
        self.write("knowledge/AI/second-brief.md", note(["topic: ai-adoption-research", "person: priya"]))
        self.ok("pointers", "add", "knowledge/AI/second-brief.md")
        row = [l for l in support.split_lines(self.text("knowledge/AI/_MOC.md")) if l.startswith("| ai-adoption-research")][0]
        self.assertIn("| priya                           |", row)
        self.assertNotIn("—", row)

    def test_crlf_moc_stays_crlf(self):
        rel = "knowledge/leadership/_MOC.md"
        self.ok("pointers", "add", "knowledge/leadership/2026-04-29-slt-meeting.md")
        self.ok("pointers", "add", "knowledge/AI/northwind/2026-04-23-joint-partnership-meeting.md")
        data = self.read(rel)
        self.assertEqual(data.count(b"\n"), data.count(b"\r\n"))
        self.assertIn(b"| slt-meeting | priya | [[leadership/2026-04-22-slt-meeting]], "
                      b"[[leadership/2026-04-29-slt-meeting]] |\r\n", data)
        self.assertIn(b"A note the owner wrote under the table.\r\n", data)

    def test_cross_moc_duplication_follows_tags_case_insensitively(self):
        result = self.json("pointers", "add", "knowledge/AI/northwind/2026-04-23-joint-partnership-meeting.md")
        self.assertEqual([entry["moc"] for entry in result["mocs"]],
                         ["knowledge/AI/_MOC.md", "knowledge/leadership/_MOC.md"])

    def test_extra_moc_flag(self):
        self.write("knowledge/reference/_MOC.md", "# Reference\n")
        result = self.json("pointers", "add", "knowledge/AI/ai-adoption-research.md",
                           "--moc", "knowledge/reference/_MOC.md")
        self.assertEqual(result["mocs"][-1], {"moc": "knowledge/reference/_MOC.md", "action": "created-section",
                                              "topic": "ai-adoption-research", "problem": None})
        self.assertTrue(self.text("knowledge/reference/_MOC.md").startswith("# Reference\n\n## Pointers\n"))

    def test_non_markdown_file_keeps_its_extension_in_the_link(self):
        result = self.json("pointers", "add", "knowledge/reference/report.pdf", "--topic", "lighthouse-report")
        self.assertEqual(result["link"], "[[reference/report.pdf]]")
        self.assertEqual(self.json("pointers", "check")["broken"], [])

    def test_dry_run_writes_nothing(self):
        before = self.snapshot()
        result = self.json("pointers", "add", "knowledge/AI/Vendor landscape, 2026.md", "--dry-run")
        self.assertEqual(result["changed"], ["knowledge/AI/_MOC.md"])
        self.assertEqual(self.snapshot(), before)

    def test_usage_errors(self):
        for args in (("pointers", "add", "projects/orion/CLAUDE.md"),
                     ("pointers", "add", "knowledge/AI/_MOC.md"),
                     ("pointers", "add", "knowledge/AI/nope.md"),
                     ("pointers", "add", "../elsewhere.md")):
            code, _out, _err = self.tool(*args)
            self.assertEqual(code, 64, args)


class Shapes(Blank):
    def moc(self, text):
        self.write("knowledge/AI/_MOC.md", text)
        self.write("knowledge/AI/topic-file.md", note(["topic: new-topic"]))
        result = self.add("knowledge/AI/topic-file.md")["mocs"][0]
        return result, self.text("knowledge/AI/_MOC.md")

    def test_malformed_table_is_skipped_and_reported(self):
        for name, table in {
            "wrong header": "| Subject | People | Links |\n|---|---|---|\n| a | b | c |\n",
            "no separator": "| Topic | Entities | Files |\n| a | b | [[AI/c]] |\n",
        }.items():
            with self.subTest(name):
                text = "# AI\n\n## Pointers\n\n" + table + "\nafter\n"
                result, after = self.moc(text)
                self.assertEqual(result["action"], "skipped")
                self.assertTrue(result["problem"])
                self.assertEqual(after, text)

    def test_row_with_too_few_cells_is_left_alone(self):
        text = "# AI\n\n## Pointers\n\n| Topic | Entities | Files |\n|---|---|---|\n| broken row |\n"
        result, after = self.moc(text)
        self.assertEqual(result["action"], "appended")
        self.assertEqual(after, text + "| new-topic |  | [[AI/topic-file]] |\n")

    def test_section_without_a_table_gets_one_and_keeps_its_text(self):
        text = "# AI\n\n## Pointers\n\nOwner's preamble.\n\n## Files\n- [[AI/x]]\n"
        result, after = self.moc(text)
        self.assertEqual(result["action"], "created-table")
        self.assertEqual(after, "# AI\n\n## Pointers\n\nOwner's preamble.\n\n| Topic | Entities | Files |\n|---|---|---|\n"
                                "| new-topic |  | [[AI/topic-file]] |\n\n## Files\n- [[AI/x]]\n")

    def test_no_section_appends_one_and_repairs_a_missing_final_newline(self):
        text = "# AI\n\n## Files\n- [[AI/x]]"
        result, after = self.moc(text)
        self.assertEqual(result["action"], "created-section")
        self.assertTrue(after.startswith(text + "\n\n## Pointers\n\n"))
        self.assertTrue(after.endswith("| new-topic |  | [[AI/topic-file]] |\n"))

    def test_last_row_without_newline(self):
        text = "# AI\n\n## Pointers\n\n| Topic | Entities | Files |\n|---|---|---|\n| a-b | x | [[AI/c]] |"
        result, after = self.moc(text)
        self.assertEqual(after, text + "\n| new-topic |  | [[AI/topic-file]] |\n")

    def test_fenced_example_is_not_the_table(self):
        text = ("# AI\n\n```markdown\n## Pointers\n\n| Topic | Entities | Files |\n|---|---|---|\n"
                "| new-topic | x | [[AI/example]] |\n```\n")
        result, after = self.moc(text)
        self.assertEqual(result["action"], "created-section")
        self.assertTrue(after.startswith(text))

    def test_soft_cap_is_flagged_at_eight(self):
        links = ", ".join("[[AI/f%d]]" % n for n in range(7))
        self.write("knowledge/AI/_MOC.md", "## Pointers\n\n| Topic | Entities | Files |\n|---|---|---|\n"
                                            "| new-topic | x | %s |\n" % links)
        self.write("knowledge/AI/topic-file.md", note(["topic: new-topic"]))
        result = self.add("knowledge/AI/topic-file.md")
        self.assertEqual(result["over_cap"], ["knowledge/AI/_MOC.md: new-topic (8 files)"])


class RenameAndCheck(Blank):
    MOC = ("# AI\n\n## Files\n- [[northwind/old_name|Old name]]\n- [[northwind/old_name.md]]\n\n## Pointers\n\n"
           "| Topic | Entities | Files |\n|---|---|---|\n"
           "| a-b | x | [[northwind/old_name]], [[northwind/old_name#Decisions]], [[northwind/old_name_2]] |\n\n"
           "```\n[[northwind/old_name]]\n```\n")

    def setUp(self):
        super().setUp()
        self.write("knowledge/AI/_MOC.md", self.MOC)
        self.write("knowledge/leadership/_MOC.md", "## Pointers\n\n| Topic | Entities | Files |\n|---|---|---|\n"
                                                    "| a-b | x | [[northwind/old_name]] |\n")

    def test_rename_rewrites_targets_only(self):
        result = self.json("pointers", "rename", "knowledge/northwind/old_name.md", "knowledge/northwind/2026-04-23-new.md")
        self.assertEqual(result["rewrites"], 5)
        self.assertEqual(result["changed"], ["knowledge/AI/_MOC.md", "knowledge/leadership/_MOC.md"])
        text = self.text("knowledge/AI/_MOC.md")
        self.assertIn("- [[northwind/2026-04-23-new|Old name]]\n", text)
        self.assertIn("- [[northwind/2026-04-23-new.md]]\n", text)
        self.assertIn("[[northwind/2026-04-23-new]], [[northwind/2026-04-23-new#Decisions]], [[northwind/old_name_2]] |", text)
        self.assertIn("```\n[[northwind/old_name]]\n```\n", text)     # the fenced example is untouched
        again = self.json("pointers", "rename", "northwind/old_name", "northwind/2026-04-23-new")
        self.assertEqual(again["rewrites"], 0)
        self.assertEqual(self.text("knowledge/AI/_MOC.md"), text)

    def test_prefix_rename_for_a_moved_folder(self):
        result = self.json("pointers", "rename", "northwind", "archived/northwind", "--prefix")
        self.assertEqual(result["rewrites"], 6)
        self.assertIn("[[archived/northwind/old_name_2]]", self.text("knowledge/AI/_MOC.md"))

    def test_rename_notes_flag_reaches_ordinary_notes(self):
        self.write("knowledge/AI/brief.md", "See [[northwind/old_name|the meeting]] and `[[northwind/old_name]]`.\n")
        self.write("knowledge/AI/other.md", "Nothing to change.\n")
        moc_only = self.json("pointers", "rename", "northwind/old_name", "northwind/new_name", "--dry-run")
        self.assertNotIn("knowledge/AI/brief.md", moc_only["changed"])
        result = self.json("pointers", "rename", "northwind/old_name", "northwind/new_name", "--notes")
        self.assertIn("knowledge/AI/brief.md", result["changed"])
        self.assertNotIn("knowledge/AI/other.md", result["changed"])
        self.assertEqual(self.text("knowledge/AI/brief.md"),
                         "See [[northwind/new_name|the meeting]] and `[[northwind/old_name]]`.\n")
        self.assertEqual(self.json("pointers", "rename", "northwind/old_name", "northwind/new_name", "--notes")["rewrites"], 0)

    def test_a_project_moved_into_the_vault_keeps_its_links(self):
        """The transition workflow: move the folder, then one `rename
        --prefix --notes` with workspace-relative paths."""
        self.write("projects/orion/plan.md", "plan\n")
        self.write("projects/orion/notes/kickoff.md", "kickoff\n")
        self.write("knowledge/planning/_MOC.md", "## Files\n- [[projects/orion/plan]]\n\n## Pointers\n\n"
                   "| Topic | Entities | Files |\n|---|---|---|\n"
                   "| orion-plan | priya | [[projects/orion/plan]], [[projects/orion/notes/kickoff|Kickoff]] |\n")
        self.write("knowledge/planning/review.md", "See [[projects/orion/notes/kickoff#Decisions]].\n")
        import os
        os.makedirs(str(self.path("knowledge/archive")))
        os.rename(str(self.path("projects/orion")), str(self.path("knowledge/archive/orion")))
        result = self.json("pointers", "rename", "projects/orion", "knowledge/archive/orion", "--prefix", "--notes")
        self.assertEqual(result["rewrites"], 4)
        self.assertEqual(result["changed"], ["knowledge/planning/_MOC.md", "knowledge/planning/review.md"])
        self.assertEqual(self.text("knowledge/planning/_MOC.md"),
                         "## Files\n- [[archive/orion/plan]]\n\n## Pointers\n\n"
                         "| Topic | Entities | Files |\n|---|---|---|\n"
                         "| orion-plan | priya | [[archive/orion/plan]], [[archive/orion/notes/kickoff|Kickoff]] |\n")
        self.assertEqual(self.text("knowledge/planning/review.md"), "See [[archive/orion/notes/kickoff#Decisions]].\n")
        again = self.json("pointers", "rename", "projects/orion", "knowledge/archive/orion", "--prefix", "--notes")
        self.assertEqual(again["rewrites"], 0)

    def test_a_project_moved_back_out_keeps_its_own_links(self):
        """Reverse transition: the project is outside the vault again, and
        its own notes still hold links to the archive location."""
        import os
        self.write("knowledge/archive/orion/plan.md", "See [[archive/orion/notes/kickoff|kickoff]].\n")
        self.write("knowledge/archive/orion/notes/kickoff.md", "Back to [[archive/orion/plan]].\n")
        self.write("knowledge/planning/review.md", "See [[archive/orion/plan]].\n")
        os.makedirs(str(self.path("projects")), exist_ok=True)
        os.rename(str(self.path("knowledge/archive/orion")), str(self.path("projects/orion")))
        result = self.json("pointers", "rename", "knowledge/archive/orion", "projects/orion", "--prefix", "--notes")
        self.assertEqual(result["rewrites"], 3)
        self.assertEqual(sorted(result["changed"]),
                         ["knowledge/planning/review.md", "projects/orion/notes/kickoff.md", "projects/orion/plan.md"])
        self.assertEqual(self.text("projects/orion/plan.md"), "See [[projects/orion/notes/kickoff|kickoff]].\n")
        self.assertEqual(self.text("projects/orion/notes/kickoff.md"), "Back to [[projects/orion/plan]].\n")
        self.assertEqual(self.text("knowledge/planning/review.md"), "See [[projects/orion/plan]].\n")
        again = self.json("pointers", "rename", "knowledge/archive/orion", "projects/orion", "--prefix", "--notes")
        self.assertEqual(again["rewrites"], 0)

    def test_rename_dry_run(self):
        before = self.snapshot()
        self.assertEqual(self.json("pointers", "rename", "northwind/old_name", "x/y", "--dry-run")["rewrites"], 5)
        self.assertEqual(self.snapshot(), before)

    def test_check_reports_only_missing_targets(self):
        self.write("knowledge/northwind/old_name.md", "x\n")
        result = self.json("pointers", "check")
        self.assertEqual(result["rows"], 2)
        self.assertEqual([(item["moc"], item["broken_link"]) for item in result["broken"]],
                         [("knowledge/AI/_MOC.md", "[[northwind/old_name_2]]")])
        code, _out, _err = self.tool("pointers", "check", "--strict")
        self.assertEqual(code, 1)

    def test_list(self):
        rows = self.json("pointers", "list", "knowledge/leadership/_MOC.md")["mocs"][0]["rows"]
        self.assertEqual(rows, [{"topic": "a-b", "entities": ["x"], "files": ["northwind/old_name"]}])


if __name__ == "__main__":
    unittest.main()
