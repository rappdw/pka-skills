"""Behaviour the skill files promise and the tool has to deliver.

Each class is one place where the skills used to contradict themselves or
say nothing, and where the answer is the tool's to give:

  ArchivedProject   a transitioned project is searchable through its own
                    Repo Map row, and not without it
  EmptyFolder       the starter layout bootstrap offers in an empty folder,
                    and the state the tools report when it is declined
  AttendeesAtTheEnd `## Attendees` appended after thinkkit's sections is
                    still what timelines and `actions` read
  TourLength        the full-tour time the tutorial quotes is the sum of
                    its modules
"""
from __future__ import annotations

import os
import re
import unittest

import support

SKILLS = support.REPO / "skills"
ARCHIVE_ROW = "| `knowledge/archived/` | Old material | flat | Archive | archived | High | |\n"
ORION_ROW = "| `knowledge/archived/orion/` | Orion, completed project | by project | Reference | archived | High | |\n"


class ArchivedProject(support.ToolsCase):
    """The transition workflow of the pka-bootstrap skill: move the folder,
    `pointers rename --prefix --notes`, give the project a Reference row,
    `index`."""

    def setUp(self):
        super().setUp()
        self.write("projects/orion/alignment.md", "# Orion alignment\n\nThe zebrafinch decision.\n")
        self.write("projects/orion/docs/deep.md", "# Deep\n\nThe quokkaplan detail.\n")
        self.write("knowledge/AI/orion-notes.md", "See [[projects/orion/alignment]] for the decision.\n")
        self.ok("db", "init")
        self.ok("index")

    def found(self, term):
        return [hit["path"] for hit in self.json("search", term)["results"]]

    def move(self, old="projects/orion", new="knowledge/archived/orion"):
        os.rename(str(self.path(old)), str(self.path(new)))
        return self.json("pointers", "rename", old, new, "--prefix", "--notes")

    def set_map(self, old, new):
        text = self.text("CLAUDE.md")
        self.assertIn(old, text)
        self.write("CLAUDE.md", text.replace(old, new))

    def test_an_active_project_is_indexed_one_level_deep(self):
        self.assertEqual(self.found("zebrafinch"), ["projects/orion/alignment.md"])
        self.assertEqual(self.found("quokkaplan"), [])          # `.pkaignore`: projects/*/*/*

    def test_with_its_own_reference_row_the_whole_project_is_searchable(self):
        renamed = self.move()
        self.assertIn("knowledge/AI/orion-notes.md", renamed["changed"])
        self.set_map(ARCHIVE_ROW, ARCHIVE_ROW + ORION_ROW)
        result = self.json("index")
        self.assertEqual(result["removed"], 2)                  # the two rows under projects/orion
        self.assertEqual(self.found("zebrafinch"), ["knowledge/archived/orion/alignment.md"])
        self.assertEqual(self.found("quokkaplan"), ["knowledge/archived/orion/docs/deep.md"])
        status = self.json("status")
        self.assertIn("knowledge/archived/orion", status["index_roots"])
        self.assertNotIn("knowledge/archived", status["index_roots"])
        # The archive destination itself stays out of the index.
        self.assertNotIn("knowledge/archived/old-plan.md", self.found("plan"))
        # The fixture is an Obsidian vault, so the link is written relative to the vault.
        self.assertIn("[[archived/orion/alignment]]", self.text("knowledge/AI/orion-notes.md"))

    def test_without_the_row_the_move_takes_it_out_of_the_index(self):
        # Why the workflow adds the row before it runs `index`.
        self.move()
        result = self.json("index")
        self.assertEqual((result["added"], result["removed"]), (0, 2))
        self.assertEqual(self.found("zebrafinch"), [])
        self.assertEqual(self.found("quokkaplan"), [])
        self.assertNotIn("knowledge/archived/orion", self.json("status")["index_roots"])

    def test_adding_the_row_afterwards_repairs_it(self):
        self.move()
        self.ok("index")
        self.set_map(ARCHIVE_ROW, ARCHIVE_ROW + ORION_ROW)
        self.ok("index")
        self.assertEqual(self.found("zebrafinch"), ["knowledge/archived/orion/alignment.md"])

    def test_a_root_above_the_destination_covers_it_whatever_its_own_row_says(self):
        text = self.text("CLAUDE.md")
        head, table = text.split("| Folder |", 1)
        lines = ("| Folder |" + table).split("\n")
        rows = ("| `knowledge/` | Everything | by topic | Active | active | High | |\n" + ARCHIVE_ROW +
                "| `projects/` | Project workspaces | by project | Active | active | High | |\n")
        self.write("CLAUDE.md", head + "\n".join(lines[:2]) + "\n" + rows)
        self.ok("index")
        self.assertEqual(self.json("status")["index_roots"], ["knowledge", "projects"])
        self.assertIn("knowledge/archived/old-plan.md", self.found("plan"))
        self.move()
        self.ok("index")
        self.assertEqual(self.found("quokkaplan"), ["knowledge/archived/orion/docs/deep.md"])

    def test_restoring_puts_it_back_in_the_shallow_index(self):
        self.move()
        self.set_map(ARCHIVE_ROW, ARCHIVE_ROW + ORION_ROW)
        self.ok("index")
        self.move("knowledge/archived/orion", "projects/orion")
        self.set_map(ARCHIVE_ROW + ORION_ROW, ARCHIVE_ROW)
        self.ok("index")
        # The archive path is no longer a root, so a plain `index` does not
        # look there and its rows are left behind. `--prune` drops them.
        self.assertEqual(self.found("zebrafinch"), ["projects/orion/alignment.md",
                                                    "knowledge/archived/orion/alignment.md"])
        self.ok("index", "--prune")
        self.assertEqual(self.found("zebrafinch"), ["projects/orion/alignment.md"])
        self.assertEqual(self.found("quokkaplan"), [])
        self.assertIn("[[projects/orion/alignment]]", self.text("knowledge/AI/orion-notes.md"))

    def test_the_skill_says_row_first_then_index(self):
        skill = (SKILLS / "pka-bootstrap" / "SKILL.md").read_text(encoding="utf-8")
        workflow = skill.split("### Transition Workflow", 1)[1].split("### Reverse Transition", 1)[0]
        row = workflow.index("Give the project its own Repo Map row")
        index = workflow.index("Run `.pka/bin/pka-tools index`")
        self.assertLess(row, index)
        self.assertIn("Priority **Reference**", workflow)
        self.assertNotIn("Then run `.pka/bin/pka-tools index`.", workflow[:row])


