/**
 * Custom branding for the sidebar header.
 *
 * Lets users white-label the in-app sidebar with their own company
 * logo (PNG/JPG/SVG) or company name. When set, the user's brand
 * shows prominently at the top of the sidebar; the
 * "OpenConstructionERP" wordmark moves below it at one-third the
 * size as a "powered by" attribution — still visible (we ship under
 * AGPL-3.0 with attribution requirements) but no longer the main
 * brand on the page.
 *
 * Persisted to localStorage so the customisation survives reload
 * without a backend round-trip. The logo is stored as a base64 data
 * URL (size-capped at 2 MB to keep localStorage healthy).
 */
import { create } from 'zustand';

const STORAGE_KEY = 'oe_custom_branding_v1';
const MAX_LOGO_BYTES = 2 * 1024 * 1024; // 2 MB cap on base64 payload

export type BrandingMode = 'default' | 'logo' | 'text';

export interface BrandingState {
  mode: BrandingMode;
  /** Base64 data URL of the uploaded logo (only valid when mode='logo'). */
  logoDataUrl: string | null;
  /** Company display text (only valid when mode='text'). */
  companyName: string;
  /**
   * Replace the user's logo. Pass `null` to clear (mode falls back
   * to whichever of `text` / `default` is appropriate).
   */
  setLogo: (dataUrl: string | null) => void;
  /**
   * Set the company name and switch to `text` mode. Empty string
   * resets to `default`.
   */
  setCompanyName: (name: string) => void;
  /** Clear all customisation and return to the OpenConstructionERP brand. */
  reset: () => void;
}

interface Persisted {
  mode: BrandingMode;
  logoDataUrl: string | null;
  companyName: string;
}

function load(): Persisted {
  try {
    const raw = localStorage.getItem(STORAGE_KEY);
    if (!raw) return { mode: 'default', logoDataUrl: null, companyName: '' };
    const parsed = JSON.parse(raw) as Partial<Persisted>;
    const mode: BrandingMode =
      parsed.mode === 'logo' || parsed.mode === 'text' ? parsed.mode : 'default';
    const logoDataUrl =
      typeof parsed.logoDataUrl === 'string' &&
      parsed.logoDataUrl.startsWith('data:image/') &&
      parsed.logoDataUrl.length < MAX_LOGO_BYTES * 2 // base64 expansion
        ? parsed.logoDataUrl
        : null;
    const companyName =
      typeof parsed.companyName === 'string' ? parsed.companyName.slice(0, 60) : '';
    return { mode, logoDataUrl, companyName };
  } catch {
    return { mode: 'default', logoDataUrl: null, companyName: '' };
  }
}

function save(s: Persisted) {
  try {
    localStorage.setItem(STORAGE_KEY, JSON.stringify(s));
  } catch {
    /* storage full or unavailable — silently drop, state stays in-memory */
  }
}

export const useBrandingStore = create<BrandingState>((set, get) => {
  const initial = load();

  // Cross-tab sync — when localStorage[STORAGE_KEY] changes in another
  // tab (e.g. user edits branding on /login while the app is open in
  // another window, or vice-versa), re-hydrate this tab's store so the
  // sidebar / login screen stays consistent without a reload. Same-tab
  // edits go through setLogo/setCompanyName so they bypass this path.
  if (typeof window !== 'undefined') {
    window.addEventListener('storage', (e) => {
      if (e.key !== STORAGE_KEY) return;
      const fresh = load();
      const current = get();
      if (
        fresh.mode === current.mode &&
        fresh.logoDataUrl === current.logoDataUrl &&
        fresh.companyName === current.companyName
      ) {
        return;
      }
      set(fresh);
    });
  }

  return {
    ...initial,
    setLogo: (dataUrl) => {
      const current = get();
      if (!dataUrl) {
        const next: Persisted = {
          mode: current.companyName ? 'text' : 'default',
          logoDataUrl: null,
          companyName: current.companyName,
        };
        save(next);
        set(next);
        return;
      }
      const next: Persisted = {
        mode: 'logo',
        logoDataUrl: dataUrl,
        companyName: current.companyName,
      };
      save(next);
      set(next);
    },
    setCompanyName: (name) => {
      const trimmed = name.trim().slice(0, 60);
      const current = get();
      // Logo wins over text — if a logo is set, we keep mode=logo
      // and just update the stored name so the user can flip back.
      const mode: BrandingMode =
        current.logoDataUrl ? 'logo' : trimmed ? 'text' : 'default';
      const next: Persisted = {
        mode,
        logoDataUrl: current.logoDataUrl,
        companyName: trimmed,
      };
      save(next);
      set(next);
    },
    reset: () => {
      const next: Persisted = { mode: 'default', logoDataUrl: null, companyName: '' };
      save(next);
      set(next);
    },
  };
});

export const BRANDING_MAX_LOGO_BYTES = MAX_LOGO_BYTES;
