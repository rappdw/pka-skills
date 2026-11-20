"""`pka-tools lint`: the rules, suppression, the report and its helpers."""
from __future__ import annotations

import datetime
import hashlib
import json
import os
import shutil
import subprocess
import sys
import time

import support
import build_vault

REPORT_GLOB = "librarian-lint-*.md"
CHARTER = ["knowledge/reference/charter.md", "team-inbox/charter copy.md"]
SCANS = ["knowledge/reference/report-copy.pdf", "knowledge/reference/report.pdf"]
SPEC = ["knowledge/reference/orion-spec.md", "knowledge/topics/orion/sources/orion-spec.md"]
RESAVED = ["knowledge/AI/summary resaved.md", "knowledge/AI/summary.md"]
NEAR = ["knowledge/lab-notebook/2026-06-01-planning-2.md", "knowledge/lab-notebook/2026-06-01-planning.md"]
CONTAINED = ["knowledge/leadership/2026-06-03-raw-notes.md", "knowledge/leadership/2026-06-03-reconciled.md"]
SUPPRESSIONS = ".pka/lint-suppressions.json"


def days_from_now(days: int) -> str:
    return (datetime.date.today() + datetime.timedelta(days=days)).isoformat()


class LintCase(support.ToolsCase):
    def setUp(self) -> None:
        super().setUp()
        build_vault.lint_cases(self.ws)

    def lint(self, *args: str) -> dict:
        return self.json("lint", *args)

    def on(self, day: str):
        """Run later commands as if today were `day` (YYYY-MM-DD); None undoes it."""
        if day is None:
            self.env.pop("PKA_LINT_TODAY", None)
        else:
            self.env["PKA_LINT_TODAY"] = day

    def duplicates(self, result: dict) -> dict:
        return {tuple(m["path"] for m in item["members"]): item
                for item in result["items"] if item["rule"] in ("8a", "8b", "8c")}

    def groups(self, result: dict, rule: str) -> dict:
        return {key: item for key, item in self.duplicates(result).items() if item["rule"] == rule}

    def listed(self, result: dict) -> list:
        return [m["path"] for item in result["items"] for m in item.get("members", [])]

    def of_rule(self, result: dict, rule: str) -> list:
        return [item for item in result["items"] if item["rule"] == rule]

    def texts(self, result: dict, rule: str) -> list:
        return [item["text"] for item in self.of_rule(result, rule)]

    def tree(self) -> dict:
        """sha256 of every file in the workspace except lint's own reports."""
        out = {}
        for folder, dirs, names in os.walk(str(self.ws)):
            dirs.sort()
            for name in sorted(names):
                path = os.path.join(folder, name)
                rel = os.path.relpath(path, str(self.ws))
                if rel.startswith("owner-inbox" + os.sep + "librarian-lint-") or os.path.islink(path):
                    continue
                with open(path, "rb") as handle:
                    out[rel] = hashlib.sha256(handle.read()).hexdigest()
        return out

    def report_path(self):
        return self.path("owner-inbox/librarian-lint-%s.md" % self.env.get("PKA_LINT_TODAY", days_from_now(0)))

    def report_text(self) -> str:
        return self.report_path().read_text(encoding="utf-8")

    def fails(self, *args: str, code: int = 1) -> str:
        """Run a command that must fail cleanly; returns its stderr."""
        got, out, err = self.tool(*args)
        self.assertEqual(got, code, (args, out, err))
        self.assertNotIn("Traceback", err)
        return err


