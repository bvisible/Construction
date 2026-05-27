/**
 * WhatsNewCard — friendly "what's new in vX.Y.Z" release-notes card.
 *
 * Compact single-row variant (audit 2026-05-23 — user feedback "сделай
 * компактней не два ряда а в один и что если пользователь один раз его
 * закроет показывай только кнопкой"):
 *
 *   - One horizontal row: sparkle badge → version headline → short tagline
 *     → 6 chip pills (one per category, icon + label) → tour CTA + close.
 *   - Each chip is a `<button>` that toggles a small inline popover with
 *     the previous bullet content. Hover (desktop) or tap (mobile) opens
 *     it; click outside or another chip closes it.
 *   - Total height ~80–100 px on a 13" laptop. Chips wrap to a second row
 *     only on narrow viewports (sm and below) — acceptable degradation.
 *
 * Dismissal & reopen:
 *
 *   - First visit on a new major.minor → card auto-shown.
 *   - Click X / Dismiss → card hidden, a small "What's new" pill renders
 *     in its place. `localStorage.oe.last_seen_version` persists the
 *     dismissal for the version (next major.minor bump resets it).
 *   - Click the pill → card re-appears for this session only. Dismissing
 *     again hides it back to the pill. Reloading keeps it as the pill.
 *   - A separate session-only flag (`oe.whatsnew_reopened`) is used to
 *     track the in-tab "I clicked the pill" state; it is NOT persisted.
 *
 * Tour wiring is preserved: the "Take a quick tour" affordance dispatches
 * `window.CustomEvent('oe:start-tour')` exactly as before.
 */

import { useCallback, useEffect, useLayoutEffect, useMemo, useRef, useState } from 'react';
import { createPortal } from 'react-dom';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import {
  Sparkles,
  X,
  ArrowRight,
  Home,
  Map,
  Box,
  List,
  Wrench,
  CheckCircle,
  type LucideIcon,
} from 'lucide-react';
import { APP_VERSION } from '@/shared/lib/version';

/** localStorage key that records which release the user has acknowledged. */
const LAST_SEEN_KEY = 'oe.last_seen_version';

/**
 * Compare versions on the major.minor axis only. Patch bumps (4.5.0 → 4.5.1)
 * do not re-show the card — those are hotfixes and the user has already seen
 * the headline content for the minor. Only feature releases re-trigger.
 */
function shouldShow(current: string, lastSeen: string | null): boolean {
  if (!current) return false;
  if (!lastSeen) return true;
  const cur = current.split('.').map((x) => parseInt(x, 10) || 0);
  const prev = lastSeen.split('.').map((x) => parseInt(x, 10) || 0);
  const a = cur[0] ?? 0;
  const b = cur[1] ?? 0;
  const pa = prev[0] ?? 0;
  const pb = prev[1] ?? 0;
  if (a > pa) return true;
  if (a < pa) return false;
  return b > pb;
}

interface Section {
  /** Stable identifier used for React keys + i18n key suffix. */
  id: string;
  /** lucide icon constructor — rendered with the card's accent treatment. */
  icon: LucideIcon;
  /** Translation key for the chip label (with English fallback). */
  titleKey: string;
  titleDefault: string;
  /** Compact 1–2 word chip label (shown on the pill itself). */
  chipKey: string;
  chipDefault: string;
  /** Short popover bullets (1–3 plain-language sentences). */
  bullets: { key: string; default: string }[];
}

/* ── v4.5.0 release content ─────────────────────────────────────────────
   Same content as the original 6-section grid, repackaged for the compact
   chip-row layout. Bullets surface only when the chip is expanded. */
