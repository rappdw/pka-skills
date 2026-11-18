# Upgrade Walkthrough and What's New

The script for a workspace that has not been upgraded on the installed release
(pre-flight step 6 in `SKILL.md`). Two parts: walking the user through
`bootstrap upgrade`, then teaching what the new release lets them do.

The tutorial explains and previews. `pka-bootstrap` performs the upgrade, and
only when the user asks for it.

---

## Part 1: The upgrade walkthrough

### 1. Say where they are

One sentence, with both versions from the `status` check:

> Your workspace was last set up on v1.6.3; the PKA installed here is v1.7.0.

When `vendored_version` is `null`, say "a release before v1.7.0". Do not guess
which one. When the versions are equal and only the role preview shows work to
do (something else installed the toolkit, but `bootstrap upgrade` never ran),
say that the toolkit is current and the role files are not.

### 2. Preview it

Run the plugin's installer with `--dry-run`. It writes nothing.

```
python3 "<plugin root>/bootstrap-assets/tools/pka-tools" install --workspace <root> --dry-run
```

`<root>` is the workspace root, not `.` (the installer does not look upward
from a subfolder). If the command fails, for example on a `manifest.json` that
is not valid JSON, relay its message and stop; nothing was changed.

Read the result with the user rather than pasting it. The first line gives the
counts; a list follows for each kind that is not empty:

| In the preview | What to tell the user |
|---|---|
| `Installed` | New files that will appear under `.pka/`. For a workspace from before v1.7.0 this is the whole toolkit, `.pka/bin/pka-tools`. |
| `Updated`, with "(previous copy saved)" | A workspace from before v1.7.0: the tool cannot tell whether a helper script was edited, so it replaces each one and moves the old file to `.pka/upgrade-backups/<timestamp>/vendored/`. Any edits they made to those scripts are there. |
| `Updated`, without it | The file was unchanged since it was installed, so it is replaced and no copy is kept. |
| `Edited locally AND changed in the plugin` (`conflicts` in the counts) | Their file is kept and stays in use; the plugin's copy is written beside it as `<name>.new` for them to compare. |
| `Kept` | Edited by them, unchanged in the plugin. Nothing happens. |
| `current` in the counts | Already up to date. Nothing happens. |
| `No longer shipped` | A file the plugin has dropped: moved to the backup folder if they never edited it, left in place if they did. |

Then describe what `bootstrap upgrade` does, in order:

1. **Toolkit and helper scripts.** What the preview just showed.
2. **The index, when there is one and its schema is older.** It shows a plan and
   asks before applying. On a yes it copies the database to `.pka/db-backups/`,
   migrates, checks the result, and re-indexes; a failure rolls back. On a no,
   the rest of the upgrade still runs, but indexing and search stay unavailable
   until the migration is done. Skip this point for a markdown-only workspace.
3. **Role files.** `.pka/roles/` is backed up first. Sections that are new in
   this release are added. Sections they already have are not rewritten. It then
   lists sections an earlier release seeded: the ones they never edited can be
   refreshed in one step, and the ones they customised are left alone unless
   they name them.

And the three things that hold throughout:

- Nothing is committed. In a git workspace the changes sit in the working tree
  for them to review.
- Notes are not touched. The upgrade changes `.pka/` only.
- It needs `python3` 3.9 or newer on PATH. If pre-flight found that missing,
  say so now; the upgrade cannot start without it.

If the installed release is more than one release ahead of the workspace, read
the "Existing workspaces" paragraph of each `CHANGELOG.md` entry in between
(`<plugin root>/CHANGELOG.md`) and mention anything a release asks for beyond
`bootstrap upgrade`.

### 3. Hand off

> When you're ready, say **"bootstrap upgrade"**. I'll be here when it's done.

If the user answers "go ahead" or "just do it", that is the explicit request
`pka-bootstrap` needs: say you are switching to `pka-bootstrap` and follow its
Upgrade procedure, including its own questions (the migration, the refresh).
The tutorial's own steps never run the installer without `--dry-run`,
`db migrate --apply`, or `upgrade-roles.py` without `--dry-run`.

If they would rather not upgrade now, respect it: continue with what they asked
for, and say which modules depend on the upgrade when you reach them.

### 4. Read the result with them

Run both pre-flight checks again.

- `vendored_version` equals `tool_version` and the role preview has nothing to
  seed or add: the workspace is on the installed release.
- `schema_current` is `false`: they declined the migration. Say that search and
  indexing wait on it, and that "bootstrap upgrade" offers it again.

Then go through the summary they were shown:

- **Backups.** Name the folders: `.pka/upgrade-backups/<timestamp>/` for scripts
  and role files, `.pka/db-backups/` for the index.
- **`.new` files.** For each, their copy is still in use. Offer to show the
  difference; the choice is theirs.
- **Refreshable sections.** If they said no to the refresh, those role sections
  still carry instructions from the earlier release. They can ask for the
  refresh at any time.
- **Git.** If the workspace is a repository, tell them `.pka/` has uncommitted
  changes that are theirs to review and commit.
