# Release playbook (build, test, cut)

# Release Playbook - OpenConstructionERP

This is a runnable playbook for building, testing, and cutting a release. Every fact below was read from the actual files in the repo. Paths are absolute from the repo root `C:\Users\Artem Boiko\Desktop\CodeProjects\ERP_26030500`.

## 0. Ground truth on current state (read this first)

The latest published version is v6.9.0. There are git tags through `v6.9.0`. But beware: your default checkout may not be on that commit.

- Repo root checkout HEAD is `0c92042d2` on branch `feat/postgres-only`. That commit is the parent of the v6.9.0 release bump, so its `backend/pyproject.toml` and `frontend/package.json` still read `6.8.0` and its workflow files do not yet carry the Node heap fix. Do not be misled: the released tree is correct, the root checkout is one commit behind the bump.
- The v6.9.0 release was actually cut from a separate worktree: `git worktree list` shows `C:/Users/Artem Boiko/Desktop/CodeProjects/_oce_rel681` on branch `release-v6.9.0` at commit `9e017014f`. This is the documented practice (commit the bump in a dedicated worktree, never in the main checkout).
- Tag dereference: `git rev-parse v6.9.0^{commit}` = `a156067de`. Always compare `vX.Y.Z^{commit}`, not the annotated tag object, when verifying a checkout.
- The two commits that make up the v6.9.0 cut: `f0db76dc1` "release: v6.9.0 ..." (the version bump) and `a156067de` "ci: raise Node heap limit ..." (the tagged commit on top). The tag points at `a156067de`.

To inspect what actually shipped in any release without checking it out: `git show vX.Y.Z:<path>`.

## 1. The five tag-triggered workflows

All five live in `.github/workflows/`. Pushing a tag matching `v*` triggers four of them at once (release, pypi-publish, desktop-release, and the two CI workflows fire on push/PR to main, not on tags). The release pipeline deliberately does NOT depend on CI passing.

### 1a. `ci.yml` - CI (fires on push to main, PR, and workflow_call; NOT on tags)
Four jobs, all must pass on main/PR but none of them gate a tag-driven release:
- `version-sync` runs `python scripts/check_version_sync.py` on Python 3.12. Catches version drift across the four lockstep files (see section 2).
- `backend` (Backend CI, 60 min timeout, working-directory `backend`) spins up a real `postgres:16` service container (user/pass `oe`/`oe`, db `openconstructionerp_test`, port 5432 with a pg_isready healthcheck). Steps: checkout, setup Python 3.12 with pip cache keyed on `backend/pyproject.toml`, create an empty `../frontend/dist/.gitkeep` so the hatchling force-include resolves, `pip install -e ".[dev]"`, `ruff check .`, then `ruff format --check .` (formatter gate is SEPARATE from the linter gate, both must pass), then `pytest` with `DATABASE_URL=postgresql+asyncpg://oe:oe@localhost:5432/openconstructionerp_test` and `DATABASE_SYNC_URL=postgresql+psycopg2://...`. conftest honours the already-set DATABASE_URL and does not boot an embedded cluster.
- `zero-width-guard` greps `frontend/src/` and `marketing-site/` for zero-width and bidi-isolate Unicode (`U+200B-200F`, `U+2060-2064`, `U+2066-2069`, `U+FEFF`), excluding `frontend/src/app/locales/ar.ts`. Reintroducing those characters fails the build. Fix with `python scripts/strip_zero_width.py`.
- `frontend` (working-directory `frontend`, Node 20, npm cache on `frontend/package-lock.json`): `npm ci`, `npm run lint`, `npm run typecheck`, `npm run build` (now with `NODE_OPTIONS: --max-old-space-size=6144` on the Build step as of v6.9.0), `npm run test`.

### 1b. `ci-postgres.yml` - CI (PostgreSQL) (fires on push to main and PR to main; NOT on tags)
One job `backend-postgres` (working-directory `backend`, env `OE_TEST_DB=pg`). Steps: checkout, Python 3.12, create empty `../frontend/dist/.gitkeep`, `pip install -e ".[dev,server]"`, then `pytest tests/pg -q -p no:cacheprovider`. This is the dedicated PostgreSQL-dialect suite (jsonb[], JSONB `@>`, ILIKE vs LIKE, UUID round-trips) run against an in-process PG cluster booted from the pixeltable-pgserver wheel (no Docker service container). The legacy SQLite-style per-file-engine suite is not yet ported to PG (documented Phase-2 stretch).