def starter_rows() -> str:
    """The starter Repo Map as the pka-bootstrap skill prints it."""
    skill = (SKILLS / "pka-bootstrap" / "SKILL.md").read_text(encoding="utf-8")
    section = skill.split("#### An empty folder", 1)[1].split("### Step 2", 1)[0]
    block = section.split("```\n", 1)[1].split("```", 1)[0]
    return block


class EmptyFolder(support.ToolsCase):
    fixture = False

    HEAD = "<!-- PKA v1.7 | vendor-agnostic -->\n\n## Storage Mode\nMarkdown-only\n\n## Repo Map\n\n"
    TABLE_HEAD = ("| Folder | Contents | Organization | Priority | Status | Confidence | Tags |\n"
                  "|--------|----------|-------------|----------|--------|------------|------|\n")

    def setUp(self):
        super().setUp()
        for folder in ("team-inbox", "owner-inbox"):
            self.path(folder).mkdir()

    def test_the_starter_layout_is_one_the_tools_understand(self):
        rows = starter_rows()
        folders = re.findall(r"^\| `([^`]+)/` \|", rows, re.M)
        self.assertEqual(folders, ["knowledge", "knowledge/meetings", "knowledge/personnel",
                                   "knowledge/archive", "projects"])
        for folder in folders:
            self.path(folder).mkdir(parents=True)
        self.write("CLAUDE.md", self.HEAD + rows)
        status = self.json("status")
        self.assertEqual(status["vault"], "knowledge")
        self.assertEqual(status["index_roots"], ["knowledge", "projects"])
        self.assertEqual(status["meeting_homes"], ["knowledge/meetings"])
        self.assertEqual(status["people_home"], "knowledge/personnel")
        self.assertEqual(status["storage_mode"], "markdown-only")
        self.assertEqual(status["repo_map_entries"], 5)
        self.assertEqual(self.json("people", "list")["people"], [])
        self.assertEqual(self.json("lint", "--quick", "--no-report")["counts"]["4"], 5)   # all five, still empty
        # The first note filed there is read from where the layout says meetings go.
        self.write("knowledge/meetings/2026-11-20-kickoff.md",
                   "**Attendees**: Sam, Robin\n\n- [ ] **Sam**: Write the plan (due: 2026-12-01)\n")
        self.assertEqual(self.json("actions", "--all-dates")["items"][0]["owners"], ["Sam"])
        # What the skill tells the user about the first health check: the
        # folders that hold nothing yet are listed (rule 4).
        lint = self.json("lint", "--quick", "--no-report")
        self.assertEqual(lint["counts"]["4"], 3)                # personnel, archive, projects

    def test_declining_it_leaves_a_state_the_tools_report_plainly(self):
        self.write("CLAUDE.md", self.HEAD + self.TABLE_HEAD)
        status = self.json("status")
        self.assertEqual((status["index_roots"], status["meeting_homes"], status["people_home"]), ([], [], None))
        self.assertEqual(status["repo_map_entries"], 0)
        self.assertEqual(self.json("actions", "--all-dates")["open"], 0)
        self.assertEqual(self.json("lint", "--quick", "--no-report")["findings"], 0)
        code, out, err = self.tool("people", "list")
        self.assertEqual(code, 3)
        self.assertIn("people-home", err)
        self.assertNotIn("Traceback", out + err)
        self.assertEqual(len(err.strip().split("\n")), 1)
        self.assertEqual(sorted(p.name for p in self.ws.iterdir()), [".pka", "CLAUDE.md", "owner-inbox", "team-inbox"])