class Duplicates(LintCase):
    def test_every_seeded_duplicate_is_found(self):
        result = self.lint()
        identical = self.groups(result, "8a")
        self.assertIn(tuple(CHARTER), identical)
        self.assertIn(tuple(SCANS), identical)
        self.assertEqual(list(self.groups(result, "8b")), [tuple(RESAVED)])
        near = self.groups(result, "8c")
        self.assertEqual(sorted(near), sorted([tuple(NEAR), tuple(CONTAINED)]))
        self.assertGreaterEqual(near[tuple(NEAR)]["similarity"], 0.8)
        self.assertLess(near[tuple(CONTAINED)]["similarity"], 0.8)
        self.assertGreaterEqual(near[tuple(CONTAINED)]["containment"], 0.9)
        entities = "\n".join(self.texts(result, "8d"))
        self.assertIn('`knowledge/personnel/robin-chen/` and `knowledge/personnel/robin-smith/`: both answer to "rob"',
                      entities)
        self.assertIn("`knowledge/personnel/taylor/` and `knowledge/personnel/taylor-brooks/`: "
                      "one folder name is contained in the other", entities)
        self.assertIn("wikis sharing the topic 'orion'", entities)
        self.assertIn("`knowledge/reference/_MOC.md` has 2 Pointers rows for the topic 'lighthouse-report'", entities)

    def test_keeper_and_group_details(self):
        charter = self.groups(self.lint(), "8a")[tuple(CHARTER)]
        self.assertEqual(charter["keeper"], "knowledge/reference/charter.md")     # linked to, and not in an inbox
        by_path = {m["path"]: m for m in charter["members"]}
        self.assertEqual(by_path["knowledge/reference/charter.md"]["inbound"], 1)
        self.assertEqual(by_path["knowledge/reference/charter.md"]["relation"], "keeper")
        self.assertEqual(by_path["team-inbox/charter copy.md"]["relation"], "bytes")
        self.assertTrue(by_path["team-inbox/charter copy.md"]["inbox"])
        self.assertEqual({m["size"] for m in charter["members"]}, {len(build_vault.CHARTER)})
        self.assertRegex(by_path["team-inbox/charter copy.md"]["modified"], r"^\d{4}-\d{2}-\d{2}$")
        report = self.report_text()
        self.assertIn("| `knowledge/reference/charter.md` | %d B |" % len(build_vault.CHARTER), report)
        self.assertIn("| suggested keeper |", report)
        self.assertIn("| identical bytes |", report)

    def test_oldest_wins_when_nothing_else_differs(self):
        old = time.time() - 90 * 86400
        os.utime(str(self.path(RESAVED[0])), (old, old))
        self.assertEqual(self.groups(self.lint(), "8b")[tuple(RESAVED)]["keeper"], RESAVED[0])

    def test_allow_listed_pairs_are_not_reported(self):
        result = self.lint()
        listed = self.listed(result)
        self.assertFalse([p for p in listed if p.endswith(".pdf.txt")], "a sidecar was listed")
        self.assertFalse([p for p in listed if "_100000_sync/" in p or "slt-sync/" in p], "a capture file was listed")
        self.assertFalse([p for p in listed if p.startswith(".pka/")])
        self.assertNotIn("knowledge/leadership/2026-06-04-sync.md", listed)
        # the far copy (1 word in 12 changed) is not a near-duplicate
        self.assertNotIn("knowledge/lab-notebook/2026-06-02-different.md", listed)
        # `ai-adoption-research` is a topic in two different MOCs: not a finding
        self.assertEqual(len([t for t in self.texts(result, "8d") if "Pointers rows" in t]), 1)
        # two identical scans are one finding, not one for the scans and one for their sidecars
        self.assertEqual(len([g for g in self.duplicates(result) if any("report" in p for p in g)]), 1)

    def test_a_wiki_source_copy_is_information(self):
        result = self.lint()
        spec = self.groups(result, "8a")[tuple(SPEC)]
        self.assertEqual(spec["severity"], "info")
        self.assertTrue(spec["wiki_source_copy"])
        self.assertEqual((result["info"], result["info_counts"]["8a"], result["info_counts"]["5"]), (2, 1, 1))
        self.assertIn("### Wiki source copy (information): `%s`, `%s` [id: %s, information]"
                      % (SPEC[0], SPEC[1], spec["id"]), self.report_text())

    def test_thresholds(self):
        from pka_tools import lint
        base = build_vault.prose(7, 400)
        same = lint.shingle_hashes(lint.normalise(base))
        self.assertEqual(lint.compare(same, same), (1.0, 1.0))
        near = lint.compare(same, lint.shingle_hashes(lint.normalise(build_vault._vary(base, 100))))
        far = lint.compare(same, lint.shingle_hashes(lint.normalise(build_vault._vary(base, 12))))
        self.assertGreaterEqual(near[0], lint.SIMILARITY)
        self.assertLess(far[0], lint.SIMILARITY)
        self.assertLess(far[1], lint.CONTAINMENT)
        part = lint.shingle_hashes(lint.normalise(" ".join(base.split()[:250])))
        similarity, containment = lint.compare(same, part)
        self.assertLess(similarity, lint.SIMILARITY)
        self.assertEqual(containment, 1.0)
        # frontmatter, case and spacing do not count
        self.assertEqual(lint.normalise("---\ntags: [x]\n---\nSome   Text\n"), lint.normalise("some text"))

    def test_short_notes_are_not_compared_for_nearness(self):
        words = build_vault.prose(9, 150)
        self.write("knowledge/AI/short-a.md", words + " one\n")
        self.write("knowledge/AI/short-b.md", words + " two\n")
        self.assertNotIn("knowledge/AI/short-a.md", self.listed(self.lint()))

    def test_one_set_of_copies_is_one_finding(self):                    # M5
        body = build_vault.prose(21, 320)
        files = {
            "knowledge/AI/set original.md": "# Set\n\n" + body + "\n",
            "knowledge/AI/set same bytes.md": "# Set\n\n" + body + "\n",
            "knowledge/AI/set resaved.md": "---\ntags: [x]\n---\n# SET\n\n" + body.upper() + "\n",
            "knowledge/AI/set near.md": "# Set\n\n" + build_vault._vary(body, 100) + "\n",
        }
        for rel, text in files.items():
            self.write(rel, text)
        self.write("knowledge/AI/set index.md", "See [[AI/set near]].\n")
        mine = [item for key, item in self.duplicates(self.lint()).items() if any("AI/set " in p for p in key)]
        self.assertEqual(len(mine), 1, [m["text"] for m in mine])
        item = mine[0]
        self.assertEqual(item["rule"], "8c")
        self.assertEqual(sorted(m["path"] for m in item["members"]), sorted(files))
        self.assertEqual(item["keeper"], "knowledge/AI/set near.md")      # the one something links to
        relation = {m["path"]: m["relation"] for m in item["members"]}
        self.assertEqual(relation, {"knowledge/AI/set near.md": "keeper", "knowledge/AI/set original.md": "near",
                                    "knowledge/AI/set same bytes.md": "near", "knowledge/AI/set resaved.md": "near"})
        # in a quick lint the near copy is not looked at: the other three are one 8b finding
        quick = [item for key, item in self.duplicates(self.lint("--no-report", "--quick")).items()
                 if any("AI/set " in p for p in key)]
        self.assertEqual([(q["rule"], len(q["members"])) for q in quick], [("8b", 3)])
        self.assertEqual(sorted(m["relation"] for m in quick[0]["members"]), ["bytes", "keeper", "text"])

    def test_a_large_family_of_near_copies_is_found(self):              # M6
        body = build_vault.prose(33, 300).split()
        for number in range(60):
            words = list(body)
            words[40 + number] = "variant%d" % number
            self.write("knowledge/lab-notebook/family-%02d.md" % number, " ".join(words) + "\n")
        result = self.lint()
        family = [key for key in self.duplicates(result) if any("family-" in p for p in key)]
        self.assertEqual(len(family), 1)
        self.assertEqual(len(family[0]), 60)
        self.assertFalse([n for n in result["notes"] if "boilerplate" in n], result["notes"])

    def test_a_paragraph_between_two_rules_is_not_frontmatter(self):    # M4
        tail = "\n---\n\n" + "The shared closing section of both notes, long enough to count as real content here.\n"
        self.write("knowledge/AI/rules-a.md", "---\nFirst note, about copper and harbours and what was agreed.\n" + tail)
        self.write("knowledge/AI/rules-b.md", "---\nSecond note, about meadows and ledgers, a different subject.\n" + tail)
        self.assertFalse([p for p in self.listed(self.lint()) if "rules-" in p])

    def test_slight_files_are_not_duplicates(self):                     # L7
        for name in ("a", "b"):
            self.write("knowledge/AI/one-byte-%s.md" % name, "x")
            self.write("knowledge/AI/todo-%s.md" % name, "# TODO\n")
            self.write("knowledge/AI/tiny-%s.bin" % name, b"\x00\x01")
            self.write("knowledge/lab-notebook/2026-07-0%d.md" % (1 if name == "a" else 2),
                       "# Daily note\n\n## Morning\n\n## Afternoon\n\n## Decisions taken today\n\n## Follow-ups for tomorrow\n")
            self.write("knowledge/hand-%s/_MOC.md" % name, "# Area\n\nThe same hand-made index text in two folders, "
                       "which is how a person might well start two areas of their notes.\n")
        listed = self.listed(self.lint())
        for fragment in ("one-byte-", "todo-", "tiny-", "2026-07-0", "hand-"):
            self.assertFalse([p for p in listed if fragment in p], fragment)


