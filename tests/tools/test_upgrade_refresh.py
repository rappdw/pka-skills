"""`upgrade-roles.py --refresh`: replace seeded sections a workspace has not
edited, leave edited ones alone, and keep the seed copies single-sourced."""
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
RESEARCHER_COMMIT = "## Commit/push protocol (gated on `hybrid_monorepo_present`)"


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
        researcher = seed_file("researcher").replace(
            "- One commit per brief.", "- One commit per brief. (Sam: we also tag briefs by quarter.)")
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
        self.assertIn("researcher.md: %s  — customised — left alone" % RESEARCHER_COMMIT, out)
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
        self.run_upgrade("--refresh", "--refresh-section", "researcher.md:" + RESEARCHER_COMMIT)
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


class SingleSource(unittest.TestCase):
    def test_seed_copies_match_the_references(self):
        proc = subprocess.run([sys.executable, str(support.REPO / "scripts" / "seeds.py"), "--check"],
                              capture_output=True, text=True)
        self.assertEqual(proc.returncode, 0, proc.stdout[-3000:])

    def test_every_current_section_is_a_known_version(self):
        up = upgrade_module()
        for filename in ("orchestrator.md", "librarian.md", "researcher.md", "_obsidian.md", "_git-protocol.md"):
            for heading, body in up.refreshable_sections(filename):
                key = "%s:%s" % (filename, heading)
                self.assertIn(up.section_hash(body), up.KNOWN_SECTION_HASHES.get(key, []), key)

    def test_old_pointer_wording_is_a_known_version(self):
        up = upgrade_module()
        body = OLD_POINTER.split("\n", 1)[1]
        self.assertIn(up.section_hash(body), up.KNOWN_SECTION_HASHES["librarian.md:" + POINTER_HEADING])

    def test_seeds_do_not_point_at_plugin_paths(self):
        for path in ("role-definitions.md", "obsidian-conventions.md", "git-protocol.md"):
            text = (support.REPO / "skills" / "pka-bootstrap" / "references" / path).read_text(encoding="utf-8")
            self.assertNotIn("pka-skills/skills/", text, path)


if __name__ == "__main__":
    unittest.main()
