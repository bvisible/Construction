# Git topology and repo hygiene

# Git state and cleanup dossier (OpenConstructionERP monorepo)

Verified live on 2026-06-05 against the working copy at `C:\Users\Artem Boiko\Desktop\CodeProjects\ERP_26030500`. Note: the agent shell starts inside the `marketing-site/` subdirectory, but this is a single git repo rooted at `ERP_26030500`. All git facts below were gathered from the repo root.

## 1. Headline: the branch checkout is stale and harmless

- Current branch: `feat/postgres-only`
- `feat/postgres-only` HEAD (and its ref) = `0c92042d2cac003108d1961958721b8eb7f453e7` ("style: apply ruff check fixes and format across backend", 2026-06-05 13:47)
- `origin/main` HEAD = `9e017014f3a205dcfedbf41084d67bd8f34742c2` ("site: translate every marketing page into all 20 languages", 2026-06-05 14:20)
- local `main` HEAD = `89d07aeaf5e2230710225acbdd2fbc5531ae67ae`

Divergence (measured with `git rev-list --left-right --count`):
- `feat/postgres-only` vs `origin/main`: 8 behind, 0 ahead. The branch has nothing unique. `git log origin/main..feat/postgres-only --oneline` returns EMPTY.
- local `main` vs `origin/main`: 52 behind, 0 ahead. Local `main` also has nothing unique; it is just old.

What this means in plain terms: the current HEAD `0c92042d2` is itself an ancestor of `origin/main` (it appears as the 4th commit down in the `origin/main` log). Everything on this branch has already been published. The 8 commits `origin/main` is ahead by are:

```
9e017014f site: translate every marketing page into all 20 languages
a156067de ci: raise Node heap limit so the frontend build stops running out of memory
f0db76dc1 release: v6.9.0 - Management of Change screen, non-US cost matching, quality-push hardening
0162056cc i18n(site): translate the homepage into all 19 languages
860e7b613 fix(desktop): repair launcher build so installers compile; v6.8.2
b91cea67c style: apply ruff format across backend test and module files
b9336a400 chore: sync version literals to 6.8.1 and clear lint in three test files
baf6a2c93 fix(desktop): resolve silent launch failure on frozen builds; v6.8.1
```

## 2. The "local-only checkpoints must NOT be pushed" warning is now OBSOLETE for the named commits

Project memory carried a standing rule that `feat/postgres-only` held local-only checkpoints (consolidation `d83b2a53b`, MoC `e5bf98ef9`, match-fix `f00549265`) that must not be pushed unless asked. Verified status of each (`git merge-base --is-ancestor`):

- `d83b2a53b` "fix: per-user backup restore, reporting empty states, quality-wave depth" - now ON origin/main (and on the branch).
- `e5bf98ef9` "feat(moc): management-of-change register UI" - now ON origin/main.
- `f00549265` "fix(match): non-US projects now return cost matches" - now ON origin/main.

All three were folded into the v6.9.0 release line and pushed. So those specific checkpoints are public history now and the embargo no longer applies to them. The general caution still stands as a habit: before any `git push` from this branch, re-confirm with `git log origin/main..feat/postgres-only` that you are not about to publish something unintended. Right now that command is empty, so a push would be a no-op anyway.

Recommended (safe, for a human to run when ready): bring the local refs up to date with the published line.

```
# from repo root
git fetch origin
# fast-forward the branch you are on to the published tip (no local commits to lose):
git merge --ff-only origin/main
# or move both stale local branches:
git branch -f main origin/main          # local main is 52 behind, 0 ahead
git switch main && git merge --ff-only origin/main
```

There are no unmerged local commits to preserve, so a `--ff-only` is non-destructive. Do NOT use `git reset --hard` while the working tree still holds the uncommitted marketing-site changes described in section 3 (it would discard nothing of value here because they already match origin/main, but stay disciplined).

## 3. Working tree (uncommitted) state

`git status` shows 32 MODIFIED tracked files, all under `marketing-site/`: the 8 page HTML files (contact, demo-register, docs, download, imprint, index, industries, license-request, news, partners, services, standards) plus the 20 locale JSONs under `marketing-site/locales/` (ar, bg, cs, da, de, en, es, fi, fr, it, ja, ko, nl, no, pl, pt, ru, sv, tr, zh).

