"""`pka-tools install`: vendoring by manifest, and what happens to edited files."""
from __future__ import annotations

import json
import os
import shutil
import unittest
from pathlib import Path

import support

from pka_tools import __version__


class Install(support.ToolsCase):
    fixture = False
    install = False

    def setUp(self):
        super().setUp()
        # A private copy of the plugin's assets, so a test can play "the plugin was updated".
        self.assets = self.base / "plugin" / "bootstrap-assets"
        shutil.copytree(str(support.ASSETS), str(self.assets), ignore=shutil.ignore_patterns("__pycache__"))
        self.tool_path = self.assets / "tools" / "pka-tools"

    def run_install(self, *extra):
        code, out, err = self._run(self.tool_path, ("install", "--workspace", str(self.ws), "--json") + extra, None)
        self.assertEqual(code, 0, err)
        return json.loads(out)

    def manifest(self):
        return json.loads(self.text(".pka/manifest.json"))

    def test_fresh_install_core_only(self):
        report = self.run_install()
        self.assertEqual(report["components"], ["core"])
        self.assertIn("bin/pka-tools", report["installed"])
        self.assertIn("bin/pka_tools/cli.py", report["installed"])
        self.assertIn("upgrade-roles.py", report["installed"])
        self.assertFalse(self.path(".pka/graduate.sh").exists())
        self.assertTrue(os.access(str(self.path(".pka/bin/pka-tools")), os.X_OK))
        self.assertTrue(os.access(str(self.path(".pka/upgrade-roles.py")), os.X_OK))
        manifest = self.manifest()
        self.assertEqual(manifest["plugin_version"], __version__)
        self.assertEqual(sorted(manifest["files"]), sorted(report["installed"]))
        code, out, _err = self.tool("version")
        self.assertEqual((code, out.strip()), (0, "pka-tools %s" % __version__))

    def test_git_component_on_request_and_remembered(self):
        report = self.run_install("--git")
        self.assertEqual(report["components"], ["core", "git"])
        for name in ("graduate.sh", "init_project_repos.sh", "reinit-project-with-lfs.sh", "push-all.sh",
                     "build-repo-list.sh", "gitattributes-template", "gitignore-template"):
            self.assertTrue(self.path(".pka/" + name).is_file(), name)
        self.assertTrue(os.access(str(self.path(".pka/graduate.sh")), os.X_OK))
        again = self.run_install()                       # no --git: still maintained
        self.assertEqual(again["components"], ["core", "git"])

    def test_second_run_is_a_no_op(self):
        self.run_install("--git")
        before = {p: p.read_bytes() for p in self.path(".pka").rglob("*") if p.is_file()}
        report = self.run_install("--git")
        self.assertEqual((report["installed"], report["updated"], report["conflicts"]), ([], [], []))
        self.assertFalse(report["manifest_changed"])
        after = {p: p.read_bytes() for p in self.path(".pka").rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_no_bytecode_is_left_in_the_vendored_copy(self):
        self.run_install()
        self.assertEqual(self.tool("status")[0], 0)
        self.assertEqual(list(self.path(".pka/bin").rglob("__pycache__")), [])

    def test_untouched_file_is_replaced_when_the_plugin_changes(self):
        self.run_install("--git")
        with open(self.assets / "scripts" / "push-all.sh", "a") as handle:
            handle.write("# a fix from a later plugin version\n")
        report = self.run_install()
        self.assertEqual(report["updated"], ["push-all.sh"])
        self.assertIn("a fix from a later plugin version", self.text(".pka/push-all.sh"))
        self.assertIsNone(report["backups"])

    def test_locally_edited_file_is_kept(self):
        self.run_install("--git")
        self.write(".pka/gitignore-template", "my own ignore rules\n")
        report = self.run_install()
        self.assertEqual(report["kept"], ["gitignore-template"])
        self.assertEqual(self.text(".pka/gitignore-template"), "my own ignore rules\n")
        self.assertFalse(self.path(".pka/gitignore-template.new").exists())

    def test_edited_locally_and_changed_in_plugin_writes_dot_new(self):
        self.run_install("--git")
        self.write(".pka/push-all.sh", "#!/bin/sh\n# my local version\n")
        with open(self.assets / "scripts" / "push-all.sh", "a") as handle:
            handle.write("# plugin v2\n")
        report = self.run_install()
        self.assertEqual(report["conflicts"], ["push-all.sh"])
        self.assertEqual(self.text(".pka/push-all.sh"), "#!/bin/sh\n# my local version\n")
        self.assertIn("# plugin v2", self.text(".pka/push-all.sh.new"))
        # and the next run does not nag again or overwrite
        again = self.run_install()
        self.assertEqual((again["conflicts"], again["kept"]), ([], ["push-all.sh"]))
        self.assertEqual(self.text(".pka/push-all.sh"), "#!/bin/sh\n# my local version\n")

    def test_pre_manifest_workspace_code_is_replaced_with_a_backup_templates_kept(self):
        """A v1.6.x workspace: helpers present, no manifest. (Finding B6.)"""
        pka = self.path(".pka")
        pka.mkdir(exist_ok=True)
        self.write(".pka/graduate.sh", "#!/bin/sh\n# the v1.6.0 copy with the data-loss bug\n")
        self.write(".pka/upgrade-roles.py", "# old helper that knows nothing of later sections\n")
        self.write(".pka/gitattributes-template", "*.psd filter=lfs diff=lfs merge=lfs -text\n")
        report = self.run_install()
        self.assertEqual(report["components"], ["core", "git"])       # detected from the files present
        self.assertIn("graduate.sh (previous copy saved)", report["updated"])
        self.assertIn("upgrade-roles.py (previous copy saved)", report["updated"])
        self.assertEqual(report["conflicts"], ["gitattributes-template"])
        self.assertNotIn("data-loss bug", self.text(".pka/graduate.sh"))
        saved = self.path(report["backups"])
        self.assertIn("data-loss bug", (saved / "graduate.sh").read_text())
        self.assertEqual(self.text(".pka/gitattributes-template"), "*.psd filter=lfs diff=lfs merge=lfs -text\n")
        self.assertTrue(self.path(".pka/gitattributes-template.new").is_file())
        self.assertEqual(self.text(".pka/upgrade-backups/.gitignore"), "*\n")

    def test_file_the_plugin_no_longer_ships(self):
        extra = self.assets / "tools" / "pka_tools" / "retired.py"
        extra.write_text("# a module a later version drops\n")
        self.run_install()
        self.assertTrue(self.path(".pka/bin/pka_tools/retired.py").is_file())
        extra.unlink()
        report = self.run_install()
        self.assertEqual(report["obsolete_moved"], ["bin/pka_tools/retired.py"])
        self.assertFalse(self.path(".pka/bin/pka_tools/retired.py").exists())
        self.assertTrue((self.path(report["backups"]) / "bin/pka_tools/retired.py").is_file())
        self.assertNotIn("bin/pka_tools/retired.py", self.manifest()["files"])

    def test_file_the_plugin_no_longer_ships_but_was_edited_stays(self):
        extra = self.assets / "tools" / "pka_tools" / "retired.py"
        extra.write_text("# a module a later version drops\n")
        self.run_install()
        self.write(".pka/bin/pka_tools/retired.py", "# the owner changed this\n")
        extra.unlink()
        report = self.run_install()
        self.assertEqual(report["obsolete_kept"], ["bin/pka_tools/retired.py"])
        self.assertEqual(self.text(".pka/bin/pka_tools/retired.py"), "# the owner changed this\n")

    def test_dry_run_writes_nothing(self):
        report = self.run_install("--dry-run", "--git")
        self.assertGreater(len(report["installed"]), 20)
        self.assertEqual([p for p in self.path(".pka").rglob("*")], [])

    def test_invalid_manifest_stops_before_touching_anything(self):
        self.run_install()
        self.write(".pka/manifest.json", "{ not json")
        with open(self.assets / "scripts" / "upgrade-roles.py", "a") as handle:
            handle.write("# changed\n")
        before = self.read(".pka/upgrade-roles.py")
        code, _out, err = self._run(self.tool_path, ("install", "--workspace", str(self.ws)), None)
        self.assertEqual(code, 1)
        self.assertIn("not valid JSON", err)
        self.assertEqual(self.read(".pka/upgrade-roles.py"), before)

    def test_the_vendored_copy_cannot_install_itself(self):
        self.run_install()
        code, _out, err = self.tool("install")
        self.assertEqual(code, 64)
        self.assertIn("plugin's copy", err)

    def test_creates_dot_pka_when_absent(self):
        shutil.rmtree(str(self.path(".pka")))
        self.run_install()
        self.assertTrue(self.path(".pka/bin/pka-tools").is_file())


class Versions(unittest.TestCase):
    def test_tool_version_matches_the_plugin_manifests(self):
        plugin = json.loads((support.REPO / ".claude-plugin" / "plugin.json").read_text())
        self.assertEqual(plugin["version"], __version__)
        market = json.loads((support.REPO / ".claude-plugin" / "marketplace.json").read_text())
        versions = {entry.get("version") for entry in market.get("plugins", []) if entry.get("version")}
        if market.get("metadata", {}).get("version"):
            versions.add(market["metadata"]["version"])
        self.assertTrue(versions <= {__version__}, versions)

    def test_every_module_is_python_3_9_syntax(self):
        import ast
        for path in sorted((support.ASSETS / "tools").rglob("*.py")) + [support.PLUGIN_TOOL]:
            source = path.read_text(encoding="utf-8")
            ast.parse(source, filename=str(path), feature_version=(3, 9))
            if path.name != "pka-tools" and path.name != "__init__.py":
                self.assertIn("from __future__ import annotations", source, path.name)

    def test_standard_library_only(self):
        import ast
        import sys
        allowed = set(sys.stdlib_module_names) if hasattr(sys, "stdlib_module_names") else None
        if allowed is None:
            self.skipTest("needs Python 3.10+ to list the standard library")
        for path in sorted((support.ASSETS / "tools").rglob("*.py")):
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0 and node.module:
                    names = [node.module]
                for name in names:
                    top = name.split(".")[0]
                    self.assertTrue(top in allowed or top == "pka_tools", "%s imports %s" % (path.name, name))

    def test_no_network_modules(self):
        banned = ("urllib.request", "http.client", "socket", "ftplib", "smtplib", "requests", "ssl")
        for path in sorted((support.ASSETS / "tools").rglob("*.py")):
            source = path.read_text(encoding="utf-8")
            for name in banned:
                self.assertNotIn("import " + name, source, path.name)


if __name__ == "__main__":
    unittest.main()
