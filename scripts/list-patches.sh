#!/usr/bin/env bash
#
# NEOFFICE FILE — Patch inventory scanner.
# Owned 100% by Neoservice. Not from upstream OCE.
# Created: 2026-05-01
#
# Lists every NEOFFICE PATCH and NEOFFICE FILE marker across the fork.
# Use after every upstream merge to verify no patch was lost in conflicts,
# and during code review to inventory what diverges from upstream OCE.
#
# Usage:
#   scripts/list-patches.sh              # human-readable report
#   scripts/list-patches.sh --count      # just print the patch count
#   scripts/list-patches.sh --check N    # exit 1 if patch count != N
#
# See Obsidian note Neoffice/Neoconstruction/25-Patches-OCE-Inventory.md

set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$ROOT"

SCAN_DIRS=(
  "frontend/src"
  "backend/app"
)

scan_glob='--include=*.ts --include=*.tsx --include=*.js --include=*.jsx --include=*.py --include=*.yml --include=*.yaml'

count_patches() {
  # Each patch block opens with a "NEOFFICE PATCH —" marker.
  # END markers are not counted (they pair 1:1 with openings).
  grep -rn "NEOFFICE PATCH —" $scan_glob "${SCAN_DIRS[@]}" 2>/dev/null \
    | grep -v "END NEOFFICE PATCH" \
    | wc -l \
    | tr -d ' '
}

count_files() {
  grep -rln "NEOFFICE FILE —" $scan_glob "${SCAN_DIRS[@]}" 2>/dev/null | wc -l | tr -d ' '
}

list_patches() {
  echo "═══════════════════════════════════════════════════════════════════"
  echo "  NEOFFICE PATCH markers (= modifications of upstream OCE files)"
  echo "═══════════════════════════════════════════════════════════════════"
  grep -rn "NEOFFICE PATCH —" $scan_glob "${SCAN_DIRS[@]}" 2>/dev/null \
    | grep -v "END NEOFFICE PATCH" \
    | sed 's|^|  |'
  echo ""
  echo "═══════════════════════════════════════════════════════════════════"
  echo "  NEOFFICE FILE headers (= files entirely owned by Neoservice)"
  echo "═══════════════════════════════════════════════════════════════════"
  grep -rln "NEOFFICE FILE —" $scan_glob "${SCAN_DIRS[@]}" 2>/dev/null \
    | sed 's|^|  |'
  echo ""
  echo "───────────────────────────────────────────────────────────────────"
  echo "  Summary:  $(count_patches) inline patches  /  $(count_files) Neoservice files"
  echo "───────────────────────────────────────────────────────────────────"
}

case "${1:-}" in
  --count)
    count_patches
    ;;
  --check)
    expected="${2:-}"
    if [[ -z "$expected" ]]; then
      echo "Usage: $0 --check <expected-count>" >&2
      exit 2
    fi
    actual="$(count_patches)"
    if [[ "$actual" != "$expected" ]]; then
      echo "FAIL: expected $expected patches, found $actual" >&2
      list_patches >&2
      exit 1
    fi
    echo "OK: $actual patches (matches expected)"
    ;;
  ""|--list|-l)
    list_patches
    ;;
  *)
    echo "Usage: $0 [--list | --count | --check N]" >&2
    exit 2
    ;;
esac
