# PyPI publish — operations doc

**Status (as of v5.0.0, 2026-05-26)**: Wheel build + sanity check
**verified green in CI** (run `26439932904` — produced a clean
`openconstructionerp-5.0.0-py3-none-any.whl` of 37 MB with
`_frontend_dist` payload). The only remaining gate is **5 minutes of
manual setup on PyPI**: the workflow's OIDC token is rejected with
`invalid-publisher: ... no corresponding publisher (Publisher with
matching claims was not found)`, which is exactly the error you get
until a Trusted Publisher is registered on the PyPI side.

After that one-time setup, every future `gh workflow run pypi-publish.yml`
(or every `git push` of a `v*` tag) will publish to PyPI automatically.

## Two paths forward — pick one

### Path A — Trusted Publishing (recommended, 2-minute one-time setup)

PyPI Trusted Publishing uses OpenID Connect to mint a short-lived
publish credential at workflow run time. **No API token ever lives in
the repo or in GitHub Secrets.** Best practice on modern PyPI.

The workflow file is already committed at
`.github/workflows/pypi-publish.yml`. To enable:

1. Sign in at https://pypi.org/manage/account/publishing/ (use the
   account that owns the existing `openconstructionerp` project —
   probably `boikoartem`).
2. **For an existing project**: open the project page on PyPI
   (https://pypi.org/manage/project/openconstructionerp/settings/publishing/)
   → "Add a new publisher". Fill in:
   - **Owner**: `DataDrivenConstruction`
   - **Repository name**: `OpenConstructionERP`
   - **Workflow name**: `pypi-publish.yml`
   - **Environment name**: `pypi`
3. **For a fresh project** (if PyPI lost the project somehow): go to
   https://pypi.org/manage/account/publishing/ → "Add a new pending
   publisher" with the same four fields plus
   - **PyPI Project Name**: `openconstructionerp`
4. Save. Optionally create the `pypi` deployment environment on the
   repo side at
   https://github.com/DataDrivenConstruction/OpenConstructionERP/settings/environments
   so you can require manual approval per release.

Once saved, next tag push to this repo runs the `PyPI Publish`
workflow automatically and publishes the wheel — no further action.

To publish v5.0.0 specifically — main HEAD is on `5.0.0` in
`backend/pyproject.toml`, so build from main rather than from the
`v5.0.0` tag (the tag predates the formatter-test build fix and would
fail the CI's `tsc -b`):

```bash
# From any machine with the gh CLI authenticated:
gh workflow run pypi-publish.yml \
  --repo DataDrivenConstruction/OpenConstructionERP \
  --ref main \
  -f version=main
```

Watch progress at
https://github.com/DataDrivenConstruction/OpenConstructionERP/actions/workflows/pypi-publish.yml

### Path B — local one-shot upload (no PyPI-side setup)

If you have a PyPI API token already (`pypi-AgEIcHl...`):

```bash
# 1. Ensure you're on v5.0.0
git checkout v5.0.0

# 2. Clean slate (PWA hashes go stale — see feedback_vps_wheel_shadowed)
rm -rf backend/app/_frontend_dist dist build *.egg-info

# 3. Build frontend bundle into wheel layout
cd frontend
npm ci
npm run build
cp -r dist ../backend/app/_frontend_dist
cd ..

# 4. Build the wheel
python -m pip install --upgrade build twine
cd backend
python -m build --wheel --outdir ../dist/
cd ..

# 5. Sanity check
ls -lh dist/
# expect: openconstructionerp-5.0.0-py3-none-any.whl  (~80-120 MB)

# 6. Upload
TWINE_USERNAME=__token__ \
TWINE_PASSWORD='pypi-<your-token-here>' \
  python -m twine upload dist/openconstructionerp-5.0.0-py3-none-any.whl

# 7. Verify
pip index versions openconstructionerp
# expect: 5.0.0 (and earlier versions)
```

To let a future Claude Code session handle this for you, drop the
token at `.claude/twine_token.txt` (gitignored) in this exact format:

```
__token__:pypi-AgEIcHl...
```

The next agent can read it, run the build + upload, then delete the
file.

## After upload — smoke test

```bash
python -m venv /tmp/oe-smoke
/tmp/oe-smoke/bin/pip install openconstructionerp==5.0.0
/tmp/oe-smoke/bin/python -c "import openconstructionerp; print(openconstructionerp.__version__)"
# expect: 5.0.0
```

## Why this can't be auto-resolved by an agent

PyPI uploads require either:
- a long-lived API token bound to the project (Path B), or
- a Trusted Publisher relationship that has to be created **once**
  through the PyPI web UI signed in as the project owner (Path A).

Neither can be created from inside this session. Path A is the only
one that's "fix it once and forget" — after the 2-minute web-UI step,
every future `git tag vX.Y.Z && git push --tags` ships the wheel to
PyPI with no further human intervention.
