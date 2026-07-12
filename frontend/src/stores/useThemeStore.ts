// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
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
    // 1. theme_active — neoffice-theme.js writes this to localStorage when the
    //    user toggles the theme from the apps menu. Authoritative once chosen.
    const active = window.localStorage.getItem('theme_active');
    if (active === 'dark' || active === 'light') return active;
    // 2. //// NEOFFICE PATCH — the LIVE value neoffice-theme.js applied to the
    //    host <html data-theme="…"> of the Frappe page that embeds us. This is
    //    the real source of truth (neoffice-theme.js: `documentElement
    //    .getAttribute("data-theme") || "light"`) and is always present, even
    //    when the user never toggled (so theme_active is absent). Read it
    //    before our own applyTheme() overwrites the attribute on first init.
    const domTheme = document.documentElement.getAttribute('data-theme');
    if (domTheme === 'dark' || domTheme === 'light') return domTheme;
    // 3. Frappe Desk standard keys (rarely set on website pages).
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

// //// NEOFFICE PATCH — Frappe SERVER preference is the single source of truth on load.
// `frappe.boot.user_desk_theme` ("Light" | "Dark" | "Automatic") is the desk theme
// the user picked in Frappe, injected into the SPA boot by the www controller. It
// MUST win over a stale localStorage: `theme_active`/`desk_theme` can drift to dark
// (an old toggle on this browser) while the server preference is Light — that drift
// is the recurring "/neoconstruction is dark but the Frappe desk is light" desync.
function readFrappeServerTheme(): 'light' | 'dark' | null {
  if (typeof window === 'undefined') return null;
  try {
    // Primary: `window.__OCE_DESK_THEME__` is injected synchronously into the page
    // HTML by the Neoconstruction www controller (= User.desk_theme). It is present
    // on EVERY load, unlike `frappe.boot.user_desk_theme` which is absent on the
    // website boot (only the Desk boot carries it) — that's why the boot-only
    // version silently no-op'd. Fall back to the boot value if the inject is missing.
    const injected = (window as { __OCE_DESK_THEME__?: string }).__OCE_DESK_THEME__;
    const raw =
      typeof injected === 'string' && injected
        ? injected
        : (window as { frappe?: { boot?: { user_desk_theme?: string } } })
            .frappe?.boot?.user_desk_theme;
    if (typeof raw === 'string') {
      const v = raw.toLowerCase();
      if (v === 'dark' || v === 'light') return v;
      if (v === 'automatic') return getSystemPreference();
    }
  } catch {
    // boot may be absent on non-embedded loads.
  }
  return null;
}

// //// NEOFFICE PATCH — Re-sync every theme key neoffice-theme.js / Frappe read, so a
// stale dark value can no longer override the server preference on the next load.
function syncFrappeThemeKeys(resolved: 'light' | 'dark'): void {
  try {
    window.localStorage.setItem('theme_active', resolved);
    window.localStorage.setItem('desk_theme', resolved);
    window.localStorage.setItem(STORAGE_KEY, resolved);
  } catch {
    // noop — sandboxed contexts.
  }
}

function resolveTheme(mode: ThemeMode): 'light' | 'dark' {
  // //// NEOFFICE PATCH — Frappe theme wins over our store when embedded.
  // When embedded we must NEVER fall back to the OS preference: a mac in dark
  // mode would turn the SPA dark while the Frappe shell around it stays light
  // (the desync bug). neoffice-theme defaults to light, so when we cannot read
  // an explicit Frappe theme we default to light too — keeping both in sync.
  if (isFrappeEmbedded()) {
    return readFrappeTheme() ?? 'light';
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
    // //// NEOFFICE PATCH — Frappe server preference wins on load (fixes the
    // recurring stale-localStorage desync: /neoconstruction dark while the Frappe
    // desk is light). When present it overrides everything and we re-sync every
    // theme key to it, so neoffice-theme.js and our store agree from now on.
    const serverTheme = isFrappeEmbedded() ? readFrappeServerTheme() : null;
    const stored = localStorage.getItem(STORAGE_KEY) as ThemeMode | null;
    const theme: ThemeMode = stored && ['light', 'dark', 'system'].includes(stored) ? stored : 'system';
    if (serverTheme) syncFrappeThemeKeys(serverTheme);
    const resolved = serverTheme ?? resolveTheme(theme);

    // Apply immediately (no transition on initial load)
    if (resolved === 'dark') {
      document.documentElement.classList.add('dark');
    } else {
      document.documentElement.classList.remove('dark');
    }
    // //// NEOFFICE PATCH — Mirror onto [data-theme] for neoffice-theme.css
    document.documentElement.setAttribute('data-theme', resolved);

    set({ theme: serverTheme ?? theme, resolved });

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