class AttendeesAtTheEnd(support.ToolsCase):
    """attendee-linking.md: a new `## Attendees` section is appended after
    everything else, thinkkit's sections included."""

    NOTE = "knowledge/leadership/2026-11-20-hiring-sync.md"
    THINKKIT = ("# Hiring sync\n\n**Date**: 2026-11-20\n**Attendees**: Priya (PM), Robin, Sam\n"
                "**Purpose**: Q1 hiring\n\n## Notes\n\n**Priya**: The plan needs a draft.\n\n## Action Items\n\n"
                "- [ ] **Robin**: Draft the Q1 hiring plan (due: 2026-12-01)\n\n## Open Questions\n\n"
                "- Who signs off the budget?\n")
    APPENDED = "\n## Attendees\n- [Priya](../personnel/priya/)\n- Robin\n"

    def test_the_tools_read_it_there(self):
        self.write(self.NOTE, self.THINKKIT + self.APPENDED)
        who = self.json("timeline", "who", self.NOTE)
        self.assertEqual([(p["slug"], p["tier"]) for p in who["people"]], [("priya", "T2")])
        self.assertIn("## Attendees link", who["people"][0]["evidence"][0])
        result = self.json("actions", "--under", "knowledge/leadership", "--since", "2026-11-20", "--until", "2026-11-20")
        self.assertEqual([(i["owners"], i["due"]) for i in result["items"]], [(["Robin"], "2026-12-01")])

    def test_the_header_line_alone_puts_nobody_on_a_timeline(self):
        # Why filing adds the section: thinkkit's `**Attendees**:` line is not a link.
        self.write(self.NOTE, self.THINKKIT)
        self.assertEqual(self.json("timeline", "who", self.NOTE)["people"], [])

    def test_the_reference_names_one_position(self):
        text = (SKILLS / "pka-meetings" / "references" / "attendee-linking.md").read_text(encoding="utf-8")
        section = text.split("## Creating the Attendees Section", 1)[1].split("\n## ", 1)[0]
        self.assertIn("One position: the end of the note", section)
        self.assertNotIn("Before `## Action Items`", text)
        skill = (SKILLS / "pka-meetings" / "SKILL.md").read_text(encoding="utf-8")
        self.assertIn("appended at the end of the note", skill)


class TourLength(unittest.TestCase):
    def test_the_quoted_total_is_the_sum_of_the_modules(self):
        text = (SKILLS / "pka-tutorial" / "SKILL.md").read_text(encoding="utf-8")
        minutes = [int(n) for n in re.findall(r"^### Module \d+: .*\((\d+) min\)$", text, re.M)]
        self.assertEqual(len(minutes), 11)
        self.assertTrue(all(2 <= n <= 4 for n in minutes), minutes)
        quoted = re.search(r"full tour \(eleven short modules, about (\d+) minutes", text)
        self.assertIsNotNone(quoted, "the first-session greeting no longer quotes a time")
        self.assertLessEqual(abs(int(quoted.group(1)) - sum(minutes)), 3, (quoted.group(1), sum(minutes)))
        self.assertNotIn("about 7 minutes", text)


if __name__ == "__main__":
    unittest.main()
