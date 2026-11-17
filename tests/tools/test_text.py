"""Unit tests for the text primitives every editing command is built on."""
from __future__ import annotations

import unittest

import support  # noqa: F401  (sets sys.path)

from pka_tools import frontmatter, markdown, pkaignore, textio
from pka_tools.workspace import Workspace, domain_tag


def L(text):
    return textio.split_lines(text)


class TextIO(unittest.TestCase):
    def test_split_lines_round_trips_every_ending(self):
        for text in ["", "a", "a\n", "a\r\nb\r\n", "a\n\nb", "x\x0cy z\n", "﻿a\n"]:
            self.assertEqual("".join(L(text)), text)

    def test_split_only_on_newline(self):
        self.assertEqual(len(L("one\x0cstill one still one\n")), 1)

    def test_line_body_and_end(self):
        self.assertEqual(textio.line_body("a \r\n"), "a ")
        self.assertEqual(textio.line_end("a\r\n"), "\r\n")
        self.assertEqual(textio.line_end("a"), "")

    def test_detect_newline(self):
        self.assertEqual(textio.detect_newline("a\r\nb\n"), "\r\n")
        self.assertEqual(textio.detect_newline("a\nb\r\n"), "\n")
        self.assertEqual(textio.detect_newline("no newline"), "\n")


class Fences(unittest.TestCase):
    def test_mask_covers_fenced_headings(self):
        lines = L("# A\n```md\n## Pointers\n```\n## Pointers\n~~~\n## X\n~~~~\n")
        mask = markdown.fence_mask(lines)
        self.assertEqual(mask, [False, True, True, True, False, True, True, True])
        self.assertEqual(markdown.find_heading(lines, mask, "Pointers", 2), 4)

    def test_longer_fence_is_not_closed_by_shorter(self):
        lines = L("````\n```\n## inside\n````\n## outside\n")
        mask = markdown.fence_mask(lines)
        self.assertEqual(mask, [True, True, True, True, False])

    def test_section_end_stops_at_same_or_higher_level(self):
        lines = L("## A\ntext\n### sub\n## B\n")
        mask = markdown.fence_mask(lines)
        self.assertEqual(markdown.section_end(lines, mask, 0), 3)


class Tables(unittest.TestCase):
    def test_cells_ignore_pipes_in_links_code_and_escapes(self):
        body = "| a | [[x/y|alias]] | `p|q` | r \\| s |"
        self.assertEqual(markdown.cell_texts(body), ["a", "[[x/y|alias]]", "`p|q`", "r \\| s"])

    def test_not_a_row(self):
        self.assertIsNone(markdown.cell_spans("plain text | with a pipe"))
        self.assertIsNone(markdown.cell_spans(""))

    def test_separator_row(self):
        self.assertTrue(markdown.is_separator_row("| :--- | ---: | :-: |"))
        self.assertTrue(markdown.is_separator_row("|---|---|---|"))
        self.assertFalse(markdown.is_separator_row("| a | --- |"))

    def test_replace_cell_keeps_padding(self):
        body = "| topic   | ent     | files |"
        spans = markdown.cell_spans(body)
        self.assertEqual(markdown.replace_cell(body, spans[1], "ent, new"), "| topic   | ent, new     | files |")

    def test_wikilink_targets(self):
        text = "[[a/b]], [[a/c.md|C]], [[d#head]], [[e\\|alias]] and [not a link]"
        self.assertEqual(markdown.wikilink_targets(text), ["a/b", "a/c", "d", "e"])