### 1c. `release.yml` - Release (TAG-triggered, `tags: v*`)
Permissions: `contents: write`, `packages: write`. Two jobs:
- `docker`: extracts version from `GITHUB_REF_NAME` (strips leading `v`), computes `major_minor`, lowercases the image path (GHCR rejects uppercase repo names while `${{ github.repository }}` keeps original casing), logs into GHCR with `GITHUB_TOKEN`, then builds and pushes `deploy/docker/Dockerfile.unified` (context `.`) tagged `:<version>`, `:<major.minor>`, and `:latest`, with gha build cache. The header comment is explicit: this job does NOT re-run tests, it trusts the tagged commit was already vetted on main, so a flaky test never blocks shipping.
- `release` (needs docker, `if: always()` so a flaky GHCR push never blocks the source release): checks out with full history, extracts version, awk-extracts the matching `## [VERSION]` section out of `CHANGELOG.md` into `/tmp/release-notes.md` (falls back to `Release <version>` if empty), then `softprops/action-gh-release@v2` creates the GitHub Release titled "OpenConstructionERP vX.Y.Z" with `draft: false`, `generate_release_notes: true`, and `prerelease` auto-set when the tag contains `-rc`/`-beta`/`-alpha`.

### 1d. `pypi-publish.yml` - PyPI Publish (TAG-triggered `tags: v*`, plus manual workflow_dispatch with a `version` input)
Permissions: `contents: read`, `id-token: write` (OIDC for Trusted Publishing). Environment `pypi`. One job `publish`:
- Checkout at `github.event.inputs.version || github.ref`.
- Python 3.12. Node 22 (locked to 22 because Cesium 1.137+ and tsc-on-prebuild need it), npm cache on `frontend/package-lock.json`.
- Build frontend: `cd frontend && npm ci && npm run build`, with `NODE_OPTIONS: --max-old-space-size=6144` on the step (added in v6.9.0). CRITICAL inline note: do NOT copy dist into `backend/app/_frontend_dist` here; hatchling force-includes `../frontend/dist` itself, and a manual pre-copy yields duplicate ZIP entries that PyPI rejects with HTTP 400 "Duplicate filename in local headers".
- `python -m pip install --upgrade build`, then `cd backend && python -m build --wheel --outdir ../dist/`.
- Sanity check: opens the wheel, asserts a `_frontend_dist` path exists, prints file count. Fails the run if the SPA payload is missing.
- Detect publish mode: if secret `PYPI_API_TOKEN` is present it uses the API-token path, otherwise Trusted Publishing (OIDC). In practice publishing goes through Trusted Publishing (`pypa/gh-action-pypi-publish@release/v1`, `packages-dir: dist/`, verbose). The PyPI pending-publisher config: project `openconstructionerp`, owner DataDrivenConstruction, repo OpenConstructionERP, workflow `pypi-publish.yml`, environment `pypi`.

### 1e. `desktop-release.yml` - Desktop Release (TAG-triggered `tags: v*`, plus workflow_dispatch)
Permissions: `contents: write`. Two jobs, both `fail-fast: false` so one OS failing never cancels the others:
- `build-sidecar` (matrix windows-latest/x86_64-pc-windows-msvc, macos-latest/aarch64-apple-darwin, ubuntu-22.04/x86_64-unknown-linux-gnu): Python 3.12, Node 20, builds the frontend with `NODE_OPTIONS: --max-old-space-size=6144` (the macOS arm64 runner OOMs the Rollup build otherwise), `pip install -e ".[dev]"`, then `pyinstaller desktop/pyinstaller.spec` (onefile), copies the single exe to `desktop/src-tauri/binaries/openestimate-server-<triple><ext>`, uploads as artifact `sidecar-<triple>`.
- `build-tauri` (needs build-sidecar, same matrix): Node 20 + frontend build (same heap flag), Rust stable, apt installs `libwebkit2gtk-4.1-dev libappindicator3-dev librsvg2-dev` on Linux, downloads the sidecar artifact, chmods it on non-Windows, then `tauri-apps/tauri-action@v0` with `projectPath: desktop`, `tagName: ${{ github.ref_name }}`, `releaseDraft: true`, `prerelease: false`. Output artifacts: Windows `.exe` (NSIS), macOS `.dmg` (Apple Silicon), Linux `.AppImage` and `.deb`.

