"""`upgrade-roles.py --refresh`: replace seeded sections a workspace has not
edited, leave edited ones alone, remove the sections of the retired
nested-repository support, and keep the seed copies single-sourced."""
from __future__ import annotations

import importlib.util
import subprocess
import sys
import unittest

import support

sys.path.insert(0, str(support.REPO / "scripts"))
import seeds  # noqa: E402

OLD_POINTER = (support.REPO / "tests" / "fixtures" / "v1.6.3-librarian-pointer-section.md").read_text(encoding="utf-8")
POINTER_HEADING = OLD_POINTER.split("\n", 1)[0]
RESEARCHER_OBSIDIAN = "## Obsidian coexistence (gated on `obsidian_present`)"
COMMIT_PUSH = "## Commit/push protocol (gated on `hybrid_monorepo_present`)"
V170 = support.REPO / "tests" / "fixtures" / "v1.7.0-roles"


def upgrade_module():
    spec = importlib.util.spec_from_file_location("upgrade_roles", str(support.ASSETS / "scripts" / "upgrade-roles.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def seed_file(role: str) -> str:
    return "\n".join(seeds.role_seed(role)).strip("\n") + "\n"


def replace_section(text: str, heading: str, new_section: str) -> str:
    up = upgrade_module()
    for found, start, _body, end in up.h2_sections(text):
        if found == heading:
            return text[:start] + new_section.rstrip("\n") + "\n\n" + text[end:]
    raise AssertionError("no section %s" % heading)


class Refresh(support.ToolsCase):
    fixture = False

    def setUp(self):
        super().setUp()
        roles = self.ws / ".pka" / "roles"
        roles.mkdir(parents=True)
        librarian = replace_section(seed_file("librarian"), POINTER_HEADING, OLD_POINTER)
        researcher = seed_file("researcher")
        self.assertIn("- `tags` always includes `research`", researcher)
        researcher = researcher.replace(
            "- `tags` always includes `research`", "- (Sam: we also tag briefs by quarter.) `tags` always includes `research`")
        self.write(".pka/roles/librarian.md", librarian)
        self.write(".pka/roles/researcher.md", researcher)
        self.write(".pka/roles/orchestrator.md", seed_file("orchestrator").replace("\n", "\r\n"))

    def run_upgrade(self, *args):
        proc = subprocess.run([sys.executable, str(self.path(".pka/upgrade-roles.py")), "--workspace", str(self.ws)]
                              + list(args), env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(proc.returncode, 0, proc.stderr)
        return proc.stdout

    def test_report_only_by_default(self):
        before = self.read(".pka/roles/librarian.md")
        out = self.run_upgrade()
        self.assertIn("librarian.md: %s  — can be refreshed" % POINTER_HEADING, out)
        self.assertIn("researcher.md: %s  — customised — left alone" % RESEARCHER_OBSIDIAN, out)
        self.assertIn("--refresh", out)
        self.assertEqual(self.read(".pka/roles/librarian.md"), before)

    def test_refresh_replaces_only_the_unchanged_old_section(self):
        before = self.text(".pka/roles/librarian.md")
        researcher_before = self.read(".pka/roles/researcher.md")
        out = self.run_upgrade("--refresh")
        self.assertIn("— refreshed", out)
        after = self.text(".pka/roles/librarian.md")
        self.assertNotIn("Jaccard", after)
        self.assertIn("pka-tools pointers add", after)
        self.assertEqual(after, seed_file("librarian"))       # now exactly the current seed
        self.assertIn("Jaccard", before)
        self.assertEqual(self.read(".pka/roles/researcher.md"), researcher_before)   # customised: untouched
        backups = list(self.path(".pka/upgrade-backups").glob("*/roles/librarian.md"))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_text(encoding="utf-8"), before)
        again = self.run_upgrade("--refresh")
        self.assertNotIn("— refreshed", again)
        self.assertEqual(self.text(".pka/roles/librarian.md"), after)

    def test_named_customised_section_is_replaced_on_request(self):
        self.run_upgrade("--refresh", "--refresh-section", "researcher.md:" + RESEARCHER_OBSIDIAN)
        self.assertEqual(self.text(".pka/roles/researcher.md"), seed_file("researcher"))

    def test_crlf_file_stays_crlf(self):
        text = seed_file("orchestrator")
        old = "## Bootstrap dispatch"
        up = upgrade_module()
        for heading, start, body, end in up.h2_sections(text):
            if heading == old:
                stale = text[:body] + "\nAn old wording that no version shipped.\n\n" + text[end:]
        self.write(".pka/roles/orchestrator.md", stale.replace("\n", "\r\n"))
        self.run_upgrade("--refresh", "--refresh-section", "orchestrator.md:" + old)
        data = self.read(".pka/roles/orchestrator.md")
        self.assertEqual(data, seed_file("orchestrator").replace("\n", "\r\n").encode("utf-8"))

    def test_diff_and_dry_run(self):
        before = self.read(".pka/roles/librarian.md")
        out = self.run_upgrade("--refresh", "--dry-run", "--diff")
        self.assertIn("would be refreshed", out)
        self.assertIn("-1. **Identify the cluster** using Jaccard", out)
        self.assertEqual(self.read(".pka/roles/librarian.md"), before)

    def test_refresh_section_needs_refresh(self):
        proc = subprocess.run([sys.executable, str(self.path(".pka/upgrade-roles.py")), "--workspace", str(self.ws),
                               "--refresh-section", "x.md:## Y"], env=self.env, capture_output=True, text=True)
        self.assertNotEqual(proc.returncode, 0)


class Obsolete(support.ToolsCase):
    """A workspace whose role files are exactly what v1.7.0 seeded, with the
    commit/push sections and `_git-protocol.md` of the removed layout."""

    fixture = False

    def setUp(self):
        super().setUp()
        (self.ws / ".pka" / "roles").mkdir(parents=True)
        for name in ("orchestrator.md", "librarian.md", "researcher.md", "_git-protocol.md"):
            self.write(".pka/roles/" + name, (V170 / name).read_text(encoding="utf-8"))

    def run_upgrade(self, *args, code=0):
        proc = subprocess.run([sys.executable, str(self.path(".pka/upgrade-roles.py")), "--workspace", str(self.ws)]
                              + list(args), env=self.env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
        self.assertEqual(proc.returncode, code, proc.stderr)
        return proc.stdout

    def headings(self, name):
        up = upgrade_module()
        return [heading for heading, _, _, _ in up.h2_sections(self.text(".pka/roles/" + name))]

    def seed_headings(self, role):
        up = upgrade_module()
        return [heading for heading, _, _, _ in up.h2_sections(seed_file(role))]

    def sections(self, name, text=None):
        """{heading: body} for the sections pka-skills seeds in this file."""
        up = upgrade_module()
        text = self.text(".pka/roles/" + name) if text is None else text
        wanted = [heading for heading, _ in up.refreshable_sections(name)]
        return {heading: up.normalise_section(text[body:end])
                for heading, _, body, end in up.h2_sections(text) if heading in wanted}

    def seed_sections(self, role):
        return self.sections(role + ".md", seed_file(role))

    def test_reported_and_left_alone_without_refresh(self):
        before = {name: self.read(".pka/roles/" + name)
                  for name in ("orchestrator.md", "librarian.md", "researcher.md", "_git-protocol.md")}
        out = self.run_upgrade()
        self.assertIn("Obsolete (pka-skills no longer commits", out)
        self.assertIn("_git-protocol.md (whole file)  — can be removed", out)
        self.assertIn("orchestrator.md: ## Session-end protocol (extended)  — can be removed", out)
        self.assertIn("orchestrator.md: ## Mid-session push handling  — can be removed", out)
        self.assertIn("librarian.md: %s  — can be removed" % COMMIT_PUSH, out)
        self.assertIn("researcher.md: %s  — can be removed" % COMMIT_PUSH, out)
        for name in ("orchestrator.md", "librarian.md", "_git-protocol.md"):
            self.assertEqual(self.read(".pka/roles/" + name), before[name], name)
        # researcher.md only gained the section that replaces the filing instruction
        self.assertIn("## Filing a brief", self.headings("researcher.md"))
        self.assertIn(COMMIT_PUSH, self.headings("researcher.md"))
        self.assertNotIn("_git-protocol.md", self.run_upgrade("--dry-run").split("Shared references seeded")[1].split("\n")[1])

    def test_git_protocol_file_is_not_seeded_any_more(self):
        self.path(".pka/roles/_git-protocol.md").unlink()
        out = self.run_upgrade()
        self.assertFalse(self.path(".pka/roles/_git-protocol.md").exists())
        self.assertNotIn("_git-protocol.md", out)

    def test_refresh_removes_the_untouched_ones_and_keeps_a_backup(self):
        out = self.run_upgrade("--refresh")
        self.assertIn("_git-protocol.md (whole file)  — removed", out)
        self.assertFalse(self.path(".pka/roles/_git-protocol.md").exists())
        for name in ("librarian.md", "researcher.md"):
            self.assertEqual(self.text(".pka/roles/" + name), seed_file(name[:-3]), name)
        # The orchestrator's unseeded sections (Key Competencies, Output
        # Conventions, Invocation) are the owner's and are never rewritten,
        # so only its seeded sections can be compared with the current seed.
        self.assertEqual(self.headings("orchestrator.md"), self.seed_headings("orchestrator"))
        self.assertEqual(self.sections("orchestrator.md"), self.seed_sections("orchestrator"))
        for name in ("orchestrator.md", "librarian.md", "researcher.md"):
            self.assertNotIn("hybrid_monorepo_present", self.text(".pka/roles/" + name))
            self.assertNotIn("_git-protocol.md", self.text(".pka/roles/" + name))
        backups = list(self.path(".pka/upgrade-backups").glob("*/roles"))
        self.assertEqual(len(backups), 1)
        self.assertEqual((backups[0] / "_git-protocol.md").read_text(encoding="utf-8"),
                         (V170 / "_git-protocol.md").read_text(encoding="utf-8"))
        self.assertIn(COMMIT_PUSH, (backups[0] / "librarian.md").read_text(encoding="utf-8"))
        again = self.run_upgrade("--refresh")
        self.assertNotIn("Obsolete", again)
        self.assertNotIn("— refreshed", again)

    def test_a_customised_obsolete_section_is_kept(self):
        text = self.text(".pka/roles/researcher.md").replace(
            "- One commit per brief.", "- One commit per brief. (Sam: and we sign them.)")
        self.write(".pka/roles/researcher.md", text)
        out = self.run_upgrade("--refresh")
        self.assertIn("researcher.md: %s  — customised — left alone" % COMMIT_PUSH, out)
        self.assertIn("librarian.md: %s  — removed" % COMMIT_PUSH, out)
        after = self.text(".pka/roles/researcher.md")
        self.assertIn("(Sam: and we sign them.)", after)
        self.assertIn(COMMIT_PUSH, self.headings("researcher.md"))
        self.assertNotIn(COMMIT_PUSH, self.headings("librarian.md"))
        # removed only when the owner names it
        out = self.run_upgrade("--refresh", "--refresh-section", "researcher.md:" + COMMIT_PUSH)
        self.assertIn("removed as requested", out)
        self.assertEqual(self.text(".pka/roles/researcher.md"), seed_file("researcher"))

    def test_a_customised_git_protocol_file_is_kept(self):
        text = self.text(".pka/roles/_git-protocol.md") + "\nSam: we push from the office network only.\n"
        self.write(".pka/roles/_git-protocol.md", text)
        out = self.run_upgrade("--refresh")
        self.assertIn("_git-protocol.md (whole file)  — customised — left alone", out)
        self.assertEqual(self.text(".pka/roles/_git-protocol.md"), text)

    def test_an_edit_above_the_first_heading_also_counts(self):
        text = self.text(".pka/roles/_git-protocol.md")
        first = text.index("\n## ")
        text = text[:first] + "\nSam: ask Robin before changing any of this.\n" + text[first:]
        self.write(".pka/roles/_git-protocol.md", text)
        out = self.run_upgrade("--refresh")
        self.assertIn("_git-protocol.md (whole file)  — customised — left alone", out)
        self.assertEqual(self.text(".pka/roles/_git-protocol.md"), text)

    def test_a_warning_stays_while_obsolete_text_remains(self):
        self.assertIn("WARNING: while any of these remain", self.run_upgrade())
        text = self.text(".pka/roles/researcher.md").replace(
            "- One commit per brief.", "- One commit per brief. (Sam: and we sign them.)")
        self.write(".pka/roles/researcher.md", text)
        self.assertIn("WARNING: while any of these remain", self.run_upgrade("--refresh"))

    def test_dry_run_and_crlf(self):
        crlf = self.text(".pka/roles/orchestrator.md").replace("\n", "\r\n")
        self.write(".pka/roles/orchestrator.md", crlf)
        before = self.read(".pka/roles/orchestrator.md")
        out = self.run_upgrade("--refresh", "--dry-run")
        self.assertIn("would be removed", out)
        self.assertEqual(self.read(".pka/roles/orchestrator.md"), before)
        self.assertTrue(self.path(".pka/roles/_git-protocol.md").exists())
        self.run_upgrade("--refresh")
        data = self.read(".pka/roles/orchestrator.md")
        self.assertNotIn(b"\n", data.replace(b"\r\n", b""))          # still CRLF throughout
        self.assertTrue(data.endswith(b"coordination.\r\n"))
        self.assertEqual(self.headings("orchestrator.md"), self.seed_headings("orchestrator"))


class SingleSource(unittest.TestCase):
    def test_seed_copies_match_the_references(self):
        proc = subprocess.run([sys.executable, str(support.REPO / "scripts" / "seeds.py"), "--check"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout[-3000:])

    def test_every_current_section_is_a_known_version(self):
        up = upgrade_module()
        for filename in ("orchestrator.md", "librarian.md", "researcher.md", "_obsidian.md"):
            for heading, body in up.refreshable_sections(filename):
                key = "%s:%s" % (filename, heading)
                self.assertIn(up.section_hash(body), up.KNOWN_SECTION_HASHES.get(key, []), key)

    def test_obsolete_sections_keep_their_known_versions(self):
        """Without these hashes an untouched obsolete section could not be told from an edited one."""
        up = upgrade_module()
        for filename, headings in up.OBSOLETE_SECTIONS.items():
            for heading in headings:
                self.assertTrue(up.KNOWN_SECTION_HASHES.get("%s:%s" % (filename, heading)), (filename, heading))
                self.assertNotIn(heading, [h for h, _ in up.refreshable_sections(filename)])
        for filename in up.OBSOLETE_FILES:
            self.assertTrue([key for key in up.KNOWN_SECTION_HASHES if key.startswith(filename + ":")], filename)
        self.assertFalse(hasattr(up, "GIT_PROTOCOL_SEED"))

    def test_old_pointer_wording_is_a_known_version(self):
        up = upgrade_module()
        body = OLD_POINTER.split("\n", 1)[1]
        self.assertIn(up.section_hash(body), up.KNOWN_SECTION_HASHES["librarian.md:" + POINTER_HEADING])

    def test_seeds_do_not_point_at_plugin_paths(self):
        for path in ("role-definitions.md", "obsidian-conventions.md"):
            text = (support.REPO / "skills" / "pka-bootstrap" / "references" / path).read_text(encoding="utf-8")
            self.assertNotIn("pka-skills/skills/", text, path)


if __name__ == "__main__":
    unittest.main()