const SECTIONS_V450: Section[] = [
  {
    id: 'propdev',
    icon: Home,
    titleKey: 'whatsnew.v450.propdev.title',
    titleDefault: 'Property Development reborn',
    chipKey: 'whatsnew.v450.propdev.chip',
    chipDefault: 'PropDev',
    bullets: [
      {
        key: 'whatsnew.v450.propdev.b1',
        default: 'Buyers get full CRUD via clicks — no more raw JSON forms.',
      },
      {
        key: 'whatsnew.v450.propdev.b2',
        default:
          'New Leads sub-tab with an FSM funnel and Convert Lead → Reservation modal.',
      },
      {
        key: 'whatsnew.v450.propdev.b3',
        default:
          'Phases, Blocks, Brokers, Price Matrix and Escrow now each have proper UI tabs.',
      },
      {
        key: 'whatsnew.v450.propdev.b4',
        default:
          'Snags get a per-handover collapsible block with photo upload and warranty promote.',
      },
      {
        key: 'whatsnew.v450.propdev.b5',
        default:
          '3-row grouped tab layout: Master data, Sales lifecycle, Operations.',
      },
    ],
  },
  {
    id: 'geo',
    icon: Map,
    titleKey: 'whatsnew.v450.geo.title',
    titleDefault: 'Geo Hub with live HUD',
    chipKey: 'whatsnew.v450.geo.chip',
    chipDefault: 'Geo Hub',
    bullets: [
      {
        key: 'whatsnew.v450.geo.b1',
        default:
          'Live cursor lat/lon and camera altitude streamed from Cesium events.',
      },
      {
        key: 'whatsnew.v450.geo.b2',
        default: 'Compass rose rotates with the camera heading.',
      },
      {
        key: 'whatsnew.v450.geo.b3',
        default:
          'HSE incidents, Punchlist items and Diary photos rendered as 3D pins on the globe.',
      },
      {
        key: 'whatsnew.v450.geo.b4',
        default:
          'New anchored-projects endpoint powers the Global mode and the mode-based filter (Global / Project / Development).',
      },
      {
        key: 'whatsnew.v450.geo.b5',
        default:
          '"View on map" deeplinks from BIM Hub and PropDev focus the right model or development.',
      },
    ],
  },
  {
    id: 'bim',
    icon: Box,
    titleKey: 'whatsnew.v450.bim.title',
    titleDefault: 'BIM 3D viewer upgrades',
    chipKey: 'whatsnew.v450.bim.chip',
    chipDefault: 'BIM viewer',
    bullets: [
      {
        key: 'whatsnew.v450.bim.b1',
        default:
          'Walk mode actually works — PointerLockControls with WASD, E/Q for vertical, Shift to sprint.',
      },
      {
        key: 'whatsnew.v450.bim.b2',
        default:
          'Top-screen hint appears while the pointer is locked so users know how to exit.',
      },
      {
        key: 'whatsnew.v450.bim.b3',
        default:
          'Section Box ships with face-handle drag and a Reset button.',
      },
      {
        key: 'whatsnew.v450.bim.b4',
        default:
          'Measure tool finishes on right-click, copies to clipboard and shows an on-screen hint.',
      },
      {
        key: 'whatsnew.v450.bim.b5',
        default:
          'Toolbar relocated next to the ViewCube (bottom-left); the Models filmstrip collapses to a slim chevron tab.',
      },
    ],
  },
  {
    id: 'housetypes',
    icon: List,
    titleKey: 'whatsnew.v450.housetypes.title',
    titleDefault: 'House Type Catalogue',
    chipKey: 'whatsnew.v450.housetypes.chip',
    chipDefault: 'House types',
    bullets: [
      {
        key: 'whatsnew.v450.housetypes.b1',
        default:
          '48 country presets seeded out of the box (DE, US, UK, RU, TR, FR, ES, IT, PL, JP, CN, SA…).',
      },
      {
        key: 'whatsnew.v450.housetypes.b2',
        default:
          'Inline "+ Add custom type" while creating a plot — no settings detour.',
      },
      {
        key: 'whatsnew.v450.housetypes.b3',
        default:
          'Dedicated Settings page at /property-dev/settings/house-types with country filter.',
      },
      {
        key: 'whatsnew.v450.housetypes.b4',
        default:
          '★ Preset badge distinguishes seeded rows from user-defined types.',
      },
      {
        key: 'whatsnew.v450.housetypes.b5',
        default:
          'Custom rows are fully editable and deletable; presets stay protected.',
      },
    ],
  },
  {
    id: 'installer',
    icon: Wrench,
    titleKey: 'whatsnew.v450.installer.title',
    titleDefault: 'Installer reliability',
    chipKey: 'whatsnew.v450.installer.chip',
    chipDefault: 'Installer',
    bullets: [
      {
        key: 'whatsnew.v450.installer.b1',
        default:
          'Fresh-DB alembic install runs on any blank Postgres or SQLite (env.py shortcut + v3112 bootstrap migration).',
      },
      {
        key: 'whatsnew.v450.installer.b2',
        default:
          'Bug-report menu filters benign network noise: Failed to fetch, NetworkError, AbortError, 502/503/504.',
      },
      {
        key: 'whatsnew.v450.installer.b3',
        default:
          'Real defects still surface — only the transient-network class is suppressed.',
      },
      {
        key: 'whatsnew.v450.installer.b4',
        default:
          'No manual stamping or schema fixups needed on first boot.',
      },
    ],
  },
  {
    id: 'fixes',
    icon: CheckCircle,
    titleKey: 'whatsnew.v450.fixes.title',
    titleDefault: '20+ correctness fixes',
    chipKey: 'whatsnew.v450.fixes.chip',
    chipDefault: 'Fixes',
    bullets: [
      {
        key: 'whatsnew.v450.fixes.b1',
        default:
          'IDOR closures on RFI, Daily Diary, Meetings, Change Orders, Inspections, Schedule, Resources, Assemblies, Takeoff and DWG Takeoff.',
      },
      {
        key: 'whatsnew.v450.fixes.b2',
        default:
          'Decimal-exact money rollups across Change Orders and the cost model.',
      },
      {
        key: 'whatsnew.v450.fixes.b3',
        default:
          'FSM gates: RFI respond/reopen, inspections complete, contracts draft-only progress claims, snag transitions.',
      },
      {
        key: 'whatsnew.v450.fixes.b4',
        default:
          'Conditional-UPDATE race safety in change-order approval; polygon coords clamped in Takeoff.',
      },
      {
        key: 'whatsnew.v450.fixes.b5',
        default:
          'server_default added to every NOT NULL alembic column so fresh installs never trip.',
      },
      {
        key: 'whatsnew.v450.fixes.b6',
        default:
          'Magic-byte gates on file uploads: Daily Diary EXIF, fieldreports import and Snag photos.',
      },
    ],
  },
];