- **Other machines.** If they keep this workspace on more than one machine, each
  needs the plugin updated. In a workspace synced through a repository the
  index (`.pka/knowledge.db`) is not shared, so each machine migrates and
  indexes its own.

---

## Part 2: What's new

Teach capabilities, not a change list. For each item: what the user can do now
that they could not before, one prompt to try with their own folder names, and
nothing about how it is implemented unless they ask.

Cover every release after the one the workspace was on, oldest first. Leave out
items that do not apply to this workspace; the condition is given with each
item. Three to five items is a good session. Offer the rest as "there is more
if you want it".

A release with no section below: read its entry in `<plugin root>/CHANGELOG.md`
and present it the same way. Start from the entry's opening paragraph and its
"Added" headings; skip "Tests" and internal changes.

### v1.7.0

**1. People have timelines.** *(Applies when the workspace has a people folder:
`people_home` in `status` is not null.)*
A person's `index.md` gains a `## Timeline`, newest first, the first time a
note involving them is filed after the upgrade: one line per meeting or note,
with a link and a one-line summary of what was decided and what they own. Until
then there is nothing to show, and notes filed before the upgrade are not
added. A line the user edits by hand is never rewritten.

> "File a 1-1 note for `<a person in their people folder>`" — then open
> `<people folder>/<person>/index.md` and look at the Timeline.

**2. Names are matched carefully, and nicknames can be taught.** *(Same
condition.)*
A name is linked to a person only when it is certain: a full name, an alias, or
a first name only one person has. A last name alone, or a first name two people
share, gets a question instead of a guess. When the user settles a nickname
once, it can be saved as an alias and is recognised from then on.

> "From now on, '`<nickname>`' means `<person>`"

**3. Every note is filed the same way.** *(Applies to all workspaces.)*
Meeting notes and wiki pages used to skip steps that routed documents got. Now
anything a skill files gets the same treatment in one pass: frontmatter and a
MOC link in an Obsidian vault, a pointer row, a timeline line and the index.
Mention only the parts this workspace has.

> "File this meeting note" — then look at what the summary says was done.

**4. Indexing and search are done by a tool.** *(Applies in index mode:
`storage_mode` is `index`.)*
They are no longer worked out afresh each session, so they behave the same
every time: only changed files are re-read, deleted files drop out of the
index, and a migration backs the index up first.

> "Re-index my knowledge base"
>
> "What do I know about `<a topic from their Repo Map>`?"

**5. Open action items across dated notes.** *(Applies to all workspaces with
meeting or daily notes.)*
Unchecked checkboxes in dated notes can be listed by date range, without
picking up examples inside code blocks.

> "What action items are still open from the last two weeks?"

**6. The greeting shows what is actually open.** *(Applies to all workspaces.)*
Session-log entries now have one form for every role, so the open threads shown
at the start of a session are things still to do, not counts.

> "What did I leave open last time?"

**7. Pointer tables without Obsidian are a choice.** *(Applies when there is no
Obsidian vault: `obsidian_present` is false.)*
Topic pointer rows in `_MOC.md` files are written only where a MOC already
exists; filing a note no longer creates one. A user who wants the pointer layer
can opt in.

> "Set up pointer tables for my knowledge folders"

**8. Role files can catch up.** *(Applies when the role preview from
pre-flight lists sections that "can be refreshed"; run it again if this is a
later session.)*
Sections of the role files that an earlier release wrote and the user never
edited can be replaced with the current wording in one step. Edited sections are
shown as a difference for the user to decide.

> "Refresh the role sections I haven't edited"

### v1.8.0

**1. PKA no longer commits or pushes.** *(Applies to every workspace; matters
most to one with a `.meta` file at its root.)*
Earlier releases could set a workspace up as a root repository with separate
repositories at `knowledge/` and each `projects/<name>/`, and committed into
them after every filed note. That is gone. Filing a note still does everything
else; the changed files are left for the user to commit, in whatever repository
they keep the workspace in. For a workspace with nested repositories, say it
plainly: their repositories, their `.meta` and their history are untouched, but
nothing is committed or pushed for them any more, and the helper scripts in
`.pka/` (`push-all.sh`, `graduate.sh` and the others) are no longer maintained.
The filing summary reminds them with a "not committed" line.

> "File this note" — then look at `git status` in the folder it went to.

**2. Role files lose their commit and push instructions.** *(Applies when the
role preview lists anything under "Obsolete".)*
The upgrade reports the commit/push sections of the role files and
`.pka/roles/_git-protocol.md` as obsolete. The ones they never edited can be
removed in one step, with a backup; edited ones are left for them to decide.

> "Refresh my role files and remove the obsolete sections"

**3. Moving a finished project keeps its links.** *(Applies to all
workspaces.)*
Transitioning a project into `knowledge/` now rewrites the wikilinks that
pointed at it, in MOCs and in notes, and lists anything else that still names
the old folder for the user to fix.

> "Transition `<a finished project>` to knowledge"

### After the last item

> That's what's new in v`<tool_version>`. Want to try one of these, or go
> through the rest of what PKA does?

Log it (see "Closing" in `SKILL.md`): the entry must begin
`What's new in v<tool_version>`.
