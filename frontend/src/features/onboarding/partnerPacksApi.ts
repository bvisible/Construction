/**
 * Onboarding ↔ partner-pack API helpers.
 *
 * The "Set up by country" picker in the onboarding wizard installs an entire
 * localized workspace for one of the real partner packs we ship (see
 * ``docs/country-pack-oneclick/DESIGN.md`` §5/§7). These helpers wrap the two
 * endpoints that flow drives:
 *
 *   - ``GET  /api/v1/partner-pack/installed``   → list discovered packs.
 *   - ``POST /api/v1/partner-pack/full-install`` → one-click install everything
 *     (apply pack + locale + relational cost DB + vector DB + N country demos).
 *
 * Logos are streamed per-slug from ``GET /api/v1/partner-pack/logo/{slug}`` and
 * rendered as plain ``<img src>``.
 */

import { apiGet, apiPost, API_BASE } from '@/shared/lib/api';

// ── Installed packs ──────────────────────────────────────────────────────────

/** Branding subset of a pack's public manifest (see ``manifest.to_public_dict``). */
export interface PartnerPackBranding {
  primary_color: string;
  accent_color: string;
  has_logo: boolean;
  has_favicon: boolean;
  powered_by_text: string;
}

/**
 * A discovered partner pack as returned by ``GET /partner-pack/installed``.
 *
 * Mirrors ``PartnerPackManifest.to_public_dict()``; only the fields the
 * onboarding picker consumes are typed. ``metadata`` is free-form per pack —
 * the reference packs carry ``country`` (ISO-3166 alpha-2) and
 * ``country_name_en``, which we use for the flag + card title.
 */
export interface InstalledPartnerPack {
  slug: string;
  partner_name: string;
  partner_url: string | null;
  pack_version: string;
  description: string;
  default_locale: string;
  additional_locales: string[];
  cwicr_regions: string[];
  default_currency: string;
  default_tax_template: string | null;
  validation_rule_packs: string[];
  default_modules: string[];
  hidden_modules: string[];
  branding: PartnerPackBranding;
  has_onboarding_script: boolean;
  metadata: Record<string, unknown>;
}

/** Response of ``GET /api/v1/partner-pack/installed``. */
export interface InstalledPacksResponse {
  active_slug: string | null;
  installed: InstalledPartnerPack[];
}

/** Fetch every discovered partner pack (+ which one is active). */
export async function fetchInstalledPacks(): Promise<InstalledPacksResponse> {
  return apiGet<InstalledPacksResponse>('/v1/partner-pack/installed');
}

/** URL for a pack's logo image, suitable for ``<img src>``. */
export function partnerPackLogoUrl(slug: string): string {
  return `${API_BASE}/v1/partner-pack/logo/${encodeURIComponent(slug)}`;
}

// ── Full install (one-click localized workspace) ─────────────────────────────

/** The five orchestration steps reported by ``full-install`` (DESIGN §5). */
export type FullInstallStepName =
  | 'apply_pack'
  | 'locale'
  | 'cost_db'
  | 'vector_db'
  | 'demos';

/** Per-step status from the ``full-install`` response. */
export type FullInstallStepStatus = 'ok' | 'error' | 'skipped';

/** One entry in the ``full-install`` ``steps`` list. */
export interface FullInstallStep {
  step: FullInstallStepName;
  status: FullInstallStepStatus;
  detail: Record<string, unknown>;
}

/** Response of ``POST /api/v1/partner-pack/full-install``. */
export interface FullInstallResponse {
  slug: string;
  ok: boolean;
  steps: FullInstallStep[];
}

/** Body of ``POST /api/v1/partner-pack/full-install``. */
export interface FullInstallRequest {
  slug: string;
  set_locale: boolean;
  install_cost_db: boolean;
  vectorize: boolean;
  demo_count: number;
}

/**
 * Install an entire localized workspace for ``slug`` in one call.
 *
 * This is heavy (relational cost DB import + vectorization + ``demoCount``
 * fully-worked demos, ~30–90s), so it opts into the api client's long-running
 * (5-minute) abort budget. The endpoint is fail-soft: it always resolves with
 * the §5 response object (never throws on a single failed step), so the caller
 * renders ``response.steps`` directly into a progress checklist.
 */
export async function fullInstallPack(
  slug: string,
  demoCount = 2,
): Promise<FullInstallResponse> {
  return apiPost<FullInstallResponse, FullInstallRequest>(
    '/v1/partner-pack/full-install',
    {
      slug,
      set_locale: true,
      install_cost_db: true,
      vectorize: true,
      demo_count: demoCount,
    },
    { longRunning: true },
  );
}

/** The ordered step names the checklist renders, even before a response. */
export const FULL_INSTALL_STEPS: FullInstallStepName[] = [
  'apply_pack',
  'locale',
  'cost_db',
  'vector_db',
  'demos',
];

/**
 * Derive an ISO-3166 alpha-2 country code for a pack.
 *
 * Prefers ``metadata.country`` (the reference packs set it), then the region
 * subtag of ``default_locale`` (``fr-CA`` → ``ca``). Returns ``null`` when
 * neither is available so the caller can fall back to a generic glyph.
 */
export function packCountryCode(pack: InstalledPartnerPack): string | null {
  const metaCountry = pack.metadata?.country;
  if (typeof metaCountry === 'string' && metaCountry.length === 2) {
    return metaCountry.toLowerCase();
  }
  const region = pack.default_locale.split('-')[1];
  if (region && region.length === 2) {
    return region.toLowerCase();
  }
  return null;
}

/**
 * Human-readable country/market name for a pack card title.
 *
 * Prefers ``metadata.country_name_en``; falls back to the partner name.
 */
export function packCountryName(pack: InstalledPartnerPack): string {
  const name = pack.metadata?.country_name_en;
  if (typeof name === 'string' && name.trim()) return name.trim();
  return pack.partner_name;
}

/**
 * A 1–2 character monogram for a pack's logo badge.
 *
 * Every reference pack ships a *wide wordmark* logo (≈5:1 aspect, e.g.
 * 240×50) intended for the co-brand strip — squeezing it into the small
 * square tile the onboarding picker uses renders an unreadable sliver. So
 * the picker draws a clean monogram badge instead (brand colour + initials),
 * which is legible at 40px and never breaks.
 *
 * Source order:
 *   1. ``metadata.country`` ISO code, when it's a real 2-letter country
 *      (skips placeholder ``XX``) — gives "US", "DE", "CA", "BR"…
 *   2. Initials of the partner name's words ("US Construction Pack" → "US",
 *      "New Zealand Construction Pack" → "NZ", "batimatech" → "BA").
 */
export function packInitials(pack: InstalledPartnerPack): string {
  const country = pack.metadata?.country;
  if (typeof country === 'string') {
    const code = country.trim().toUpperCase();
    if (/^[A-Z]{2}$/.test(code) && code !== 'XX') return code;
  }
  const words = pack.partner_name
    .replace(/[^\p{L}\p{N}\s]/gu, ' ')
    .split(/\s+/)
    .filter(Boolean)
    // Drop generic suffixes so "US Construction Pack" → "US", not "UC".
    .filter((w) => !/^(construction|pack|the|and|of|für|de|für)$/i.test(w));
  if (words.length >= 2) {
    return (words[0]![0]! + words[1]![0]!).toUpperCase();
  }
  if (words.length === 1) {
    return words[0]!.slice(0, 2).toUpperCase();
  }
  return pack.partner_name.slice(0, 2).toUpperCase() || '··';
}
