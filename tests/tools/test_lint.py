"""`pka-tools lint`: the rules, suppression, the report and its helpers."""
from __future__ import annotations

import datetime
import hashlib
import json
import os
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


class LintCase(support.ToolsCase):
    def setUp(self) -> None:
        super().setUp()
        build_vault.lint_cases(self.ws)

    def lint(self, *args: str) -> dict:
        return self.json("lint", *args)

    def groups(self, result: dict, rule: str) -> dict:
        return {tuple(m["path"] for m in item["members"]): item
                for item in result["items"] if item["rule"] == rule}

    def texts(self, result: dict, rule: str) -> list:
        return [item["text"] for item in result["items"] if item["rule"] == rule]

    def tree(self) -> dict:
        """sha256 of every file in the workspace except lint's own reports."""
        out = {}
        for folder, dirs, names in os.walk(str(self.ws)):
            dirs.sort()
            for name in sorted(names):
                path = os.path.join(folder, name)
                rel = os.path.relpath(path, str(self.ws))
                if rel.startswith("owner-inbox" + os.sep + "librarian-lint-"):
                    continue
                with open(path, "rb") as handle:
                    out[rel] = hashlib.sha256(handle.read()).hexdigest()
        return out

    def report_text(self) -> str:
        reports = sorted(self.path("owner-inbox").glob(REPORT_GLOB))
        self.assertTrue(reports)
        return reports[-1].read_text(encoding="utf-8")


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
        self.assertTrue(by_path["team-inbox/charter copy.md"]["inbox"])
        self.assertEqual({m["size"] for m in charter["members"]}, {len(build_vault.CHARTER)})
        self.assertRegex(by_path["team-inbox/charter copy.md"]["modified"], r"^\d{4}-\d{2}-\d{2}$")
        report = self.report_text()
        self.assertIn("| `knowledge/reference/charter.md` | %d |" % len(build_vault.CHARTER), report)
        self.assertIn("suggested keeper", report)

    def test_oldest_wins_when_nothing_else_differs(self):
        old = time.time() - 90 * 86400
        os.utime(str(self.path(RESAVED[0])), (old, old))
        self.assertEqual(self.groups(self.lint(), "8b")[tuple(RESAVED)]["keeper"], RESAVED[0])

    def test_allow_listed_pairs_are_not_reported(self):
        result = self.lint()
        listed = [m["path"] for item in result["items"] for m in item.get("members", [])]
        self.assertFalse([p for p in listed if p.endswith(".pdf.txt")], "a sidecar was listed")
        self.assertFalse([p for p in listed if "_100000_sync/" in p or "slt-sync/" in p], "a capture file was listed")
        self.assertFalse([p for p in listed if p.startswith(".pka/")])
        self.assertNotIn("knowledge/leadership/2026-06-04-sync.md", listed)
        # the far copy (1 word in 12 changed) is not a near-duplicate
        self.assertNotIn("knowledge/lab-notebook/2026-06-02-different.md", listed)
        # `ai-adoption-research` is a topic in two different MOCs: not a finding
        self.assertEqual(len([t for t in self.texts(result, "8d") if "Pointers rows" in t]), 1)
        # two identical scans are one finding, not one for the scans and one for their sidecars
        self.assertEqual(len([g for g in self.groups(result, "8a") if any("report" in p for p in g)]), 1)

    def test_a_wiki_source_copy_is_information(self):
        result = self.lint()
        spec = self.groups(result, "8a")[tuple(SPEC)]
        self.assertEqual(spec["severity"], "info")
        self.assertTrue(spec["wiki_source_copy"])
        self.assertEqual(result["info"], 2)                 # this, and the timelines line
        self.assertIn("### Wiki source copy (information): `%s`, `%s` [id: %s]" % (SPEC[0], SPEC[1], spec["id"]),
                      self.report_text())
        for rule in ("8b", "8c"):
            self.assertNotIn(tuple(SPEC), self.groups(result, rule))

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
        result = self.lint()
        listed = [p for g in self.groups(result, "8c") for p in g]
        self.assertNotIn("knowledge/AI/short-a.md", listed)


