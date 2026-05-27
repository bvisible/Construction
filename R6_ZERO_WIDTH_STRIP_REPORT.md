# R6 — Zero-Width Unicode Strip Report

**Task:** #135 — fix React reconciliation crash on `/contracts` (and other
pages) caused by zero-width Unicode characters in i18n `defaultValue`
strings.

**Date:** 2026-05-22
**Branch:** `worktree-agent-ae2ea9075df0d7963`
**Base commit:** `faf575f9` (v4.2.4)

---

## Root cause

`frontend/src/features/contracts/ContractsPage.tsx` (and 362 other source
files) had the byte sequence **U+200C U+2060 U+200D** ("zero-width
non-joiner + word joiner + zero-width joiner") appended to i18n
`defaultValue` strings as an invisible authorship fingerprint. When a
browser extension (Google Translate, Grammarly, ad blocker) mutated the
text node — even just to re-set `nodeValue` to the same string — React's
reconciler tried to `insertBefore` against a node it no longer
recognised and threw:

```
Failed to execute 'insertBefore' on 'Node':
The node before which the new node is to be inserted is not a child of this node.
```

That blanked the page in production.

---

## Audit

| Scope | Files audited | Files with ZW chars |
|------|--------------:|--------------------:|
| `frontend/src/**` | 1 186 | 362 |
| `marketing-site/**` | included above | 1 |
| **Total** | **1 186** | **363** |

### Counts by codepoint (stripped)

| Codepoint | Name | Stripped occurrences |
|---|---|---:|
| U+200B | ZERO WIDTH SPACE | 11 |
| U+200C | ZERO WIDTH NON-JOINER | 4 503 |
| U+200D | ZERO WIDTH JOINER | 4 503 |
| U+200F | RIGHT-TO-LEFT MARK | 1 |
| U+2060 | WORD JOINER | 4 504 |
| U+FEFF | ZERO WIDTH NO-BREAK SPACE (BOM) | 4 |
| **Total** | | **13 526** |

(U+200E LRM, U+2061-U+2064 invisible operators, U+2066-U+2069 bidi
isolates: zero occurrences outside the preserved `ar.ts`.)

### Strip diff sanity

```
$ git diff -U0 frontend/src marketing-site | scan_zw.py
Added lines with ZW chars:   0
Removed lines with ZW chars: 4 499
```

(366 source files modified + 4 untracked artefacts; 4 545 insertions
and 4 499 deletions — the deltas come from re-encoded lines that lost
their invisible suffix.)

---

## Files explicitly preserved

| File | Reason |
|------|--------|
| `frontend/src/app/locales/ar.ts` | Contains 4× U+200E LRM marks inside Arabic RTL phrases (e.g. `‎.ocep‎` around a Latin filename embedded in Arabic text). LRM is linguistically required to bracket the Latin segment so the bidi algorithm renders it correctly. CI guard exempts this file by path. |

No deliberate test fixtures were found — the ZW chars in
`__tests__/*.test.{ts,tsx}` and `__snapshots__/*.snap` were the same
authorship-fingerprint marker as in production source, and Vitest will
re-record snapshots on next run.

One JS regex literal
(`frontend/src/modules/collaboration/CollaborationModule.test.tsx:235`)
had a mixed escape/literal pattern
`replace(/[​-‏⁠﻿]/g, '')`. Stripping the literal
chars between the escape sequences left an **equivalent, smaller**
pattern that still matches the same codepoints, so no special-case was
needed.

---

## Guards added

### 1. ESLint rule (`frontend/eslint.config.js`)

```js
'no-irregular-whitespace': ['error', {
  skipStrings: false, skipComments: false,
  skipRegExps: false, skipTemplates: false,
}],
```

Covers U+200B-200F, U+2028-2029, U+202F, U+205F, U+2060, U+FEFF and the
common irregular whitespace family. Block-level — any reintroduction in
`.ts`/`.tsx`/`.js`/`.jsx` will fail `npm run lint`.

### 2. CI grep guard (`.github/workflows/ci.yml`)

New job `zero-width-guard` runs before the frontend job and greps all
text source for the full ZW codepoint range, including bidi isolates
(U+2066-2069) that ESLint does not cover. Whitelists `ar.ts`.

```yaml
zero-width-guard:
  name: Block zero-width Unicode characters
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - name: Scan frontend/src and marketing-site
      run: |
        set +e
        grep -rP '[\x{200B}-\x{200F}\x{2060}-\x{2064}\x{2066}-\x{2069}\x{FEFF}]' \
          --include='*.ts' --include='*.tsx' --include='*.js' --include='*.jsx' \
          --include='*.css' --include='*.html' --include='*.md' --include='*.py' \
          --exclude-dir=node_modules --exclude-dir=dist --exclude-dir=build \
          frontend/src/ marketing-site/ 2>/dev/null \
          | grep -v 'frontend/src/app/locales/ar.ts'
        rc=$?
        [ $rc -eq 0 ] && { echo "::error::Zero-width Unicode found"; exit 1; }
        exit 0
```

### 3. Local lint script (`frontend/package.json`)

`npm run lint:unicode` runs the same scan locally without needing
ripgrep — pure Node, walks `frontend/src/`. Useful before pushing.

### 4. Maintenance helper (`scripts/strip_zero_width.py`)

The script that performed the bulk strip lives in the repo for future
use. Run from repo root:

```
python scripts/strip_zero_width.py
```

It writes `.strip_report_files.txt` and `.strip_report_counts.txt`
beside the project root for diff review.

---

## Playwright regression test

**File:** `frontend/e2e/zero-width-regression.spec.ts`

Covers `/contracts`, `/property-dev`, `/boq`, `/bim`,
`/admin/permissions`. For each page:

1. Asserts visible text contains no zero-width Unicode.
2. Captures a `*_before.png` full-page screenshot to
   `.tests-artifacts/r6/zero_width_regression/`.
3. Walks every text node and re-sets `nodeValue` after stripping ZW
   chars — the exact mutation pattern Google Translate uses.
4. Clicks a tab / nav link / button / heading to force React to walk
   the mutated tree.
5. Captures a `*_after.png` screenshot.
6. Asserts no console error matched
   `Failed to execute 'insertBefore' on 'Node'`,
   `is not a child of this node`, or `NotFoundError`.

**Artefact count expected:** 5 pages × 2 (before + after) = **10
screenshots** per Playwright run.

Run locally:

```
cd frontend
npx playwright test e2e/zero-width-regression.spec.ts
```

---

## Verification

- [x] `npm run lint:unicode` returns 0 (`No zero-width Unicode characters found.`).
- [x] `git diff` shows **0 lines added** with ZW chars, **4 499 removed**.
- [x] All 363 originally-flagged files re-audited — only `ar.ts` retains
      ZW chars, as intended.
- [x] No backend files touched (pytest unaffected).
- [x] `frontend/eslint.config.js` valid ESM syntax.
- [x] `frontend/package.json` valid JSON.

---

## Unexpected finds

- The marker triplet `U+200C U+2060 U+200D` appeared **inside locale JSON
  string values** in every translation file (e.g. `en.ts` has 131
  occurrences, `de.ts` has 107). These were not in `defaultValue` but
  *would* still hit React if the locale string was rendered — task #135
  could have surfaced on many more pages once their translations loaded.
- `frontend/src/shared/lib/version.ts:2` had a longer 4× marker
  embedded in a block comment — invisible-only-in-source, never rendered
  to React, but caught by the grep guard for cleanliness.
- 4× U+FEFF BOM stripped from mid-file positions in test files (not
  start-of-file BOM, which is harmless) — these were embedded inside the
  same marker fingerprint construction.
- `marketing-site/demo-register-api.py` carried the marker inside three
  Python docstrings — out of React's reach but still a fingerprint and
  still removed.

---

## Commit

```
fix(i18n): strip zero-width Unicode from defaultValue strings + add lint guard
```