class FrontmatterParse(unittest.TestCase):
    def test_absent(self):
        fm = frontmatter.parse(L("# Title\n---\nnot frontmatter\n"))
        self.assertFalse(fm.present)

    def test_reads_scalars_lists_and_comments(self):
        lines = L(
            "---\n# comment\ntype: meeting\ndate: 2026-04-23\n"
            'attendees: ["[[personnel/priya/index]]", jamie-lin]  # trailing\n'
            "tags:\n  - research\n  - strategy\nrelated:\n- \"[[AI/x]]\"\nempty:\n---\nbody\n"
        )
        fm = frontmatter.parse(lines)
        self.assertIsNone(fm.error)
        self.assertEqual(frontmatter.get_scalar(lines, fm, "type"), "meeting")
        self.assertEqual(frontmatter.get_list(lines, fm, "attendees"), ["[[personnel/priya/index]]", "jamie-lin"])
        self.assertEqual(frontmatter.get_list(lines, fm, "tags"), ["research", "strategy"])
        self.assertEqual(frontmatter.get_list(lines, fm, "related"), ["[[AI/x]]"])
        self.assertEqual(frontmatter.get_list(lines, fm, "empty"), [])

    def test_bom_and_crlf(self):
        lines = L("﻿---\r\ntags: [a]\r\n---\r\nbody\r\n")
        fm = frontmatter.parse(lines)
        self.assertTrue(fm.usable)
        self.assertEqual(frontmatter.get_list(lines, fm, "tags"), ["a"])

    def test_malformed_cases_are_errors(self):
        cases = {
            "no closing": "---\ntype: x\nbody\n",
            "unquoted colon": "---\ntopic: this: has a colon\n---\n",
            "trailing colon": "---\ntopic: ends with:\n---\n",
            "tab indent": "---\ntags:\n\t- a\n---\n",
            "duplicate key": "---\ntags: [a]\ntags: [b]\n---\n",
            "not a key": "---\njust some words\n---\n",
            "unterminated quote": '---\ntitle: "open\n---\n',
            "unclosed flow": "---\ntags: [a, b\n---\n",
            "orphan list item": "---\n- a\n---\n",
        }
        for name, text in cases.items():
            with self.subTest(name):
                fm = frontmatter.parse(L(text))
                self.assertTrue(fm.present)
                self.assertIsNotNone(fm.error)

    def test_valid_but_unusual_yaml_is_not_an_error(self):
        cases = [
            "---\nurl: https://example.com/a:b\n---\n",
            "---\ntime: 10:30\n---\n",
            "---\ndesc: |\n  line: one\n  line two\n---\n",
            "---\nnested:\n  key: value\n  other: [1, 2]\n---\n",
            "---\ntitle: \"quoted: colon\"  # ok\n---\n",
            "---\ntitle: 'it''s fine'\n---\n",
            "---\ntags: [a,\n  b]\n---\n",
            "---\naliases: []\ncssclasses: wide\n---\n",
        ]
        for text in cases:
            with self.subTest(text):
                self.assertIsNone(frontmatter.parse(L(text)).error)


class FrontmatterEdit(unittest.TestCase):
    def merge(self, text, tag="ai"):
        lines = L(text)
        fm = frontmatter.parse(lines)
        out, status = frontmatter.merge_tag(lines, fm, tag, textio.detect_newline(text))
        return "".join(out), status

    def test_flow_list(self):
        self.assertEqual(self.merge("---\ntags: [a, b]\n---\n"), ("---\ntags: [a, b, ai]\n---\n", "added"))

    def test_flow_list_with_comment_and_brackets_in_comment(self):
        out, status = self.merge("---\ntags: [a]   # see [x]\n---\n")
        self.assertEqual(out, "---\ntags: [a, ai]   # see [x]\n---\n")

    def test_empty_flow_list_and_empty_value(self):
        self.assertEqual(self.merge("---\ntags: []\n---\n")[0], "---\ntags: [ai]\n---\n")
        self.assertEqual(self.merge("---\ntags:\n---\n")[0], "---\ntags: [ai]\n---\n")

    def test_block_list_keeps_indent_and_line_endings(self):
        out, status = self.merge("---\r\ntags:\r\n  - a\r\n  - b\r\nx: 1\r\n---\r\n")
        self.assertEqual(out, "---\r\ntags:\r\n  - a\r\n  - b\r\n  - ai\r\nx: 1\r\n---\r\n")

    def test_present_is_case_and_hash_insensitive(self):
        self.assertEqual(self.merge("---\ntags: [AI]\n---\n")[1], "present")
        self.assertEqual(self.merge('---\ntags: ["#ai"]\n---\n')[1], "present")

    def test_uneditable_forms_are_left_alone(self):
        for text in ["---\ntags: daily\n---\n", "---\ntags: [a,\n  b]\n---\n", "---\nTags: [a]\n---\n",
                     "---\ntag: a\n---\n"]:
            with self.subTest(text):
                self.assertEqual(self.merge(text), (text, "uneditable"))

    def test_missing_key_is_added_above_the_closing_fence(self):
        out, status = self.merge("---\ntype: brief\n---\nbody\n")
        self.assertEqual(out, "---\ntype: brief\ntags: [ai]\n---\nbody\n")

    def test_prepend_block_keeps_bom_first_and_body_bytes(self):
        lines = L("﻿Body line\r\nmore\r\n")
        out = "".join(frontmatter.prepend_block(lines, [("tags", "[ai]")], "\r\n"))
        self.assertEqual(out, "﻿---\r\ntags: [ai]\r\n---\r\n\r\nBody line\r\nmore\r\n")

    def test_prepend_block_on_empty_file(self):
        self.assertEqual("".join(frontmatter.prepend_block([], [("tags", "[ai]")], "\n")), "---\ntags: [ai]\n---\n")

    def test_scalar_quotes_what_yaml_would_misread(self):
        self.assertEqual(frontmatter.scalar("slt-meeting"), "slt-meeting")
        self.assertEqual(frontmatter.scalar("2026-04-22"), "2026-04-22")
        self.assertEqual(frontmatter.scalar("budget review: second pass"), '"budget review: second pass"')
        self.assertEqual(frontmatter.scalar("true"), '"true"')
        self.assertEqual(frontmatter.scalar("42"), '"42"')
        self.assertEqual(frontmatter.scalar('say "hi"'), '"say \\"hi\\""')
        self.assertEqual(frontmatter.scalar("Zoë Åkesson"), '"Zoë Åkesson"')
        for value in ["slt-meeting", "budget review: second pass", "true", 'say "hi"', "Zoë Åkesson"]:
            lines = L("---\nkey: %s\n---\n" % frontmatter.scalar(value))
            fm = frontmatter.parse(lines)
            self.assertIsNone(fm.error)
            self.assertEqual(frontmatter.get_scalar(lines, fm, "key"), value)