History gotcha (now resolved): desktop installers were broken through v6.8.1 (sidecar path mismatch + onedir-vs-onefile + fail-fast cancellation). v6.8.1 had the right DB fix but its installer build failed with a Rust E0597 borrow error; v6.8.2 fixed the borrow and shipped all 7 installers. As of v6.8.2/v6.9.0 the desktop release builds and ships.

### Other workflows present (not part of the release cut)
`cla.yml`, `codeql.yml`, `dependency-review.yml`, `eval-match.yml`, `release-please.yml`, `release-signing.yml`, `sbom-and-licenses.yml`, `scorecard.yml`. Note: `release-please.yml` exists but `.release-please-manifest.json` is stale (it reads `2.6.11` while the project is at 6.9.0), so release-please is NOT the active release path. Releases are cut by hand via tag push.

## 2. Version lockstep - the EXACT files to bump

`scripts/check_version_sync.py` is the source of truth and is wired into both the pre-commit hook (`.pre-commit-config.yaml`, hook id `version-sync-check`) and the `version-sync` CI job. It compares four files, resolving paths relative to the repo root:

- `backend/pyproject.toml` - the SOURCE OF TRUTH. The first `version = "..."` literal under `[project]` (matched by regex, no TOML parser). The running app reports this via `importlib.metadata.version("openconstructionerp")`, so drift makes `/api/health` lie.
- `frontend/package.json` - the `version` field (must be a non-empty string).
- `CHANGELOG.md` - the topmost `## [N.N.N]` entry.
- `frontend/src/features/about/Changelog.tsx` - the topmost `version: 'N.N.N'` literal in the in-app changelog component (newest first).

Rules the script enforces (exit 1 on any failure):
- backend version MUST equal frontend version (hard fail if not).
- CHANGELOG.md top entry, IF present, must equal the backend version (a missing entry is tolerated as bump-in-progress).
- Changelog.tsx top entry, IF present, must equal the backend version.

So a release bump touches all four in one commit. The pre-commit hook only runs when one of those four paths is in the diff (the `files:` regex in `.pre-commit-config.yaml`).

SEPARATE, not checked by the script: `desktop/src-tauri/tauri.conf.json` has its own `"version"` field. It is NOT covered by `check_version_sync.py`. It drifts easily: in the current root checkout it reads `6.7.0` while the package files read `6.8.0`, and the v6.9.0 release commit had to bump it to `6.9.0` manually. Always bump tauri.conf.json by hand as part of the cut, or the desktop installers ship a wrong version string.

There is also a feedback note in the project memory: "Version sync needs 4 files + 2 ruff gates" - meaning after bumping, also expect the backend CI to run `ruff check` THEN `ruff format --check` as two independent gates; fix both before tagging if you touched backend code.

## 3. The frontend wheel packaging gotcha (do not break this)

The wheel must bundle the built SPA so `pip install openconstructionerp` ships a usable UI. The mechanism, in `backend/pyproject.toml`:

```
[tool.hatch.build.targets.wheel]
packages = ["app", "openconstructionerp"]

[tool.hatch.build.targets.wheel.force-include]
"../frontend/dist" = "app/_frontend_dist"
```

