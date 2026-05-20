// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Renders a green / yellow / red dot next to a cost item to communicate
// rate certainty.  Backed by ``GET /v1/costs/{id}/certainty/`` —
// frequency + recency of recorded usage drives the band.  Lazy by
// design: a hover tooltip explains the rule, and the component caches
// per-id via React Query so a grid of 50 rows costs 50 lookups once
// and zero on re-render.

import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import clsx from 'clsx';

import { fetchCertainty, type CertaintyBadge as CertaintyBadgeData } from './api';

interface CertaintyBadgeProps {
  costItemId: string;
  /** Render a "..." placeholder while the request is in-flight.  Set to
   *  false in dense table cells where a spinner would jiggle the layout. */
  showLoadingPlaceholder?: boolean;
  /** Optional extra classes for the wrapper span. */
  className?: string;
}

const BAND_STYLES: Record<CertaintyBadgeData['confidence_badge'], string> = {
  green: 'bg-semantic-success',
  yellow: 'bg-semantic-warning',
  red: 'bg-semantic-error',
};

const BAND_RING: Record<CertaintyBadgeData['confidence_badge'], string> = {
  green: 'ring-semantic-success/30',
  yellow: 'ring-semantic-warning/30',
  red: 'ring-semantic-error/30',
};

const STALE_AGE_SENTINEL = 999_000;

function formatAge(ageDays: number, t: ReturnType<typeof useTranslation>['t']): string {
  if (ageDays >= STALE_AGE_SENTINEL) {
    return t('costs.certainty.never_used', { defaultValue: 'never used' });
  }
  if (ageDays < 30) {
    return t('costs.certainty.age_days', {
      count: ageDays,
      defaultValue: '{{count}}d ago',
    });
  }
  if (ageDays < 365) {
    const months = Math.round(ageDays / 30);
    return t('costs.certainty.age_months', {
      count: months,
      defaultValue: '{{count}}mo ago',
    });
  }
  const years = Math.round((ageDays / 365) * 10) / 10;
  return t('costs.certainty.age_years', {
    count: years,
    defaultValue: '{{count}}y ago',
  });
}

export function CertaintyBadge({
  costItemId,
  showLoadingPlaceholder = false,
  className,
}: CertaintyBadgeProps) {
  const { t } = useTranslation();

  const { data, isLoading, isError } = useQuery<CertaintyBadgeData | null>({
    queryKey: ['costs', 'certainty', costItemId],
    queryFn: () => fetchCertainty(costItemId),
    // Certainty changes only when somebody applies the rate elsewhere —
    // safe to cache for a minute.
    staleTime: 60_000,
    // Single retry: the badge is decorative, not a blocker.
    retry: 1,
    enabled: Boolean(costItemId),
  });

  if (isError) {
    // Decorative — hide on error.
    return null;
  }

  if (isLoading) {
    if (!showLoadingPlaceholder) return null;
    return (
      <span
        className={clsx(
          'inline-flex h-2 w-2 shrink-0 rounded-full bg-content-tertiary/20 animate-pulse',
          className,
        )}
        aria-label={t('costs.certainty.loading', { defaultValue: 'Loading certainty…' })}
      />
    );
  }

  if (!data) return null;

  const tooltip = t('costs.certainty.tooltip', {
    defaultValue:
      'Used {{frequency}}× · last {{age}} · source {{source}}',
    frequency: data.frequency,
    age: formatAge(data.age_days, t),
    source: data.source || 'manual',
  });

  return (
    <span
      title={tooltip}
      className={clsx(
        'inline-flex h-2.5 w-2.5 shrink-0 rounded-full ring-2',
        BAND_STYLES[data.confidence_badge],
        BAND_RING[data.confidence_badge],
        className,
      )}
      aria-label={tooltip}
      data-certainty={data.confidence_badge}
    />
  );
}