class Links(LintCase):
    SOURCE = "knowledge/AI/links.md"

    def mine(self, result: dict) -> dict:
        return {i["target"]: i for i in self.of_rule(result, "2") if i["source"] == self.SOURCE}

    def test_every_link_form(self):                                     # rule 2, L3, L4
        mine = self.mine(self.lint())
        self.assertEqual(sorted(mine), sorted([
            "../reference/gone.md", "[[missing/heading]]", "[[missing/wikilink]]", "missing(20).md",
            "[[AI/AI-Adoption-Research]]", "VENDOR%20landscape,%202026.md", "../reference/gone-by-reference.md"]))
        self.assertEqual(mine["[[AI/AI-Adoption-Research]]"]["reason"], "case")
        self.assertEqual(mine["VENDOR%20landscape,%202026.md"]["reason"], "case")
        self.assertIn("differs only in upper and lower case", mine["[[AI/AI-Adoption-Research]]"]["text"])
        self.assertEqual(mine["missing(20).md"]["reason"], "missing")

    def test_a_pointer_row_link_carries_its_topic(self):
        row = [i for i in self.of_rule(self.lint(), "2") if i["target"] == "[[reference/vanished]]"][0]
        self.assertEqual((row["source"], row["topic"]), ("knowledge/reference/_MOC.md", "Lighthouse Report"))
        self.assertIn("in the Pointers row for topic 'Lighthouse Report'", row["text"])

    def test_a_bare_name_in_an_obsidian_vault(self):                    # L3
        self.write("knowledge/AI/bare.md", "[[ai-adoption-research]] [[Vendor landscape, 2026]] [[report.pdf]] "
                                           "[[nobody-has-this-name]] [[twin]]\n")
        self.write("knowledge/AI/twin.md", "one of two\n")
        self.write("knowledge/reference/twin.md", "two of two\n")
        got = {i["target"]: i for i in self.of_rule(self.lint(), "2") if i["source"] == "knowledge/AI/bare.md"}
        self.assertEqual(sorted(got), ["[[nobody-has-this-name]]", "[[twin]]"])
        self.assertEqual(got["[[twin]]"]["reason"], "ambiguous")
        self.assertIn("2 notes have that name", got["[[twin]]"]["text"])

    def test_a_bare_name_without_obsidian_is_reported_with_the_full_link(self):
        shutil.rmtree(str(self.path("knowledge/.obsidian")))
        self.write("knowledge/AI/bare.md", "[[ai-adoption-research]]\n")
        got = [i for i in self.of_rule(self.lint(), "2") if i["source"] == "knowledge/AI/bare.md"]
        self.assertEqual([(i["target"], i["suggestion"]) for i in got],
                         [("[[ai-adoption-research]]", "[[AI/ai-adoption-research]]")])

    def test_a_link_outside_the_workspace_is_not_judged(self):
        self.write("knowledge/AI/outside.md", "[up](../../../elsewhere/file.md) and [abs](/etc/hosts)\n")
        self.assertFalse([i for i in self.of_rule(self.lint(), "2") if i["source"].endswith("outside.md")])

    def test_a_list_continuation_is_not_an_indented_code_block(self):
        self.write("knowledge/AI/list.md", "- an item\n\n    continued with [gone](missing-in-list.md)\n")
        got = [i["target"] for i in self.of_rule(self.lint(), "2") if i["source"] == "knowledge/AI/list.md"]
        self.assertEqual(got, ["missing-in-list.md"])


