/**
 * SiteTravelCard — shows the dynamically-computed labour travel cost for a
 * project's construction site.
 *
 * Uses the project's own address (already geocoded via Nominatim/OSM) to call the
 * composed-tariff engine (POST /neoffice/labor-tariff/compose/), which resolves
 * the Sottens -> chantier driving time and applies the CN/CCT travel split. The
 * déplacement is billed on TIME (minutes) — the km is shown for context only.
 *
 * The "Calculé dynamiquement" pill makes it obvious to the estimator that this
 * value came from a live rule, not a hand-typed number.
 */
import { useQuery } from '@tanstack/react-query';
import { useTranslation } from 'react-i18next';
import { Truck, Sparkles } from 'lucide-react';
import { Card } from '@/shared/ui';
import { apiPost } from '@/shared/lib/api';
import type { Project } from '../api';

// Reference class shown in the headline: Q — ouvrier qualifié CFC (CN 2026 base).
const REF_BASE_HOURLY = 34.0;
const REF_CLASS = 'Q';

interface TariffResult {
  distance_km?: number;
  round_trip_min?: number;
  offered_min?: number;
  passenger_billable_min?: number;
  cout_horaire_sans_deplacement_chf: string;
  cout_horaire_conducteur_chf: string;
  cout_horaire_passager_chf: string;
}

// French decimal display (54.37 -> 54,37).
const fr = (v?: string) => (v ? v.replace('.', ',') : '—');

export function SiteTravelCard({ project }: { project: Project }) {
  const { t } = useTranslation();
  const addr = project.address as Record<string, unknown> | null | undefined;
  const siteAddress = addr
    ? [addr.street, addr.postal_code, addr.city, addr.country].filter(Boolean).join(', ')
    : '';

  const { data, isLoading, isError } = useQuery<TariffResult>({
    queryKey: ['neoffice', 'labor-tariff', project.id, siteAddress],
    queryFn: () =>
      apiPost<TariffResult>('/v1/neoffice/labor-tariff/compose/', {
        base_hourly: REF_BASE_HOURLY,
        site_address: siteAddress,
      }),
    enabled: siteAddress.length > 3,
    staleTime: 1000 * 60 * 30,
    retry: false,
  });

  return (
    <Card padding="md" className="h-full">
      <div className="flex items-center justify-between mb-3">
        <div className="flex items-center gap-2 text-sm font-semibold text-content-primary">
          <Truck size={16} className="text-oe-blue" />
          {t('project.travel.title', { defaultValue: 'Main-d’œuvre — déplacement chantier' })}
        </div>
        {data && (
          <span className="inline-flex items-center gap-1 rounded-full bg-oe-blue-subtle/40 px-2 py-0.5 text-2xs font-medium text-oe-blue-text">
            <Sparkles size={10} />
            {t('project.travel.dynamic', { defaultValue: 'Calculé dynamiquement' })}
          </span>
        )}
      </div>

      {!siteAddress && (
        <div className="text-2xs text-content-tertiary">
          {t('project.travel.no_address', {
            defaultValue: "Renseignez l’adresse du chantier pour calculer le déplacement depuis Sottens.",
          })}
        </div>
      )}
      {siteAddress && isLoading && <div className="h-20 animate-pulse rounded bg-surface-secondary" />}
      {siteAddress && isError && (
        <div className="text-2xs text-content-tertiary">
          {t('project.travel.error', { defaultValue: 'Adresse non localisée — précisez la ville du chantier.' })}
        </div>
      )}
      {data && (
        <>
          <div className="flex flex-wrap items-baseline gap-x-3 gap-y-1 text-sm text-content-secondary mb-3">
            <span>
              <strong className="text-content-primary tabular-nums">{data.round_trip_min}</strong>{' '}
              {t('project.travel.min_rt', { defaultValue: 'min A/R' })}
            </span>
            <span className="text-content-quaternary">·</span>
            <span className="tabular-nums text-content-tertiary">{data.distance_km} km</span>
            <span className="text-content-quaternary">·</span>
            <span className="text-2xs text-content-tertiary">Sottens → chantier</span>
          </div>
          <div className="grid grid-cols-2 gap-2">
            <div className="rounded-lg border border-border-light px-3 py-2">
              <div className="text-2xs text-content-tertiary">
                {t('project.travel.driver', { defaultValue: 'Conducteur' })} · {REF_CLASS}
              </div>
              <div className="text-lg font-semibold tabular-nums text-content-primary">
                {fr(data.cout_horaire_conducteur_chf)}{' '}
                <span className="text-2xs font-normal text-content-tertiary">CHF/h</span>
              </div>
            </div>
            <div className="rounded-lg border border-border-light px-3 py-2">
              <div className="text-2xs text-content-tertiary">
                {t('project.travel.passengers', { defaultValue: 'Passagers' })} · {REF_CLASS}
              </div>
              <div className="text-lg font-semibold tabular-nums text-content-primary">
                {fr(data.cout_horaire_passager_chf)}{' '}
                <span className="text-2xs font-normal text-content-tertiary">CHF/h</span>
              </div>
            </div>
          </div>
          <div className="mt-2 text-2xs text-content-tertiary">
            {t('project.travel.rule', {
              defaultValue: 'Règle CN/CCT : {{offered}} min offerts, facturé au temps (min). Base sans déplacement {{base}} CHF/h.',
              offered: data.offered_min,
              base: fr(data.cout_horaire_sans_deplacement_chf),
            })}
          </div>
        </>
      )}
    </Card>
  );
}