Hatchling vendors `frontend/dist` into the wheel as `app/_frontend_dist`. The rules:
- Build the frontend first (`cd frontend && npm run build`), THEN build the wheel. The dist directory must exist.
- Do NOT manually copy `frontend/dist` into `backend/app/_frontend_dist` before building the wheel. If you do, the same files are seen by both the `packages=["app"]` walker AND the force-include map, producing duplicate ZIP entries, and PyPI rejects the upload with HTTP 400 "Duplicate filename in local headers". This is called out in `pypi-publish.yml` and in the pyproject comments.
- The baked flagship/demo assets at `app/scripts/flagship_assets` are already inside the `app` package, so they ship via the package walk. They must NOT also be force-included or hatchling aborts with "a second file is being added to the wheel archive at the same path".
- A custom build hook `backend/hatch_build.py` (registered under `[tool.hatch.build.hooks.custom]`) pre-creates `../frontend/dist/.placeholder` so the force-include resolves even on a cold clone where Vite has not run. That is why CI's "create empty frontend dist" step exists as belt-and-braces.
- Editable installs (`pip install -e ./backend`) deliberately do NOT bundle the frontend: the editable target has an empty `force-include`, `dev-mode-dirs = ["."]`, and `only-include = ["app", "openconstructionerp"]` so the dist path never enters the candidate list. Vite's dev server serves the UI on :5173 during development.

Memory gotcha worth repeating: when building the wheel locally for a manual PyPI upload, move `backend/app/_frontend_dist` aside first if it exists from a prior local copy, otherwise you hit the duplicate-ZIP/PyPI-400 trap.

## 4. The Node heap fix (now present in four places)

The Vite/Rollup build now exceeds Node's default ~4 GB heap and dies with exit 134 ("JavaScript heap out of memory"), most reliably on the macOS arm64 runner. The fix is `NODE_OPTIONS=--max-old-space-size=6144` applied to every frontend-build step:
- `.github/workflows/desktop-release.yml` - on the Build frontend step of BOTH the build-sidecar and build-tauri jobs (this is where it landed first, present since v6.8.0).
- `.github/workflows/ci.yml` - on the frontend Build step (added in v6.9.0, tag commit `a156067de`).
- `.github/workflows/pypi-publish.yml` - on the Build frontend bundle step (added in v6.9.0).
- `deploy/docker/Dockerfile.unified` - as `ENV NODE_OPTIONS=--max-old-space-size=6144` in the node:22-alpine frontend-build stage (added in v6.9.0).

If you build the frontend locally and hit exit 134, set the same env var: PowerShell `$env:NODE_OPTIONS = '--max-old-space-size=6144'` before `npm run build`.

## 5. Local dev, test, and build on Windows

The Makefile targets shell out to `cd` + bash-isms and a Docker compose stack, so on Windows prefer the direct commands. Backend is PostgreSQL-only at runtime via embedded PG (pixeltable-pgserver, no Docker).

First-time setup:
- Backend: from `backend/`, `pip install -e .[server]` (or `.[dev]` to get pytest, ruff==0.15.14 pinned, mypy, pyinstaller, etc.).
- Frontend: from `frontend/`, `npm install` (or `npm ci` for a clean lockfile-exact install).

Run the backend (two equivalent ways):
- App CLI (embedded PostgreSQL, the real product path): `python -m app.cli serve --port 8000 --data-dir "C:/Users/Artem Boiko/.openestimate-v6live"` from `backend/`. The console scripts `openconstructionerp` and `openestimate` both map to `app.cli:main` (see `[project.scripts]`); `python -m openconstructionerp` works too. Default product port is 8080; dev uses 8000.
- Uvicorn factory (matches `make dev-backend`): `uvicorn app.main:create_app --factory --reload --port 8000` from `backend/`.

Run the frontend: from `frontend/`, `npm run dev` (Vite on :5173, proxies API to the backend). `make dev` just prints the two-terminal instructions because the POSIX `dev-unix` background trick does not work in cmd.exe/MSYS2 make.

Tests:
- Backend: from `backend/`, `pytest` (or `make test-backend` = `pytest -x -v`). Tests run SERIALLY (`addopts = []`, no xdist): the suite shares one PostgreSQL database that conftest sets up at import time and bootstraps the first registered user as admin, so parallel workers race on create_all DDL and admin ordering. To target the PG-dialect suite: `pytest tests/pg -q`. conftest boots its own embedded cluster when no `DATABASE_URL` is set; to point at an external PG set `DATABASE_URL`/`DATABASE_SYNC_URL` (the asyncpg + psycopg2 pair) as CI does.
- Frontend: from `frontend/`, `npm run test` (vitest). Lint/typecheck/build before pushing: `npm run lint`, `npm run typecheck`, `npm run build`.

