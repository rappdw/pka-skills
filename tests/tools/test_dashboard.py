"""`pka-tools dashboard data`, and the reference page that reads what it writes."""
from __future__ import annotations

import json
import os
import re
import shutil
import subprocess
import unittest
from pathlib import Path

import support

DATA = "dashboard-data.js"
PAGE = support.REPO / "skills" / "pka-interface" / "references" / "dashboard-template.html"
SKILL_DIR = support.REPO / "skills" / "pka-interface"
HARNESS = Path(__file__).resolve().parent / "dashboard_page.js"
NODE = shutil.which("node")
NOW = "2026-11-20T09:30:00Z"

AWKWARD = "knowledge/AI/it's 100% #1 \"quoted\" & <b>? [x].md"
HOSTILE_TITLE = "Closing </script><script>alert(1)</script> tag \u2028 and <!-- a comment"


def parse(text: str) -> dict:
    """The data file as JSON: what sits between `window.PKA_DATA = ` and the final `;`."""
    head, _, rest = text.partition("\n")
    assert head.startswith("/* pka-dashboard-data v1 "), head
    prefix = "window.PKA_DATA = "
    assert rest.startswith(prefix) and rest.endswith(";\n"), rest[:40]
    return json.loads(rest[len(prefix):-2])


def files_of(data: dict) -> dict:
    """path -> {column: value}"""
    out = {}
    for row in data["files"]:
        item = dict(zip(data["file_columns"], row))
        folder = data["dirs"][item["dir"]]
        item["tags"] = [data["tags"][pos] for pos in item["tags"]]
        out[(folder + "/" if folder else "") + item["name"]] = item
    return out