export interface WhatsNewCardProps {
  /** When true, ignores localStorage and forces the card to render. Used by
   *  the Settings → "Show release highlights" action and tests. */
  forceShow?: boolean;
  /** Override the persisted version (test seam). */
  versionOverride?: string;
}

type Mode = 'card' | 'pill';

export function WhatsNewCard({ forceShow = false, versionOverride }: WhatsNewCardProps = {}) {
  const { t } = useTranslation();
  const navigate = useNavigate();
  const version = versionOverride ?? APP_VERSION;
  /** What we render in the slot: full card, just the reopen pill, or nothing. */
  const [mode, setMode] = useState<Mode | null>(null);
  /** Drives the entrance transition for the full card. */
  const [mounted, setMounted] = useState<boolean>(false);
  /** Which chip's popover (if any) is currently expanded. */
  const [openChipId, setOpenChipId] = useState<string | null>(null);
  const containerRef = useRef<HTMLDivElement | null>(null);

  // Decide initial visibility. Wrapped in try/catch so a hardened browser
  // without localStorage (Safari private mode, locked-down kiosks) still
  // renders the dashboard rather than crashing the whole tree.
  useEffect(() => {
    let show = forceShow;
    let alreadyAcked = false;
    if (!show) {
      try {
        const lastSeen = window.localStorage.getItem(LAST_SEEN_KEY);
        show = shouldShow(version, lastSeen);
        alreadyAcked = !show && lastSeen != null;
      } catch {
        show = false;
      }
    }
    if (show) {
      setMode('card');
      // Trigger the entry animation on the next frame so the card actually
      // slides in instead of appearing pre-positioned.
      const id = window.requestAnimationFrame(() => setMounted(true));
      return () => window.cancelAnimationFrame(id);
    }
    // Already acknowledged this version → show the reopen pill in place of
    // the full card. We do NOT show the pill if there's no version match
    // to begin with (e.g. localStorage unavailable) — quiet by default.
    if (alreadyAcked) {
      setMode('pill');
    } else {
      setMode(null);
    }
    return undefined;
  }, [forceShow, version]);

  // Close the chip popover when clicking outside the card.
  useEffect(() => {
    if (mode !== 'card' || !openChipId) return undefined;
    const onClick = (ev: MouseEvent) => {
      const root = containerRef.current;
      if (!root) return;
      if (!root.contains(ev.target as Node)) {
        setOpenChipId(null);
      }
    };
    document.addEventListener('mousedown', onClick);
    return () => document.removeEventListener('mousedown', onClick);
  }, [mode, openChipId]);

  const handleDismiss = useCallback(() => {
    setMounted(false);
    setOpenChipId(null);
    // Persist the version so the next dashboard visit stays quiet.
    try {
      window.localStorage.setItem(LAST_SEEN_KEY, version);
    } catch {
      /* localStorage unavailable — silent */
    }
    // Wait for the leave animation to complete before swapping to the pill.
    window.setTimeout(() => setMode('pill'), 200);
  }, [version]);

  const handleReopen = useCallback(() => {
    setMode('card');
    setOpenChipId(null);
    // Re-trigger the entry animation just like the initial render.
    setMounted(false);
    window.requestAnimationFrame(() => setMounted(true));
  }, []);

  const handleTour = useCallback(() => {
    try {
      window.dispatchEvent(
        new CustomEvent('oe:start-tour', { detail: { from: 'whatsnew' } }),
      );
    } catch {
      /* CustomEvent unsupported — silent */
    }
    handleDismiss();
  }, [handleDismiss]);

  const handleChangelog = useCallback(() => {
    handleDismiss();
    // AboutPage already exposes a `data-changelog-anchor` element that the
    // page's own "Changelog" link scrolls to via #changelog. Use the same
    // hash so the in-app behaviour stays consistent with the rest of the
    // About page.
    navigate('/about#changelog');
  }, [navigate, handleDismiss]);

  const sections = useMemo(() => SECTIONS_V450, []);

  if (mode === null) return null;

  if (mode === 'pill') {
    return (
      <div className="flex">
        <button
          type="button"
          onClick={handleReopen}
          aria-label={t('whatsnew.reopen', { defaultValue: "What's new" })}
          className={[
            'inline-flex items-center gap-2 rounded-full',
            'border border-sky-400/50 ring-1 ring-sky-500/20',
            'dark:border-sky-500/40 dark:ring-sky-400/15',
            'bg-white/65 dark:bg-slate-900/50 backdrop-blur-md',
            'px-4 py-2 text-[13px] font-medium',
            'text-blue-700 hover:text-blue-800 dark:text-sky-200 dark:hover:text-sky-100',
            'hover:bg-sky-500/10 dark:hover:bg-sky-400/10',
            'hover:ring-sky-500/40 hover:shadow-md hover:shadow-sky-500/20',
            'shadow-sm shadow-sky-500/10 transition-all',
          ].join(' ')}
        >
          <Sparkles size={16} strokeWidth={2.25} />
          <span>
            {t('whatsnew.reopen', { defaultValue: "What's new" })}
          </span>
          <span className="text-blue-600/70 dark:text-sky-300/70">v{version}</span>
        </button>
      </div>
    );
  }

  // mode === 'card'
  return (
    <div
      ref={containerRef}
      role="region"
      aria-label={t('whatsnew.title', {
        defaultValue: "What's new in v{{version}}",
        version,
      })}
      className={[
        'relative overflow-visible rounded-xl border ring-1',
        'border-sky-400/50 ring-sky-500/10',
        'dark:border-sky-500/40 dark:ring-sky-400/10',
        'bg-gradient-to-br from-sky-50/90 via-blue-50/85 to-cyan-50/80',
        'dark:from-sky-950/40 dark:via-blue-950/30 dark:to-cyan-950/20',
        'backdrop-blur-md shadow-md shadow-sky-500/10',
        'transition-all duration-300 ease-out',
        mounted ? 'opacity-100 translate-y-0' : 'opacity-0 -translate-y-2',
      ].join(' ')}
    >
      <div className="flex flex-wrap items-center gap-2 sm:gap-3 px-3 sm:px-4 py-2.5">
        {/* Sparkle badge */}
        <div className="relative shrink-0">
          <span
            aria-hidden="true"
            className="absolute inset-0 rounded-lg bg-sky-500/30 animate-ping"
          />
          <div className="relative flex h-7 w-7 items-center justify-center rounded-lg bg-gradient-to-br from-sky-500 to-blue-600 text-white shadow-sm shadow-blue-500/30">
            <Sparkles size={13} strokeWidth={2.5} />
          </div>
        </div>

        {/* Headline + tagline (single line on desktop) */}
        <div className="flex min-w-0 items-baseline gap-2">
          <h2 className="truncate text-[13px] sm:text-sm font-semibold text-blue-900 dark:text-sky-100 leading-tight">
            {t('whatsnew.title', {
              defaultValue: "What's new in v{{version}}",
              version,
            })}
          </h2>
          <span className="hidden md:inline truncate text-[12px] text-blue-700/75 dark:text-sky-300/70">
            {t('whatsnew.tagline', {
              defaultValue: 'Tap a chip for details.',
            })}
          </span>
        </div>

        {/* Chip row — flex-grow pushes the trailing buttons to the right.
         *  Each chip's popover is rendered through a portal (`ChipPopover`
         *  below) because the parent card uses `backdrop-blur-md`, which
         *  creates a stacking context. An absolutely-positioned popover
         *  inside that context cannot escape it via z-index — it always
         *  paints below sibling widgets on the dashboard. Portaling to
         *  document.body removes that constraint. */}
        <div className="flex flex-1 flex-wrap items-center gap-1.5 min-w-0">
          {sections.map((s) => {
            const Icon = s.icon;
            const expanded = openChipId === s.id;
            return (
              <ChipWithPopover
                key={s.id}
                section={s}
                expanded={expanded}
                onToggle={() => setOpenChipId(expanded ? null : s.id)}
                onReadMore={handleChangelog}
                Icon={Icon}
                t={t}
              />
            );
          })}
        </div>

        {/* Trailing actions: tour CTA, changelog link, close */}
        <div className="flex shrink-0 items-center gap-1.5">
          <button
            type="button"
            onClick={handleTour}
            className="inline-flex items-center gap-1 rounded-full bg-gradient-to-br from-sky-500 to-blue-600 hover:from-sky-600 hover:to-blue-700 px-2.5 py-1 text-[11px] font-semibold text-white shadow-sm shadow-blue-500/30 ring-1 ring-blue-500/20 transition-all"
          >
            <Sparkles size={11} />
            <span className="hidden sm:inline">
              {t('whatsnew.tour_cta', { defaultValue: 'Take a quick tour' })}
            </span>
            <span className="sm:hidden">
              {t('whatsnew.tour_cta_short', { defaultValue: 'Tour' })}
            </span>
          </button>
          <button
            type="button"
            onClick={handleChangelog}
            className="hidden sm:inline-flex items-center gap-0.5 rounded-full px-2 py-1 text-[11px] font-medium text-blue-700 hover:text-blue-800 dark:text-sky-300 dark:hover:text-sky-200 hover:bg-sky-500/10 dark:hover:bg-sky-400/10 transition-colors"
          >
            {t('whatsnew.changelog_link', {
              defaultValue: 'Full release notes',
            })}
            <ArrowRight size={11} />
          </button>
          <button
            type="button"
            onClick={handleDismiss}
            aria-label={t('whatsnew.dismiss', { defaultValue: 'Dismiss' })}
            className="flex h-7 w-7 items-center justify-center rounded-md text-sky-600/70 hover:text-blue-700 hover:bg-sky-500/10 dark:text-sky-300/70 dark:hover:text-sky-100 dark:hover:bg-sky-400/10 transition-colors"
          >
            <X size={14} />
          </button>
        </div>
      </div>
    </div>
  );
}

