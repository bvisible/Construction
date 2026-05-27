Screenshots and axe-results will land here when qa/V_TENDERING.spec.ts
runs against a live dev stack.

To run manually:
  cd frontend && npm run dev        # vite 5192
  cd backend  && uvicorn app.main:app --port 8022
  npx playwright test --config qa/playwright.config.ts

Files produced by the spec:
  01-empty-or-list.png       — initial /tendering view, post-login
  02-project-selected.png    — after first project chosen
  02-no-projects.png         — fallback when demo seed has zero projects
  03-package-detail.png      — first package expanded, new outlier
                                highlighting + recommendation banner +
                                GAEB/PDF buttons visible
  axe-empty.json             — axe-core violations on empty state
  axe-detail.json            — axe-core violations on populated detail
  mobile-01-home.png         — 375x812 layout sanity
