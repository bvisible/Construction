# Install Playwright (QA E2E Harness)

This runbook gets a fresh clone to a state where `npm run test:e2e:smoke`
runs end-to-end. Audience: developers and CI bootstrappers.

## 1. Prerequisites

| Tool | Min Version | How to check |
|------|-------------|--------------|
| Node.js | 20.x LTS | `node -v` |
| npm | 10.x | `npm -v` |
| Python | 3.12 | `python --version` (for backend) |
| Git | 2.40 | `git --version` |
| Bash | any | `bash --version` (Windows: use Git Bash or WSL) |

## 2. Install dependencies

From the repo root:

```bash
cd frontend
npm install
```

This installs `@playwright/test ^1.60.0` and `@axe-core/playwright ^4.11.3`
along with the rest of the frontend deps.

## 3. Install browser binaries

```bash
# From frontend/
npm run test:e2e:install
```

Equivalent to `playwright install chromium firefox webkit --with-deps`.
Downloads ~300 MB. On Linux, `--with-deps` also `apt install`s system
libraries (libnss3, libatk1.0-0, etc.) — needs sudo.

**Smaller install (CI):** just chromium —
```bash
npx playwright install chromium
```

## 4. Start the app

The harness expects the frontend and backend to be running. In two
separate terminals:

```bash
# Terminal 1 — backend
cd backend
uvicorn app.main:app --reload --port 8000

# Terminal 2 — frontend
cd frontend
npm run dev          # serves http://localhost:5173
```

Quicker alternative — Docker Compose:

```bash
docker compose up    # spins up both + Postgres + Redis + MinIO
```

## 5. Verify

```bash
cd frontend
# Smoke health check — should pass in <5 s
npx playwright test smoke/health.spec.ts --project=chromium

# Full smoke suite (10 specs × 3 browsers = 30 tests)
npm run test:e2e:smoke

# Open the HTML report
npm run test:e2e:report
```

A successful run prints something like:

```
Running 30 tests using 4 workers
  30 passed (1.2m)
HTML report: qa-report/index.html
```

## 6. Environment overrides

Create a `.env.test` (or export vars) when running against a non-default
deployment:

```bash
export OE_TEST_BASE_URL=https://staging.openconstructionerp.io
export OE_TEST_API_URL=https://api.staging.openconstructionerp.io
export OE_TEST_DEMO_EMAIL=qa-bot@datadrivenconstruction.io
export OE_TEST_DEMO_PASSWORD='...'
npm run test:e2e:smoke
```

See `frontend/tests/e2e/README.md` for the full variable list.

## 7. Windows-specific notes

- **Use Git Bash or WSL** to run `parallel-runner.sh` and most npm
  scripts. CMD/PowerShell do not understand the shebang.
- **Long path errors** during `playwright install`: enable Win32 long
  paths —
  ```powershell
  New-ItemProperty -Path 'HKLM:\SYSTEM\CurrentControlSet\Control\FileSystem' `
    -Name 'LongPathsEnabled' -Value 1 -PropertyType DWORD -Force
  ```
- **Windows Defender slowing tests:** add `frontend\node_modules\@playwright`
  and `frontend\test-results` to Defender exclusions (Settings → Virus
  & threat protection → Exclusions). Same workaround as Qdrant per
  the internal Qdrant/Windows-Defender snapshot note.
- **Symlink errors during npm install:** run the shell as Administrator,
  or set npm to use junctions: `npm config set bin-links false`.

## 8. Troubleshooting

### `Error: browserType.launch: Executable doesn't exist at ...`
Browsers not installed yet. Run `npm run test:e2e:install`.

### `auth.fixture: cannot log in (demo-login=404, login=429)`
Backend not exposing `/api/v1/users/auth/demo-login/` (older deployment)
AND the standard login endpoint rate-limited the previous run. Wait
60 seconds and re-run, or set `OE_TEST_DEMO_*` to a non-rate-limited
account.

### `Test timeout of 60000ms exceeded`
Most likely the dev server is up but not responding (e.g. a vite HMR
crash). Reload the dev server. If it reproduces, run a single test with
`--debug` to step through it interactively.

### `Cannot find module '../fixtures'` (TypeScript)
You're in `tests/e2e/<module>/<spec>.spec.ts` but importing from `./fixtures`
instead of `../fixtures`. Fix the import path.

### Tests pass locally but fail in CI
- Set `CI=1` locally to force retries=2 + forbidOnly=true and reproduce
  the same conditions.
- Check for orphaned screenshots from a previous failed run — `rm -rf
  qa-screenshots qa-report` and retry.

### Need to debug a single failure
```bash
npx playwright test tests/e2e/smoke/health.spec.ts --debug
# Opens the inspector + pauses at each step.
```

## 9. CI integration sketch

```yaml
# .github/workflows/e2e.yml
jobs:
  e2e:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-node@v4
        with: { node-version: '20', cache: 'npm', cache-dependency-path: frontend/package-lock.json }
      - run: cd frontend && npm ci
      - run: cd frontend && npx playwright install chromium --with-deps
      - run: docker compose up -d
      - run: cd frontend && npm run test:e2e:smoke
        env: { CI: '1' }
      - uses: actions/upload-artifact@v4
        if: always()
        with:
          name: e2e-report
          path: |
            frontend/qa-report/
            frontend/qa-screenshots/
            frontend/qa-results.json
```

## Questions?

Open an issue on GitHub or contact info@datadrivenconstruction.io.
