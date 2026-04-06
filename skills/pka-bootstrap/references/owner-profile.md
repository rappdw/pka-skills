# Owner Profile

At bootstrap, the system captures a lightweight owner profile that gives every role
enough context to communicate in the owner's voice and understand their priorities.
The profile is stored at `.pka/owner-profile.md` and referenced by all roles.

---

## Interview Protocol

The owner profile is built by expanding Q1 of the bootstrap interview. Instead of
just asking for a first name, the system asks a small cluster of questions. These
should feel conversational, not like a form — the agent gathers what it can from
natural responses and only asks follow-ups for gaps.

### Required Fields

| Field | Question | Example |
|-------|----------|---------|
| **Name** | "What's your first name?" | Dan |
| **Role / title** | "What do you do — title or one-liner is fine?" | VP Engineering at Acme / independent researcher / grad student in ML |
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
- The profile is a living document — roles can update it as they learn more about the owner through normal interaction.

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

- **@orchestrator** — adapts greeting verbosity and session summaries to communication style
- **@researcher** — matches output depth and framing to domain expertise (don't over-explain what they already know)
- **@librarian** — uses domain expertise to improve routing confidence (a document about "distributed consensus" is high-relevance for someone with distributed systems expertise)
- **All roles** — reference the profile when generating any owner-facing content to maintain consistent voice and appropriate technical depth

---

## Updating the Profile

The profile updates organically:
- Any role that learns something new about the owner (e.g., "I just switched teams" or "I prefer shorter summaries") appends to the relevant section
- Updates logged in `session-log.md`: `## <date> | <role> | Updated owner profile: <what changed>`
- The `last-updated` frontmatter field is refreshed on every edit