class DashboardCase(support.ToolsCase):
    def index(self) -> None:
        self.ok("db", "init")
        self.ok("index")

    def data(self, *args: str) -> dict:
        self.result = self.json("dashboard", "data", *args)
        return parse(self.text(self.result["path"]))

    def page(self, data_path=None, query: str = "", page: Path = PAGE) -> dict:
        args = [NODE, str(HARNESS), str(page), str(data_path) if data_path else "", query]
        proc = subprocess.run(args, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return json.loads(proc.stdout)


class Shape(DashboardCase):
    def test_index_mode_has_what_the_views_need(self):
        self.index()
        self.ok("timeline", "add", "knowledge/leadership/2026-04-29-slt-meeting.md", "--person", "priya",
                "--summary", "Deferred the vendor decision")
        self.ok("index")
        data = self.data()
        self.assertEqual(list(data), [
            "version", "generated_at", "generated_by", "mode", "indexed_at", "root", "title", "counts", "sections",
            "dirs", "tags", "file_columns", "files", "people", "projects", "actions", "activity"])
        self.assertEqual(data["version"], 1)
        self.assertEqual(data["mode"], "index")
        self.assertEqual(data["root"], "")
        self.assertEqual(data["title"], "Sam's Personal Knowledge Assistance")
        self.assertRegex(data["generated_at"], r"^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\dZ$")
        self.assertTrue(data["indexed_at"])
        self.assertEqual(data["file_columns"],
                         ["dir", "name", "title", "date", "modified", "size", "tags", "summary", "headings"])

        files = files_of(data)
        self.assertEqual(list(files), sorted(files))
        self.assertEqual(data["counts"]["files"], len(files))
        self.assertEqual(data["counts"]["notes"], sum(1 for path in files if path.endswith(".md")))
        note = files["knowledge/AI/northwind/2026-04-23-joint-partnership-meeting.md"]
        self.assertEqual(note["title"], "Joint partnership meeting")
        self.assertEqual(note["date"], "2026-04-23")
        self.assertEqual(note["tags"], ["ai", "leadership", "meeting"])
        self.assertEqual(note["headings"], ["Action Items"])
        self.assertRegex(note["modified"], r"^\d{4}-\d\d-\d\d$")
        self.assertEqual(note["size"], len(self.read("knowledge/AI/northwind/2026-04-23-joint-partnership-meeting.md")))
        self.assertEqual(files["knowledge/AI/Vendor landscape, 2026.md"]["summary"], "No frontmatter on this one.")
        # A PDF is listed; its sidecar text gives the summary and is not a file of its own.
        self.assertIn("lighthouse", files["knowledge/reference/report.pdf"]["summary"])
        self.assertNotIn("knowledge/reference/report.pdf.txt", files)
        # A fenced example is not where a title or a summary comes from.
        self.assertEqual(files["knowledge/reference/code-fence.md"]["summary"], "Text after the fence.")
        # Navigation files, the archive and what .pkaignore hides are not listed.
        self.assertFalse([path for path in files if path.endswith("_MOC.md")])
        self.assertFalse([path for path in files if path.startswith("knowledge/archived/")])
        self.assertNotIn("projects/orion/src/main.rs", files)
        self.assertNotIn("knowledge/AI/build.log", files)
        # Only the narrative of a capture directory.
        self.assertEqual([path for path in files if path.startswith("meeting-notes/")],
                         ["meeting-notes/2026-11-10_140000_slt-sync/narrative.md"])

        sections = {item["folder"]: item for item in data["sections"]}
        self.assertEqual(sections["knowledge/leadership"]["tags"], ["meeting-home"])
        self.assertEqual(sections["knowledge/leadership"]["files"], 3)
        self.assertEqual(sections["knowledge/archived"]["priority"], "Archive")

        people = {item["slug"]: item for item in data["people"]}
        self.assertEqual(list(people), ["priya", "robin-smith", "zoë-åkesson"])
        self.assertEqual(people["priya"]["name"], "Priya Nair")
        self.assertEqual(people["priya"]["index"], "knowledge/personnel/priya/index.md")
        self.assertEqual(people["robin-smith"]["index"], "")
        self.assertEqual(people["priya"]["timeline"], [{
            "date": "2026-04-29", "kind": "meeting", "summary": "Deferred the vendor decision",
            "path": "knowledge/leadership/2026-04-29-slt-meeting.md"}])
        self.assertEqual(people["priya"]["timeline_total"], 1)

        self.assertEqual(data["projects"], [{
            "slug": "orion", "name": "Orion", "folder": "projects/orion", "has_claude_md": True, "docs": 1,
            "latest": data["projects"][0]["latest"], "status": "active", "events": []}])
        self.assertEqual([(item["path"], item["line"], item["text"]) for item in data["actions"]], [
            ("knowledge/leadership/2026-04-22-slt-meeting.md", 3, "Review the Q2 budget proposal @Sam"),
            ("knowledge/leadership/2026-04-22-slt-meeting.md", 4, "Circulate minutes"),
            ("knowledge/personnel/priya/2026-03-31-1-1-priya.md", 3, "Follow up on the adapter spike")])
        self.assertEqual(data["actions"][0]["owners"], ["Sam"])
        self.assertEqual(data["counts"]["open_actions"], 3)
        self.assertEqual(data["activity"], [
            {"at": "2026-11-01", "role": "bootstrap", "summary": "PKA initialized", "open": "", "next": ""}])

        result = self.result
        self.assertEqual(result["path"], DATA)
        self.assertEqual(result["bytes"], len(self.read(DATA)))
        self.assertEqual(result["mode"], "index")
        self.assertEqual(result["counts"], data["counts"])
        self.assertFalse(result["page"])

    def test_note_bodies_are_not_in_the_file(self):
        self.write("knowledge/AI/long.md", "# Long\n\nFirst paragraph.\n\n" + "filler words here. " * 400
                   + "\n\nxyzzy-deep-in-the-body\n")
        self.index()
        self.data()
        text = self.text(DATA)
        self.assertIn("First paragraph.", text)
        self.assertNotIn("xyzzy-deep-in-the-body", text)
        self.assertNotIn("filler words here. filler words here. filler words here. filler words here. "
                         "filler words here. filler words here. filler words here. filler words here. "
                         "filler words here. filler words here.", text)

    def test_project_status_follows_the_lifecycle_table(self):
        import sqlite3
        self.index()
        conn = sqlite3.connect(str(self.path(".pka/knowledge.db")))
        conn.execute("INSERT INTO project_lifecycle(project_slug, event, event_date, notes) "
                     "VALUES('orion', 'created', '2026-01-05', ''), ('orion', 'archiving', '2026-10-01', 'winding down'),"
                     " ('lyra', 'transitioned', '2026-06-30', 'moved to knowledge')")
        conn.commit()
        conn.close()
        projects = {item["slug"]: item for item in self.data()["projects"]}
        self.assertEqual(projects["orion"]["status"], "archiving")
        self.assertEqual([event["event"] for event in projects["orion"]["events"]], ["created", "archiving"])
        self.assertEqual(projects["lyra"]["status"], "archived")
        self.assertEqual(projects["lyra"]["folder"], "")

    def test_a_file_gone_since_the_index_is_left_out_and_counted(self):
        self.index()
        self.path("knowledge/AI/ai-adoption-research.md").unlink()
        data = self.data()
        self.assertNotIn("knowledge/AI/ai-adoption-research.md", files_of(data))
        self.assertEqual(self.result["missing"], 1)
        self.assertIn("no longer exist", self.ok("dashboard", "data"))

    def test_text_output_and_page_hint(self):
        out = self.ok("dashboard", "data")
        self.assertIn("Dashboard data written: dashboard-data.js", out)
        self.assertIn("markdown-only mode", out)
        self.assertIn("There is no dashboard.html beside it yet", out)
        self.write("dashboard.html", "<!doctype html>")
        self.assertIn("Reload dashboard.html", self.ok("dashboard", "data"))


class PlainWords(DashboardCase):
    """Titles, summaries and headings lose markdown emphasis, and only that."""

    NOTE = "knowledge/AI/snake.md"
    BODY = ("# snake_case_title and pka_tools with **bold**, _emphasis_ and `code_span`\n\n"
            "A line with under_scores and 2*3*4 stars, a __dunder__ word, *one* ~~gone~~ `x_y*z` and a lone * star.\n\n"
            "## The MAX_SIZE * 2 rule\n\n### ***Very*** important_thing\n")

    def check(self, data):
        note = files_of(data)[self.NOTE]
        self.assertEqual(note["title"], "snake_case_title and pka_tools with bold, emphasis and code_span")
        self.assertEqual(note["summary"], "A line with under_scores and 2*3*4 stars, a dunder word, one gone x_y*z "
                                          "and a lone * star.")
        self.assertEqual(note["headings"], ["The MAX_SIZE * 2 rule", "Very important_thing"])

    def test_marks_inside_words_survive_in_both_modes(self):
        self.write(self.NOTE, self.BODY)
        self.check(self.data())
        self.index()
        self.check(self.data())

    def test_unit(self):
        from pka_tools import dashboard
        for text, plain in (
                ("snake_case_title", "snake_case_title"), ("2*3", "2*3"), ("2*3*4", "2*3*4"), ("a_b_c and d_e", "a_b_c and d_e"),
                ("**bold** and __bold__", "bold and bold"), ("*it* and _it_", "it and it"), ("***both***", "both"),
                ("**_nested_**", "nested"), ("~~struck~~", "struck"), ("`code_span`", "code_span"),
                ("`a*b*c` and *c*", "a*b*c and c"), ("__init__", "init"), ("file __init__.py", "file __init__.py"),
                ("5 * 3 * 2", "5 * 3 * 2"), ("a lone _ and *", "a lone _ and *"), ("**Robin**: Draft it", "Robin: Draft it"),
                ("(*aside*)", "(aside)"), ("*not closed", "*not closed"), ("C** and D**", "C** and D**"),
                ("[label_one](x_y.md) and [[a_b|c_d]]", "label_one and c_d"), ("- [ ] **Sam** `x`", "Sam x")):
            self.assertEqual(dashboard._plain(text), plain, text)

    @unittest.skipUnless(NODE, "node is not installed: the page's search was not run")
    def test_the_page_finds_them(self):
        self.write(self.NOTE, self.BODY)
        self.data()
        for query in ("snake_case", "snake_case_title", "under_scores", "2*3", "max_size", "pka_tools"):
            self.assertEqual(self.page(self.path(DATA), query)["search"]["paths"], [self.NOTE], query)


class MarkdownOnly(DashboardCase):
    def test_same_files_and_titles_without_an_index(self):
        plain = self.data()
        self.assertEqual(plain["mode"], "markdown-only")
        self.assertEqual(plain["indexed_at"], "")
        self.assertFalse(self.path(".pka/knowledge.db").exists(), "the command must not create an index")
        self.index()
        indexed = self.data()
        self.assertEqual(indexed["mode"], "index")
        for key in ("dirs", "tags", "files", "people", "projects", "actions", "activity", "sections", "counts"):
            self.assertEqual(plain[key], indexed[key], key)

    def test_a_tag_with_a_comma_is_the_same_tags_in_both_modes(self):
        note = "knowledge/AI/comma.md"
        self.write(note, '---\ntags: ["a,b", " c ", plain]\n---\n# Comma\n')
        plain = files_of(self.data())[note]["tags"]
        self.index()
        self.assertEqual(files_of(self.data())[note]["tags"], plain)
        self.assertEqual(plain, ["a", "b", "c", "plain"])

    def test_a_file_left_out_for_its_name_is_counted_in_both_modes(self):
        try:
            self.write("knowledge/AI/back\\slash.md", "# A backslash in the name\n")
        except OSError:
            self.skipTest("this filesystem has no backslash in names")
        out = self.ok("dashboard", "data")
        self.assertIn("1 file(s) with a path that is not workspace-relative were left out.", out)
        self.assertEqual(self.json("dashboard", "data")["skipped"], 1)
        self.index()
        out = self.ok("dashboard", "data")
        self.assertNotIn("back", self.text(DATA))


class Deterministic(DashboardCase):
    def test_same_bytes_at_the_same_moment(self):
        self.index()
        self.env["PKA_DASHBOARD_NOW"] = NOW
        self.ok("dashboard", "data")
        first = self.read(DATA)
        self.ok("dashboard", "data")
        self.assertEqual(first, self.read(DATA))
        self.assertIn(b'"generated_at":"%s"' % NOW.encode(), first)

    def test_only_the_generation_time_differs_between_runs(self):
        self.env["PKA_DASHBOARD_NOW"] = NOW
        self.ok("dashboard", "data")
        first = self.text(DATA).split("\n")
        self.env["PKA_DASHBOARD_NOW"] = "2026-11-21T10:00:00Z"
        self.ok("dashboard", "data")
        second = self.text(DATA).split("\n")
        self.assertEqual(len(first), len(second))
        self.assertEqual([pos for pos, (a, b) in enumerate(zip(first, second)) if a != b], [3])
        self.assertTrue(first[3].startswith('"generated_at":'))

    def test_a_bad_moment_is_a_usage_error(self):
        self.env["PKA_DASHBOARD_NOW"] = "yesterday"
        code, _out, err = self.tool("dashboard", "data")
        self.assertEqual(code, 64)
        self.assertIn("PKA_DASHBOARD_NOW", err)
        self.assertNotIn("Traceback", err)
        self.assertFalse(self.path(DATA).exists())

    def test_nothing_else_changes(self):
        self.index()
        before = self.snapshot(".")
        self.ok("dashboard", "data")
        after = self.snapshot(".")
        self.assertEqual(self.changed(before, after), [DATA])
        self.ok("dashboard", "data")
        again = self.changed(after, self.snapshot("."))        # a second run: at most its own file, for the time in it
        self.assertEqual([name for name in again if name != DATA], [])


class Paths(DashboardCase):
    def test_no_absolute_path_anywhere(self):
        self.index()
        self.ok("timeline", "add", "knowledge/leadership/2026-04-29-slt-meeting.md", "--person", "priya")
        data = self.data()
        text = self.text(DATA)
        for needle in (str(self.ws), str(self.base), os.path.expanduser("~"), "file://", "\\\\"):
            self.assertNotIn(needle, text)
        paths = list(files_of(data)) + [a["path"] for a in data["actions"]]
        paths += [p["folder"] for p in data["people"]] + [p["folder"] for p in data["projects"]]
        paths += [e["path"] for p in data["people"] for e in p["timeline"]] + [s["folder"] for s in data["sections"]]
        for path in paths:
            self.assertFalse(path.startswith("/") or ".." in path.split("/"), path)
            self.assertTrue(self.path(path).exists(), path)

    TIMELINE_END = "<!-- /pka:timeline -->"

    def add_timeline_lines(self, *lines: str) -> None:
        self.ok("timeline", "add", "knowledge/personnel/priya/2026-03-31-1-1-priya.md")
        index = "knowledge/personnel/priya/index.md"
        text = self.text(index)
        self.assertIn(self.TIMELINE_END, text)
        self.write(index, text.replace(self.TIMELINE_END, "".join(line + "\n" for line in lines) + self.TIMELINE_END))

    def test_a_timeline_link_that_leaves_the_workspace_keeps_its_text_and_loses_its_path(self):
        outside = self.base / "outside"
        outside.mkdir()
        (outside / "secret-note.md").write_text("# Not in the workspace\n", encoding="utf-8")
        self.add_timeline_lines(
            "- 2026-11-04 · note · [[/etc/hostname]] — absolute",
            "- 2026-11-03 · note · [[../../outside/secret-note]] — up and out, the file exists",
            "- 2026-11-02 · note · [[../../outside/no-such-note]] — up and out, no such file",
            "- 2026-11-01 · note · [[%s]] — the full path" % (outside / "secret-note"),
            "- 2026-10-31 · note · [[../../../../../../../../etc/passwd]] — far up",
            "- 2026-10-30 · note · [[AI/../leadership/2026-04-29-slt-meeting]] — dots that stay inside",
            "- 2026-10-29 · note · [[AI/no-such-note]] — inside, no such file",
            "- 2026-10-28 · note · [[.obsidian/app.json]] — a hidden folder")
        for indexed in (False, True):
            if indexed:
                self.index()
            code, out, err = self.tool("dashboard", "data")
            self.assertEqual((code, err), (0, ""), "no traceback from any link text")
            self.assertIn("6 timeline link(s) lead outside the workspace or into a hidden folder", out)
            data = self.data()
            self.assertEqual(self.result["skipped_links"], 6)
            entries = {e["summary"]: e for p in data["people"] if p["slug"] == "priya" for e in p["timeline"]}
            self.assertEqual(len(entries), 9, "every entry is kept")
            self.assertEqual(entries["dots that stay inside"]["path"], "knowledge/leadership/2026-04-29-slt-meeting.md")
            for summary, entry in entries.items():
                if summary != "dots that stay inside" and entry["kind"] == "note":
                    self.assertEqual(entry["path"], "", summary)
            text = self.text(DATA)
            for needle in ("secret-note", "hostname", "passwd", "outside", "..", str(self.base), ".obsidian"):
                self.assertNotIn(needle, text)
        # The snapshot is the same whether the file outside exists or not.
        before = self.read(DATA)
        (outside / "secret-note.md").unlink()
        (outside / "no-such-note.md").write_text("now it exists\n", encoding="utf-8")
        self.ok("dashboard", "data")
        strip = lambda raw: re.sub(rb'"generated_at":"[^"]*"', b"", raw)
        self.assertEqual(strip(self.read(DATA)), strip(before))

    def test_a_workspace_without_stray_links_reports_none(self):
        self.add_timeline_lines("- 2026-10-29 · note · [[AI/no-such-note]] — inside, no such file")
        out = self.ok("dashboard", "data")
        self.assertNotIn("timeline link", out)
        self.data()
        self.assertEqual(self.result["skipped_links"], 0)

    def test_a_repo_map_row_for_a_hidden_folder_is_not_a_section(self):
        claude = self.text("CLAUDE.md")
        row = next(line for line in claude.split("\n") if line.startswith("| `knowledge/reference/`"))
        self.write("CLAUDE.md", claude.replace(row, row + "\n" + row.replace("knowledge/reference/", ".pka/")
                                               + "\n" + row.replace("knowledge/reference/", "knowledge/.obsidian/")))
        data = self.data()
        folders = [section["folder"] for section in data["sections"]]
        self.assertIn("knowledge/reference", folders)
        self.assertFalse([folder for folder in folders if folder.startswith(".") or "/." in folder], folders)

    def test_rows_with_paths_that_are_not_workspace_relative_are_left_out(self):
        import sqlite3
        self.index()
        conn = sqlite3.connect(str(self.path(".pka/knowledge.db")))
        for rel in (str(self.ws / "knowledge/AI/ai-adoption-research.md"), "./knowledge/AI/_MOC.md",
                    "../outside.md", "knowledge/.obsidian/app.json"):
            conn.execute("INSERT INTO file_index(path, folder, filename) VALUES(?, '', '')", (rel,))
        conn.commit()
        conn.close()
        self.data()
        self.assertEqual(self.result["skipped"], 4)
        self.assertNotIn(str(self.ws), self.text(DATA))
        self.assertNotIn("outside.md", self.text(DATA))
        self.assertNotIn(".obsidian", self.text(DATA))

    def test_out_elsewhere_records_the_way_back_to_the_root(self):
        data = self.data("--out", "views/board/data.js")
        self.assertEqual(self.result["path"], "views/board/data.js")
        self.assertEqual(data["root"], "../../")
        self.assertFalse(self.path(DATA).exists())

    def test_out_must_be_a_script_inside_the_workspace(self):
        for out, needle in (("../elsewhere.js", "outside the workspace"), ("notes.json", "must name a .js file"),
                            (str(self.base / "x.js"), "outside the workspace")):
            code, _out, err = self.tool("dashboard", "data", "--out", out)
            self.assertEqual(code, 64, out)
            self.assertIn(needle, err)
            self.assertNotIn("Traceback", err)

    def test_out_is_never_a_hidden_place(self):
        before = self.snapshot(".pka")
        for out in (".pka/bin/pka_tools/cli.js", ".pka/bin/data.js", ".pka/data.js", "knowledge/.obsidian/x.js",
                    ".x.js", "views/.cache/data.js", ".pka", ".pka/bin"):
            code, _out, err = self.tool("dashboard", "data", "--out", out)
            self.assertEqual(code, 64, out)
            self.assertIn("must not be a hidden file or inside a hidden folder", err)
            self.assertEqual(len(err.strip().split("\n")), 1, err)
        self.assertEqual(self.changed(before, self.snapshot(".pka")), [])
        self.assertFalse(self.path("knowledge/.obsidian/x.js").exists())
        self.assertFalse(self.path(".x.js").exists())
        self.assertFalse(self.path("views").exists())

    def test_a_folder_with_the_data_files_name_is_refused(self):
        self.path(DATA).mkdir()
        code, _out, err = self.tool("dashboard", "data")
        self.assertEqual(code, 1)
        self.assertIn("dashboard-data.js is a folder", err)
        self.assertEqual(len(err.strip().split("\n")), 1, err)
        self.assertEqual(list(self.path(DATA).iterdir()), [])

    def test_awkward_names_survive_and_links_are_encoded(self):
        self.write(AWKWARD, "# Awkward\n\nBody.\n")
        self.write("knowledge/AI/naïve café — 日本語.md", "Just text.\n")
        self.index()
        data = self.data()
        files = files_of(data)
        self.assertIn(AWKWARD, files)
        self.assertEqual(files[AWKWARD]["title"], "Awkward")
        self.assertIn("knowledge/AI/naïve café — 日本語.md", files)
        if not NODE:
            self.skipTest("node is not installed: the page's link encoding was not run")
        report = self.page(self.path(DATA))
        href = report["hrefs"][report["paths"].index(AWKWARD)]
        self.assertEqual(href, "knowledge/AI/it's%20100%25%20%231%20%22quoted%22%20%26%20%3Cb%3E%3F%20%5Bx%5D.md")
        for href in report["hrefs"]:
            self.assertNotRegex(href, r"^(/|[a-z]+:)|[#?\"<> ]")


class Generated(DashboardCase):
    def refused(self, *args: str) -> str:
        code, out, err = self.tool("dashboard", "data", *args)
        self.assertEqual(code, 1, out + err)
        self.assertNotIn("Traceback", err)
        self.assertEqual(len(err.strip().split("\n")), 1, err)
        return err

    def test_never_written_through_a_link(self):
        note = "knowledge/AI/ai-adoption-research.md"
        before = self.read(note)
        os.symlink(os.path.join("knowledge", "AI", "ai-adoption-research.md"), str(self.path(DATA)))
        self.assertIn("dashboard-data.js is a symbolic link", self.refused())
        self.assertEqual(self.read(note), before)
        self.assertTrue(self.path(DATA).is_symlink())

    def test_a_dangling_link_or_a_link_out_of_the_workspace(self):
        outside = self.base / "outside.js"
        for target in (str(self.base / "nowhere.js"), str(outside)):
            os.symlink(target, str(self.path(DATA)))
            self.assertIn("is a symbolic link", self.refused())
            self.assertFalse(outside.exists())
            self.path(DATA).unlink()

    def test_a_linked_folder_on_the_way(self):
        elsewhere = self.base / "elsewhere"
        elsewhere.mkdir()
        os.symlink(str(elsewhere), str(self.path("views")))
        self.assertIn("views is a symbolic link", self.refused("--out", "views/data.js"))
        self.assertEqual(list(elsewhere.iterdir()), [])

    def test_a_file_it_did_not_write_is_not_overwritten(self):
        self.write("knowledge/AI/mine.js", "// my own script\n")
        err = self.refused("--out", "knowledge/AI/mine.js")
        self.assertIn("was not written by `dashboard data`", err)
        self.assertEqual(self.text("knowledge/AI/mine.js"), "// my own script\n")
        # Its own earlier output is replaced.
        self.ok("dashboard", "data")
        self.ok("dashboard", "data")

    def test_an_empty_file_or_one_that_only_starts_like_ours_is_not_overwritten(self):
        foreign = (b"", b"\n", b"/* pka-dashboard-data v", b"/* pka-dashboard-data v1 */\nmy own notes\n",
                   b"/* pka-dashboard-data vNEXT - written by me */\nwindow.MINE = 1;\n",
                   b"/* pka-dashboard-data v1 \xe2\x80\x94 written by `pka-tools dashboard data`. Do not edit */\n",
                   b"\xff\xfe not text")
        for content in foreign:
            self.write(DATA, content)
            err = self.refused()
            self.assertIn("dashboard-data.js exists and was not written by `dashboard data`", err)
            self.assertEqual(self.read(DATA), content)
        # Its own file is replaced, also one written by a later format, with a BOM or CRLF.
        self.path(DATA).unlink()
        self.ok("dashboard", "data")
        own = self.text(DATA)
        for variant in (own.replace(" v1 ", " v12 ", 1), "\ufeff" + own, own.replace("\n", "\r\n")):
            self.write(DATA, variant)
            self.ok("dashboard", "data")
            self.assertEqual(self.text(DATA).split("\n", 1)[0], own.split("\n", 1)[0])

    def test_a_folder_that_cannot_be_written_is_one_line_without_an_absolute_path(self):
        if hasattr(os, "geteuid") and os.geteuid() == 0:
            self.skipTest("root ignores permission bits")
        self.path("views").mkdir()
        os.chmod(str(self.path("views")), 0o555)
        try:
            err = self.refused("--out", "views/data.js")
        finally:
            os.chmod(str(self.path("views")), 0o755)
        self.assertIn("dashboard data not written: views/data.js could not be written (Permission denied)", err)
        self.assertNotIn(str(self.base), err)
        self.assertNotIn("pka-tmp", err)

    def test_no_workspace(self):
        empty = self.base / "empty"
        empty.mkdir()
        code, _out, err = self.tool("dashboard", "data", "--workspace", str(empty))
        self.assertNotEqual(code, 0)
        self.assertNotIn("Traceback", err)
        self.assertEqual(list(empty.iterdir()), [])


class Injection(DashboardCase):
    def setUp(self) -> None:
        super().setUp()
        self.write("knowledge/AI/hostile.md",
                   "---\ntitle: \"%s\"\ntags: [\"</script>\", \"a&b\"]\n---\n\n"
                   "Summary with </script><img src=x onerror=alert(2)> and \u2029 in it.\n\n"
                   "## Heading </script>\n\n- [ ] Do </script> thing\n" % HOSTILE_TITLE)
        self.write("knowledge/leadership/2026-06-01-<script>alert(3)<!--.md", "- [ ] Close </script> the loop\n")
        self.write(".pka/session-log.md", "## 2026-11-02 09:00 | librarian | Filed </script><b>x</b> | — | —\n")

    def test_the_file_cannot_end_a_script_element_or_a_line(self):
        for indexed in (False, True):
            if indexed:
                self.index()
            data = self.data()
            text = self.text(DATA)
            self.assertNotIn("</", text[text.index("\n"):])
            self.assertNotIn("<!--", text)
            self.assertNotIn("\u2028", text)
            self.assertNotIn("\u2029", text)
            self.assertNotIn("<", text[text.index("\n"):])
            files = files_of(data)
            self.assertEqual(files["knowledge/AI/hostile.md"]["title"], " ".join(HOSTILE_TITLE.split()))
            self.assertIn("</script>", files["knowledge/AI/hostile.md"]["tags"])
            self.assertIn("knowledge/leadership/2026-06-01-<script>alert(3)<!--.md", files)
            self.assertTrue(any("</script>" in item["text"] for item in data["actions"]))
            self.assertIn("</script>", data["activity"][0]["summary"])

    @unittest.skipUnless(NODE, "node is not installed: the page was not run")
    def test_the_page_shows_it_as_text(self):
        self.index()
        self.data()
        report = self.page(self.path(DATA), "closing")
        self.assertIsNone(report["error"])
        self.assertTrue(report["ok"])
        self.assertEqual(report["search"]["paths"], ["knowledge/AI/hostile.md"])
        shown = "\n".join(view["html"] for view in report["views"]) + report["searchHtml"]
        self.assertIn("&lt;/script&gt;", shown)
        for needle in ("<script", "</script", "<img", "<b>x</b>", "onerror=alert(2)>"):
            self.assertNotIn(needle, shown.replace("&lt;img src=x onerror=alert(2)&gt;", ""))

    @unittest.skipUnless(NODE, "node is not installed: the page was not run")
    def test_a_page_that_inlines_the_data_still_parses(self):
        self.index()
        self.data()
        html = PAGE.read_text(encoding="utf-8")
        tag = '<script src="dashboard-data.js"></script>'
        self.assertEqual(html.count(tag), 1)
        inlined = self.base / "inlined.html"
        inlined.write_text(html.replace(tag, "<script>\n%s</script>" % self.text(DATA)), encoding="utf-8")
        report = self.page(None, "closing", page=inlined)
        self.assertIsNone(report["error"])
        self.assertTrue(report["ok"])
        self.assertEqual(report["external"], [])
        self.assertEqual(report["search"]["paths"], ["knowledge/AI/hostile.md"])


@unittest.skipUnless(NODE, "node is not installed: the reference page's scripts were not run")
class ReferencePage(DashboardCase):
    def test_the_loader_reads_the_snapshot_and_every_view_draws(self):
        self.index()
        self.ok("timeline", "add", "knowledge/leadership/2026-04-29-slt-meeting.md", "--person", "priya",
                "--summary", "Deferred the vendor decision")
        self.ok("index")
        data = self.data()
        report = self.page(self.path(DATA), "budget")
        self.assertIsNone(report["error"])
        self.assertEqual(report["external"], ["dashboard-data.js"])
        self.assertTrue(report["ok"], report["problem"])
        self.assertEqual(report["files"], data["counts"]["files"])
        self.assertEqual(report["paths"], list(files_of(data)))
        self.assertEqual(report["people"], ["priya", "robin-smith", "zoë-åkesson"])
        self.assertEqual(report["mode"], "index")
        self.assertEqual(report["title"], "Sam's Personal Knowledge Assistance")
        self.assertIn("index mode", report["status"])
        self.assertIn("pka-tools dashboard data", report["status"])
        self.assertEqual(report["problemShown"], "")
        # Titles: from the note, else from the filename.
        titles = dict(zip(report["paths"], report["titles"]))
        self.assertEqual(titles["knowledge/leadership/2026-04-22-slt-meeting.md"], "SLT meeting")
        self.assertEqual(titles["knowledge/leadership/2026-05-06-budget review.md"], "Budget review")
        self.assertEqual(titles["knowledge/lab-notebook/2026-04-22.md"], "2026-04-22")

        views = {view["id"]: view for view in report["views"]}
        self.assertEqual(sorted(view["view"] for view in report["views"]),
                         ["actions", "activity", "calendar", "files", "people", "projects", "search", "timeline", "topics"])
        expect = {
            "actions": ["Review the Q2 budget proposal @Sam", 'href="knowledge/leadership/2026-04-22-slt-meeting.md"'],
            "personnel": ["Priya Nair", 'href="knowledge/personnel/priya/index.md"', "Deferred the vendor decision",
                          'href="knowledge/leadership/2026-04-29-slt-meeting.md"', "Zoë Åkesson"],
            "leadership": ["2026-05-06", 'href="knowledge/leadership/2026-05-06-budget%20review.md"', "SLT meeting"],
            "research": ["Northwind", 'href="knowledge/AI/northwind/"', "Vendor landscape, 2026"],
            "lab-notebook": ['href="knowledge/lab-notebook/2026-04-23.md"', 'class="heat"'],
            "projects": ["Orion", 'href="projects/orion/"', "has CLAUDE.md"],
            "reference": ['href="knowledge/reference/report.pdf"', "<table>"],
            "activity": ["PKA initialized", "Recently changed files"],
            "search": ['id="q"'],
        }
        for name, needles in expect.items():
            for needle in needles:
                self.assertIn(needle, views[name]["html"], name)
        for view in report["views"]:
            self.assertTrue(view["html"].strip(), view["id"])
            for bad in ("undefined", "NaN", "[object", "file://", "could not be shown"):
                self.assertNotIn(bad, view["html"], view["id"])
        self.assertEqual(report["search"]["paths"], ["knowledge/leadership/2026-05-06-budget review.md",
                                                     "knowledge/leadership/2026-04-22-slt-meeting.md"])
        self.assertIn("<mark>Budget</mark> review", report["searchHtml"])

    def test_search_covers_titles_paths_tags_headings_summaries_and_people(self):
        self.index()
        self.data()
        for query, expected in (
                ("joint partnership", ["knowledge/AI/northwind/2026-04-23-joint-partnership-meeting.md"]),   # title
                ("zurich", ["knowledge/AI/northwind/Übersicht – Zürich.md"]),                                # accents folded
                ("strategy", ["knowledge/AI/ai-adoption-research.md"]),                                      # tag
                ("action items", ["knowledge/AI/northwind/2026-04-23-joint-partnership-meeting.md"]),        # heading
                ("lighthouse december", ["meeting-notes/2026-11-10_140000_slt-sync/narrative.md"]),          # summary
                ("hiring plan", ["knowledge/personnel/robin-smith/2026-04-22-1on1.md"]),
        ):
            self.assertEqual(self.page(self.path(DATA), query)["search"]["paths"], expected, query)
        self.assertEqual(self.page(self.path(DATA), "nair")["search"]["people"], ["priya"])
        # The body of a note is not searched, and the page says so.
        self.write("knowledge/AI/deep.md", "# Deep\n\nFirst.\n\nSecond paragraph mentions quokka.\n")
        self.ok("index")
        self.data()
        report = self.page(self.path(DATA), "quokka")
        self.assertEqual(report["search"]["total"], 0)
        self.assertIn("Only titles, paths, tags, headings and summaries are searched", report["searchHtml"])

    def test_a_folder_named_like_a_built_in_is_a_folder_like_any_other(self):
        names = ("constructor", "toString", "valueOf", "__proto__", "hasOwnProperty", "prototype", "watch")
        for name in names:
            self.write("knowledge/AI/%s/note.md" % name, "# Note %d\n\nSummary number %d.\n" % ((names.index(name),) * 2))
            self.write("knowledge/lab-notebook/%s/2026-04-2%d.md" % (name, names.index(name)), "# Entry\n")
            self.write("knowledge/reference/%s/toString" % name, "plain\n")
        self.write("knowledge/AI/__proto__/constructor.md", "# Second\n")
        for indexed in (False, True):
            if indexed:
                self.index()
            self.data()
            report = self.page(self.path(DATA), "constructor")
            self.assertIsNone(report["error"])
            self.assertTrue(report["ok"], report["problem"])
            views = {view["id"]: view for view in report["views"]}
            for view in report["views"]:
                self.assertNotIn("could not be shown", view["html"], view["id"])
                self.assertNotIn("function ", view["html"], view["id"])
                self.assertNotIn("[native code]", view["html"], view["id"])
            for name in names:
                self.assertIn('href="knowledge/AI/%s/"' % name, views["research"]["html"], name)
                self.assertIn("Summary number %d." % names.index(name), views["research"]["html"], name)
            self.assertIn("2 files", views["research"]["html"])
            self.assertIn("knowledge/AI/constructor/note.md", report["search"]["paths"])

    def test_a_status_or_a_column_named_like_a_built_in(self):
        self.data()
        text = self.text(DATA)
        odd = self.base / "odd.js"
        odd.write_text(text.replace('"status":"active"', '"status":"constructor"'), encoding="utf-8")
        self.assertIn('"status":"constructor"', odd.read_text(encoding="utf-8"))
        report = self.page(odd)
        views = {view["id"]: view for view in report["views"]}
        self.assertIn('<span class="badge constructor">constructor</span>', views["projects"]["html"])
        self.assertNotIn("function", views["projects"]["html"])

    def test_search_marks_words_with_accents(self):
        self.index()
        self.data()
        report = self.page(self.path(DATA), "zurich ubersicht")
        self.assertEqual(report["search"]["paths"], ["knowledge/AI/northwind/Übersicht – Zürich.md"])
        self.assertIn("<mark>Übersicht</mark> – <mark>Zürich</mark>", report["searchHtml"])
        report = self.page(self.path(DATA), "budget")
        self.assertIn("<mark>Budget</mark> review", report["searchHtml"])
        # What is marked is still escaped.
        self.write("knowledge/AI/tags.md", "# A <b>bold</b> café & more\n")
        self.ok("index")
        self.data()
        self.assertIn("A &lt;b&gt;bold&lt;/b&gt; <mark>café</mark> &amp; more", self.page(self.path(DATA), "cafe")["searchHtml"])

    def test_incomplete_data_says_so_instead_of_staying_on_loading(self):
        self.data()
        text = self.text(DATA)
        cases = {
            "no-columns": re.sub(r'"file_columns":\[[^\]]*\],\n', "", text),
            "no-tags": re.sub(r'\n"tags":\[[^\]]*\],', "", text),
            "odd-rows": re.sub(r'"files":\[\n\[', '"files":[\nnull,\n[', text),
            "cut-short": text[: len(text) // 2],
        }
        for name, changed in cases.items():
            self.assertNotEqual(changed, text, name)
            path = self.base / (name + ".js")
            path.write_text(changed, encoding="utf-8")
            report = self.page(path)
            self.assertIsNone(report["error"], name)
            self.assertFalse(report["ok"], name)
            self.assertEqual(report["status"], "No data", name)
            self.assertIn("pka-tools dashboard data", report["problemShown"], name)
            self.assertNotIn("undefined", report["problemShown"], name)
        self.assertIn("it has no <code>file_columns</code> list", self.page(self.base / "no-columns.js")["problemShown"])
        self.assertIn("it has no <code>tags</code> list", self.page(self.base / "no-tags.js")["problemShown"])
        self.assertIn("could not be read", self.page(self.base / "odd-rows.js")["problemShown"])
        self.assertIn("or it is incomplete and could not be read", self.page(self.base / "cut-short.js")["problemShown"])

    def test_data_dated_in_the_future_is_not_minus_days_ago(self):
        self.data()
        for stamp in ("2099-01-01T00:00:00Z", "not a date"):
            path = self.base / "future.js"
            path.write_text(re.sub(r'"generated_at":"[^"]*"', '"generated_at":"%s"' % stamp, self.text(DATA)), encoding="utf-8")
            status = self.page(path)["status"]
            self.assertNotIn("days ago", status)
            self.assertNotIn("-", status.split("·")[0].split("(")[-1] if "(" in status.split("·")[0] else "")
            self.assertNotIn("Invalid Date", status)
            self.assertNotIn("NaN", status)

    def test_open_actions_are_plain_words_and_say_the_due_date_once(self):
        note = "knowledge/leadership/2026-11-20-hiring-sync.md"
        self.write(note, "**Attendees**: Robin, Sam\n\n"
                         "- [ ] **Robin**: Draft the `Q1_plan` (due: Dec 1)\n"
                         "- [ ] Send the comparison — @Sam — by 2026-11-28\n"
                         "- [ ] **Sam**: Book rooms (due: Friday)\n")
        data = self.data()
        got = {a["line"]: a for a in data["actions"] if a["path"] == note}
        self.assertEqual((got[3]["text"], got[3]["owners"], got[3]["due"], got[3]["due_text"]),
                         ("Robin: Draft the Q1_plan (due: Dec 1)", ["Robin"], "2026-12-01", "Dec 1"))
        self.assertEqual((got[4]["due"], got[4]["due_text"]), ("2026-11-28", "2026-11-28"))
        self.assertEqual((got[5]["text"], got[5]["due"], got[5]["due_text"]), ("Sam: Book rooms (due: Friday)", "", "Friday"))
        html = {view["id"]: view for view in self.page(self.path(DATA))["views"]}["actions"]["html"]
        self.assertIn("Robin: Draft the Q1_plan (due: Dec 1) <span class=\"badge quiet\">due 2026-12-01</span>", html)
        self.assertIn("Send the comparison — @Sam — by 2026-11-28<div", html)
        self.assertEqual(html.count("2026-11-28"), 1, "a date written in the item is not repeated as a badge")
        self.assertNotIn("**", html)
        self.assertIn("Sam: Book rooms (due: Friday)<div", html)

    def test_markdown_only_mode_draws_the_same_views(self):
        self.data()
        report = self.page(self.path(DATA), "budget")
        self.assertIsNone(report["error"])
        self.assertTrue(report["ok"])
        self.assertIn("markdown-only mode", report["status"])
        self.assertEqual(len(report["search"]["paths"]), 2)
        for view in report["views"]:
            self.assertTrue(view["html"].strip(), view["id"])

    def test_without_the_data_file_the_page_says_what_to_do(self):
        report = self.page(None)
        self.assertIsNone(report["error"])
        self.assertFalse(report["ok"])
        self.assertIn("dashboard-data.js", report["problemShown"])
        self.assertIn("pka-tools dashboard data", report["problemShown"])
        self.assertIn("was not found beside this page, or it is incomplete", report["problemShown"])

    def test_data_from_a_later_format_is_refused_politely(self):
        self.data()
        later = self.base / "later.js"
        later.write_text(self.text(DATA).replace('"version":1,', '"version":2,'), encoding="utf-8")
        report = self.page(later)
        self.assertIsNone(report["error"])
        self.assertFalse(report["ok"])
        self.assertIn("update the dashboard", report["problemShown"])

    def test_data_written_elsewhere_links_back_to_the_root(self):
        self.data("--out", "views/data.js")
        report = self.page(self.path("views/data.js"))
        self.assertTrue(all(href.startswith("../knowledge/") or href.startswith("../projects/")
                            or href.startswith("../meeting-notes/") for href in report["hrefs"]))


class SkillText(unittest.TestCase):
    """The skill's own files: nothing fetched, nothing from the network, no
    table or column the tool does not create."""

    def texts(self) -> dict:
        return {path.relative_to(SKILL_DIR).as_posix(): path.read_text(encoding="utf-8")
                for path in sorted(SKILL_DIR.rglob("*")) if path.is_file()}

    def test_the_page_needs_nothing_but_the_data_file(self):
        html = PAGE.read_text(encoding="utf-8")
        self.assertEqual(re.findall(r'<script[^>]*\bsrc="([^"]*)"', html), ["dashboard-data.js"])
        for needle in ("http://", "https://", "//cdn", "fetch(", "XMLHttpRequest", "import(", "sql.js", "initSqlJs",
                       "showDirectoryPicker", "file:///", "<link", "@import", "url("):
            self.assertNotIn(needle, html, needle)

    def test_section_markers_are_paired(self):
        html = PAGE.read_text(encoding="utf-8")
        starts = re.findall(r"<!-- pka:section:start:([\w-]+) -->", html)
        ends = re.findall(r"<!-- pka:section:end:([\w-]+) -->", html)
        self.assertEqual(starts, ends)
        self.assertIn("search", starts)
        self.assertIn("activity", starts)
        self.assertEqual(len(starts), len(set(starts)))
        for block in ("loader", "views"):
            self.assertEqual(html.count("<!-- pka:%s:start" % block), 1)
            self.assertEqual(html.count("<!-- pka:%s:end -->" % block), 1)

    def test_no_instruction_depends_on_what_does_not_exist(self):
        for name, text in self.texts().items():
            for needle in ("personnel_index", "leadership_index", "projects_index", "person_slug", "note_date",
                           "has_claude_md, last_modified", "cdnjs", "initSqlJs", "db.exec", "https://"):
                self.assertNotIn(needle, text, "%s mentions %s" % (name, needle))

    def test_every_view_named_in_the_references_exists_in_the_page(self):
        html = PAGE.read_text(encoding="utf-8")
        defined = set(re.findall(r"VIEWS\.(\w+) = function", html))
        self.assertEqual(defined, {"people", "timeline", "topics", "calendar", "projects", "files", "actions",
                                   "activity", "search"})
        for name, text in self.texts().items():
            if name.endswith(".md"):
                for view in re.findall(r'data-view="(\w+)"', text):
                    self.assertIn(view, defined, "%s names a view the page does not have: %s" % (name, view))


if __name__ == "__main__":
    unittest.main()