class OtherRules(LintCase):
    OLD = "team-inbox/unsorted/old-scan.md"

    def orphans(self) -> list:
        return [(i["path"], i["age_days"]) for i in self.of_rule(self.lint("--no-report"), "1")]

    def test_orphans_not_changed_for_two_weeks(self):                   # M7
        self.assertEqual(self.orphans(), [])
        self.on(days_from_now(14))
        self.assertEqual(self.orphans(), [])
        self.on(days_from_now(30))
        self.assertEqual(sorted(self.orphans()), [("team-inbox/unsorted/new-scan.md", 30), (self.OLD, 30)])
        item = self.of_rule(self.lint("--no-report"), "1")[0]
        self.assertIn("last changed 30 days ago", item["text"])

    def test_an_old_file_dropped_in_today_is_not_an_orphan(self):       # M7
        old = time.time() - 700 * 86400
        os.utime(str(self.path(self.OLD)), (old, old))      # an old PDF copied in now: old mtime, new ctime
        self.assertEqual(self.orphans(), [])

    def test_a_capture_directory_in_unsorted_is_one_item(self):         # M7
        self.write("team-inbox/unsorted/2026-06-09_090000_sync/meeting.json", "{}\n")
        self.write("team-inbox/unsorted/2026-06-09_090000_sync/narrative.md", "what was said\n")
        self.write("team-inbox/unsorted/2026-06-09_090000_sync/audio.wav", b"RIFF")
        self.on(days_from_now(20))
        paths = [path for path, _age in self.orphans()]
        self.assertIn("team-inbox/unsorted/2026-06-09_090000_sync/", paths)
        self.assertFalse([p for p in paths if p.endswith(("meeting.json", "narrative.md", "audio.wav"))])

    def test_stale_wiki_sources(self):
        items = self.of_rule(self.lint(), "3")
        self.assertEqual([(i["wiki"], i["cited"]) for i in items],
                         [("knowledge/topics/orion/wiki.md", "knowledge/reference/withdrawn.md")])

    def test_wiki_source_forms(self):                                   # L5
        wiki = self.text("knowledge/topics/orion/wiki.md").replace(
            "## Changelog", "1. `knowledge/reference/orion-spec.md#scope` — a section of a file that is there\n"
                            "2) the notes in `knowledge/reference/numbered-gone.md`, second on the line after `mcp`\n"
                            "- see `knowledge/reference/gone.md#part` for the rest\n\n## Changelog")
        self.write("knowledge/topics/orion/wiki.md", wiki)
        cited = sorted(i["cited"] for i in self.of_rule(self.lint(), "3"))
        self.assertEqual(cited, ["knowledge/reference/gone.md#part", "knowledge/reference/numbered-gone.md",
                                 "knowledge/reference/withdrawn.md"])

    def test_empty_and_missing_repo_map_folders(self):
        folders = sorted(i["folder"] for i in self.of_rule(self.lint(), "4"))
        self.assertEqual(folders, ["knowledge/empty-area", "knowledge/never-made"])

    def test_a_folder_of_dot_markdown_files_is_not_empty(self):         # L6
        self.write("knowledge/empty-area/a.markdown", "a note with the longer extension\n")
        folders = sorted(i["folder"] for i in self.of_rule(self.lint(), "4"))
        self.assertEqual(folders, ["knowledge/never-made"])

    def test_timelines_agree_with_the_backfill_planner(self):
        item = self.of_rule(self.lint(), "5")[0]
        self.assertEqual((item["id"], item["severity"]), ("5-timelines", "info"))
        plan = self.json("timeline", "plan")
        self.assertEqual(item["lines"], len(plan["entries"]))
        self.assertEqual(item["notes"], len({e["note"] for e in plan["entries"]}))
        applied = self.json("timeline", "apply", plan["plan_file"])
        self.assertTrue(applied["verified"])
        self.assertFalse(self.of_rule(self.lint(), "5"))

    def test_the_timelines_line_cannot_be_suppressed(self):             # M1
        self.lint()
        err = self.fails("lint", "suppress", "5-timelines", code=64)
        self.assertIn("backfill timelines", err)
        self.assertIn("no-backref: true", err)
        self.assertFalse(self.path(SUPPRESSIONS).exists())
        # and an entry someone put in the file by hand hides nothing
        self.write(SUPPRESSIONS, json.dumps({"version": 1, "suppressed": {"5-timelines": {"reason": "by hand"}}}))
        result = self.lint()
        self.assertTrue(self.of_rule(result, "5"))
        self.assertEqual(result["suppressed"], 0)

    def test_information_never_fails_a_strict_run(self):                # M1
        clean = self.base / "clean"
        (clean / ".pka").mkdir(parents=True)
        (clean / "CLAUDE.md").write_text(
            "## Repo Map\n\n| Folder | Priority | Status | Tags |\n|---|---|---|---|\n"
            "| `people/` | Active | active | people-home |\n", encoding="utf-8")
        (clean / "people" / "priya").mkdir(parents=True)
        (clean / "people" / "priya" / "2026-06-01-1-1-priya.md").write_text("A 1-1.\n", encoding="utf-8")
        code, out, err = self.tool("lint", "--strict", "--json", "--workspace", str(clean))
        self.assertEqual(code, 0, out + err)
        result = json.loads(out)
        self.assertEqual((result["findings"], result["info"]), (0, 1))
        self.assertFalse(self.json("lint", "latest", "--workspace", str(clean))["mention"])

    def test_no_people_folder_is_a_note_not_an_error(self):
        shutil.rmtree(str(self.path("knowledge/personnel")))
        result = self.lint()
        self.assertFalse(self.of_rule(result, "5"))
        self.assertTrue([n for n in result["notes"] if n.startswith("Rule 5 skipped")])

    def test_a_linked_vault_is_still_scanned(self):
        elsewhere = self.base / "vault-elsewhere"
        shutil.move(str(self.path("knowledge")), str(elsewhere))
        os.symlink(str(elsewhere), str(self.path("knowledge")))
        result = self.lint()
        self.assertIn(tuple(CHARTER), self.groups(result, "8a"))
        self.assertTrue([i for i in self.of_rule(result, "2") if i["source"] == "knowledge/AI/links.md"])

    def test_quick_runs_the_fast_rules_only(self):
        result = self.lint("--quick")
        self.assertEqual(result["rules"], ["1", "2", "3", "4", "8a", "8b"])
        self.assertFalse([i for i in result["items"] if i["rule"] in ("5", "8c", "8d")])
        self.assertIn(tuple(CHARTER), self.groups(result, "8a"))
        self.assertIn("Not part of a quick lint.", self.report_text())


