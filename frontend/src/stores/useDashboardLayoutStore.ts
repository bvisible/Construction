/**
 * useDashboardLayoutStore — user-controlled dashboard widget layout.
 *
 * The dashboard is a stack of independent content widgets (KPI ribbon,
 * project cards, analytics, …). This store lets the user reorder them and
 * hide the ones they don't care about. Purely presentational, no server
 * round-trip — persisted to localStorage so the layout sticks per browser.
 *
 * The persisted `order` is reconciled against the live widget registry at
 * render time via `reconcileOrder`, so adding a new widget in code (or
 * removing one) never corrupts a saved layout: unknown ids are dropped and
 * newly-introduced ids are appended in their registry position.
 */
import { create } from 'zustand';
import { persist } from 'zustand/middleware';

interface DashboardLayoutState {
  /** Widget ids in display order. Empty until the user customises. */
  order: string[];
  /** Widget ids the user has hidden. */
  hidden: string[];

  setOrder: (ids: string[]) => void;
  toggleHidden: (id: string) => void;
  show: (id: string) => void;
  hide: (id: string) => void;
  /** Wipe all customisation — back to registry default order, nothing hidden. */
  reset: () => void;
}

export const useDashboardLayoutStore = create<DashboardLayoutState>()(
  persist(
    (set) => ({
      order: [],
      hidden: [],

      setOrder: (ids) => set({ order: ids }),
      toggleHidden: (id) =>
        set((s) => ({
          hidden: s.hidden.includes(id)
            ? s.hidden.filter((x) => x !== id)
            : [...s.hidden, id],
        })),
      show: (id) => set((s) => ({ hidden: s.hidden.filter((x) => x !== id) })),
      hide: (id) =>
        set((s) => (s.hidden.includes(id) ? s : { hidden: [...s.hidden, id] })),
      reset: () => set({ order: [], hidden: [] }),
    }),
    { name: 'oe.dashboard-layout' },
  ),
);

/**
 * Merge a persisted order with the canonical registry order.
 *
 * - Saved ids that no longer exist in the registry are dropped.
 * - Registry ids missing from the saved order are inserted at their
 *   natural registry index (so a freshly-shipped widget shows up where
 *   the code intends, not jammed at the end).
 * - When the saved order is empty (never customised) the registry order
 *   is returned verbatim.
 */
export function reconcileOrder(
  saved: readonly string[],
  registry: readonly string[],
): string[] {
  if (saved.length === 0) return [...registry];

  const known = new Set(registry);
  const result = saved.filter((id) => known.has(id));
  const present = new Set(result);

  registry.forEach((id, idx) => {
    if (present.has(id)) return;
    // Insert at the registry index, clamped to the current length.
    const at = Math.min(idx, result.length);
    result.splice(at, 0, id);
    present.add(id);
  });

  return result;
}
