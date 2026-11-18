# PKA Skills — Personal Knowledge Assistance for Claude Code

A set of Claude Code skills that turn any folder — or set of folders — into a Personal Knowledge Assistance system. The system infers the meaning of your existing structure rather than imposing one. It stores everything as plain files you can read without any tooling. It uses SQLite as an optional accelerant when your knowledge base grows large enough to need it.

You can install one skill or all six. They compose but are independently useful.

## The Six Skills

| Skill | Purpose | Standalone? | Optional Dependency |
|-------|---------|-------------|---------------------|
| `pka-bootstrap` | First-run setup, Repo Map, SQLite, roles, lifecycle | Yes — foundation | — |
| `pka-librarian` | Document ingestion, OCR, routing, indexing, lint | Yes | — |
| `pka-interface` | Browser dashboard | Best with bootstrap | — |
| `pka-meetings` | Meeting capture, reconciliation, routing, indexing | Yes (route-only without thinkkit) | [thinkkit](https://github.com/rappdw/thinkkit) (`take-notes`, `resolve-against-transcript`) |
| `pka-wiki` | Topic wiki synthesis, ingest, query enhancement | Best with bootstrap + librarian | — |
| `pka-tutorial` | Conversational onboarding and capability walkthrough | Best with bootstrap | — |

## Design Principles

- **Infer, don't impose.** Bootstrap reads your existing folder structure and infers what things mean from names and content samples.
- **Markdown is the source of truth.** SQLite is a fast index over files you already own.
- **The map is alive.** The Repo Map in your `CLAUDE.md` is maintained as your structure evolves.
- **Vendor-agnostic output.** Every generated file works under Claude Code, Gemini CLI, local LLMs, or any tool that accepts markdown context.
- **Skills compose without coupling.** `pka-meetings` orchestrates thinkkit when available but degrades gracefully without it.

## Installation

```bash
# In Claude Code
/plugin marketplace add https://github.com/rappdw/pka-skills
/plugin install pka-skills
```

If the repo isn't published yet, install from a local path:
```bash
claude --plugin-dir /path/to/pka-skills
```

### Requirements

- `python3` 3.9 or newer on PATH. The skills run a small bundled helper, `pka-tools`, for every mechanical step. It uses the Python standard library only (nothing to `pip install`) and makes no network calls.
- For the optional hybrid monorepo (`bootstrap git`): `git` 2.28 or newer and `git-lfs`.

### Optional: Install thinkkit for meeting capture

```bash
/plugin marketplace add https://github.com/rappdw/thinkkit
/plugin install thinkkit
```

## Quick Start

```bash
cd ~/your-knowledge-folder
claude
```

Then say: *"Set up my PKA"* or *"Bootstrap my personal knowledge system."*

Bootstrap will:
1. Scan your existing structure
2. Infer a Repo Map
3. Ask three questions (name, autonomy level, confirm the map)
4. Write `CLAUDE.md`, `.pka/` infrastructure, and inboxes
5. Initialize SQLite if your knowledge base is large enough

## Build Order

If building from scratch, skills should be implemented in this order:

1. **pka-bootstrap** — topology, Repo Map, SQLite schema, role definitions
2. **pka-librarian** — content indexing, OCR, transcript awareness
3. **pka-interface** — visualization, meeting timeline views
4. **pka-meetings** — meeting pipeline (depends on Repo Map, SQLite, thinkkit)

## Coexistence: Obsidian & Hybrid Monorepo

Two additive capabilities sit on top of the base PKA setup. Both are user-triggered (never auto-detected) and idempotent:

- **Obsidian coexistence** — when `knowledge/.obsidian/` exists, roles enhance files they touch with frontmatter, MOC entries, and `[[wikilinks]]`. Run `bootstrap obsidian` for a one-time mechanical retrofit (MOC stubs, person indexes, filename-pattern frontmatter — never reads file bodies, never overwrites).
- **Hybrid monorepo bootstrap** — `bootstrap git` sets up a root `.git` coordinating independent child repos at `knowledge/` and each `projects/<name>/` via a `.meta` manifest, with LFS-configured templates. Roles then auto-commit per semantic unit in **child** repos (with `Co-Authored-By: Claude` trailer) while the root repo remains a human-review gate. Sessions end with a consolidated push.

A user with no Obsidian vault and no hybrid monorepo sees identical behavior to before. See [`docs/specification-addendum.md`](docs/specification-addendum.md) (spec) and the seed references in `skills/pka-bootstrap/references/` (`obsidian-conventions.md`, `git-protocol.md`, `obsidian-bootstrap.md`, `git-bootstrap.md`).

**v1.6.1 — Pointer layer for MOC files.** The librarian maintains a `## Pointers` section inside each `_MOC.md` (one row per concept cluster, three columns: Topic, Entities, Files). FTS5 indexes pointer-row content with a 3× rank boost over body matches, turning a 1,500-file haystack query into a 30-cluster summary followed by 3–5 targeted file reads. No vector store, no embeddings. In an Obsidian vault it is on by default; without Obsidian it is opt-in from v1.7 (`pka-tools pointers init`), so a plain-markdown workspace gets no `_MOC.md` files it did not ask for. See `skills/pka-librarian/references/pointer-layer.md`.

**v1.7.1 — timeline backfill.** "Backfill timelines" puts the notes you already have on people's timelines: `pka-tools timeline plan` writes a report to review, `timeline apply` writes the lines (backed up, verified, one commit), and `timeline restore` undoes it. Notes are never changed. Without Obsidian, timelines now reach notes anywhere in the workspace (`projects/`, a root meeting folder), not only `knowledge/`.

**v1.7.0 — people and timelines.** Each person folder's `index.md` gets a `## Timeline`, newest first, with one line per meeting, 1-1 or document about them, written when the note is filed. Who belongs on a note is decided from evidence in the note (its folder, `attendees`, `## Attendees` links), never guessed; ambiguous names are asked about, and nicknames are remembered only when you confirm them (`pka-tools people alias`).

**v1.7.0-beta — one filing pipeline.** Every skill that files a note (the librarian, `pka-meetings`, `pka-wiki`, the researcher) now runs the same `pka-tools post-route` afterwards, so meeting notes and wiki pages get the frontmatter, MOC link, pointer row, index entry and commit that routed documents get. The session log has one grammar, written by `pka-tools log add`. `bootstrap upgrade` can refresh role-file sections that an earlier version seeded and the user never edited.

**v1.7.0-alpha — `pka-tools`.** The mechanical half of every skill now lives in one small Python command, vendored into each workspace at `.pka/bin/pka-tools`: the index schema and its migration, indexing, search, pointer rows, the Obsidian retrofit, open action items and path-scoped commits. Skills decide what a note is about and where it belongs; the tool makes the edit, changing only the lines it owns. It needs Python 3.9+, uses the standard library only and makes no network calls. See [`bootstrap-assets/tools/README.md`](bootstrap-assets/tools/README.md). An existing workspace gets it through `bootstrap upgrade`, which asks before migrating the index.

**v1.6.3 — Repair and safety.** No new features. The vendored helper scripts no longer lose data: `graduate.sh` and `reinit-project-with-lfs.sh` keep the previous repository as a backup, validate their targets, check every git step and roll back on failure; `init_project_repos.sh` reports failures instead of success; `push-all.sh` and `.meta` agree about remotes. Re-run `bootstrap git` (or `bootstrap upgrade`) in an existing workspace to pick up the fixed scripts. See [`CHANGELOG.md`](CHANGELOG.md).

## Documentation

- [Tutorial](docs/TUTORIAL.md) — A practical walkthrough of the system after setup
- Individual skill documentation in `skills/<name>/SKILL.md`
- Addendum spec: [`specification-addendum.md`](docs/specification-addendum.md) — Obsidian coexistence, hybrid monorepo bootstrap, commit/push protocol
- Toolkit: [`bootstrap-assets/tools/README.md`](bootstrap-assets/tools/README.md) — the `pka-tools` commands, exit codes and editing rules
- Test harness: [`tests/README.md`](tests/README.md) — tests for the helper scripts and `pka-tools`; JSON evals for role-level behavior

## Repository Structure

```
pka-skills/
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── skills/
│   ├── pka-bootstrap/
│   │   ├── SKILL.md
│   │   └── references/        # role seeds, bootstrap algorithms, shared-reference seeds
│   ├── pka-librarian/
│   │   ├── SKILL.md
│   │   └── references/
│   ├── pka-interface/
│   │   ├── SKILL.md
│   │   └── references/
│   ├── pka-meetings/
│   │   ├── SKILL.md
│   │   └── references/
│   ├── pka-wiki/
│   │   ├── SKILL.md
│   │   └── references/
│   └── pka-tutorial/
│       ├── SKILL.md
│       └── references/
├── bootstrap-assets/           # everything vendored into a workspace's .pka/
│   ├── gitattributes-template
│   ├── gitignore-template
│   ├── scripts/                # graduate.sh, init_project_repos.sh, push-all.sh, build-repo-list.sh, reinit-project-with-lfs.sh, upgrade-roles.py
│   └── tools/                  # pka-tools (launcher) and the pka_tools package; installs to .pka/bin/
├── tests/                      # tests for the helper scripts and for pka-tools
│   ├── run-all.sh
│   ├── lib.sh
│   ├── test_git_bootstrap.sh
│   ├── test_obsidian_bootstrap.sh
│   ├── test_commit_protocol.sh
│   ├── test_upgrade.sh
│   ├── test_pointer_layer.sh
│   ├── test_script_safety.sh   # one regression test per helper-script safety fix
│   ├── test_tools.sh           # runs tests/tools/test_*.py against the shipped tool
│   ├── tools/                  # unittest modules for pka-tools
│   └── fixtures/               # build_vault.py: the fixture workspace (CRLF, BOM, non-ASCII names, …)
├── evals/
│   ├── pka-bootstrap.evals.json
│   ├── pka-librarian.evals.json
│   ├── pka-interface.evals.json
│   ├── pka-meetings.evals.json
│   ├── pka-wiki.evals.json
│   └── pka-tutorial.evals.json
├── docs/
│   └── TUTORIAL.md
├── README.md
├── CHANGELOG.md
└── LICENSE
```

## Two Content Layers

PKA distinguishes two kinds of content:

- **Authored moments** — your meeting notes, 1-1s, drafts, journal. Your voice, immutable records of specific moments.
- **Synthesis pages** — topic wikis (via `pka-wiki`) that cite authored moments and evolve over time. Optional layer inspired by [Karpathy's LLM wiki pattern](https://gist.github.com/karpathy/442a6bf555914893e9891c11519de94f), adapted to PKA's files-are-source-of-truth model.

Wikis cite moments. Moments never cite wikis. The synthesis layer is additive — delete any wiki without losing underlying content.

## Personal Context as a Portable Asset

PKA treats your knowledge base as an **agent-maintained personal context portfolio**. The owner profile, decision log, session history, and Repo Map together form a structured representation of who you are, how you work, and what you know — maintained by the AI agents as they work with you, not by you filling out forms.

This context is:
- **Portable** — plain markdown files, no vendor lock-in. Works with Claude Code, Gemini CLI, local LLMs, or any tool that reads files.
- **Living** — roles update the owner profile and decision log organically as they learn more about you through normal interaction.
- **Composable** — share your `.pka/owner-profile.md` with any AI tool for instant context. The Repo Map gives any agent a map of your knowledge topology.

## Future Scope

- **`pka-mcp`** — An MCP (Model Context Protocol) server that exposes the PKA knowledge base as a tool surface. Would allow any MCP-compatible client to query your knowledge base, search across documents, and retrieve context without direct file access. This is a natural evolution once MCP tooling matures.

## License

MIT