class RunAndReport(LintCase):
    def test_a_run_changes_nothing_but_its_report(self):
        before = self.tree()
        self.lint()
        self.lint("--quick")
        self.assertEqual(self.tree(), before)
        reports = [p.name for p in self.path("owner-inbox").glob(REPORT_GLOB)]
        self.assertEqual(reports, ["librarian-lint-%s.md" % days_from_now(0)])

    def test_two_runs_write_the_same_bytes(self):
        self.lint()
        first = self.report_text()
        self.lint()
        self.assertEqual(self.report_text(), first)
        self.assertEqual(self.lint()["items"], self.lint()["items"])

    def test_no_report_writes_nothing(self):
        before = self.tree()
        result = self.lint("--no-report")
        self.assertIsNone(result["report"])
        self.assertEqual(self.tree(), before)
        self.assertFalse(list(self.path("owner-inbox").glob(REPORT_GLOB)))

    def test_strict_exits_1_only_for_findings(self):
        code, _out, err = self.tool("lint", "--strict")
        self.assertEqual(code, 1, err)
        clean = self.base / "clean"
        (clean / ".pka").mkdir(parents=True)
        (clean / "note.md").write_text("A workspace with one note and nothing wrong.\n", encoding="utf-8")
        code, out, err = self.tool("lint", "--strict", "--workspace", str(clean))
        self.assertEqual(code, 0, out + err)

    def test_the_report_is_never_written_through_a_link(self):          # H1
        note = "knowledge/AI/ai-adoption-research.md"
        before = self.read(note)
        os.symlink(os.path.join("..", note), str(self.report_path()))
        err = self.fails("lint")
        self.assertIn("owner-inbox/librarian-lint-%s.md is a symbolic link" % days_from_now(0), err)
        self.assertNotIn(str(self.ws), err)
        self.assertEqual(self.read(note), before)
        self.assertTrue(self.report_path().is_symlink())
        # a quick run and a report-less run behave the same way and as usual
        self.fails("lint", "--quick")
        self.assertEqual(self.read(note), before)
        self.assertEqual(self.tool("lint", "--no-report")[0], 0)

    def test_owner_inbox_must_be_a_real_folder(self):                   # H1
        before = self.tree()
        shutil.rmtree(str(self.path("owner-inbox")))
        for make in (lambda p: os.symlink(str(self.base / "nowhere"), p),          # a dangling link
                     lambda p: os.symlink(str(self.base), p),                      # a link out of the workspace
                     lambda p: open(p, "w").close()):                              # a plain file
            make(str(self.path("owner-inbox")))
            err = self.fails("lint")
            self.assertIn("owner-inbox is ", err)
            self.assertNotIn("Errno", err)
            self.assertNotIn(str(self.ws), err)
            self.assertFalse(list(self.base.glob(REPORT_GLOB)))
            os.remove(str(self.path("owner-inbox")))
        self.path("owner-inbox").mkdir()
        (self.path("owner-inbox") / ".keep").write_bytes(b"")
        self.assertEqual(self.tree(), before)

    def test_the_backfill_plan_is_not_written_through_a_link_either(self):      # H1
        shutil.rmtree(str(self.path("owner-inbox")))
        outside = self.base / "outside"
        outside.mkdir()
        os.symlink(str(outside), str(self.path("owner-inbox")))
        err = self.fails("timeline", "plan")
        self.assertIn("owner-inbox is a symbolic link", err)
        self.assertEqual(list(outside.iterdir()), [])
        self.assertFalse(self.path(".pka/backfill").exists())

    def test_what_the_librarian_appended_survives_a_rerun(self):        # M2
        self.lint()
        marker = "<!-- librarian:rules-6-7 -->"
        head, _tail = self.report_text().split(marker)
        added = "\n### Contradiction candidates (1)\n- `knowledge/topics/orion/wiki.md`: 3 newer notes\n"
        self.report_path().write_text(head + marker + added, encoding="utf-8")
        self.write("knowledge/AI/another.md", "[gone](not-there.md)\n")
        result = self.lint()
        text = self.report_text()
        self.assertTrue(text.endswith(marker + added))
        self.assertIn("not-there.md", text)
        self.assertEqual(text.count(marker), 1)
        self.lint()
        self.assertEqual(self.report_text(), text)
        self.assertIsNotNone(result["report"])

    def test_a_quick_run_does_not_replace_todays_full_report(self):     # M2
        full = self.lint()
        before = self.report_text()
        quick = self.lint("--quick")
        self.assertIsNone(quick["report"])
        self.assertEqual(quick["report_kept"], full["report"])
        self.assertEqual(self.report_text(), before)
        self.assertIn("this quick run wrote nothing", self.ok("lint", "--quick"))
        # the other way round is fine: a full run replaces a quick report
        os.remove(str(self.report_path()))
        self.lint("--quick")
        self.assertEqual(self.lint()["report"], full["report"])
        self.assertIn('"mode": "full"', self.report_text().splitlines()[0])

    def test_the_report_leaves_a_place_for_the_librarian(self):
        self.lint()
        report = self.report_text()
        self.assertIn("## Librarian checks (rules 6 and 7)", report)
        self.assertIn("<!-- librarian:rules-6-7 -->", report)
        self.assertIn("Not run by the tool", report)

    def test_earlier_reports_are_not_lint_input(self):
        self.lint()
        self.write("owner-inbox/librarian-lint-2026-01-05.md", self.report_text())
        self.assertFalse([p for p in self.listed(self.lint()) if "librarian-lint-" in p])

    def test_awkward_names_do_not_break_the_report(self):               # L9
        awkward = "knowledge/AI/odd `tick` and\nnewline.md"
        self.write(awkward, build_vault.CHARTER)
        self.write("knowledge/AI/odd link.md", "[x](never%60there.md)\n")
        result = self.lint()
        self.assertIn(awkward, self.listed(result))
        report = self.report_text()
        self.assertIn("`` knowledge/AI/odd `tick` and\\nnewline.md ``", report)
        self.assertNotIn("and\nnewline.md", report)
        for line in report.splitlines():
            if line.startswith("| ") and "odd" in line:
                self.assertEqual(line.count(" | "), 4, line)

    def test_sizes_counts_and_what_was_not_read(self):                  # L9
        self.write("knowledge/reference/big-a.bin", b"\x07" * 3 * 1024 * 1024)
        self.write("knowledge/reference/big-b.bin", b"\x07" * 3 * 1024 * 1024)
        result = self.lint()
        report = self.report_text()
        self.assertIn("| 3.0 MB |", report)
        self.assertIn("| 1.8 KB |", report)
        self.assertIn("- Not read: 1 file (see \"Not read\" below)", report)
        self.assertIn("Re-save as UTF-8", report)
        self.assertIn("- `knowledge/reference/latin1.md`", report)
        # headings, the summary, the command line and JSON agree, and say what is information
        self.assertIn("## 8a. Byte-identical files (%d findings, 1 informational)" % result["counts"]["8a"], report)
        self.assertIn("## 5. Notes not on a person's timeline (1 informational)", report)
        self.assertIn("- Information: ", report)
        out = self.ok("lint", "--no-report")
        self.assertIn("%d findings, 1 informational" % result["counts"]["8a"], out)
        self.assertIn("not read: 1 file(s)", out)
        self.assertEqual(result["findings"], sum(result["counts"].values()))

    def test_a_long_rule_is_capped_in_the_report_but_not_in_json(self):  # L9
        self.write("knowledge/AI/many.md", "".join("[l%d](gone-%03d.md)\n" % (n, n) for n in range(250)))
        result = self.lint()
        mine = [i for i in self.of_rule(result, "2") if i["source"] == "knowledge/AI/many.md"]
        self.assertEqual(len(mine), 250)
        report = self.report_text()
        total = len(self.of_rule(result, "2"))
        self.assertIn("… and %d more; `pka-tools lint --json` has all of them." % (total - 200), report)
        self.assertEqual(len([line for line in report.splitlines() if "[id: 2-" in line]), 200)
        hidden = self.of_rule(result, "2")[-1]["id"]
        self.assertNotIn("[id: %s]" % hidden, report)
        self.json("lint", "suppress", hidden)               # an id past the cap can still be suppressed
        self.assertEqual(self.lint()["suppressed_ids"], [hidden])
        self.assertEqual(self.json("lint", "latest")["findings"], result["findings"] - 1)

    def test_latest(self):
        self.assertIsNone(self.json("lint", "latest")["report"])
        result = self.lint()
        latest = self.json("lint", "latest")
        self.assertEqual((latest["report"], latest["age_days"], latest["findings"], latest["mode"]),
                         (result["report"], 0, result["findings"], "full"))
        self.assertTrue(latest["mention"])
        self.on(days_from_now(30))
        latest = self.json("lint", "latest")
        self.assertEqual((latest["age_days"], latest["recent"], latest["mention"]), (30, False, False))
        self.on(None)
        self.report_path().write_text("# rewritten by hand, no header\n", encoding="utf-8")
        self.assertIsNone(self.json("lint", "latest")["findings"])

    def test_latest_counts_what_is_still_open(self):                    # L10
        result = self.lint()
        ids = [i["id"] for i in result["items"] if i["severity"] == "finding"]
        for ident in ids[:3]:
            self.json("lint", "suppress", ident)
        self.assertEqual(self.json("lint", "latest")["findings"], len(ids) - 3)
        for ident in ids[3:]:
            self.json("lint", "suppress", ident)
        latest = self.json("lint", "latest")
        self.assertEqual((latest["findings"], latest["mention"]), (0, False))

    def test_reports_with_impossible_or_future_dates_are_ignored(self):  # M3
        result = self.lint()
        for name in ("2999-01-01", "2026-13-45"):
            self.write("owner-inbox/librarian-lint-%s.md" % name,
                       '<!-- pka-lint {"version": 1, "date": "%s", "mode": "full", "findings": 99, "info": 0, '
                       '"suppressed": 0, "scanned": 1} -->\n- stray [id: 8a-0badf00d]\n' % name)
        latest = self.json("lint", "latest")
        self.assertEqual((latest["report"], latest["findings"]), (result["report"], result["findings"]))
        self.fails("lint", "suppress", "8a-0badf00d", code=64)
        ident = self.groups(result, "8a")[tuple(CHARTER)]["id"]
        self.assertFalse(self.json("lint", "suppress", ident)["already"])

    def test_schedule_prints_and_installs_nothing(self):                # L2, L11
        before = self.tree()
        result = self.json("lint", "schedule")
        self.assertFalse(result["installed"])
        self.assertIn("lint --quick --workspace '%s'" % self.ws, result["cron"])
        self.assertTrue(result["cron"].startswith("0 9 * * 1 "))
        self.assertNotIn("/dev/null", result["cron"])
        self.assertTrue(result["cron"].endswith(">> '%s/.pka/lint-cron-log.txt' 2>&1" % self.ws))
        self.assertIn("<key>StandardErrorPath</key><string>%s/.pka/lint-cron-log.txt</string>" % self.ws,
                      result["launchd_plist"])
        self.assertIn("<string>--quick</string>", result["launchd_plist"])
        self.assertIn("Nothing was installed", self.ok("lint", "schedule"))
        self.assertEqual(self.tree(), before)
        self.assertFalse(list(self.path("owner-inbox").glob(REPORT_GLOB)))

    def test_schedule_with_awkward_workspace_paths(self):               # L11
        labels = []
        for parent in ("one", "two"):
            ws = self.base / parent / "notes 100% Zoë"
            (ws / ".pka").mkdir(parents=True)
            result = self.json("lint", "schedule", "--workspace", str(ws))
            self.assertIn("notes 100\\% Zoë", result["cron"])
            self.assertNotRegex(result["cron"], r"(?<!\\)%")
            self.assertRegex(result["label"], r"^org\.pka-skills\.lint\.notes-100-zo-[0-9a-f]{8}$")
            labels.append(result["label"])
        self.assertNotEqual(labels[0], labels[1])