Critical finding: these "modifications" are phantom. `git diff origin/main -- marketing-site/index.html` and `git diff origin/main -- marketing-site/locales/de.json` both return EMPTY. The working-tree content already equals `origin/main` HEAD `9e017014f` ("site: translate every marketing page into all 20 languages"). They only register as "modified" because the branch is checked out at the older `0c92042d2`. The full diff against the current (stale) HEAD is 46,466 insertions / 2,468 deletions across the 32 files - that is exactly the already-published translation commit. A fast-forward to `origin/main` (section 2) will make `git status` clean for these files with zero risk of losing work.

## 4. Worktrees

`git worktree list` reports a very large number of worktrees. Two matter for a human; the rest are agent scratch.

The two human-relevant worktrees:
- `C:/Users/Artem Boiko/Desktop/CodeProjects/ERP_26030500` -> `0c92042d2` [feat/postgres-only] - the main working copy (where you are).
- `C:/Users/Artem Boiko/Desktop/CodeProjects/_oce_rel681` -> `9e017014f` [release-v6.9.0] - the dedicated RELEASE worktree. It is currently sitting exactly at `origin/main` HEAD, i.e. up to date and clean as of this writing. Its role is to be a clean tree for cutting and verifying releases (the v6.9.0 cut happened here). Treat it as the release staging area; do day-to-day feature work in the main copy, not here.

Stale-stash hazard (verified): `git stash list` shows 7 stashes shared across ALL worktrees (stashes are global to the repo, not per-worktree):

```
stash@{0} WIP on main: 7bcbe330 release: v5.7.1 ...
stash@{1} WIP on main: 7bcbe330 release: v5.7.1 ...
stash@{2} WIP on main: 7bcbe330 release: v5.7.1 ...
stash@{3} On main: pre-pr-audit-sweep-2026-05-28
stash@{4} On main: leak-pre-tendering-cherry
stash@{5} On i18n/wave-2026-05-24-backfill-all-locales: i18n-leak-pre-V6-commit
stash@{6} On worktree-agent-af84ee82a8a3accd6: orphan-pre-inventory-merge
```

These are old (v5.7.1-era and earlier). Do NOT `git stash pop` or `git stash apply` any of them, especially inside the `_oce_rel681` release worktree. There is documented prior damage from an orphaned background task running an unconditional `git stash pop` into a clean release tree, which injected conflict markers (project memory: "Zombie bg-task stash-pop"). The stashes contain leak-prevention and pre-audit snapshots that are no longer relevant to the current v6.9.0 line. Leave them untouched. If they are ever to be cleaned, that is a separate, explicit, human-confirmed decision (`git stash drop`/`git stash clear`), not part of routine hygiene, and only after confirming nothing of value is in them.

The remaining hundreds of `worktree-agent-<hash>` entries plus a few named ones (`agent-a001793743feecc20` detached, `agent-a001cc588a207fd30` on `audit/costmodel-r5`, etc., all marked `locked`) are spawned agent worktrees under `.claude/worktrees/`. They are isolation sandboxes from prior multi-agent runs. They are locked, so `git worktree prune` will not remove them automatically. Do not manually delete their directories or unlock+prune them as part of this hygiene pass without an explicit request; some workflows still reference them by hash. They do not affect your ability to work on the main tree. The branch list (`git branch -a`) similarly carries ~200 `worktree-agent-*` branches and dozens of `agent/*`, `feat/*`, `fix/*`, `qa/*`, `wave/*`, `pr-*` branches; the vast majority are stale agent/feature branches that were merged or abandoned.

## 5. Untracked scratch files

Important distinction: the session-start snapshot in the task prompt listed an OLDER batch of scratch (`_audit_d3.txt`, `_d3_rawsql.txt`, `_scan_*.txt`, `d5_*.txt`, `oe_*.txt`, `qa_*.txt/py`, `backend/markup_id_qa.txt`, `backend/sess_id.txt`, `docs/postgres-migration/*.txt`, etc.). Every one of those has since been DELETED from disk (verified with file-existence checks: all report "gone") AND most now have matching `.gitignore` rules (lines 242-289). So that batch is already cleaned up; no action needed.

The CURRENT untracked set (`git status --porcelain | grep '^??'`) is a NEW, different batch, none of which is yet gitignored:

