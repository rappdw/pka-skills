# Project Summary Template

Used when transitioning a project from active workspace to knowledge archive. The orchestrator generates this from the project's `CLAUDE.md` and top-level markdown files.

---

## Template

```markdown
# {{project_name}} — Project Summary
**Period:** {{start_date}} – {{end_date}}
**Transitioned:** {{transition_date}}

## What It Was
{{one_paragraph_description}}

## Key Decisions
{{bullet_list_of_major_decisions}}

## Outcomes
{{what_was_produced_or_achieved}}

## Documents Worth Reading
{{list_of_most_important_files_with_one_line_descriptions}}

## Related Knowledge
{{links_to_related_folders_or_files_in_knowledge_base}}
```

---

## Generation Rules

1. **Source material:** Read the project's `CLAUDE.md` (primary) and all top-level `.md` files (secondary). Do not read code files or subdirectories deeper than one level.

2. **What It Was:** One paragraph. Focus on what the project aimed to accomplish, not how it was structured. Use past tense.

3. **Key Decisions:** Bullet list of significant choices made during the project. Extract from decision-language in documents ("we decided", "the approach is", "chosen over", "rejected because"). Limit to 5–8 items.

4. **Outcomes:** What was produced or achieved. Concrete deliverables: documents, presentations, code, decisions ratified. Include counts where meaningful ("six executive documents", "three-phase migration plan").

5. **Documents Worth Reading:** The 3–5 most important files in the project. For each: filename + one sentence explaining why someone would want to read it. These are the files a future reader should start with.

6. **Related Knowledge:** Cross-references to other folders or files in the knowledge base that provide context. Look for:
   - Personnel folders for key contributors
   - Leadership/strategy notes from the same time period
   - Research outputs that informed the project

---

## Process

1. Draft saved to `owner-inbox/<project>-summary-draft.md`
2. **Mandatory pause** — user must review and approve regardless of autonomy level
3. User may edit the draft directly or provide corrections verbally
4. After approval: summary copied to `<archive-destination>/<project>/project-summary.md`

The summary is the permanent record of the project. It's what surfaces when someone searches the knowledge base years later. Write it for a reader who wasn't involved.

---

## Example

```markdown
# Team Charter — Project Summary
**Period:** Sep 2025 – Jan 2026
**Transitioned:** 2026-03-31

## What It Was
Planning work for the Orion/Beacon team structure. Produced a suite of 
six planning documents: charter, roles matrix, working agreement, 90-day rollout plan.

## Key Decisions
- Shared ownership model with dedicated resources
- Working agreement between platform and product as governing document
- Three-phase rollout: pilot → handoff → steady state
- Roles matrix built at team level, not individual level

## Outcomes
Six published documents. Presented to the leadership team. Working agreement adopted 
by both teams. 90-day rollout plan in execution.

## Documents Worth Reading
- `01-executive-brief.md` — the one-pager for leadership
- `04-working-agreement.md` — the binding governance document
- `06-90-day-rollout-plan.md` — implementation timeline and milestones

## Related Knowledge
- `knowledge/leadership/` — SLT context during this period
- `knowledge/personnel/priya/` — primary stakeholder notes
```
