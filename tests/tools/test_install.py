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

    def test_git_flag_is_accepted_and_installs_nothing_extra(self):
        """`--git` used to add the nested-repository scripts. Old instructions still pass it."""
        report = self.run_install("--git")
        self.assertEqual(report["components"], ["core"])
        for name in ("graduate.sh", "init_project_repos.sh", "reinit-project-with-lfs.sh", "push-all.sh",
                     "build-repo-list.sh", "gitattributes-template", "gitignore-template"):
            self.assertFalse(self.path(".pka/" + name).exists(), name)
        self.assertEqual(sorted(self.manifest()["files"]), sorted(report["installed"]))
        code, out, _err = self._run(self.tool_path, ("install", "--workspace", str(self.ws), "--git"), None)
        self.assertEqual(code, 0)
        self.assertIn("--git is deprecated and ignored", out)

    def test_second_run_is_a_no_op(self):
        self.run_install()
        before = {p: p.read_bytes() for p in self.path(".pka").rglob("*") if p.is_file()}
        report = self.run_install()
        self.assertEqual((report["installed"], report["updated"], report["conflicts"]), ([], [], []))
        self.assertFalse(report["manifest_changed"])
        after = {p: p.read_bytes() for p in self.path(".pka").rglob("*") if p.is_file()}
        self.assertEqual(before, after)

    def test_no_bytecode_is_left_in_the_vendored_copy(self):
        self.run_install()
        self.assertEqual(self.tool("status")[0], 0)
        self.assertEqual(list(self.path(".pka/bin").rglob("__pycache__")), [])

    def test_untouched_file_is_replaced_when_the_plugin_changes(self):
        self.run_install()
        with open(self.assets / "scripts" / "upgrade-roles.py", "a") as handle:
            handle.write("# a fix from a later plugin version\n")
        report = self.run_install()
        self.assertEqual(report["updated"], ["upgrade-roles.py"])
        self.assertIn("a fix from a later plugin version", self.text(".pka/upgrade-roles.py"))
        self.assertIsNone(report["backups"])

    def test_locally_edited_file_is_kept(self):
        self.run_install()
        self.write(".pka/upgrade-roles.py", "# my own version\n")
        report = self.run_install()
        self.assertEqual(report["kept"], ["upgrade-roles.py"])
        self.assertEqual(self.text(".pka/upgrade-roles.py"), "# my own version\n")
        self.assertFalse(self.path(".pka/upgrade-roles.py.new").exists())

    def test_edited_locally_and_changed_in_plugin_writes_dot_new(self):
        self.run_install()
        self.write(".pka/upgrade-roles.py", "# my local version\n")
        with open(self.assets / "scripts" / "upgrade-roles.py", "a") as handle:
            handle.write("# plugin v2\n")
        report = self.run_install()
        self.assertEqual(report["conflicts"], ["upgrade-roles.py"])
        self.assertEqual(self.text(".pka/upgrade-roles.py"), "# my local version\n")
        self.assertIn("# plugin v2", self.text(".pka/upgrade-roles.py.new"))
        # and the next run does not nag again or overwrite
        again = self.run_install()
        self.assertEqual((again["conflicts"], again["kept"]), ([], ["upgrade-roles.py"]))
        self.assertEqual(self.text(".pka/upgrade-roles.py"), "# my local version\n")

    def test_pre_manifest_workspace_code_is_replaced_with_a_backup(self):
        """A v1.6.x workspace: helpers present, no manifest. (Finding B6.)"""
        pka = self.path(".pka")
        pka.mkdir(exist_ok=True)
        self.write(".pka/upgrade-roles.py", "# old helper that knows nothing of later sections\n")
        report = self.run_install()
        self.assertIn("upgrade-roles.py (previous copy saved)", report["updated"])
        self.assertNotIn("old helper", self.text(".pka/upgrade-roles.py"))
        saved = self.path(report["backups"])
        self.assertIn("old helper", (saved / "upgrade-roles.py").read_text())
        self.assertEqual(self.text(".pka/upgrade-backups/.gitignore"), "*\n")

    # ---- the helpers of the removed nested-repository layout ----------

    RETIRED = ("graduate.sh", "init_project_repos.sh", "reinit-project-with-lfs.sh", "push-all.sh",
               "build-repo-list.sh", "gitattributes-template", "gitignore-template")

    def vendor_retired(self, recorded):
        """Put the retired helpers in .pka/ as an earlier release left them."""
        import hashlib
        self.run_install()
        manifest = self.manifest()
        for name in self.RETIRED:
            data = ("# %s as shipped by an earlier release\n" % name).encode()
            self.write(".pka/" + name, data)
            if recorded:
                manifest["files"][name] = {"sha256": hashlib.sha256(data).hexdigest(), "component": "git"}
        self.write(".pka/manifest.json", json.dumps(manifest, indent=2, sort_keys=True) + "\n")

    def test_retired_helpers_never_recorded_are_left_in_place_and_named(self):
        """A workspace from before the manifest: nothing says whether the
        owner edited them, and they may still be in use by hand."""
        self.vendor_retired(recorded=False)
        self.write(".pka/graduate-backups/orion-20260101.git/HEAD", "ref: refs/heads/main\n")
        self.write(".meta", '{"projects": {}}\n')
        report = self.run_install()
        self.assertEqual(sorted(report["retired_unmanaged"]), sorted(self.RETIRED))
        self.assertEqual((report["obsolete_moved"], report["obsolete_kept"]), ([], []))
        for name in self.RETIRED:
            self.assertEqual(self.text(".pka/" + name), "# %s as shipped by an earlier release\n" % name)
        self.assertTrue(self.path(".pka/graduate-backups/orion-20260101.git/HEAD").is_file())
        self.assertEqual(self.text(".meta"), '{"projects": {}}\n')
        code, out, _err = self._run(self.tool_path, ("install", "--workspace", str(self.ws)), None)
        self.assertEqual(code, 0)
        self.assertIn("removed nested-repository support", out)
        self.assertIn("push-all.sh", out)

    def test_retired_helpers_recorded_and_untouched_move_to_the_backup(self):
        self.vendor_retired(recorded=True)
        report = self.run_install()
        self.assertEqual(sorted(report["obsolete_moved"]), sorted(self.RETIRED))
        self.assertEqual(report["retired_unmanaged"], [])
        saved = self.path(report["backups"])
        for name in self.RETIRED:
            self.assertFalse(self.path(".pka/" + name).exists(), name)
            self.assertEqual((saved / name).read_text(), "# %s as shipped by an earlier release\n" % name)
            self.assertNotIn(name, self.manifest()["files"])
        again = self.run_install()
        self.assertEqual((again["obsolete_moved"], again["retired_unmanaged"]), ([], []))

    def test_retired_helper_recorded_but_edited_stays(self):
        self.vendor_retired(recorded=True)
        self.write(".pka/push-all.sh", "#!/bin/sh\n# the owner's own push script\n")
        report = self.run_install()
        self.assertEqual(report["obsolete_kept"], ["push-all.sh"])
        self.assertEqual(self.text(".pka/push-all.sh"), "#!/bin/sh\n# the owner's own push script\n")
        self.assertEqual(len(report["obsolete_moved"]), len(self.RETIRED) - 1)
        again = self.run_install()                      # and it is not moved on a later run either
        self.assertEqual(again["obsolete_kept"], ["push-all.sh"])
        self.assertTrue(self.path(".pka/push-all.sh").is_file())

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
        report = self.run_install("--dry-run")
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

    def test_nothing_can_run_git(self):
        """pka-tools edits files and nothing else: no module may be able to
        start a process, so no command can stage, commit or push."""
        import ast
        banned = {"subprocess", "pty", "multiprocessing"}
        scanned = sorted((support.ASSETS / "tools").rglob("*.py")) + [support.PLUGIN_TOOL]
        scanned += sorted((support.ASSETS / "scripts").glob("*.py"))
        for path in scanned:
            tree = ast.parse(path.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                names = []
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.module:
                    names = [node.module]
                for name in names:
                    self.assertNotIn(name.split(".")[0], banned, "%s imports %s" % (path.name, name))
                if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name) and node.value.id == "os":
                    self.assertFalse(node.attr in ("system", "popen") or node.attr.startswith(("exec", "spawn")),
                                     "%s calls os.%s" % (path.name, node.attr))
        self.assertFalse((support.ASSETS / "tools" / "pka_tools" / "gitops.py").exists())


if __name__ == "__main__":
    unittest.main()
