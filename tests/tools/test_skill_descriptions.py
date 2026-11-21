"""The `description` in each skill's frontmatter is what decides which skill
a request reaches. Two things go wrong with it silently: it grows past the
1,024 characters a description may have, and two skills claim the same
phrase, so which one answers is a coin toss.

Ownership of the first-contact phrases:

  pka-tutorial    newcomers and questions: "I just installed PKA", a tour,
                  "how do I…", "what can this do", "what's new"
  pka-bootstrap   doing the setup or the upgrade: "set up PKA", "bootstrap …",
                  "upgrade my PKA"

The other skills name only their own job and defer to these two.
"""
from __future__ import annotations

import re
import unittest
from typing import Dict, List

import support

SKILLS = support.REPO / "skills"
LIMIT = 1024
EXPECTED = {"pka-bootstrap", "pka-interface", "pka-librarian", "pka-meetings", "pka-tutorial", "pka-wiki"}

# Words that only the owner's description may use, in or out of quotes
# (skill names such as `pka-bootstrap` are set aside before looking).
RESERVED = {
    "pka-tutorial": ["just installed", "new here", "how do i", "what can", "tour", "walk me through",
                     "what's new", "get started", "show me the ropes"],
    "pka-bootstrap": ["set up pka", "set up my pka", "initialize pka", "bootstrap", "upgrade my pka"],
}
# Phrases the owner must go on claiming, quoted.
MUST_QUOTE = {
    "pka-tutorial": ["i just installed pka", "how do i use this", "what can this do", "give me a tour",
                     "what's new", "do i need to upgrade"],
    "pka-bootstrap": ["set up pka", "set up my pka", "bootstrap upgrade", "upgrade my pka", "bootstrap obsidian"],
}


def description(text: str) -> str:
    """The frontmatter `description`, with a folded (`>`) or literal (`|`)
    block joined the way a YAML reader folds it: lines joined by one space."""
    lines = text.split("\n")
    if lines[0] != "---":
        raise AssertionError("no frontmatter")
    end = lines.index("---", 1)
    for idx in range(1, end):
        if not lines[idx].startswith("description:"):
            continue
        rest = lines[idx][len("description:"):].strip()
        if rest not in (">", ">-", ">+", "|", "|-", "|+"):
            return rest.strip("\"'")
        body: List[str] = []
        for line in lines[idx + 1:end]:
            if line.strip() and not line.startswith((" ", "\t")):
                break
            body.append(line.strip())
        return " ".join(part for part in body if part)
    raise AssertionError("no description")


def normalise(phrase: str) -> str:
    phrase = phrase.lower().replace("’", "'").replace("…", "...")
    phrase = re.sub(r"[.?!,;:]+$", "", phrase.strip())
    return re.sub(r"\s+", " ", phrase).strip()


def quoted(text: str) -> List[str]:
    return [normalise(found) for found in re.findall(r'"([^"]+)"', text)]


def descriptions() -> Dict[str, str]:
    return {path.parent.name: description(path.read_text(encoding="utf-8"))
            for path in sorted(SKILLS.glob("*/SKILL.md"))}


class Parsing(unittest.TestCase):
    def test_folded_block_is_joined_with_single_spaces(self):
        text = "---\nname: x\ndescription: >\n  One two\n  three.\n\n  Four.\nuser-invocable: true\n---\nbody\n"
        self.assertEqual(description(text), "One two three. Four.")

    def test_plain_scalar(self):
        self.assertEqual(description('---\ndescription: "One line."\n---\n'), "One line.")

    def test_quoted_phrases_are_normalised(self):
        self.assertEqual(quoted('Use for "What’s  new?", "re-index".'), ["what's new", "re-index"])


class Descriptions(unittest.TestCase):
    def setUp(self):
        self.found = descriptions()

    def test_every_skill_has_one(self):
        self.assertEqual(set(self.found), EXPECTED)
        for name, text in self.found.items():
            self.assertGreater(len(text), 100, name)

    def test_none_is_longer_than_the_limit(self):
        over = {name: len(text) for name, text in self.found.items()
                if len(text) > LIMIT or len(text.encode("utf-8")) > LIMIT}
        self.assertEqual(over, {}, "descriptions over %d characters: %s" % (LIMIT, over))

    def test_no_quoted_trigger_is_claimed_by_two_skills(self):
        owners: Dict[str, List[str]] = {}
        for name, text in self.found.items():
            for phrase in sorted(set(quoted(text))):
                owners.setdefault(phrase, []).append(name)
        shared = {phrase: names for phrase, names in owners.items() if len(names) > 1}
        self.assertEqual(shared, {}, "a trigger phrase is quoted by more than one skill")

    def test_no_quoted_trigger_is_inside_another_skills_trigger(self):
        # "bootstrap upgrade" in one skill and "run bootstrap upgrade now" in
        # another compete just as two identical phrases do.
        clashes = []
        for name, text in self.found.items():
            for phrase in set(quoted(text)):
                if len(phrase.split()) < 3:
                    continue
                for other, other_text in self.found.items():
                    if other != name and any(phrase in theirs for theirs in quoted(other_text)):
                        clashes.append((name, phrase, other))
        self.assertEqual(clashes, [])

    def test_first_contact_words_belong_to_their_owner(self):
        strays = []
        for owner, words in RESERVED.items():
            for name, text in self.found.items():
                if name == owner:
                    continue
                plain = re.sub(r"pka-[a-z]+", " ", text.lower().replace("’", "'"))
                strays.extend((name, word) for word in words if re.search(r"\b%s\b" % re.escape(word), plain))
        self.assertEqual(strays, [], "another skill's description uses a phrase that %s own" % " and ".join(RESERVED))

    def test_owners_still_claim_their_phrases(self):
        for owner, phrases in MUST_QUOTE.items():
            have = quoted(self.found[owner])
            for phrase in phrases:
                self.assertIn(phrase, have, "%s no longer quotes %r" % (owner, phrase))

    def test_the_others_say_where_newcomers_and_setup_go(self):
        self.assertIn("pka-bootstrap", self.found["pka-tutorial"])
        self.assertIn("pka-tutorial", self.found["pka-bootstrap"])
        for name in ("pka-librarian", "pka-meetings", "pka-wiki"):
            self.assertIn("pka-tutorial", self.found[name], name)


class TheCheckItself(unittest.TestCase):
    """The checks above must fail on the things they are for."""

    def test_a_long_description_is_caught(self):
        text = "---\ndescription: >\n" + "".join("  %s\n" % ("word " * 15).strip() for _ in range(15)) + "---\n"
        self.assertGreater(len(description(text)), LIMIT)

    def test_a_shared_phrase_is_caught(self):
        one = quoted('Triggers: "I just installed PKA".')
        two = quoted('Use when the user says "i just installed pka!"')
        self.assertEqual(set(one) & set(two), {"i just installed pka"})


if __name__ == "__main__":
    unittest.main()
