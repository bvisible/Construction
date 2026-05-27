V_HSE screenshots
=================

Screenshots are written by the Playwright spec
(qa/V_HSE.spec.ts) once a live frontend (vite :5194) +
backend (uvicorn :8024) are available.

Run:
  cd <worktree>
  # backend
  VITE_API_TARGET=http://127.0.0.1:8024 \
    uvicorn app.main:app --reload --port 8024 \
    --app-dir backend &
  # frontend
  cd frontend && npm i && \
    VITE_API_TARGET=http://127.0.0.1:8024 \
    npx vite --port 5194 &
  # playwright
  cd .. && npx playwright test --config qa/playwright.config.ts

Expected files:
  01_page_render.png
  02_kpi_strip.png
  03_permits_tab.png
  04_permit_prereq_checklist.png  (when a permit exists)
  04_permit_empty_state.png        (when no permits)