Root-level i18n probe scripts and dumps (session scratch, safe to delete):
- `_i18n_build_en.py`
- `_i18n_gap.json`
- `_i18n_merge.py`
- `_i18n_pages_gen.py`
- `_i18n_pages_merge.py`
- `_i18n_pages_workflow.js`
- `_i18n_workflow.js`

Root-level QA scratch outputs and ephemeral data dirs (safe to delete):
- `_qa_tmp_cargocheck.txt`
- `_qa_tmp_cleanbuild.txt`
- `_qa_tmp_frozen_run.txt`
- `_qa_tmp_frozen_run2.txt`
- `_qa_tmp_live_index.html`
- `_qa_tmp_rebuild.txt`
- `_qa_tmp_served_index.html`
- `_qa_tmp_sidecar_build.txt`
- `_qa_tmp_datadir2/` (an embedded-Postgres data directory - contains `pgdata/`, `.demo_credentials.json`, etc.; this is what blew the `git status` output up to ~214 KB)
- `_qa_tmp_desktop_datadir/` (another ephemeral desktop/PG data dir)

Backend scratch (safe to delete; note `backend/_*.txt` is already ignored but these are `.json`/`.js` so they slip through):
- `backend/_qa_tmp_audit_findings.json`
- `backend/_qa_tmp_fix_groups.json`
- `backend/_qa_tmp_fixwf.js`

Under marketing-site (DO NOT blindly delete - likely product source in progress):
- `marketing-site/i18n/i18n.js` (11 KB, dated 2026-06-05 12:30). Project memory describes issue #100 as wiring the other 11 marketing pages to a shared loader at `marketing-site/assets/i18n.js`. There is currently NO tracked i18n loader under `marketing-site/` (`git ls-files marketing-site/ | grep i18n` is empty), so this untracked `marketing-site/i18n/i18n.js` may be the new shared loader that still needs to be committed and referenced by the pages. Verify before deleting. If it is the intended loader, it should be moved/committed (and possibly relocated to `assets/` to match the memory note), not gitignored.

## 6. Recommended .gitignore additions

The existing `.gitignore` (293 lines) already covers the old batch. The new scratch slips through because the existing patterns are too narrow:
- line 239 `_qa_tmp/` matches only a directory literally named `_qa_tmp`, not the `_qa_tmp_*` prefix used now.
- line 260 `/_i18n_*.mjs` matches only `.mjs`, not the `.py`/`.js`/`.json` variants now produced.
- line 272 `backend/_*.txt` matches text only, not the `.json`/`.js` QA scratch.

Suggested additions (append near the existing scratch block, lines 238-289). For a human to apply later:

```
# --- session scratch (current batch) ---
/_qa_tmp_*
/_qa_tmp_*/
/_i18n_*.py
/_i18n_*.js
/_i18n_*.json
/_i18n_gap.json
backend/_qa_tmp_*
```

Do not add a blanket `marketing-site/i18n/` ignore until it is confirmed that `marketing-site/i18n/i18n.js` is throwaway rather than the new shared loader.

## 7. Recommended cleanup commands (for a human to run; nothing deleted here)

```
# 0) From repo root. First fast-forward stale local refs to the published line.
cd "C:/Users/Artem Boiko/Desktop/CodeProjects/ERP_26030500"
git fetch origin
git merge --ff-only origin/main            # clears the 32 phantom-modified marketing-site files
git branch -f main origin/main             # update stale local main (52 behind, 0 ahead)

# 1) Review then remove the current scratch batch (do NOT touch marketing-site/i18n yet).
git clean -nd -- ':!marketing-site/i18n'   # DRY RUN first - inspect the list
# then, if the list looks right:
git clean -fd  _i18n_build_en.py _i18n_gap.json _i18n_merge.py _i18n_pages_gen.py \
               _i18n_pages_merge.py _i18n_pages_workflow.js _i18n_workflow.js \
               _qa_tmp_cargocheck.txt _qa_tmp_cleanbuild.txt _qa_tmp_frozen_run.txt \
               _qa_tmp_frozen_run2.txt _qa_tmp_live_index.html _qa_tmp_rebuild.txt \
               _qa_tmp_served_index.html _qa_tmp_sidecar_build.txt \
               _qa_tmp_datadir2 _qa_tmp_desktop_datadir \
               backend/_qa_tmp_audit_findings.json backend/_qa_tmp_fix_groups.json \
               backend/_qa_tmp_fixwf.js

# 2) Decide marketing-site/i18n/i18n.js: commit it (likely the #100 shared loader) or remove it.
#    Inspect it and the page <script> tags before deciding.

# 3) Add the .gitignore patterns from section 6, then commit just the .gitignore.

# DO NOT: pop/apply/drop any stash; unlock+prune agent worktrees; reset --hard;
#         run git stash pop anywhere (especially in _oce_rel681).
```

