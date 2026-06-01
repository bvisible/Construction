# CI / PyPI Publish Audit — OpenConstructionERP

Read-only audit of `.github/workflows/` + `scripts/check_version_sync.py` to document exactly
how a release is published to PyPI and what version-consistency checks exist, so v5.9.2 can be
cut correctly.

Date: 2026-05-30. Method: static read of the workflow YAML, the version-sync script, and the
four version-bearing files. All claims are quote-backed.

---

## 1. Workflow inventory (`.github/workflows/`)

| File | Trigger | Role |
|------|---------|------|
| `ci.yml` | push to `main`, any PR, `workflow_call` | Lint/test/build. Contains the **version-sync** gate. Does NOT publish. |
| `pypi-publish.yml` | **push tag `v*`** + `workflow_dispatch` | **Builds the wheel (frontend vendored) and publishes to PyPI via Trusted Publishing.** |
| `release.yml` | **push tag `v*`** | Builds + pushes a **Docker image to GHCR**, then creates the **GitHub Release** from CHANGELOG. |
| `desktop-release.yml` | **push tag `v*`** + `workflow_dispatch` | Builds Tauri desktop installers (Win/macOS/Linux), draft release. |
| `release-signing.yml` | `release: published` + dispatch | cosign/Sigstore keyless signing of release assets (SHA256SUMS). |
| `sbom-and-licenses.yml` | `release: published` + dispatch | Generates SBOM + third-party license inventory, attaches to release. |
| `release-please.yml` | push to `main` | release-please bot: maintains a "Release PR" from Conventional Commits; on merge it can create the tag. (Automation path — see note in section 6.) |
| `cla.yml`, `codeql.yml`, `dependency-review.yml`, `eval-match.yml`, `scorecard.yml` | misc | Not release-related. |

So **a single `git push` of tag `v5.9.2` fans out to 4 workflows**: `pypi-publish.yml`,
`release.yml`, `desktop-release.yml`, and (via the Release object they create)
`release-signing.yml` + `sbom-and-licenses.yml`.

---

## 2. The PyPI publish workflow — `.github/workflows/pypi-publish.yml`

### 2a. Trigger (exact `on:` block)

```yaml
on:
  push:
    tags:
      - 'v*'
  workflow_dispatch:
    inputs:
      version:
        description: 'Version tag to build (e.g., v5.0.0). Required for workflow_dispatch.'
        required: true
        type: string
```

Tag pattern is the glob **`v*`** (not a strict semver regex). `v5.9.2` matches. The
`workflow_dispatch` path takes a `version` input and checks out that ref
(`ref: ${{ github.event.inputs.version || github.ref }}`).

### 2b. Trusted Publishing — YES (OIDC), with an API-token fallback

Job-level OIDC permission and the `pypi` environment are declared:

```yaml
permissions:
  contents: read
  # id-token: write is the OIDC permission Trusted Publishing requires.
  id-token: write

jobs:
  publish:
    name: Build + Publish to PyPI
    runs-on: ubuntu-latest
    environment:
      name: pypi
      url: https://pypi.org/p/openconstructionerp
```

The workflow auto-detects the mode: if a `PYPI_API_TOKEN` secret is present it uses the token
path, otherwise it uses Trusted Publishing (OIDC):

```yaml
      - name: Detect publish mode
        id: pubmode
        env:
          PYPI_API_TOKEN: ${{ secrets.PYPI_API_TOKEN }}
        run: |
          if [ -n "${PYPI_API_TOKEN:-}" ]; then
            echo "has_token=true" >> "$GITHUB_OUTPUT"
            ...
          else
            echo "has_token=false" >> "$GITHUB_OUTPUT"
            echo "Publishing via Trusted Publishing (OIDC)."
          fi

      - name: Publish to PyPI (Trusted Publishing)
        if: steps.pubmode.outputs.has_token == 'false'
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          packages-dir: dist/
          verbose: true

      - name: Publish to PyPI (API token fallback)
        if: steps.pubmode.outputs.has_token == 'true'
        uses: pypa/gh-action-pypi-publish@release/v1
        with:
          packages-dir: dist/
          password: ${{ secrets.PYPI_API_TOKEN }}
          verbose: true
          attestations: false
```

The header comment documents the one-time PyPI-side Trusted Publisher config: PyPI project
`openconstructionerp`, owner `DataDrivenConstruction`, repo `OpenConstructionERP`, workflow file
`pypi-publish.yml`, environment `pypi`. (Per memory, Trusted Publishing has been the working path
since 5.x — the token branch is a fallback only.)

### 2c. Build directory — `backend/`, but frontend is built first and vendored

The frontend is built first, then the wheel is built from `backend/` and emitted to `../dist/`
(repo-root `dist/`, not `backend/dist/`):

```yaml
      - name: Build frontend bundle into wheel layout
        run: |
          cd frontend
          npm ci
          npm run build
          # NOTE: do NOT copy dist into backend/app/_frontend_dist here.
          # backend/pyproject.toml already declares
          #   [tool.hatch.build.targets.wheel.force-include]
          #   "../frontend/dist" = "app/_frontend_dist"
          # so hatchling vendors the bundle into the wheel itself...

      - name: Build wheel
        run: |
          cd backend
          python -m build --wheel --outdir ../dist/
```

