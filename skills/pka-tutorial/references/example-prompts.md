# Example Prompts Library

Categorized by module. Use these when teaching a new user; adapt folder names
and topics to their actual Repo Map.

---

## Orientation

- "Show me my current Repo Map"
- "What's in `<folder>`?"
- "How is my knowledge base organized?"
- "What autonomy level am I on?"
- "Show me my owner profile"

## Finding Things

### Simple lookup
- "What do I know about `<person>`?"
- "What do I know about `<topic>`?"
- "Pull up my notes on `<subject>`"

### Cross-repo search
- "Find everything I've written about `<topic>` across all my work"
- "Search for `<keyword>` in my knowledge base"
- "Where have I mentioned `<project-or-concept>`?"

### Project status
- "What's the state of `<project>`?"
- "Summarize the `<project>` project"
- "What's the most recent update in `<project>`?"

### Date-scoped
- "What did I write about `<topic>` in Q1?"
- "Show me everything from `<month/year>`"
- "What did I decide about `<topic>` last quarter?"

### Decision history
- "What did I decide about `<topic>`?"
- "Why did I archive `<project>`?" (reads decision log)

## The Inbox Pattern

- "Process my team-inbox"
- "What's in team-inbox?"
- "Show me what's in owner-inbox"
- "Route the files I just dropped"
- "File `<document>` into the right folder"

## Meeting Capture

### Starting capture (thinkkit)
- "I'm about to start a 1-1 with `<name>`"
- "Take notes — meeting with `<attendees>` about `<topic>`"
- "Start a meeting note"

### Mid-meeting (inside take-notes)
- Terse bullets: "aarav on mcp work | q2 deadline needs decision | send architecture doc"
- "done" / "end notes" to finish

### Reconcile with transcript
- "Reconcile my `<meeting>` notes against the transcript in team-inbox"
- "I have a Zoom transcript — process it"
- "Generate notes from the transcript directly" (if no manual notes)

### Route-only
- "File these meeting notes: `<path>`"
- "File my meeting notes from the `<name>` 1-1"
- "Route this note to the right place"

### Action items
- "What action items do I have this week?"
- "Show me open action items from recent meetings"
- "What did I commit to in last week's meetings?"

## Dashboard

- "Generate my dashboard"
- "Update my dashboard"
- "Refresh the dashboard"
- "Add a `<section-name>` to the dashboard"
- "Add a timeline view for `<folder>`"
- "Show me my dashboard" (asks how to open it)

## Project Lifecycle

- "What projects are winding down?"
- "What projects haven't had activity recently?"
- "Transition `<project>` to knowledge"
- "Archive `<project>`"
- "Restore `<project>` to active"
- "Show me my project summary draft" (after transition Step 1)

## Role System

- "Show me my role roster"
- "What roles do I have?"
- "Add a `<role-name>` to my team"
- "@researcher synthesize `<topic>`"
- "@librarian re-index my knowledge base"
- "Update my communication style"

## Topic Wikis

### Lifecycle
- "Create a topic wiki on `<topic>`"
- "Start a wiki for `<topic>`"
- "Show me my topic wikis"
- "List my topic wikis"
- "Retire my `<topic>` wiki"

### Ingest
- "Ingest `<path>` into my `<topic>` wiki"
- "Add this paper to the `<topic>` wiki"
- "Synthesize this source into `<topic>`"
- "Read `<path>` and update my `<topic>` wiki"

### Query (wiki-aware)
- "What do I know about `<topic>`?" (auto-uses wiki if exists)
- "Summarize my `<topic>` wiki"
- "What's in my `<topic>` wiki that I haven't thought about lately?"

### Thinking
- "Update my thinking on `<topic>`"
- "Add my opinion on `<topic>` to the wiki"
- "My view has changed on `<topic>`"

## Health Checks

- "Run a health check"
- "Lint my knowledge base"
- "What needs attention?"
- "Check for broken links"
- "What files are orphaned?"
- "Quick lint" (fast subset)
- "Full lint"

## Meta / Getting Help

- "Give me a tour"
- "Walk me through PKA"
- "Teach me `<capability>`"
- "Show me the reference tutorial"
- "What can PKA do?"
- "I'm stuck — what do I do next?"

---

## Adapting prompts

When giving examples to a user, **substitute their real folder names and
topics**. Bad:

> Try: "What do I know about Aarav?"

Good (after reading their Repo Map and seeing a `personnel/` folder with real
subfolders):

> Try: "What do I know about Maria?" — that's a real person in your
> `personnel/` folder.

Or if you don't know specifics:

> Try asking about anyone in your `<their-personnel-folder-name>/` folder.