Lint/format the way CI checks it:
- Backend: `ruff check .` then `ruff format --check .` (two separate gates; the dev extra pins `ruff==0.15.14` exactly so local output matches the CI gate). Config: `[tool.ruff]` line-length 120, target py312, a pragmatic select set (E/F/W/I/N/UP/B/A/C4/PT/RET/SIM) with a long ignore list.
- Frontend: `npm run lint` (eslint), `npm run typecheck` (tsc --noEmit).
- Unicode guard locally: `npm run lint:unicode` mirrors the CI zero-width guard.

Build a wheel locally (`make build-wheel` equivalent): `cd frontend && npm ci && npm run build`, then `cd backend && python -m build`. Remember the force-include/duplicate-ZIP rule in section 3 (do not pre-copy dist; remove any stale `backend/app/_frontend_dist` first).

Pre-commit: `pip install pre-commit && pre-commit install`. Hooks include trailing-whitespace, end-of-file-fixer, check-yaml/json, large-file guard, detect-private-key, ruff + ruff-format, gitleaks, conventional-commit message check, and the local version-sync check.

## 6. The release cut procedure used in practice (step by step)

The cut is done by hand: bump the four-plus-one version files in a dedicated worktree, push to main by explicit SHA refspec after an ls-remote verify, then push the annotated tag to fire the three release workflows.

1. Make sure main is green and the tree you intend to ship is what is on main. The release pipeline does not re-test, so vetting happens before the tag.

2. Create or reuse a dedicated release worktree, separate from the main working checkout (v6.9.0 used `C:/Users/Artem Boiko/Desktop/CodeProjects/_oce_rel681`, branch `release-v6.9.0`). Working in a separate worktree keeps the bump commit isolated from whatever the main checkout has staged. Do NOT commit the bump in the primary checkout.

3. In that worktree, bump versions in ALL of these in one commit:
   - `backend/pyproject.toml` (`version = "X.Y.Z"`)
   - `frontend/package.json` (`"version": "X.Y.Z"`)
   - `CHANGELOG.md` (add a new `## [X.Y.Z] - YYYY-MM-DD` section at the top with Added/Fixed prose in DDC voice, no em-dashes)
   - `frontend/src/features/about/Changelog.tsx` (add a new top entry with matching `version: 'X.Y.Z'`)
   - `desktop/src-tauri/tauri.conf.json` (`"version": "X.Y.Z"`) - separate, not script-checked, easy to forget
   Run `python scripts/check_version_sync.py` and confirm it prints `[OK] All version literals consistent at X.Y.Z`.

4. Commit with a conventional, human-voice message (e.g. `release: vX.Y.Z - <short summary>`). In v6.9.0 the cut was two commits: the release bump (`f0db76dc1`) then a small follow-up (`a156067de`, the Node heap fix) that ended up being the tagged commit.

5. Push to main by EXPLICIT SHA refspec, never a bare `git push origin main`. A plain push can print "Everything up-to-date" while the remote is actually behind (documented gotcha, bit us before). The procedure: verify the remote head first with `git ls-remote origin refs/heads/main`, then push by SHA: `git push origin <sha>:refs/heads/main`, then re-run `git ls-remote` to confirm the remote head moved to your SHA.

6. Create the annotated tag at the exact commit you pushed and push the tag: `git tag -a vX.Y.Z -m "vX.Y.Z" <sha>` then `git push origin vX.Y.Z`. The tag push (matching `v*`) fires three workflows in parallel: `release.yml` (Docker to GHCR + GitHub Release), `pypi-publish.yml` (wheel to PyPI via Trusted Publishing), and `desktop-release.yml` (Win/mac/Linux installers attached to a draft release).

