/**
 * PartnerLogoBadge — co-branding strip shown on every page when a
 * partner pack is active.
 *
 * Variants:
 *  - "nav"      — slim chip with partner logo + "in partnership with X",
 *                 mounted in the top nav-bar center where space allows.
 *  - "dashboard" — wider banner with logo + powered-by line, mounted at
 *                 the top of the dashboard.
 *
 * Dismiss behaviour: the user can hide the badge for the current session
 * via a small ✕. We persist the dismissal to ``sessionStorage`` so it
 * comes back on next browser launch — matches the product spec ("logo
 * can be hidden but reappears on next launch").
 */

import { X } from 'lucide-react';
import { useEffect, useState } from 'react';
import { usePartnerPack, partnerLogoUrl } from '@/shared/hooks/usePartnerPack';

const SESSION_DISMISS_KEY = 'partner-pack:dismissed';

interface PartnerLogoBadgeProps {
  variant: 'nav' | 'dashboard';
  className?: string;
}

export function PartnerLogoBadge({ variant, className = '' }: PartnerLogoBadgeProps) {
  const packQ = usePartnerPack();
  const [logoBroken, setLogoBroken] = useState(false);
  const [dismissed, setDismissed] = useState<boolean>(() => {
    try {
      return sessionStorage.getItem(SESSION_DISMISS_KEY) === '1';
    } catch {
      return false;
    }
  });

  useEffect(() => {
    if (dismissed) {
      try {
        sessionStorage.setItem(SESSION_DISMISS_KEY, '1');
      } catch {
        /* ignore — sessionStorage may be unavailable */
      }
    }
  }, [dismissed]);

  if (packQ.isLoading || !packQ.data?.active || dismissed) return null;

  const m = packQ.data.manifest!;
  const url = m.partner_url ?? '#';
  const isExternal = m.partner_url && /^https?:\/\//.test(m.partner_url);
  // Brand colour (pack's primary). Only an exact 6-digit hex can synthesize the
  // alpha-tinted banner background; otherwise fall back to the app accent token
  // (a CSS var can't carry an alpha suffix).
  const brand = m.branding.primary_color || '';
  const isHex = /^#[0-9a-f]{6}$/i.test(brand);
  const accent = isHex ? brand : 'var(--accent)';
  // Clearly-visible, brand-tinted background for the dashboard banner.
  const dashBg = isHex
    ? `linear-gradient(90deg, ${brand}26, ${brand}0d 55%, transparent)`
    : undefined;
  // Show the logo image only when the pack declares one AND it actually loads;
  // a declared-but-unreadable logo falls back to the partner name text instead
  // of a broken-image glyph.
  const showLogo = m.branding.has_logo && !logoBroken;

  if (variant === 'nav') {
    return (
      <div
        className={`inline-flex items-center gap-2 rounded-full bg-surface-secondary/60 px-2.5 py-1 text-xs text-content-secondary backdrop-blur ${className}`}
        data-testid="partner-logo-nav"
      >
        <a
          href={url}
          target={isExternal ? '_blank' : undefined}
          rel={isExternal ? 'noreferrer' : undefined}
          className="inline-flex items-center gap-1.5 hover:text-content-primary"
          title={m.branding.powered_by_text}
        >
          {showLogo && (
            <img
              src={partnerLogoUrl(m.slug)}
              alt={`${m.partner_name} logo`}
              className="h-5 w-5 shrink-0 rounded-[5px] object-contain"
              onError={() => setLogoBroken(true)}
            />
          )}
          <span className="max-w-[10rem] truncate font-medium">{m.partner_name}</span>
        </a>
        <button
          type="button"
          aria-label="Hide partner badge"
          onClick={() => setDismissed(true)}
          className="rounded p-0.5 text-content-tertiary hover:text-content-primary hover:bg-surface-tertiary"
        >
          <X size={12} />
        </button>
      </div>
    );
  }

  // variant === 'dashboard'
  return (
    <div
      className={`flex items-center justify-between gap-3 rounded-lg border border-border border-l-[3px] bg-surface-secondary px-4 py-3 text-sm shadow-sm ${className}`}
      style={{ borderLeftColor: accent, backgroundImage: dashBg }}
      data-testid="partner-logo-dashboard"
    >
      <a
        href={url}
        target={isExternal ? '_blank' : undefined}
        rel={isExternal ? 'noreferrer' : undefined}
        className="flex min-w-0 items-center gap-3 hover:opacity-90"
      >
        {showLogo ? (
          <img
            src={partnerLogoUrl(m.slug)}
            alt={`${m.partner_name} logo`}
            className="h-9 w-9 shrink-0 rounded-md object-contain"
            onError={() => setLogoBroken(true)}
          />
        ) : (
          <span className="shrink-0 text-base font-semibold" style={{ color: accent }}>
            {m.partner_name}
          </span>
        )}
        <div className="min-w-0 leading-tight">
          <div className="text-xs uppercase tracking-wide text-content-tertiary">
            {m.branding.powered_by_text}
          </div>
          {m.description && (
            <div className="mt-0.5 max-w-2xl truncate text-xs text-content-secondary">
              {m.description}
            </div>
          )}
        </div>
      </a>
      <button
        type="button"
        aria-label="Hide partner badge"
        onClick={() => setDismissed(true)}
        className="shrink-0 rounded p-1 text-content-tertiary hover:text-content-primary hover:bg-surface-tertiary"
      >
        <X size={14} />
      </button>
    </div>
  );
}
