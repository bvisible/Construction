import { useMemo } from 'react';
import { useNavigate } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { MapPin, ChevronRight } from 'lucide-react';
import { ProjectWeather } from '@/shared/ui/ProjectWeather/ProjectWeather';
import { resolveProjectCoords, type ProjectPin } from './DashboardProjectsMap';

interface DashboardSitesPanelProps {
  projects: ProjectPin[];
}

interface SiteRow {
  id: string;
  name: string;
  cityLabel: string;
  coords: { lat: number; lng: number } | null;
}

/**
 * Right-side companion to the dashboard project map. Lists the same
 * projects grouped by city, and for each one shows a compact Open-Meteo
 * weather summary (next 7 days and ~15-day average) so a manager can spot
 * bad weather coming to a site at a glance. Rows link to the project.
 *
 * Coordinates come from the shared `resolveProjectCoords` helper (explicit
 * lat/lng, then the geocode cache the map fills, then a region centroid),
 * so weather appears without waiting on the map's async geocoder.
 */
export function DashboardSitesPanel({ projects }: DashboardSitesPanelProps) {
  const { t, i18n } = useTranslation();
  const navigate = useNavigate();

  const groups = useMemo(() => {
    const otherLabel = t('dashboard.sites_other', { defaultValue: 'Other locations' });
    const rows: SiteRow[] = projects.map((p) => ({
      id: p.id,
      name: p.name,
      cityLabel: (p.city || p.country || p.region || '').trim(),
      coords: resolveProjectCoords(p),
    }));
    const byCity = new Map<string, SiteRow[]>();
    for (const r of rows) {
      const key = r.cityLabel || otherLabel;
      const bucket = byCity.get(key);
      if (bucket) bucket.push(r);
      else byCity.set(key, [r]);
    }
    // Named cities alphabetically, the unlabeled bucket last.
    return [...byCity.entries()].sort((a, b) => {
      if (a[0] === otherLabel) return 1;
      if (b[0] === otherLabel) return -1;
      return a[0].localeCompare(b[0]);
    });
  }, [projects, t]);

  return (
    <div className="flex h-full flex-col overflow-hidden rounded-xl border border-border-light bg-surface-elevated/90">
      <div className="flex items-center justify-between border-b border-border-light px-3 py-2">
        <span className="text-xs font-semibold text-content-primary">
          {t('dashboard.sites_title', { defaultValue: 'Sites & weather' })}
        </span>
        <span className="text-[10px] tabular-nums text-content-tertiary">{projects.length}</span>
      </div>
      <div className="flex-1 divide-y divide-border-light/60 overflow-y-auto max-h-[22rem] lg:max-h-none">
        {groups.map(([city, rows]) => (
          <div key={city}>
            <div className="sticky top-0 z-10 bg-surface-elevated/95 px-3 py-1 text-[10px] font-semibold uppercase tracking-wide text-content-tertiary backdrop-blur-sm">
              {city}
            </div>
            {rows.map((r) => (
              <button
                key={r.id}
                type="button"
                onClick={() => navigate(`/projects/${r.id}`)}
                className="group flex w-full items-center gap-2 px-3 py-2 text-left transition-colors hover:bg-surface-primary/60"
              >
                <span className="flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-oe-blue/10 text-oe-blue">
                  <MapPin size={12} />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-xs font-medium text-content-primary">
                    {r.name}
                  </span>
                  {r.coords ? (
                    <ProjectWeather
                      lat={r.coords.lat}
                      lng={r.coords.lng}
                      locale={i18n.language}
                      variant="summary"
                      className="mt-0.5"
                    />
                  ) : (
                    <span className="text-[10px] text-content-quaternary">
                      {t('dashboard.sites_no_location', { defaultValue: 'No location set' })}
                    </span>
                  )}
                </span>
                <ChevronRight
                  size={13}
                  className="shrink-0 text-content-quaternary opacity-0 transition-opacity group-hover:opacity-100"
                />
              </button>
            ))}
          </div>
        ))}
      </div>
    </div>
  );
}
