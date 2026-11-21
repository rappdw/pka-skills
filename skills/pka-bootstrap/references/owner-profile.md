# Owner Profile

At bootstrap, the system captures a lightweight owner profile that gives every role
enough context to communicate in the owner's voice and understand their priorities.
The profile is stored at `.pka/owner-profile.md`. The orchestrator reads it once at
session start; the role seeds (`role-definitions.md`, section "Owner profile and
decision log" of each role) and the `CLAUDE.md` template say who uses it for what.

---

## Interview Protocol

The owner profile is built by expanding Q1 of the bootstrap interview. Instead of
just asking for a first name, the system asks a small cluster of questions. These
should feel conversational, not like a form — the agent gathers what it can from
natural responses and only asks follow-ups for gaps.

### Required Fields

| Field | Question | Example |
|-------|----------|---------|
| **Name** | "What's your first name?" | Sam |
| **Role / title** | "What do you do — title or one-liner is fine?" | VP Engineering at Northwind / independent researcher / grad student in ML |
| **Domain expertise** | "What are you strongest in? A few keywords is enough." | distributed systems, team leadership, Rust |

### Optional Fields (inferred or asked as follow-ups)

| Field | How to gather | Example |
|-------|---------------|---------|
| **Communication style** | Inferred from conversation so far, or ask: "When I write for you, do you prefer concise bullet points, narrative prose, or somewhere in between?" | concise, direct, minimal jargon |
| **Current goals** | "What are you focused on right now — any top priorities I should know?" | shipping v2 by Q3, writing a paper on X |
| **Working context** | "Solo or team? Anything about how you work that I should know?" | manages 8 engineers, async-heavy, US Pacific time |

### Rules

- Never ask more than 5 questions total across the entire bootstrap interview (3 original + up to 2 profile follow-ups).
- If the user gives a terse answer, accept it — don't push for more detail.
- If the user says "skip" or similar, write what you have and move on.
- The profile is a living document — the orchestrator updates it when the owner says something lasting (see "Updating the Profile").

---

## Output: `.pka/owner-profile.md`

```markdown
---
name: {{name}}
role: {{role_title}}
expertise: [{{domain_keywords}}]
communication: {{style}}
last-updated: {{date}}
---

# {{name}}

## Role
{{role_title}}

## Domain Expertise
{{expertise_narrative_or_list}}

## Communication Style
{{style_description}}
Preferred formats: {{preferred_formats}}

## Current Goals
{{goals_list}}

## Working Context
{{working_context}}
```

### Placeholder Reference

| Placeholder | Source |
|-------------|--------|
| `{{name}}` | Q1 |
| `{{role_title}}` | Profile question |
| `{{domain_keywords}}` | Profile question, comma-separated |
| `{{style}}` | Inferred or asked — one of: concise, narrative, mixed |
| `{{style_description}}` | 1-2 sentences on how to write for this person |
| `{{preferred_formats}}` | bullet points, prose, tables, etc. |
| `{{goals_list}}` | Bulleted list of current priorities |
| `{{working_context}}` | Team size, timezone, work style notes |

---

## How Roles Use the Profile

The rules live in the role seeds; this is the summary.

- **@orchestrator** — reads the file once at session start and keeps it for the session. Adapts the greeting, summaries and deliveries to the communication style; leads the greeting with what the current goals make important; passes the expertise on when delegating. The only role that edits the profile.
- **@researcher** — matches output depth and framing to domain expertise (don't over-explain what they already know)
- **@librarian** — uses domain expertise to improve routing confidence (a document about "distributed consensus" is high-relevance for someone with distributed systems expertise). The profile never overrides the Repo Map or a routing rule.

**The profile does not hold the autonomy level.** That is set in `## Autonomy Level` of `CLAUDE.md` and nowhere else, so there is one place to read it and one place to change it.

Where the profile and `## Communication Style` in `CLAUDE.md` differ, the profile is followed: `CLAUDE.md` records what was said at setup and the profile is kept current.

A workspace without the file (set up before profiles existed, or the file was deleted) works from `CLAUDE.md` alone. No role creates a profile unasked.

---

## Updating the Profile

The profile changes when the owner says something lasting about themselves or about how they want to be written for ("I just switched teams", "I prefer shorter summaries"):
- The orchestrator edits the section it belongs in. Another role that hears it passes it to the orchestrator
- Only what the owner said is recorded, never an inference about them
- The update is logged: `.pka/bin/pka-tools log add --role orchestrator --summary "Updated owner profile: <what changed>"`
- The `last-updated` frontmatter field is refreshed on every edit
