/**
 * ModuleHelpButton — small pill button surfaced on a module page header
 * that launches that module's guided tour.
 *
 * Pattern: one button per module page (BOQ Editor, BIM Hub, PropDev, …)
 * dispatches the existing `oe:start-tour` window event with a `tourId`
 * detail payload.  The single global ProductTour mounted at App root
 * picks up the event, swaps to the matching playlist from
 * TOUR_REGISTRY, and runs the spotlight walkthrough.
 *
 * Mobile collapse: on `sm` and below the label hides and only the
 * HelpCircle icon shows — the button stays accessible via aria-label.
 */

import { useCallback } from 'react';
import { useTranslation } from 'react-i18next';
import { HelpCircle } from 'lucide-react';
import clsx from 'clsx';

import { TOUR_START_EVENT, type TourId } from './ProductTour';

export interface ModuleHelpButtonProps {
  /** Registered tour id to launch (must exist in TOUR_REGISTRY). */
  tourId: TourId;
  /** Optional extra classes for layout-specific tweaks. */
  className?: string;
}

export function ModuleHelpButton({ tourId, className }: ModuleHelpButtonProps) {
  const { t } = useTranslation();

  const handleClick = useCallback(() => {
    // Dispatch on window so the ProductTour listener (mounted at App
    // root) picks it up regardless of which module page is active.
    window.dispatchEvent(
      new CustomEvent(TOUR_START_EVENT, { detail: { tourId } }),
    );
  }, [tourId]);

  const label = t('module_help.tour_button', { defaultValue: 'Tour' });
  const aria = t('module_help.tour_aria', {
    defaultValue: 'Start guided tour for this module',
  });

  return (
    <button
      type="button"
      onClick={handleClick}
      data-testid={`module-help-button-${tourId}`}
      aria-label={aria}
      title={aria}
      className={clsx(
        'inline-flex items-center gap-1.5 rounded-full',
        'border border-oe-blue/30 bg-oe-blue/5 hover:bg-oe-blue/10',
        'px-2.5 h-7 text-xs font-medium text-oe-blue',
        'transition-colors focus:outline-none focus:ring-2 focus:ring-oe-blue/40',
        className,
      )}
    >
      <HelpCircle size={13} strokeWidth={2} />
      <span className="hidden sm:inline">{label}</span>
    </button>
  );
}
