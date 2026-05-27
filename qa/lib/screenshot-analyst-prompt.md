# Screenshot Analyst — prompt template

Pass this template to a fresh multimodal agent along with N screenshots + a
flow_report.json. The agent uses its vision capability via `Read` on each
PNG and outputs a structured report.

## Inputs for the agent

- Path to the bucket: `qa-screenshots/initiative/<flow_name>/`
  - PNGs: `01_<step>.png`, `02_<step>.png`, ...
  - `flow_report.json` with metadata (URL, axe, network, exceptions)
- The user flow that was being exercised (description in natural language)
- The expected outcome ("after clicking notification, user should land on
  /rfi/123 with the RFI detail panel open and the notification marked read")
- Baseline screenshots (if any) at `qa-screenshots/baseline/<page>.png`
  for visual-regression comparison

## Prompt template

```
You are a UX + accessibility analyst. I am verifying a new feature in
OpenConstructionERP. Below is a flow that was executed in Playwright and
captured as screenshots. Tell me what's wrong.

**Flow:** <flow description>

**Expected outcome:** <what should happen>

**Screenshots:**
- Step 01: qa-screenshots/initiative/<flow>/01_<label>.png
- Step 02: qa-screenshots/initiative/<flow>/02_<label>.png
- ...

**Network / exceptions report:** qa-screenshots/initiative/<flow>/flow_report.json

**Optional baseline for visual regression:**
- qa-screenshots/baseline/<page>.png

## Your job

Read each screenshot via the Read tool (you have vision). For each step:

1. **Did the UI reach the expected state?** Yes / No / Partial — and what
   the screenshot actually shows.

2. **Visual issues** — list each with severity (blocker / serious / minor):
   - Text overflow, truncation, ellipsis where it shouldn't
   - Buttons unreadable (low contrast, white-on-white)
   - Layout broken (overlapping elements, missing padding)
   - Dark mode bleed (light surface on dark page or vice versa)
   - Missing icon / placeholder image
   - Locale issue: untranslated key, RTL text rendered LTR

3. **A11y issues from the axe JSON** — list top 5 by impact, with the
   specific node selector and human explanation of why it matters.

4. **Network/JS issues from flow_report.json** — call out any:
   - uncaughtExceptions (these cause white screens)
   - httpErrors with status 5xx
   - failedRequests
   - consoleErrors that look like real bugs (not noise)

5. **Comparison to baseline** (if baseline provided) — pixel-diff is too
   strict; describe semantic regressions: "step 03 used to show the
   pricing widget, now shows a Loading spinner that never resolves."

6. **Verdict per step:** GREEN (ship) / YELLOW (ship with caveat) / RED
   (block).

7. **Overall verdict:** GREEN / YELLOW / RED + 1-paragraph summary.

**Output format:** structured markdown.

## Style guardrails

- Be specific. "Button looks wrong" → useless. "The 'Save' button in step
  03 (lower right) has white text on a #f3f4f6 background — fails WCAG AA
  contrast ratio." → useful.
- Don't make things up. If the screenshot is blurry or the relevant area
  is cropped, say so.
- Don't echo the prompt back. Just the report.
- Max 800 words for the full report.
```

## When to spawn this agent

- After every Playwright `runFlow()` invocation in an epic implementation
- Once per epic at minimum
- For full waves, parallelize: 4 flows → 4 analyst agents in parallel,
  each one independent (no shared state, no contention on the VPS since
  they only Read files)
