# PKA Skills — Personal Knowledge Assistance for Claude Code

A set of Claude Code skills that turn any folder — or set of folders — into a Personal Knowledge Assistance system. The system infers the meaning of your existing structure rather than imposing one. It stores everything as plain files you can read without any tooling. It uses SQLite as an optional accelerant when your knowledge base grows large enough to need it.

You can install one skill or all four. They compose but are independently useful.

## The Four Skills

| Skill | Purpose | Standalone? | Optional Dependency |
|-------|---------|-------------|---------------------|
| `pka-bootstrap` | First-run setup, Repo Map, SQLite, roles, lifecycle | Yes — foundation | — |
| `pka-librarian` | Document ingestion, OCR, routing, indexing | Yes | — |
| `pka-interface` | Browser dashboard | Best with bootstrap | — |
| `pka-meetings` | Meeting capture, reconciliation, routing, indexing | Yes (route-only without thinkkit) | [thinkkit](https://github.com/rappdw/thinkkit) (`take-notes`, `resolve-against-transcript`) |

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

## Documentation

- [Tutorial](docs/TUTORIAL.md) — A practical walkthrough of the system after setup
- Individual skill documentation in `skills/<name>/SKILL.md`

## Repository Structure

```
pka-skills/
├── .claude-plugin/
│   ├── plugin.json
│   └── marketplace.json
├── skills/
│   ├── pka-bootstrap/
│   │   ├── SKILL.md
│   │   └── references/
│   ├── pka-librarian/
│   │   ├── SKILL.md
│   │   └── references/
│   ├── pka-interface/
│   │   ├── SKILL.md
│   │   └── references/
│   └── pka-meetings/
│       ├── SKILL.md
│       └── references/
├── evals/
│   ├── pka-bootstrap.evals.json
│   ├── pka-librarian.evals.json
│   ├── pka-interface.evals.json
│   └── pka-meetings.evals.json
├── docs/
│   └── TUTORIAL.md
├── README.md
├── CHANGELOG.md
└── LICENSE
```

## License

MIT