class Ignore(unittest.TestCase):
    def test_default_patterns(self):
        ig = pkaignore.Ignore.from_text(pkaignore.DEFAULT_PATTERNS)
        self.assertTrue(ig.is_ignored("projects/orion/src/main.rs", False))
        self.assertFalse(ig.is_ignored("projects/orion/README.md", False))
        self.assertTrue(ig.is_ignored("knowledge/a/node_modules/x.md", False))
        self.assertTrue(ig.is_ignored(".pka/knowledge.db", False))
        self.assertTrue(ig.is_ignored("knowledge/AI/build/notes.md", False))
        self.assertFalse(ig.is_ignored("knowledge/AI/notes.md", False))

    def test_negation_anchoring_and_dir_only(self):
        ig = pkaignore.Ignore.from_text("*.log\n!keep.log\n/top.md\ndocs/\nfoo/**/bar.md\n")
        self.assertTrue(ig.is_ignored("a/b/x.log", False))
        self.assertFalse(ig.is_ignored("a/keep.log", False))
        self.assertTrue(ig.is_ignored("top.md", False))
        self.assertFalse(ig.is_ignored("sub/top.md", False))
        self.assertTrue(ig.is_ignored("a/docs", True))
        self.assertFalse(ig.is_ignored("a/docs", False))
        self.assertTrue(ig.is_ignored("a/docs/x.md", False))
        self.assertTrue(ig.is_ignored("foo/bar.md", False))
        self.assertTrue(ig.is_ignored("foo/a/b/bar.md", False))

    def test_sections_scope_rules(self):
        ig = pkaignore.Ignore.from_text("# @pka-section: knowledge\n*.tmp\ndrafts/\n")
        self.assertTrue(ig.is_ignored("knowledge/a/x.tmp", False))
        self.assertFalse(ig.is_ignored("projects/a/x.tmp", False))
        self.assertTrue(ig.is_ignored("knowledge/drafts/x.md", False))


class RepoMap(support.ToolsCase):
    install = False

    def test_reads_the_fixture_repo_map(self):
        ws = Workspace(self.ws)
        entries = {entry.folder: entry for entry in ws.repo_map()}
        self.assertEqual(entries["knowledge/leadership"].tags, ["meeting-home"])
        self.assertEqual(entries["knowledge/archived"].priority, "Archive")
        roots = [ws.rel(root) for root in ws.index_roots()]
        self.assertIn("knowledge/AI", roots)
        self.assertNotIn("knowledge/archived", roots)
        self.assertEqual([ws.rel(p) for p in ws.meeting_homes()], ["knowledge/leadership"])
        self.assertEqual(ws.rel(ws.people_home()), "knowledge/personnel")

    def test_falls_back_without_a_repo_map(self):
        self.path("CLAUDE.md").unlink()
        ws = Workspace(self.ws)
        self.assertEqual([ws.rel(root) for root in ws.index_roots()], ["knowledge"])
        self.assertEqual([ws.rel(p) for p in ws.meeting_homes()], ["knowledge/leadership"])

    def test_walk_skips_ignored_dot_and_capture_content(self):
        ws = Workspace(self.ws)
        seen = {ws.rel(path) for path in ws.walk(self.ws)}
        self.assertIn("knowledge/AI/Vendor landscape, 2026.md", seen)
        self.assertIn("meeting-notes/2026-11-10_140000_slt-sync/narrative.md", seen)
        self.assertNotIn("meeting-notes/2026-11-10_140000_slt-sync/transcript.md", seen)
        self.assertNotIn("knowledge/AI/build.log", seen)
        self.assertNotIn("knowledge/.obsidian/app.json", seen)
        self.assertNotIn("projects/orion/src/main.rs", seen)

    def test_resolve_refuses_paths_outside_the_workspace(self):
        from pka_tools.errors import ToolError
        ws = Workspace(self.ws)
        with self.assertRaises(ToolError):
            ws.resolve("../outside.md")
        with self.assertRaises(ToolError):
            ws.resolve("/etc/hosts")

    def test_domain_tag(self):
        self.assertEqual(domain_tag("AI"), "ai")
        self.assertEqual(domain_tag("ArchCouncil"), "archcouncil")
        self.assertEqual(domain_tag("lab-notebook"), "lab-notebook")
        self.assertEqual(domain_tag("Dev Process"), "dev-process")


if __name__ == "__main__":
    unittest.main()