## 8. Tags

Latest tags by version and by creation date agree:

```
v6.9.0  2026-06-05   (current published version)
v6.8.2  2026-06-05
v6.8.1  2026-06-05
v6.8.0  2026-06-04
v6.7.0  2026-06-03
v6.6.0  2026-06-03
v6.5.0  2026-06-02
v6.4.2  2026-06-02
v6.4.1  2026-06-02
v6.4.0  2026-06-02
```

`v6.9.0` is the tip of the release line and matches the v6.9.0 release commit `f0db76dc1`. The release worktree `_oce_rel681` is on branch `release-v6.9.0` at `9e017014f` (two doc/CI/i18n commits past the release commit, all already on origin/main).

## 9. Latest commits on origin/main (top 15)

```
9e017014f site: translate every marketing page into all 20 languages
a156067de ci: raise Node heap limit so the frontend build stops running out of memory
f0db76dc1 release: v6.9.0 - Management of Change screen, non-US cost matching, quality-push hardening
0c92042d2 style: apply ruff check fixes and format across backend          <- current branch HEAD
f7aa2090b fix: quality-push hardening across modules plus desktop and frontend fixes
0162056cc i18n(site): translate the homepage into all 19 languages
860e7b613 fix(desktop): repair launcher build so installers compile; v6.8.2
b91cea67c style: apply ruff format across backend test and module files
b9336a400 chore: sync version literals to 6.8.1 and clear lint in three test files
baf6a2c93 fix(desktop): resolve silent launch failure on frozen builds; v6.8.1
d04176b12 fix(teams,moc): close team-member IDOR + restore MoC metadata in responses
3d45227c5 chore(property_dev): drop dead _maybe_existing_dev placeholder
7e3eb6df4 fix(procurement): enforce draft-only PO creation and normalise match quantities
da5248da0 fix: procurement list 500 and restore frontend typecheck
e5bf98ef9 feat(moc): management-of-change register UI
```

## 10. Where a fresh agent should work

- Day-to-day work: the main copy at `ERP_26030500`. First action each session: `git fetch origin` and fast-forward to `origin/main` so you are not building on the stale `0c92042d2`. Consider switching off `feat/postgres-only` onto an up-to-date branch since that branch name no longer carries anything special.
- Releases only: the `_oce_rel681` worktree on `release-v6.9.0`.
- Never touch: the 7 global stashes, the locked `worktree-agent-*` sandboxes, and the `backup-pre-*` / `wip-recovery-*` safety branches.



## OPEN QUESTIONS
- marketing-site/i18n/i18n.js (untracked, 11 KB, 2026-06-05) is most likely the shared i18n loader for issue #100, but project memory says the planned path was marketing-site/assets/i18n.js. It is unconfirmed whether this file is the real loader to be committed (and possibly relocated to assets/) or leftover scratch. A human should inspect it and the page <script> tags before deciding to commit, move, or delete it.
- The branch feat/postgres-only is now 8 behind / 0 ahead of origin/main and carries nothing unique, so its historical 'do not push the local-only checkpoints' status is moot. It is unconfirmed whether the team still wants this branch kept as a named long-lived branch or whether it can be deleted/retired after fast-forwarding local main.
- The 7 stashes appear obsolete (v5.7.1-era leak/audit snapshots), but it was not verified that none contains still-needed work. Recommendation is to leave them alone; confirming they are safe to drop would require diffing each (git stash show -p stash@{n}) and an explicit decision.
- The repo has roughly 200 stale worktree-agent-* branches and hundreds of locked agent worktrees under .claude/worktrees/. Whether any are still referenced by active multi-agent workflows was not verified, so no pruning is recommended without confirmation.
- git fetch was run at the start of this session; if other work lands on origin/main afterward, the ahead/behind counts (8 behind for the branch, 52 for local main) will increase. Re-run git fetch before acting on the cleanup commands.
