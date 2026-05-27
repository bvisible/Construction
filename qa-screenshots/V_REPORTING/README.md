# V_REPORTING screenshots

Populated by `qa/V_REPORTING.spec.ts` runs. Expected output:

- `01-reports-landing.png` — /reports page header + selectors after demo login
- `02-history-panel.png` — `<GeneratedReportsHistory>` panel mounted (skeleton, list, or empty state)
- `03-builder-preset.png` — Custom Report Builder with "Monthly Progress" preset applied

To capture:

```bash
# Start backend (8023) and vite (5193) in two terminals, then:
npx playwright test --config=qa/playwright.config.ts
```

This README is force-added so the directory is committed even when the
worktree run is skipped (no live server / no node_modules).
