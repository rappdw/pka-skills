# bootstrap-assets

Everything `pka-bootstrap` vendors into a target workspace's `.pka/` directory: the `pka-tools` helper and `upgrade-roles.py`.

These are **vendored** here so the bootstrap works for any user without reading from anyone's personal workspace at runtime.

## What gets installed where

| Source (in this repo)                    | Destination in user workspace      |
|------------------------------------------|------------------------------------|
| `tools/pka-tools`                        | `.pka/bin/pka-tools`               |
| `tools/pka_tools/*.py`                   | `.pka/bin/pka_tools/*.py`          |
| `scripts/upgrade-roles.py`               | `.pka/upgrade-roles.py`            |

## How it gets there

```
python3 <plugin root>/bootstrap-assets/tools/pka-tools install --workspace <workspace>
```

`install` copies the files above and writes `.pka/manifest.json`: the plugin version and a SHA-256 of each file as last offered.

On a later run the three hashes (plugin's copy, file on disk, manifest) decide what happens to each file:

| File on disk | Result |
|---|---|
| Absent | installed |
| Same as the plugin's copy | nothing |
| Same as the manifest (untouched since install) | replaced |
| Differs from both; the plugin's copy has not changed | kept |
| Differs from both; the plugin's copy has changed | kept, and the plugin's copy is written beside it as `<name>.new` |
| No manifest entry (a workspace from before v1.7), a file still shipped | replaced; the previous copy is saved under `.pka/upgrade-backups/<timestamp>/vendored/` |
| In the manifest but no longer shipped | moved to the backup folder if untouched, left in place if edited |
| A retired helper (below) with no manifest entry | left in place and listed in the report |

Nothing is deleted. Running it twice changes nothing the second time. `--dry-run` reports without writing.

`pka-tools` itself is documented in [`tools/README.md`](tools/README.md).

## Hard guarantees

- **No network calls.**
- **No git.** Nothing here runs `git`. `pka-tools` does not stage, commit or push; what it changes is left in the working tree.
- **No hardcoded user-specific topology.** Nothing embeds a host, an organization or a filesystem layout.
- **Nothing is deleted.** A replaced or retired file the user never edited is moved to `.pka/upgrade-backups/`; an edited one stays.

## Retired: the nested-repository helpers

Earlier releases also vendored the scripts and templates of a "hybrid monorepo" layout (a root repository coordinating separate repositories at `knowledge/` and each `projects/<name>/` through a `.meta` manifest):

```
.pka/graduate.sh   .pka/init_project_repos.sh   .pka/reinit-project-with-lfs.sh
.pka/push-all.sh   .pka/build-repo-list.sh
.pka/gitattributes-template   .pka/gitignore-template
```

They are no longer shipped, and `install --git`, which used to add them, is accepted and ignored. In a workspace that has them:

- A copy the manifest records and the user never edited is moved to `.pka/upgrade-backups/<timestamp>/vendored/` on the next `install`.
- A copy the user edited stays where it is.
- A copy from before the manifest existed (a workspace bootstrapped before v1.7) stays where it is, because nothing says whether it was edited. The install report lists these.

The copies that stay are the user's: unmaintained, theirs to keep running by hand or to delete. `install` never touches `.meta`, the nested repositories, the root `.gitignore`, `.pka/graduate-backups/` or `.pka/reinit-backups/`. The last two hold the complete former repositories of graduated or re-initialised projects (`git clone <backup path>` restores one) and must never be removed automatically.

The scripts themselves, with their history and safety fixes, remain in this repository's history up to v1.7.0.

## Notes for implementers

- `upgrade-roles.py` carries generated copies of the role seeds; edit the seeds in `skills/pka-bootstrap/references/` and run `python3 scripts/seeds.py --write`. See `skills/pka-bootstrap/references/upgrade.md`.
- A new module under `tools/pka_tools/` is vendored automatically: `install.py` globs `pka_tools/*.py`.
