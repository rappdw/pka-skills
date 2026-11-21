"""`pka-tools actions`: every form of action item it reads, and the ones it
does not. The forms are the one pka-meetings writes
(`- [ ] action — @owner — by date`) and the one thinkkit's take-notes writes
(`- [ ] **Owner**: action (due: date)`). `actions` only reads: a note is
never rewritten into another form."""
from __future__ import annotations

import datetime
import unittest

import support

from pka_tools import actions

NOTE = "knowledge/leadership/2026-11-20-hiring-sync.md"
DAY = datetime.date(2026, 11, 20)


class Owners(unittest.TestCase):
    def owners(self, text):
        return actions.owners_of(text)

    def test_at_mentions_as_before(self):
        self.assertEqual(self.owners("Review the Q2 budget proposal @Sam"), ["Sam"])
        self.assertEqual(self.owners("Send the comparison — @Sam — by 2026-05-01"), ["Sam"])
        self.assertEqual(self.owners("Pair on it @Priya @robin.smith"), ["Priya", "robin.smith"])

    def test_an_email_address_or_a_path_is_not_an_owner(self):
        self.assertEqual(self.owners("Write to sam@example.com"), [])
        self.assertEqual(self.owners("Check node_modules/@types"), [])
        self.assertEqual(self.owners("Install @types/node"), [])

    def test_punctuation_after_a_mention_is_not_part_of_the_name(self):
        self.assertEqual(self.owners("Ask @Sam."), ["Sam"])
        self.assertEqual(self.owners("Ask @Sam, then @Priya; then @robin.smith."), ["Sam", "Priya", "robin.smith"])
        self.assertEqual(self.owners("For @Sam-"), ["Sam"])
        self.assertEqual(self.owners("Ask @zoë-åkesson!"), ["zoë-åkesson"])

    def test_a_mention_inside_code_is_not_an_owner(self):
        self.assertEqual(self.owners("Add the `@dataclass` decorator"), [])
        self.assertEqual(self.owners("Add ``@property`` for @Sam"), ["Sam"])
        self.assertEqual(self.owners("Hidden <!-- @Robin --> note"), [])

    def test_thinkkit_bold_name_with_a_colon(self):
        self.assertEqual(self.owners("**Robin**: Draft the Q1 hiring plan (due: 2026-12-01)"), ["Robin"])
        self.assertEqual(self.owners("**Robin:** Draft the Q1 hiring plan"), ["Robin"])
        self.assertEqual(self.owners("__Robin__: Draft the Q1 hiring plan"), ["Robin"])
        self.assertEqual(self.owners("**Robin Smith**: Draft the plan"), ["Robin Smith"])
        self.assertEqual(self.owners("**Robin (Northwind)**: Draft the plan"), ["Robin"])
        self.assertEqual(self.owners("**@Robin**: Draft the plan"), ["Robin"])

    def test_several_owners_in_the_bold_lead(self):
        for lead in ("Robin and Sam", "Robin, Sam", "Robin & Sam", "Robin / Sam", "Robin, Sam and Priya"):
            found = self.owners("**%s**: Agree the interview panel" % lead)
            self.assertEqual(found[:2], ["Robin", "Sam"], lead)
        self.assertEqual(self.owners("**Robin, Sam and Priya**: Agree the panel"), ["Robin", "Sam", "Priya"])

    def test_bold_owner_and_mentions_are_combined_once_each(self):
        self.assertEqual(self.owners("**Robin**: Draft the plan with @Sam and @robin"), ["Robin", "Sam"])

    def test_a_bold_label_is_not_an_owner(self):
        for label in ("Note", "TODO", "Action", "Decision", "Follow-up", "Owner", "TBD", "Unassigned"):
            self.assertEqual(self.owners("**%s**: Draft the hiring plan" % label), [], label)

    def test_a_bold_phrase_is_not_an_owner(self):
        self.assertEqual(self.owners("**Draft the plan**: before the offsite"), [])
        self.assertEqual(self.owners("**Q1 plan**: draft it"), [])
        self.assertEqual(self.owners("**Robin and the team**: draft it"), [])

    def test_bold_without_a_colon_or_not_at_the_start(self):
        self.assertEqual(self.owners("**Robin** to draft the hiring plan"), [])
        self.assertEqual(self.owners("Draft the plan for **Robin**: the Q1 one"), [])
        self.assertEqual(self.owners("*Robin*: Draft the plan"), [])
        self.assertEqual(self.owners("Robin: Draft the plan"), [])

    def test_a_bold_noun_is_an_owner_only_when_it_names_someone_known(self):
        known = actions.Known(["Robin Smith", "priya", "Priya Nair", "Sam", "Zoë Åkesson"])
        for lead in ("Budget", "Orion", "Decision Needed", "Team", "Northwind", "Lyra", "Hiring Plan", "Everyone"):
            self.assertEqual(actions.owners_of("**%s**: sort it out" % lead, known), [], lead)
        for lead, expected in (("Robin", ["Robin"]), ("Robin Smith", ["Robin Smith"]), ("Smith", ["Smith"]),
                               ("Dr. Smith", ["Dr. Smith"]), ("robin", []), ("Priya", ["Priya"]),
                               ("Zoe Akesson", ["Zoe Akesson"]), ("Robin and Sam", ["Robin", "Sam"]),
                               ("Robin (Northwind)", ["Robin"]), ("@Sam", ["Sam"])):
            self.assertEqual(actions.owners_of("**%s**: sort it out" % lead, known), expected, lead)
        # When unsure, no owner: one unknown name and the lead-in names nobody.
        self.assertEqual(actions.owners_of("**Robin and Budget**: sort it out", known), [])
        self.assertEqual(actions.owners_of("**Robin Nair**: sort it out", known), [])
        # A mention is an owner whoever it is.
        self.assertEqual(actions.owners_of("**Budget**: sort it out @Lyra", known), ["Lyra"])
        self.assertEqual(actions.owners_of("**Robin**: sort it out", actions.Known()), [])

    def test_attendees_are_read_from_the_three_places_a_note_has_them(self):
        lines = support.split_lines(
            "---\nattendees: [priya, robin-smith]\n---\n# Sync\n\n**Date**: 2026-11-20\n"
            "**Attendees**: Robin (PM, Northwind), Sam and Priya\n\n```\n**Attendees**: Nobody\n```\n\n"
            "## Attendees\n- [Priya](../personnel/priya/)\n- [[personnel/zoë-åkesson/index|Zoë]] — CTO\n- Sam (guest)\n"
            "\n## Notes\n- Budget\n")
        self.assertEqual(actions.attendees_of(lines),
                         ["priya", "robin-smith", "Robin", "Sam", "Priya", "Priya", "Zoë", "Sam"])
        self.assertEqual(actions.attendees_of(support.split_lines("**Attendees:** Sam, Robin\n")), ["Sam", "Robin"])
        self.assertEqual(actions.attendees_of(support.split_lines("Attendees: Sam; Robin\n")), ["Sam", "Robin"])
        self.assertEqual(actions.attendees_of(support.split_lines("# Notes\n\nNo list here.\n")), [])

    def test_names_with_particles_accents_and_hyphens(self):
        self.assertEqual(self.owners("**Robin van Smith**: Draft it"), ["Robin van Smith"])
        self.assertEqual(self.owners("**Zoë Åkesson-Smith**: Draft it"), ["Zoë Åkesson-Smith"])
        self.assertEqual(self.owners("**Dr. Nair**: Draft it"), ["Dr. Nair"])
        self.assertEqual(self.owners("**van**: Draft it"), [])