`pyproject.toml` (the package metadata + version) lives in `backend/`. The wheel is built there
with hatchling, which force-includes `../frontend/dist` as `app/_frontend_dist`. A sanity step
then asserts the wheel actually contains `_frontend_dist`:

```yaml
      - name: Sanity check wheel
        ...
          has_dist = any('_frontend_dist' in f for f in files)
          assert has_dist, f'wheel {whl} missing _frontend_dist payload'
```

Both publish steps read from `packages-dir: dist/` (repo root).

Important: **`pypi-publish.yml` does NOT itself assert that the tag matches the version.** There
is no "verify tag matches package version" step inside the publish workflow. Version correctness
is guarded separately by `ci.yml`'s `version-sync` job (section 3), which runs on the push to
`main` (and PRs), not on the tag. So the safe practice is: get `main` green (version-sync passes)
BEFORE tagging.

### 2d. Docker — YES, via `release.yml` (separate from PyPI)

`release.yml` triggers on the same tag push and builds/pushes a Docker image to GHCR:

```yaml
on:
  push:
    tags:
      - 'v*'

permissions:
  contents: write
  packages: write

env:
  REGISTRY: ghcr.io
  IMAGE_NAME: ${{ github.repository }}
```

```yaml
      - name: Build and push Docker image
        uses: docker/build-push-action@v6
        with:
          context: .
          file: deploy/docker/Dockerfile.unified
          push: true
          tags: |
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ steps.version.outputs.version }}
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:${{ steps.version.outputs.major_minor }}
            ${{ env.REGISTRY }}/${{ env.IMAGE_NAME }}:latest
```

It logs in to GHCR with the built-in `secrets.GITHUB_TOKEN` (no external Docker Hub creds). The
`version` is derived from the tag (`VERSION=${GITHUB_REF_NAME#v}`). After Docker, the `release`
job in the same file creates the GitHub Release (`softprops/action-gh-release@v2`) with notes
extracted from CHANGELOG.

CHANGELOG extraction in `release.yml` (anchored, version-bracketed):

```yaml
          CONTENT=$(awk "/^## \[$VERSION\]/{found=1; next} /^## \[/{if(found) exit} found{print}" CHANGELOG.md)
          if [ -z "$CONTENT" ]; then
            CONTENT="Release $VERSION"
          fi
```

This matches a heading of the exact form `## [5.9.2]` (note: requires the square brackets). If
absent it falls back to `Release 5.9.2` — missing CHANGELOG does not block the release, only
degrades the notes. `prerelease` auto-detects `-rc`/`-beta`/`-alpha` suffixes.

---

## 3. Version-sync / consistency check — `ci.yml` job + `scripts/check_version_sync.py`

This is the real version-consistency gate. It is a JOB in `ci.yml`, and it runs the script:

```yaml
jobs:
  version-sync:
    name: Version Sync Check
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4
      - name: Set up Python 3.12
        uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - name: Verify backend/frontend version literals match
        run: python scripts/check_version_sync.py
```

(The script is also wired into the local pre-commit hook per its own docstring.)

`ci.yml` runs on `push: branches: [main]` and on every `pull_request` — i.e. it gates the commit
that lands the version bump, NOT the tag.

### What `check_version_sync.py` compares and HOW it extracts each version

It compares **four files**, all resolved relative to repo root:

| Const | Path | Extraction |
|-------|------|-----------|
| `PYPROJECT` | `backend/pyproject.toml` | regex `^\s*version\s*=\s*"([^"]+)"` (MULTILINE), first match. (Source of truth.) |
| `PACKAGE_JSON` | `frontend/package.json` | `json.loads(...)["version"]` (must be a non-empty string) |
| `CHANGELOG_MD` | `CHANGELOG.md` | regex `^##\s*\[(\d+\.\d+\.\d+)\]` (MULTILINE), first match — i.e. the top `## [X.Y.Z]` heading |
| `CHANGELOG_TSX` | `frontend/src/features/about/Changelog.tsx` | regex `version:\s*['\"](\d+\.\d+\.\d+)['\"]`, first match — the top `version: '...'` entry |

Pass/fail logic:

- **HARD FAIL** if `backend/pyproject.toml` != `frontend/package.json`. These two must always be
  equal (this is the drift the script was created to stop — v1.3.32→v1.4.2 shipped with
  pyproject stuck at 1.3.31).
- **HARD FAIL** if `CHANGELOG.md` has a top `## [X.Y.Z]` entry AND it doesn't equal the backend
  version. (A *missing* top entry is tolerated — "bump in progress".)
- **HARD FAIL** if `Changelog.tsx` has a top `version: '...'` entry AND it doesn't equal the
  backend version. (Missing is tolerated.)

So both changelog files are checked **only when they carry a top entry**: if you forget to add the
new section the script passes, but if you add a section with the WRONG version it fails. The X.Y.Z
shape is mandatory for both (the regexes require three dot-separated integers).