export default WhatsNewCard;

/* ── ChipWithPopover ───────────────────────────────────────────────────────
 *  A chip that, when expanded, renders its detail popover through a portal
 *  attached to `document.body`. This is the only way to make the popover
 *  paint above the rest of the dashboard: the WhatsNewCard root uses
 *  `backdrop-blur-md`, and any `filter`-style property creates a CSS
 *  stacking context that traps `position:absolute` descendants — even with
 *  `z-50` they still render below sibling widgets that live outside the
 *  card. A portal escapes that context entirely.
 *
 *  Position is measured from the chip button's `getBoundingClientRect()`
 *  on mount and re-measured on scroll / resize so the popover tracks the
 *  chip if the page moves while it is open.
 */

interface ChipWithPopoverProps {
  section: Section;
  expanded: boolean;
  onToggle: () => void;
  onReadMore: () => void;
  Icon: LucideIcon;
  t: (key: string, options?: { defaultValue: string }) => string;
}

function ChipWithPopover({
  section: s,
  expanded,
  onToggle,
  onReadMore,
  Icon,
  t,
}: ChipWithPopoverProps) {
  const chipRef = useRef<HTMLButtonElement | null>(null);
  const popoverRef = useRef<HTMLDivElement | null>(null);
  const [pos, setPos] = useState<{ top: number; left: number } | null>(null);

  // Re-measure the chip's screen position so the portaled popover stays
  // anchored. useLayoutEffect prevents a one-frame flicker at (0,0).
  useLayoutEffect(() => {
    if (!expanded) {
      setPos(null);
      return undefined;
    }
    const measure = () => {
      const el = chipRef.current;
      if (!el) return;
      const r = el.getBoundingClientRect();
      // Default-align under the chip; clamp right edge so a chip near the
      // right viewport edge doesn't push the 400px popover off-screen.
      const POPOVER_WIDTH = 400;
      const MARGIN = 8;
      const maxLeft = window.innerWidth - POPOVER_WIDTH - MARGIN;
      const left = Math.max(MARGIN, Math.min(r.left, maxLeft));
      setPos({ top: r.bottom + 6, left });
    };
    measure();
    window.addEventListener('resize', measure);
    window.addEventListener('scroll', measure, true);
    return () => {
      window.removeEventListener('resize', measure);
      window.removeEventListener('scroll', measure, true);
    };
  }, [expanded]);

  // Outside-click handler runs against BOTH the chip and the portaled
  // popover so clicking inside the popover doesn't close it.
  useEffect(() => {
    if (!expanded) return undefined;
    const onMouseDown = (ev: MouseEvent) => {
      const target = ev.target as Node;
      if (chipRef.current?.contains(target)) return;
      if (popoverRef.current?.contains(target)) return;
      onToggle();
    };
    document.addEventListener('mousedown', onMouseDown);
    return () => document.removeEventListener('mousedown', onMouseDown);
  }, [expanded, onToggle]);

  return (
    <>
      <button
        ref={chipRef}
        type="button"
        onClick={onToggle}
        aria-expanded={expanded}
        aria-controls={`whatsnew-chip-${s.id}-popover`}
        title={t(s.titleKey, { defaultValue: s.titleDefault })}
        className={[
          'inline-flex items-center gap-1 rounded-full px-2 py-1 text-[11px] font-medium',
          'ring-1 transition-colors',
          expanded
            ? 'bg-gradient-to-br from-sky-500 to-blue-600 text-white ring-blue-500/40 shadow-sm shadow-blue-500/30'
            : 'bg-white/65 dark:bg-slate-900/45 text-blue-900 dark:text-sky-100 ring-sky-500/25 hover:bg-sky-500/15 dark:hover:bg-sky-400/15',
        ].join(' ')}
      >
        <Icon size={11} strokeWidth={2.25} />
        <span>{t(s.chipKey, { defaultValue: s.chipDefault })}</span>
      </button>
      {expanded && pos
        ? createPortal(
            <div
              ref={popoverRef}
              id={`whatsnew-chip-${s.id}-popover`}
              role="dialog"
              aria-label={t(s.titleKey, { defaultValue: s.titleDefault })}
              style={{
                position: 'fixed',
                top: pos.top,
                left: pos.left,
                width: 400,
                // z-[1000] sits above the sticky AppLayout header (z-30),
                // dashboard widget cards, and any module floating UI we ship.
                // Modal overlays use z-[2000]+ so this still ducks under them.
                zIndex: 1000,
              }}
              className={[
                'rounded-lg border border-sky-300/60 ring-1 ring-sky-500/10',
                'dark:border-sky-700/50 dark:ring-sky-400/10',
                'bg-white/95 dark:bg-slate-900/95 backdrop-blur-md',
                'shadow-lg shadow-sky-500/20 p-3',
              ].join(' ')}
            >
              <h3 className="text-[12px] font-semibold text-blue-900 dark:text-sky-100 leading-snug mb-1.5 line-clamp-4">
                {t(s.titleKey, { defaultValue: s.titleDefault })}
              </h3>
              <ul className="space-y-0.5">
                {s.bullets.map((b) => (
                  <li
                    key={b.key}
                    className="flex items-start gap-1.5 text-xs leading-snug text-blue-900/85 dark:text-sky-100/85"
                  >
                    <span
                      aria-hidden="true"
                      className="mt-[6px] h-1 w-1 shrink-0 rounded-full bg-sky-500/70"
                    />
                    <span>{t(b.key, { defaultValue: b.default })}</span>
                  </li>
                ))}
              </ul>
              <button
                type="button"
                onClick={onReadMore}
                className="mt-2 inline-flex items-center gap-0.5 text-[11px] font-medium text-blue-700 hover:text-blue-800 dark:text-sky-300 dark:hover:text-sky-100 transition-colors"
              >
                {t('whatsnew.read_more', { defaultValue: 'Read more' })}
                <ArrowRight size={11} />
              </button>
            </div>,
            document.body,
          )
        : null}
    </>
  );
}