class OtherRules(LintCase):
    def test_orphans_older_than_two_weeks(self):
        old = time.time() - 30 * 86400
        os.utime(str(self.path("team-inbox/unsorted/old-scan.md")), (old, old))
        items = [i for i in self.lint()["items"] if i["rule"] == "1"]
        self.assertEqual([i["path"] for i in items], ["team-inbox/unsorted/old-scan.md"])
        self.assertEqual(items[0]["age_days"], 30)

    def test_every_link_form(self):
        result = self.lint()
        mine = sorted(i["target"] for i in result["items"] if i["rule"] == "2" and i["source"] == "knowledge/AI/links.md")
        self.assertEqual(mine, ["../reference/gone.md", "[[ai-adoption-research]]", "[[missing/heading]]",
                                "[[missing/wikilink]]"])
        bare = [i for i in result["items"] if i["rule"] == "2" and i["target"] == "[[ai-adoption-research]]"][0]
        self.assertEqual(bare["suggestion"], "[[AI/ai-adoption-research]]")
        row = [i for i in result["items"] if i["rule"] == "2" and i["target"] == "[[reference/vanished]]"][0]
        self.assertEqual((row["source"], row["topic"]), ("knowledge/reference/_MOC.md", "Lighthouse Report"))
        self.assertIn("in the Pointers row for topic 'Lighthouse Report'", row["text"])

    def test_a_link_outside_the_workspace_is_not_judged(self):
        self.write("knowledge/AI/outside.md", "[up](../../../elsewhere/file.md) and [abs](/etc/hosts)\n")
        self.assertFalse([i for i in self.lint()["items"] if i["rule"] == "2" and i["source"].endswith("outside.md")])

    def test_stale_wiki_sources(self):
        items = [i for i in self.lint()["items"] if i["rule"] == "3"]
        self.assertEqual([(i["wiki"], i["cited"]) for i in items],
                         [("knowledge/topics/orion/wiki.md", "knowledge/reference/withdrawn.md")])

    def test_empty_and_missing_repo_map_folders(self):
        items = sorted(i["folder"] for i in self.lint()["items"] if i["rule"] == "4")
        self.assertEqual(items, ["knowledge/empty-area", "knowledge/never-made"])

    def test_timelines_agree_with_the_backfill_planner(self):
        item = [i for i in self.lint()["items"] if i["rule"] == "5"][0]
        self.assertEqual((item["id"], item["severity"]), ("5-timelines", "info"))
        plan = self.json("timeline", "plan")
        self.assertEqual(item["lines"], len(plan["entries"]))
        self.assertEqual(item["notes"], len({e["note"] for e in plan["entries"]}))
        applied = self.json("timeline", "apply", plan["plan_file"])
        self.assertTrue(applied["verified"])
        self.assertFalse([i for i in self.lint()["items"] if i["rule"] == "5"])

    def test_no_people_folder_is_a_note_not_an_error(self):
        import shutil
        shutil.rmtree(str(self.path("knowledge/personnel")))
        result = self.lint()
        self.assertFalse([i for i in result["items"] if i["rule"] == "5"])
        self.assertTrue([n for n in result["notes"] if n.startswith("Rule 5 skipped")])

    def test_a_linked_vault_is_still_scanned(self):
        import shutil
        elsewhere = self.base / "vault-elsewhere"
        shutil.move(str(self.path("knowledge")), str(elsewhere))
        os.symlink(str(elsewhere), str(self.path("knowledge")))
        result = self.lint()
        self.assertIn(tuple(CHARTER), self.groups(result, "8a"))
        self.assertTrue([i for i in result["items"] if i["rule"] == "2" and i["source"] == "knowledge/AI/links.md"])

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
        self.assertEqual(reports, ["librarian-lint-%s.md" % datetime.date.today().isoformat()])

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
        clean = support.ToolsCase.path(self, "..") / "clean"
        clean.mkdir()
        (clean / ".pka").mkdir()
        (clean / "note.md").write_text("A workspace with one note and nothing wrong.\n", encoding="utf-8")
        code, out, err = self.tool("lint", "--strict", "--workspace", str(clean))
        self.assertEqual(code, 0, out + err)

    def test_the_report_leaves_a_place_for_the_librarian(self):
        self.lint()
        report = self.report_text()
        self.assertIn("## Librarian checks (rules 6 and 7)", report)
        self.assertIn("<!-- librarian:rules-6-7 -->", report)
        self.assertIn("Not run by the tool", report)

    def test_earlier_reports_are_not_lint_input(self):
        self.lint()
        self.write("owner-inbox/librarian-lint-2026-01-05.md", self.report_text())
        result = self.lint()
        listed = [m["path"] for item in result["items"] for m in item.get("members", [])]
        self.assertFalse([p for p in listed if "librarian-lint-" in p])

    def test_latest(self):
        self.assertIsNone(self.json("lint", "latest")["report"])
        result = self.lint()
        latest = self.json("lint", "latest")
        self.assertEqual((latest["report"], latest["age_days"], latest["findings"], latest["mode"]),
                         (result["report"], 0, result["findings"], "full"))
        self.assertTrue(latest["mention"])
        os.remove(str(self.path(result["report"])))
        old = (datetime.date.today() - datetime.timedelta(days=30)).isoformat()
        self.write("owner-inbox/librarian-lint-%s.md" % old,
                   '<!-- pka-lint {"version": 1, "date": "%s", "mode": "quick", "findings": 3, "info": 0, '
                   '"suppressed": 0, "scanned": 9} -->\n# old\n' % old)
        latest = self.json("lint", "latest")
        self.assertEqual((latest["age_days"], latest["findings"], latest["recent"], latest["mention"]),
                         (30, 3, False, False))
        self.write("owner-inbox/librarian-lint-%s.md" % old, "# rewritten by hand, no header\n")
        self.assertIsNone(self.json("lint", "latest")["findings"])

    def test_schedule_prints_and_installs_nothing(self):
        before = self.tree()
        result = self.json("lint", "schedule")
        self.assertFalse(result["installed"])
        self.assertIn("lint --quick --workspace '%s'" % self.ws, result["cron"])
        self.assertTrue(result["cron"].startswith("0 9 * * 1 "))
        self.assertIn("<string>--quick</string>", result["launchd_plist"])
        self.assertIn("<string>%s</string>" % self.ws, result["launchd_plist"])
        self.assertIn("Nothing was installed", self.ok("lint", "schedule"))
        self.assertEqual(self.tree(), before)
        self.assertFalse(list(self.path("owner-inbox").glob(REPORT_GLOB)))


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
        self.assertTrue(self.json("lint", "suppress", ident)["already"])
        listed = self.json("lint", "suppressions")["suppressed"]
        self.assertEqual([(i["id"], i["reason"]) for i in listed], [(ident, "the inbox copy is on purpose")])
        self.json("lint", "unsuppress", ident)
        self.assertIn(tuple(CHARTER), self.groups(self.lint(), "8a"))

    def test_a_group_that_gains_a_file_is_a_new_finding(self):
        ident = self.charter_id()
        self.json("lint", "suppress", ident)
        self.write("knowledge/AI/charter third.md", build_vault.CHARTER)
        result = self.lint()
        grown = [g for g in self.groups(result, "8a") if "knowledge/reference/charter.md" in g]
        self.assertEqual(len(grown), 1)
        self.assertEqual(len(grown[0]), 3)
        self.assertEqual(result["stale_suppressions"], [ident])

    def test_ids_do_not_change_between_runs_or_modes(self):
        full = {i["id"] for i in self.lint()["items"]}
        quick = {i["id"] for i in self.lint("--quick")["items"]}
        self.assertTrue(quick < full)
        self.assertEqual(full, {i["id"] for i in self.lint()["items"]})

    def test_an_unknown_id_is_refused_with_near_matches(self):
        ident = self.charter_id()
        wrong = ident[:-1] + ("0" if ident[-1] != "0" else "1")
        code, _out, err = self.tool("lint", "suppress", wrong)
        self.assertEqual(code, 64)
        self.assertIn(ident, err)
        self.assertFalse(self.path(".pka/lint-suppressions.json").exists())
        code, _out, err = self.tool("lint", "unsuppress", ident)
        self.assertEqual(code, 64)
        code, _out, err = self.tool("lint", "suppress")
        self.assertEqual(code, 64)

    def test_suppress_needs_a_report_to_take_the_id_from(self):
        code, _out, err = self.tool("lint", "suppress", "8a-00000000")
        self.assertEqual(code, 64)
        self.assertIn("run `pka-tools lint` first", err)

    def test_a_corrupt_file_is_reported_and_left_alone(self):
        ident = self.charter_id()
        for bad in ("{not json", "[1, 2]\n", '{"suppressed": [1]}\n'):
            self.write(".pka/lint-suppressions.json", bad)
            for args in (("lint",), ("lint", "suppress", ident), ("lint", "suppressions"), ("lint", "unsuppress", ident)):
                code, out, err = self.tool(*args)
                self.assertEqual(code, 1, (args, out, err))
                self.assertNotIn("Traceback", err)
                self.assertIn("lint-suppressions.json", err)
            self.assertEqual(self.text(".pka/lint-suppressions.json"), bad)

    def test_entries_it_does_not_understand_are_kept(self):
        ident = self.charter_id()
        self.write(".pka/lint-suppressions.json", json.dumps(
            {"version": 7, "suppressed": {"9z-deadbeef": {"shape": ["from", "a", "later", "release"]}},
             "something_else": {"kept": True}}))
        self.json("lint", "suppress", ident)
        data = json.loads(self.text(".pka/lint-suppressions.json"))
        self.assertEqual(data["something_else"], {"kept": True})
        self.assertEqual(data["version"], 7)
        self.assertEqual(data["suppressed"]["9z-deadbeef"], {"shape": ["from", "a", "later", "release"]})
        self.assertIn(ident, data["suppressed"])
        self.assertEqual(self.lint()["suppressed_ids"], [ident])


if __name__ == "__main__":
    import unittest
    unittest.main()