7. Verify after the run:
   - PyPI: `pip install -U openconstructionerp` resolves to X.Y.Z (or check https://pypi.org/p/openconstructionerp).
   - GHCR: `ghcr.io/datadrivenconstruction/openconstructionerp:X.Y.Z` (and `:X.Y`, `:latest`) pushed.
   - GitHub Release page exists and titled "OpenConstructionERP vX.Y.Z" with the changelog body. The desktop-release job creates a DRAFT release with installers attached; publish/merge it and confirm all installer assets are present.
   - Tag dereference sanity: `git rev-parse vX.Y.Z^{commit}` equals the SHA you intended.

8. VPS deploy (if cutting over the public site) is a SEPARATE manual step, not part of the tag workflows. See the environments section of `HANDOVER_NEW_AGENT.md` (VPS root@31.97.123.81, systemd unit `openconstructionerp`, port 9090 behind Caddy; build the frontend locally and tar it over ssh because the VPS disk is ~96 percent).

## 7. Auth, tokens, secrets

- PyPI publishing uses Trusted Publishing (OIDC), no secret needed in the normal path; an optional `PYPI_API_TOKEN` secret enables the fallback path.
- GHCR uses the built-in `GITHUB_TOKEN`.
- For manual git/API work the documented token retrieval is `printf 'protocol=https\nhost=github.com\n\n' | git credential fill` and read the `password=` line (per HANDOVER_NEW_AGENT.md). The `gh` CLI is noted there as not authenticated, so REST/push go through that credential. Never print the token.

## 8. Key file index
- `scripts/check_version_sync.py` - version lockstep checker (4 files).
- `.github/workflows/ci.yml`, `ci-postgres.yml`, `release.yml`, `pypi-publish.yml`, `desktop-release.yml` - the pipelines.
- `backend/pyproject.toml` - version source of truth, ruff/pytest config, the hatchling force-include map and the editable-target overrides.
- `backend/hatch_build.py` - custom build hook that pre-creates the dist placeholder.
- `frontend/package.json` - frontend version + the dev/build/lint/typecheck/test scripts (no separate frontend/README.md exists).
- `deploy/docker/Dockerfile.unified` - the image built and pushed by release.yml (node:22-alpine frontend stage + python:3.12-slim runtime).
- `desktop/src-tauri/tauri.conf.json` - desktop version (separate bump) + externalBin sidecar config.
- `desktop/pyinstaller.spec` - sidecar build (now onefile).
- `CHANGELOG.md` and `frontend/src/features/about/Changelog.tsx` - the two changelogs.
- `Makefile` - dev/test/lint/build targets (POSIX-flavoured; on Windows use the direct commands).
- `.pre-commit-config.yaml` - local hooks including version-sync.
- `HANDOVER_NEW_AGENT.md` - environment + deploy + token details (note: written at v6.2.5, parts are dated).



## OPEN QUESTIONS
- The repo root checkout is on branch feat/postgres-only at 0c92042d2 (one commit before the v6.9.0 bump), so its local version files read 6.8.0 and its workflow files lack the Node heap fix. The v6.9.0 tag tree is correct. A fresh agent should confirm which branch/worktree they should actually work from before cutting the next release, and whether feat/postgres-only is meant to be merged into main.
- HANDOVER_NEW_AGENT.md is dated 2026-06-01 and describes v6.2.5 with desktop installers BROKEN as the main open item. That is now stale: desktop installers were fixed and shipped in v6.8.2, and PG-default plus other items moved on. The handover doc should be refreshed; treat its 'open work' section with caution.
- I did not verify against the live GitHub Actions run history that the v6.9.0 tag push actually produced green release/pypi/desktop runs (no network/gh access used). The playbook describes intended behaviour from the workflow YAML; a fresh agent should confirm the actual run status for the last tag.
- release-please.yml exists but .release-please-manifest.json is stale at 2.6.11 (project is 6.9.0). I concluded release-please is not the active release path, but it was not confirmed whether release-please is disabled, ignored, or simply orphaned. Worth confirming so it does not interfere with a manual cut.
- The Docker image's runtime ENV in Dockerfile.unified still defaults DATABASE_URL to sqlite (lines 66-67) even though the app is described as PostgreSQL-only with embedded PG. This may be intentional legacy for the unified container, but it is a possible inconsistency a release engineer should be aware of when validating the GHCR image boots correctly.
- tauri.conf.json version is NOT covered by check_version_sync.py and drifted (root checkout shows 6.7.0 vs package files at 6.8.0). The bump must be done manually each release; there is no automated guard, so it is an easy miss. Consider whether the version-sync script should be extended to cover it.