Exact heading format CHANGELOG.md must use for both this script AND `release.yml`'s notes
extraction: `## [X.Y.Z]` — the square brackets are required by both. (Current top entry:
`## [5.9.1] - 2026-05-30`.)

The script's own fix hint:

```
Fix: bump backend/pyproject.toml + frontend/package.json + CHANGELOG.md +
frontend/src/features/about/Changelog.tsx in a single commit so the running app
and the docs stay honest about which version users are actually getting.
```

The app reads its runtime version from the installed Python package via
`importlib.metadata.version("openconstructionerp")`, which is why `backend/pyproject.toml` is the
source of truth and `/api/health` reflects it.

---

## 4. Current state of the four files (verified, working tree 2026-05-30)

All four are ALREADY bumped to 5.9.2 and consistent — i.e. the version bump (step 2 below) is
done; what remains is committing, getting `main` green, and tagging.

| File | Current value |
|------|---------------|
| `backend/pyproject.toml` (line 3) | `version = "5.9.2"` |
| `frontend/package.json` (line 4) | `"version": "5.9.2"` |
| `CHANGELOG.md` (line 8) | `## [5.9.2] - 2026-05-30` |
| `frontend/src/features/about/Changelog.tsx` (line 32) | top entry `version: '5.9.2', date: '2026-05-30'` |

So `check_version_sync.py` should already report `[OK] All version literals consistent at 5.9.2`.
(For reference, the last released tag was v5.9.1; these files have since been edited to 5.9.2 in
the working tree but, per the goal, the tag has not yet been pushed.)

---

## 5. Other tag-triggered workflows to be aware of (side effects of pushing `v5.9.2`)

- `desktop-release.yml` — also fires on `v*`; builds Tauri installers and creates a **draft**
  release (`releaseDraft: true`). Note it references the old `openestimate` product name in
  artifacts; this is a desktop side-channel, not the PyPI/Docker path.
- `release-signing.yml` + `sbom-and-licenses.yml` — fire on `release: published` (the Release
  object that `release.yml` publishes), adding cosign signatures + SBOM/license attachments.

None of these block or affect the PyPI publish; they run independently.

---

## 6. Precise, ordered steps to publish v5.9.2

The enforced invariants:
- CI `version-sync` (on `main`) requires `pyproject.toml` == `package.json`, and if a top
  changelog entry exists it must equal the version. So bump all four together.
- The PyPI publish and Docker/Release fire on the **`v*` tag** (exact tag: `v5.9.2`, leading `v`,
  no pre-release suffix unless you want it flagged prerelease).

Manual sequence:

1. Branch off `main` if not already on it (repo convention: branch first for changes).
2. Bump all four version literals in ONE commit:
   - `backend/pyproject.toml` line 7 → `version = "5.9.2"`
   - `frontend/package.json` line 3 → `"version": "5.9.2"`
   - `CHANGELOG.md` → add new top section `## [5.9.2] - 2026-05-30` (square brackets required) with notes
   - `frontend/src/features/about/Changelog.tsx` → add new top entry `{ version: '5.9.2', date: '2026-05-30', title: ..., highlights: [...] }`
3. (Optional, recommended) Run locally: `python scripts/check_version_sync.py` → expect
   `[OK] All version literals consistent at 5.9.2`.
4. Commit: `git commit -am "release: v5.9.2 — <summary>"`.
5. Push `main`: `git push origin main`. This runs `ci.yml` — confirm the **Version Sync Check**
   job (and backend/frontend jobs) are green BEFORE tagging. (Verify the push actually landed via
   `git ls-remote`; if "up-to-date" lies, push by explicit SHA refspec — known repo gotcha.)
6. Create the tag with the EXACT format `v5.9.2`:
   `git tag -a v5.9.2 -m "v5.9.2"`.
7. Push the tag: `git push origin v5.9.2`.
   This single tag push triggers:
   - `pypi-publish.yml` → npm build frontend → `python -m build --wheel` in `backend/` to
     `../dist/` → sanity-check `_frontend_dist` → `pypa/gh-action-pypi-publish` Trusted
     Publishing → PyPI project `openconstructionerp` 5.9.2.
   - `release.yml` → build+push GHCR image
     `ghcr.io/<repo>:5.9.2` / `:5.9` / `:latest` → create GitHub Release "OpenConstructionERP
     v5.9.2" with notes from the `## [5.9.2]` CHANGELOG section.
   - (`desktop-release.yml` draft installers; `release-signing.yml` + `sbom-and-licenses.yml` on
     the published Release.)
8. Verify: PyPI shows `openconstructionerp 5.9.2`; GHCR has the `:5.9.2` image; GitHub Releases
   shows v5.9.2; both `pypi-publish.yml` and `release.yml` Actions runs are green.

Caveat: nothing inside `pypi-publish.yml` re-checks tag == pyproject at publish time, so if you
tag `v5.9.2` while `pyproject.toml` still says `5.9.1`, it will publish a wheel named 5.9.1 from
the tagged commit. The protection is the `version-sync` job on `main` — that's why step 5 (green
`main`) must precede step 6/7 (tag).