class Due(unittest.TestCase):
    def due(self, text, date=DAY):
        return actions.due_of(text, date)

    def test_by_and_due_with_an_iso_date_as_before(self):
        self.assertEqual(self.due("Send it @Sam by 2026-05-01"), ("2026-05-01", "2026-05-01"))
        self.assertEqual(self.due("Send it, due 2026-05-01"), ("2026-05-01", "2026-05-01"))
        self.assertEqual(self.due("Send it — @Sam — by 2026-05-01"), ("2026-05-01", "2026-05-01"))

    def test_thinkkit_bracketed_due(self):
        self.assertEqual(self.due("**Robin**: Draft the plan (due: 2026-12-01)"), ("2026-12-01", "2026-12-01"))
        self.assertEqual(self.due("**Robin**: Draft the plan (Due: 2026-12-01)"), ("2026-12-01", "2026-12-01"))
        self.assertEqual(self.due("**Robin**: Draft the plan (due 2026-12-01)"), ("2026-12-01", "2026-12-01"))
        self.assertEqual(self.due("**Robin**: Draft the plan (by: 2026-12-01)"), ("2026-12-01", "2026-12-01"))
        self.assertEqual(self.due("**Robin**: Draft the plan [due: 2026-12-01]"), ("2026-12-01", "2026-12-01"))

    def test_month_names_take_the_year_from_the_note(self):
        self.assertEqual(self.due("x (due: Dec 1)"), ("2026-12-01", "Dec 1"))
        self.assertEqual(self.due("x (due: December 1st)"), ("2026-12-01", "December 1st"))
        self.assertEqual(self.due("x (due: 1 December)"), ("2026-12-01", "1 December"))
        self.assertEqual(self.due("x (due: Sept. 3, 2027)"), ("2027-09-03", "Sept. 3, 2027"))
        self.assertEqual(self.due("x (due: 3 Jan 2027)"), ("2027-01-03", "3 Jan 2027"))
        # No year: the first such day on or after the note's date.
        self.assertEqual(self.due("x (due: Jan 15)"), ("2027-01-15", "Jan 15"))
        self.assertEqual(self.due("x (due: Nov 20)"), ("2026-11-20", "Nov 20"))

    def test_a_month_name_without_a_year_needs_a_dated_note(self):
        self.assertEqual(self.due("x (due: Dec 1)", None), (None, "Dec 1"))
        self.assertEqual(self.due("x (due: Dec 1, 2026)", None), ("2026-12-01", "Dec 1, 2026"))

    def test_what_is_not_a_calendar_date_is_returned_as_written(self):
        for written in ("Friday", "next week", "end of month", "EOD", "12/1", "12/01/2026", "Q1", "Feb 30",
                        "2026-13-45"):
            self.assertEqual(self.due("**Robin**: Draft the plan (due: %s)" % written), (None, written), written)

    def test_a_bare_iso_date_ends_the_item_after_a_dash(self):
        self.assertEqual(self.due("Send it — @Sam — 2026-11-21"), ("2026-11-21", "2026-11-21"))
        self.assertEqual(self.due("Send it – 2026-11-21"), ("2026-11-21", "2026-11-21"))
        self.assertEqual(self.due("Send it - 2026-11-21."), ("2026-11-21", "2026-11-21"))
        self.assertEqual(self.due("Send it —2026-11-21"), ("2026-11-21", "2026-11-21"))

    def test_an_iso_date_anywhere_else_is_not_a_due_date(self):
        for text in ("Review the 2026-11-21 minutes",
                     "Send it — 2026-11-21 — @Sam",
                     "Re-read the notes from 2026-11-21",
                     "Rename plan-2026-11-21",
                     "Cover the period 2026-11-01 — 2026-11-21",
                     "Standby 2026-11-21 rota"):
            self.assertEqual(self.due(text), (None, None), text)

    def test_two_different_dates_are_never_one_due_date(self):
        for text, written in (
                ("x (due: 2026-12-01 or 2026-12-05)", "2026-12-01 or 2026-12-05"),
                ("x (due: 2026-12-01 – 2026-12-05)", "2026-12-01 – 2026-12-05"),
                ("x (due: 2026-12-01 to 2026-12-05)", "2026-12-01 to 2026-12-05"),
                ("x due 2026-12-01 to 2026-12-05", "2026-12-01 to 2026-12-05"),
                ("x by 2026-12-01 or 2026-12-05", "2026-12-01 or 2026-12-05"),
                ("x by 2026-12-01 - 2026-12-05", "2026-12-01 - 2026-12-05"),
                ("x due: 2026-12-01/2026-12-05", "2026-12-01/2026-12-05"),
                ("x (due: 2026-12-01) (due: 2026-12-31)", "2026-12-01; 2026-12-31"),
                ("x (due: 2026-12-01) — 2026-12-31", "2026-12-01; 2026-12-31"),
                ("x (due: Dec 1) — 2026-12-02", "Dec 1; 2026-12-02"),
                ("Send it by 2026-11-25 — 2026-11-21", "2026-11-25 — 2026-11-21"),
                ("x by 2026-12-01 (due: 2026-12-05)", "2026-12-01; 2026-12-05"),
                ("x (due: next Friday, 2026-12-04) — 2026-12-09", "next Friday, 2026-12-04; 2026-12-09")):
            self.assertEqual(self.due(text), (None, written), text)

    def test_a_bracket_is_resolved_only_when_it_is_exactly_one_date(self):
        self.assertEqual(self.due("x (due: next Friday, 2026-12-04)"), (None, "next Friday, 2026-12-04"))
        self.assertEqual(self.due("x (due: 2026-12-04 at the latest)"), (None, "2026-12-04 at the latest"))
        self.assertEqual(self.due("x (due: a week after 2026-12-04)"), (None, "a week after 2026-12-04"))

    def test_a_bracket_that_is_not_a_date_does_not_hide_the_date_after_the_dash(self):
        self.assertEqual(self.due("Send it (due: tomorrow) — @Sam — 2026-12-09"), ("2026-12-09", "tomorrow"))
        self.assertEqual(self.due("Send it (due: Friday) — 2026-11-21"), ("2026-11-21", "Friday"))
        self.assertEqual(self.due("Send it (due: Friday) by 2026-11-21"), ("2026-11-21", "Friday"))

    def test_the_same_date_said_twice_is_one_date(self):
        self.assertEqual(self.due("x (due: 2026-12-01) — 2026-12-01"), ("2026-12-01", "2026-12-01"))
        self.assertEqual(self.due("x (due: Dec 1) — 2026-12-01"), ("2026-12-01", "Dec 1"))
        self.assertEqual(self.due("x by 2026-12-01 — 2026-12-01")[0], "2026-12-01")

    def test_words_in_a_bracket_that_are_not_about_time(self):
        for text in ("Finish the (due diligence) pack", "Review [by Robin] the draft", "Sign (by hand) the form",
                     "Check (due process) with legal", "Use (by default) the template"):
            self.assertEqual(self.due(text), (None, None), text)
        # With a colon the bracket is a due field whatever it holds; without one it must speak of time.
        for text, written in (("x (due Friday)", "Friday"), ("x (by end of month)", "end of month"),
                              ("x (due next sprint)", "next sprint"), ("x [by EOD]", "EOD"), ("x (by Q1)", "Q1"),
                              ("x (due: when Robin is back)", "when Robin is back")):
            self.assertEqual(self.due(text), (None, written), text)

    def test_by_after_a_verb_that_owns_it_is_not_a_deadline(self):
        for text in ("It went by 2026-12-01 standards", "Stand by 2026-12-01", "We stood by 2026-12-01 as agreed",
                     "Drop by 2026-12-01 if free", "Abide by 2026-12-01 rules"):
            self.assertEqual(self.due(text), (None, None), text)
        self.assertEqual(self.due("Send it by 2026-12-01 to Sam"), ("2026-12-01", "2026-12-01"))
        self.assertEqual(self.due("Stand in, due 2026-12-01"), ("2026-12-01", "2026-12-01"))

    def test_a_date_inside_code_is_not_a_due_date(self):
        self.assertEqual(self.due("Document the `by 2026-01-01` syntax"), (None, None))
        self.assertEqual(self.due("Document `(due: Friday)` — 2026-12-01"), ("2026-12-01", "2026-12-01"))

    def test_a_yearless_date_just_before_the_note_is_not_guessed(self):
        christmas = datetime.date(2026, 12, 25)
        self.assertEqual(actions.due_of("x (due: Dec 24)", christmas), (None, "Dec 24"))
        self.assertEqual(actions.due_of("x (due: Nov 1)", christmas), (None, "Nov 1"))
        self.assertEqual(actions.due_of("x (due: Dec 25)", christmas), ("2026-12-25", "Dec 25"))
        self.assertEqual(actions.due_of("x (due: Jan 5)", christmas), ("2027-01-05", "Jan 5"))
        self.assertEqual(actions.due_of("x (due: Sep 30)", christmas), ("2027-09-30", "Sep 30"))
        self.assertEqual(actions.due_of("x (due: Dec 24, 2027)", christmas), ("2027-12-24", "Dec 24, 2027"))