class Suppression(LintCase):
    def charter_id(self) -> str:
        return self.groups(self.lint(), "8a")[tuple(CHARTER)]["id"]

    def test_a_suppressed_finding_stays_suppressed(self):
        ident = self.charter_id()
        self.assertRegex(ident, r"^8a-[0-9a-f]{8}$")
        done = self.json("lint", "suppress", ident, "--reason", "the inbox copy is on purpose")
        self.assertFalse(done["already"])
        self.assertIn("`knowledge/reference/charter.md`", done["entry"]["subject"])
        for _ in range(2):
            result = self.lint()
            self.assertNotIn(tuple(CHARTER), self.groups(result, "8a"))
            self.assertEqual((result["suppressed"], result["suppressed_ids"]), (1, [ident]))
        report = self.report_text()
        self.assertNotIn(ident, report)
        self.assertIn("- Suppressed: 1", report)
        # unrelated edits, and edits to the files themselves that keep them identical, change nothing
        self.write("knowledge/AI/unrelated.md", "A new note about something else entirely.\n")
        for rel in CHARTER:
            self.write(rel, build_vault.CHARTER + "One more line in both copies.\n")
        self.assertEqual(self.lint()["suppressed_ids"], [ident])
        again = self.json("lint", "suppress", ident)
        self.assertEqual((again["already"], again["updated"]), (True, False))
        listed = self.json("lint", "suppressions")["suppressed"]
        self.assertEqual([(i["id"], i["reason"]) for i in listed], [(ident, "the inbox copy is on purpose")])
        self.json("lint", "unsuppress", ident)
        self.assertIn(tuple(CHARTER), self.groups(self.lint(), "8a"))

    def test_a_new_reason_replaces_the_old_one(self):                   # L2
        ident = self.charter_id()
        self.json("lint", "suppress", ident, "--reason", "first thought")
        again = self.json("lint", "suppress", ident, "--reason", "second thought")
        self.assertEqual((again["already"], again["updated"]), (True, True))
        self.assertEqual(self.json("lint", "suppressions")["suppressed"][0]["reason"], "second thought")

    def test_a_group_that_gains_a_file_is_a_new_finding(self):          # also L9 (singular) and L13
        ident = self.charter_id()
        self.json("lint", "suppress", ident)
        self.write("knowledge/AI/charter third.md", build_vault.CHARTER)
        result = self.lint()
        grown = [g for g in self.groups(result, "8a") if "knowledge/reference/charter.md" in g]
        self.assertEqual(len(grown), 1)
        self.assertEqual(len(grown[0]), 3)
        self.assertEqual(result["stale_suppressions"], [ident])
        self.assertIn("- 1 suppression no longer matches anything", self.report_text())
        # a quick lint does not look at every rule, so it does not say what is stale
        self.assertEqual(self.lint("--quick", "--no-report")["stale_suppressions"], [])

    def test_ids_do_not_change_between_runs_or_modes(self):
        full = {i["id"] for i in self.lint()["items"]}
        quick = {i["id"] for i in self.lint("--quick", "--no-report")["items"]}
        self.assertTrue(quick < full)
        self.assertEqual(full, {i["id"] for i in self.lint()["items"]})

    def test_an_id_from_an_earlier_report_can_be_suppressed(self):      # M3
        self.on(days_from_now(-2))
        full = self.lint()
        entity = self.of_rule(full, "8d")[0]["id"]
        self.on(None)
        self.lint("--quick")                    # today's report has no rule 8d
        self.assertNotIn(entity, self.report_text())
        self.assertFalse(self.json("lint", "suppress", entity)["already"])
        self.assertIn(entity, self.lint("--no-report")["suppressed_ids"])
        # but not from a report older than 30 days
        self.json("lint", "unsuppress", entity)
        self.on(days_from_now(40))
        self.fails("lint", "suppress", entity, code=64)

    def test_an_unknown_id_is_refused_with_near_matches(self):
        ident = self.charter_id()
        wrong = ident[:-1] + ("0" if ident[-1] != "0" else "1")
        err = self.fails("lint", "suppress", wrong, code=64)
        self.assertIn(ident, err)
        self.assertFalse(self.path(SUPPRESSIONS).exists())
        self.fails("lint", "unsuppress", ident, code=64)
        self.fails("lint", "suppress", code=64)

    def test_suppress_needs_a_report_to_take_the_id_from(self):
        err = self.fails("lint", "suppress", "8a-00000000", code=64)
        self.assertIn("run `pka-tools lint` first", err)

    def test_suppressing_several_at_once_loses_none(self):              # M8
        result = self.lint()
        ids = [i["id"] for i in result["items"] if i["severity"] == "finding"][:8]
        self.assertEqual(len(ids), 8)
        tool = str(self.ws / ".pka" / "bin" / "pka-tools")
        for _ in range(3):
            if self.path(SUPPRESSIONS).exists():
                os.remove(str(self.path(SUPPRESSIONS)))
            running = [subprocess.Popen([sys.executable, tool, "lint", "suppress", ident], cwd=str(self.ws),
                                        env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE) for ident in ids]
            for proc in running:
                _out, err = proc.communicate()
                self.assertEqual(proc.returncode, 0, err)
            stored = json.loads(self.text(SUPPRESSIONS))["suppressed"]
            self.assertEqual(sorted(stored), sorted(ids))

    def test_a_corrupt_file_is_reported_and_left_alone(self):           # also L1
        ident = self.charter_id()
        for bad in ("{not json", "[1, 2]\n", '{"suppressed": [1]}\n', "[" * 100000):
            self.write(SUPPRESSIONS, bad)
            for args in (("lint",), ("lint", "suppress", ident), ("lint", "suppressions"), ("lint", "unsuppress", ident)):
                err = self.fails(*args)
                self.assertIn("lint-suppressions.json", err)
            self.assertEqual(self.text(SUPPRESSIONS), bad)

    def test_the_suppressions_file_is_never_a_link(self):               # H1
        ident = self.charter_id()
        note = "knowledge/AI/ai-adoption-research.md"
        before = self.read(note)
        os.symlink(str(self.path(note)), str(self.path(SUPPRESSIONS)))
        for args in (("lint",), ("lint", "suppress", ident), ("lint", "suppressions")):
            err = self.fails(*args)
            self.assertIn(".pka/lint-suppressions.json is a symbolic link", err)
            self.assertNotIn(str(self.ws), err)
        self.assertEqual(self.read(note), before)

    def test_entries_it_does_not_understand_are_kept(self):
        ident = self.charter_id()
        self.write(SUPPRESSIONS, "﻿" + json.dumps(             # a byte-order mark is accepted (L2)
            {"version": 1, "suppressed": {"9z-deadbeef": {"shape": ["from", "somewhere", "else"]}},
             "something_else": {"kept": True}}))
        self.json("lint", "suppress", ident)
        data = json.loads(self.text(SUPPRESSIONS))
        self.assertEqual(data["something_else"], {"kept": True})
        self.assertEqual(data["suppressed"]["9z-deadbeef"], {"shape": ["from", "somewhere", "else"]})
        self.assertIn(ident, data["suppressed"])
        self.assertEqual(self.lint()["suppressed_ids"], [ident])

    def test_a_file_from_a_later_release_is_read_but_not_rewritten(self):       # L2
        ident = self.charter_id()
        other = self.groups(self.lint(), "8a")[tuple(SCANS)]["id"]
        text = json.dumps({"version": 7, "suppressed": {ident: {"reason": "from the future"}}, "new_field": 1})
        self.write(SUPPRESSIONS, text)
        result = self.lint()
        self.assertEqual(result["suppressed_ids"], [ident])
        self.assertTrue([n for n in result["notes"] if "later release" in n])
        self.assertTrue(self.json("lint", "suppressions")["read_only"])
        for args in (("lint", "suppress", other), ("lint", "unsuppress", ident),
                     ("lint", "suppress", ident, "--reason", "changed")):
            err = self.fails(*args)
            self.assertIn("later release", err)
        self.assertEqual(self.text(SUPPRESSIONS), text)


if __name__ == "__main__":
    import unittest
    unittest.main()
