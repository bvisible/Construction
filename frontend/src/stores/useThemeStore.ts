import { create } from 'zustand';

type ThemeMode = 'light' | 'dark' | 'system';

interface ThemeState {
  /** User preference: light, dark, or system. */
  theme: ThemeMode;
  /** Resolved effective theme after evaluating system preference. */
  resolved: 'light' | 'dark';
  /** Set theme and persist to localStorage. */
  setTheme: (theme: ThemeMode) => void;
  /** Convenience: cycle light -> dark -> system -> light. */
  toggleTheme: () => void;
  /** Initialize from localStorage + system preference. Call once on mount. */
  init: () => void;
}

const STORAGE_KEY = 'oe_theme';

// //// NEOFFICE PATCH — Follow Frappe theme when embedded
// WHY: When the SPA runs inside the Neoconstruction Frappe shell
//      (window.__FRAPPE_INTEGRATION__ === true) the user expects the
//      same dark/light setting as the rest of their Frappe desk —
//      they pick it once in Frappe's appearance settings and it
//      should apply everywhere. The upstream store followed the OS
//      preference, which created inconsistent UX (dark Frappe + light
//      SPA on a light-mode mac, etc.).
// HOW : Frappe stores the active theme in two localStorage keys on the
//      same domain that hosts the SPA:
//        appearance     "light" | "dark" | "automatic"
//        theme_active   "light" | "dark"
//      We read `theme_active` (already-resolved) and fall back to
//      `appearance` if missing. We also listen to the `storage` event
//      so changing the Frappe theme in another tab flips the SPA live.
// REVIEW: drop when upstream OCE adds a generic "embed theme bridge"
//         hook we can implement without patching this store.

function isFrappeEmbedded(): boolean {
  if (typeof window === 'undefined') return false;
  return (window as { __FRAPPE_INTEGRATION__?: boolean }).__FRAPPE_INTEGRATION__ === true;
}

function readFrappeTheme(): 'light' | 'dark' | null {
  if (typeof window === 'undefined') return null;
  try {
    const active = window.localStorage.getItem('theme_active');
    if (active === 'dark' || active === 'light') return active;
    const appearance = window.localStorage.getItem('appearance');
    if (appearance === 'dark' || appearance === 'light') return appearance;
    if (appearance === 'automatic' || appearance === '"automatic"') {
      return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
    }
  } catch {
    // localStorage access can throw in some sandboxed contexts.
  }
  return null;
}

function getSystemPreference(): 'light' | 'dark' {
  if (typeof window === 'undefined') return 'light';
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
}

function resolveTheme(mode: ThemeMode): 'light' | 'dark' {
  // //// NEOFFICE PATCH — Frappe theme wins over our store when embedded
  if (isFrappeEmbedded()) {
    const frappe = readFrappeTheme();
    if (frappe) return frappe;
  }
  if (mode === 'system') return getSystemPreference();
  return mode;
}

function applyTheme(resolved: 'light' | 'dark'): void {
  const root = document.documentElement;

  // Add a transient class to enable smooth color transitions
  root.classList.add('theme-transition');

  if (resolved === 'dark') {
    root.classList.add('dark');
  } else {
    root.classList.remove('dark');
  }

  // //// NEOFFICE PATCH — Mirror onto [data-theme] for neoffice-theme.css
  // WHY: The Neoffice shell stylesheet that wraps the SPA (page chrome,
  //      body background, dropdown panes, etc.) keys all its dark rules
  //      on `html[data-theme="dark"]`, not on `html.dark`. Without this
  //      mirror, the SPA's own components dark up correctly via Tailwind
  //      `.dark` but the host body background stays light → ugly seam.
  root.setAttribute('data-theme', resolved);

  // Remove transition class after animation completes to avoid interfering
  // with normal interactive transitions elsewhere
  window.setTimeout(() => {
    root.classList.remove('theme-transition');
  }, 350);
}

export const useThemeStore = create<ThemeState>((set, get) => ({
  theme: 'system',
  resolved: 'light',

  setTheme: (theme) => {
    const resolved = resolveTheme(theme);
    localStorage.setItem(STORAGE_KEY, theme);
    applyTheme(resolved);
    set({ theme, resolved });
  },

  toggleTheme: () => {
    const { theme } = get();
    const next: ThemeMode = theme === 'light' ? 'dark' : theme === 'dark' ? 'system' : 'light';
    get().setTheme(next);
  },

  init: () => {
    const stored = localStorage.getItem(STORAGE_KEY) as ThemeMode | null;
    const theme: ThemeMode = stored && ['light', 'dark', 'system'].includes(stored) ? stored : 'system';
    const resolved = resolveTheme(theme);

    // Apply immediately (no transition on initial load)
    if (resolved === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    // //// NEOFFICE PATCH — Mirror onto [data-theme] for neoffice-theme.css
    document.documentElement.setAttribute('data-theme', resolved);

    set({ theme, resolved });

    // Listen for OS-level preference changes when in "system" mode
    const mql = window.matchMedia('(prefers-color-scheme: dark)');
    const handler = () => {
      const current = get();
      if (current.theme === 'system') {
        const newResolved = getSystemPreference();
        applyTheme(newResolved);
        set({ resolved: newResolved });
      }
    };
    mql.addEventListener('change', handler);

    // //// NEOFFICE PATCH — Live-sync with Frappe theme changes (embedded)
    // WHY: Frappe writes `theme_active` / `appearance` to the same-origin
    //      localStorage when the user flips the appearance in Frappe.
    //      The `storage` event fires in OTHER tabs, but not in the tab
    //      that triggered the change — so a same-tab flip via the Frappe
    //      navbar wouldn't trigger us. We listen to both `storage` and a
    //      coarse 1 s polling fallback (Frappe doesn't broadcast a custom
    //      event for theme changes we can hook into). Polling stops if
    //      the value didn't change — cheap.
    if (isFrappeEmbedded()) {
      let lastSeen: 'light' | 'dark' | null = readFrappeTheme();
      const syncFromFrappe = () => {
        const fresh = readFrappeTheme();
        if (!fresh || fresh === lastSeen) return;
        lastSeen = fresh;
        applyTheme(fresh);
        // Also remember the choice in oe_theme so a reload picks it up
        // before the embed flag is re-set (avoids a brief flash).
        try { localStorage.setItem(STORAGE_KEY, fresh); } catch { /* noop */ }
        set({ theme: fresh, resolved: fresh });
      };
      window.addEventListener('storage', syncFromFrappe);
      window.setInterval(syncFromFrappe, 1000);
    }
  },
}));