class InNotes(support.ToolsCase):
    """The same forms, through the vendored command, in a filed note."""

    def items(self, body, name=NOTE, *args):
        self.write(name, body)
        result = self.json("actions", "--under", name.rsplit("/", 1)[0], "--since", "2026-11-20",
                           "--until", "2026-11-20", *args)
        return result

    def test_a_thinkkit_note_gives_owner_and_due(self):
        body = ("# Hiring sync\n\n**Date**: 2026-11-20\n**Attendees**: Robin (PM), Sam, Priya\n\n## Notes\n\n"
                "**Robin**: The Q1 plan needs a draft.\n\n## Action Items\n\n"
                "- [ ] **Robin**: Draft the Q1 hiring plan (due: 2026-12-01)\n"
                "- [ ] **Sam**: Book the interview rooms (due: Friday)\n"
                "- [ ] **Priya and Sam**: Agree the panel\n"
                "- [x] **Robin**: Send the agenda (due: 2026-11-19)\n"
                "- [ ] Circulate the notes\n\n## Open Questions\n\n- Who signs off the budget?\n")
        result = self.items(body)
        got = [(i["owners"], i["due"], i["due_text"]) for i in result["items"]]
        self.assertEqual(got, [(["Robin"], "2026-12-01", "2026-12-01"),
                               (["Sam"], None, "Friday"),
                               (["Priya", "Sam"], None, None),
                               ([], None, None)])
        self.assertEqual((result["open"], result["closed"]), (4, 1))
        self.assertEqual(result["items"][0]["text"], "**Robin**: Draft the Q1 hiring plan (due: 2026-12-01)")
        self.assertEqual(result["items"][0]["line"], 12)

    def test_the_pka_meetings_form_with_and_without_by(self):
        result = self.items("## Action Items\n"
                            "- [ ] Send the comparison — @Sam — by 2026-11-28\n"
                            "- [ ] Review the budget — @Priya — 2026-11-27\n"
                            "- [ ] Review the 2026-11-21 minutes — @Robin\n")
        self.assertEqual([(i["owners"], i["due"]) for i in result["items"]],
                         [(["Sam"], "2026-11-28"), (["Priya"], "2026-11-27"), (["Robin"], None)])

    def test_nested_and_numbered_items_are_read(self):
        result = self.items("**Attendees**: Robin, Sam, Priya\n\n- Hiring\n"
                            "  - [ ] **Robin**: Draft the plan (due: Dec 1)\n"
                            "    * [ ] **Sam**: Cost it — 2026-11-30\n"
                            "1. [ ] **Priya**: Review it\n"
                            "\t+ [ ] Tabbed item @Sam\n")
        self.assertEqual([(i["owners"], i["due"]) for i in result["items"]],
                         [(["Robin"], "2026-12-01"), (["Sam"], "2026-11-30"), (["Priya"], None), (["Sam"], None)])

    def test_a_bold_label_in_a_filed_note_is_not_an_owner(self):
        result = self.items("# Planning\n\n**Attendees**: Sam (guest)\n\n## Action Items\n"
                            "- [ ] **Budget**: agree the number\n"
                            "- [ ] **Orion**: decide on the adapter\n"
                            "- [ ] **Decision Needed**: who signs\n"
                            "- [ ] **Team**: read the plan\n"
                            "- [ ] **Priya**: from her person folder\n"
                            "- [ ] **Robin Smith**: from the folder robin-smith\n"
                            "- [ ] **Sam**: an attendee of this note\n"
                            "- [ ] **Budget**: with a mention @Sam\n")
        self.assertEqual([i["owners"] for i in result["items"]],
                         [[], [], [], [], ["Priya"], ["Robin Smith"], ["Sam"], ["Sam"]])

    def test_the_owner_in_the_owner_profile_is_known(self):
        body = "- [ ] **Sam**: Write the plan\n- [ ] **Lyra**: Review it\n"
        self.assertEqual([i["owners"] for i in self.items(body)["items"]], [[], []])
        self.write(".pka/owner-profile.md", "---\nname: Sam\nrole: Engineering manager\n---\n\n# Sam\n")
        self.assertEqual([i["owners"] for i in self.items(body)["items"]], [["Sam"], []])
        self.write(".pka/owner-profile.md", "# Owner Profile\n\n- Name: Sam\n- Role: Engineering manager\n")
        self.assertEqual([i["owners"] for i in self.items(body)["items"]], [["Sam"], []])

    def test_items_in_a_quote_or_a_callout_are_read(self):
        result = self.items("> [!todo] Follow-ups\n> - [ ] Send the deck @Sam by 2026-11-28\n> - [x] Done already\n"
                            "> > - [ ] Quoted twice\n")
        self.assertEqual([(i["text"], i["owners"], i["due"]) for i in result["items"]],
                         [("Send the deck @Sam by 2026-11-28", ["Sam"], "2026-11-28"), ("Quoted twice", [], None)])
        self.assertEqual(result["closed"], 1)

    def test_items_in_a_comment_a_math_block_or_indented_code_are_not_items(self):
        result = self.items("<!--\n- [ ] hidden in a comment\n-->\n\n$$\n- [ ] inside math\n$$\n\n"
                            "Example:\n\n    - [ ] indented code\n\n%%\n- [ ] an Obsidian comment\n%%\n\n"
                            "- [ ] the real one\n    - [ ] nested under it\n")
        self.assertEqual([i["text"] for i in result["items"]], ["the real one", "nested under it"])

    def test_two_dates_in_a_filed_note(self):
        self.write(NOTE, "- [ ] Ship it (due: 2026-12-01 or 2026-12-05)\n- [ ] Call (due: tomorrow) — @Sam — 2026-12-09\n"
                         "- [ ] Finish the (due diligence) pack\n")
        result = self.json("actions", "--under", "knowledge/leadership", "--since", "2026-11-20", "--until", "2026-11-20")
        self.assertEqual([(i["due"], i["due_text"]) for i in result["items"]],
                         [(None, "2026-12-01 or 2026-12-05"), ("2026-12-09", "tomorrow"), (None, None)])
        out = self.ok("actions", "--under", "knowledge/leadership", "--since", "2026-11-20", "--until", "2026-11-20")
        self.assertIn("%s:1  [due: 2026-12-01 or 2026-12-05 (as written)]" % NOTE, out)
        self.assertIn("%s:2  [owner: Sam; due: 2026-12-09]" % NOTE, out)
        self.assertIn("      %s:3\n" % NOTE, out)
        self.assertNotIn("diligence (as written)", out)

    def test_items_inside_code_fences_are_examples(self):
        result = self.items("Format:\n\n```markdown\n- [ ] **Owner**: Description (due: 2026-12-01)\n```\n\n"
                            "~~~\n- [ ] **Robin**: also an example\n~~~\n\n- [ ] **Robin**: the real one\n")
        self.assertEqual([i["text"] for i in result["items"]], ["**Robin**: the real one"])

    def test_a_ticked_box_is_closed_in_either_form(self):
        result = self.items("- [x] **Robin**: Draft the plan (due: 2026-12-01)\n"
                            "- [X] Send the comparison — @Sam — by 2026-11-28\n"
                            "  - [x] nested and done\n")
        self.assertEqual((result["open"], result["closed"], result["items"]), (0, 3, []))

    def test_what_is_not_a_checkbox_is_not_an_item(self):
        result = self.items("- **Robin**: Draft the plan (due: 2026-12-01)\n"
                            "**Robin**: Draft the plan (due: 2026-12-01)\n"
                            "- [] **Robin**: no space in the box\n"
                            "- [ ]\n"
                            "-[ ] **Robin**: no space after the dash\n")
        self.assertEqual(result["open"], 0)

    def test_the_note_is_never_rewritten(self):
        body = ("## Action Items\r\n- [ ] **Robin**: Draft the Q1 hiring plan (due: 2026-12-01)\r\n"
                "- [ ] Send it — @Sam — 2026-11-27")
        self.write(NOTE, body)
        before = self.snapshot("knowledge")
        for args in (("actions", "--all-dates"), ("actions", "--all-dates", "--scope", "all", "--json")):
            self.ok(*args)
        self.assertEqual(self.changed(before, self.snapshot("knowledge")), [])
        self.assertEqual(self.read(NOTE), body.encode("utf-8"))

    def test_text_output_names_owner_and_due(self):
        self.write(NOTE, "**Attendees**: Robin, Sam\n\n- [ ] **Robin**: Draft the plan (due: 2026-12-01)\n"
                         "- [ ] **Sam**: Book rooms (due: Friday)\n- [ ] Circulate the notes\n")
        out = self.ok("actions", "--under", "knowledge/leadership", "--since", "2026-11-20", "--until", "2026-11-20")
        self.assertIn("%s:3  [owner: Robin; due: 2026-12-01]" % NOTE, out)
        self.assertIn("%s:4  [owner: Sam; due: Friday (as written)]" % NOTE, out)
        self.assertIn("      %s:5\n" % NOTE, out)

    def test_an_undated_note_leaves_a_yearless_date_unresolved(self):
        self.write("knowledge/leadership/standing-items.md", "- [ ] **Robin**: Draft it (due: Dec 1)\n")
        result = self.json("actions", "--under", "knowledge/leadership", "--all-dates", "--include-undated")
        item = [i for i in result["items"] if i["path"].endswith("standing-items.md")][0]
        self.assertEqual((item["date"], item["due"], item["due_text"]), (None, None, "Dec 1"))


if __name__ == "__main__":
    unittest.main()
