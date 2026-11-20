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
