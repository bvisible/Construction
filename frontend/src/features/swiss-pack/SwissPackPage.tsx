/**
 * NEOFFICE FILE — Owned 100% by Neoservice. Not from upstream OCE.
 *
 * SwissPackPage — Reference dashboard for the Swiss regional pack.
 *
 * Surfaces the data exposed by the ``oe_swiss_pack`` backend module:
 * - Identity (region, currency, locales, formats)
 * - 15 standards (4 classifications + 11 SIA norms)
 * - Searchable CFC / eBKP-H / eBKP-T / NPK browsers
 * - TVA Suisse 2024 rates
 * - Contract types per SIA 118
 * - Legal notices required by CRB
 */

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  Building2,
  Flag,
  Coins,
  Languages,
  CalendarDays,
  Hash,
  FileText,
  Search,
  Info,
  ScrollText,
  Briefcase,
  ArrowRight,
} from 'lucide-react';
import clsx from 'clsx';
import { Card, Badge, Input, EmptyState, Skeleton } from '@/shared/ui';
import { apiGet } from '@/shared/lib/api';
import type {
  ClassificationSummary,
  ContractType,
  StandardDetail,
  StandardSummary,
  TaxRule,
} from './types';

const CATALOG_KEYS = ['CFC', 'eBKP-H', 'eBKP-T', 'NPK'] as const;
type CatalogKey = (typeof CATALOG_KEYS)[number];

interface SwissPackConfigSummary {
  region_code: string;
  countries: string[];
  default_currency: string;
  supported_locales: string[];
  default_locale: string;
  date_format: string;
  number_format: string;
  paper_size: string;
  measurement_system: string;
  display_name_i18n: Record<string, string>;
  metadata?: {
    schema_version?: string;
    generated_on?: string;
    legal_notice?: string;
    sipal_notice?: string;
    source_subproject?: string;
  };
}

/* ── Hooks ──────────────────────────────────────────────────────────────── */

function useSwissPackIdentity() {
  // We fetch the full config but only render its identity-level fields here;
  // TanStack Query memoises the response across the page.
  return useQuery({
    queryKey: ['swiss-pack', 'config-light'],
    queryFn: async () => {
      const cfg = await apiGet<SwissPackConfigSummary & Record<string, unknown>>(
        '/v1/swiss_pack/config/',
      );
      return cfg;
    },
    staleTime: 5 * 60 * 1000,
  });
}

function useSwissPackStandards() {
  return useQuery({
    queryKey: ['swiss-pack', 'standards'],
    queryFn: () => apiGet<StandardSummary[]>('/v1/swiss_pack/standards/'),
    staleTime: 5 * 60 * 1000,
  });
}

function useStandardDetail(code: string | null) {
  return useQuery({
    queryKey: ['swiss-pack', 'standards', code],
    queryFn: () => apiGet<StandardDetail>(`/v1/swiss_pack/standards/${code}/`),
    enabled: !!code,
    staleTime: 5 * 60 * 1000,
  });
}

function useTaxRules() {
  return useQuery({
    queryKey: ['swiss-pack', 'tax-rules'],
    queryFn: () => apiGet<TaxRule[]>('/v1/swiss_pack/tax-rules/'),
    staleTime: 60 * 60 * 1000,
  });
}

function useContractTypes() {
  return useQuery({
    queryKey: ['swiss-pack', 'contract-types'],
    queryFn: () => apiGet<ContractType[]>('/v1/swiss_pack/contract-types/'),
    staleTime: 60 * 60 * 1000,
  });
}

function useClassificationsSummary() {
  return useQuery({
    queryKey: ['swiss-pack', 'classifications'],
    queryFn: () => apiGet<ClassificationSummary>('/v1/swiss_pack/classifications/'),
    staleTime: 5 * 60 * 1000,
  });
}

/* ── Sub-components ─────────────────────────────────────────────────────── */

function IdentityCard({ data }: { data: SwissPackConfigSummary | undefined }) {
  if (!data) {
    return <Skeleton className="h-32 w-full" />;
  }
  const items: Array<{ icon: React.ReactNode; label: string; value: string }> = [
    {
      icon: <Flag className="h-4 w-4" />,
      label: 'Code région',
      value: `${data.region_code} (${data.countries.join(', ')})`,
    },
    {
      icon: <Coins className="h-4 w-4" />,
      label: 'Devise',
      value: data.default_currency,
    },
    {
      icon: <Languages className="h-4 w-4" />,
      label: 'Langues supportées',
      value: data.supported_locales.join(' / ').toUpperCase() + ` (défaut: ${data.default_locale.toUpperCase()})`,
    },
    {
      icon: <CalendarDays className="h-4 w-4" />,
      label: 'Format de date',
      value: data.date_format,
    },
    {
      icon: <Hash className="h-4 w-4" />,
      label: 'Format numérique',
      value: `${data.number_format} (apostrophe suisse)`,
    },
    {
      icon: <FileText className="h-4 w-4" />,
      label: 'Format papier',
      value: data.paper_size,
    },
  ];
  return (
    <Card padding="md">
      <div className="flex items-start justify-between gap-4">
        <div className="flex items-center gap-3">
          <div className="rounded-lg bg-rose-50 p-3 text-rose-600">
            <Building2 className="h-6 w-6" />
          </div>
          <div>
            <h2 className="text-xl font-semibold tracking-tight">
              Pack régional — Suisse (CH)
            </h2>
            <p className="text-sm text-slate-500">
              Standards de construction suisses (CFC, eBKP-H/T, NPK), normes SIA, TVA, contrats SIA 118
            </p>
          </div>
        </div>
        <Badge variant="success">Module activé</Badge>
      </div>
      <div className="mt-5 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
        {items.map((item) => (
          <div
            key={item.label}
            className="flex items-center gap-2 rounded-md border border-slate-200 bg-slate-50 px-3 py-2"
          >
            <span className="text-slate-500">{item.icon}</span>
            <div className="min-w-0">
              <div className="text-xs uppercase tracking-wide text-slate-500">
                {item.label}
              </div>
              <div className="truncate text-sm font-medium text-slate-900">
                {item.value}
              </div>
            </div>
          </div>
        ))}
      </div>
    </Card>
  );
}

function StandardsOverview({ data }: { data: StandardSummary[] | undefined }) {
  if (!data) return <Skeleton className="h-48 w-full" />;
  const classifications = data.filter((s) =>
    (CATALOG_KEYS as readonly string[]).includes(s.code),
  );
  const sia = data.filter((s) => s.code.startsWith('SIA_'));
  return (
    <Card padding="md">
      <h3 className="mb-3 text-lg font-semibold">Standards exposés</h3>
      <div className="grid grid-cols-1 gap-6 md:grid-cols-2">
        <div>
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            Classifications ({classifications.length})
          </div>
          <ul className="divide-y divide-slate-100">
            {classifications.map((s) => (
              <li key={s.code} className="flex items-center justify-between py-2">
                <div>
                  <span className="font-mono text-sm font-semibold">{s.code}</span>
                  <div className="text-xs text-slate-500 line-clamp-1">{s.name}</div>
                </div>
                <Badge variant="blue">{s.size.toLocaleString('fr-CH')} entrées</Badge>
              </li>
            ))}
          </ul>
        </div>
        <div>
          <div className="mb-2 text-xs font-medium uppercase tracking-wide text-slate-500">
            Normes SIA ({sia.length})
          </div>
          <ul className="divide-y divide-slate-100">
            {sia.map((s) => (
              <li key={s.code} className="flex items-center justify-between py-2">
                <div>
                  <span className="font-mono text-sm font-semibold">{s.code}</span>
                  <div className="text-xs text-slate-500 line-clamp-1">{s.name}</div>
                </div>
              </li>
            ))}
          </ul>
        </div>
      </div>
    </Card>
  );
}

function ClassificationBrowser({
  summary,
}: {
  summary: ClassificationSummary | undefined;
}) {
  const [active, setActive] = useState<CatalogKey>('CFC');
  const [search, setSearch] = useState('');

  const entries = summary?.[active] ?? [];
  const filtered = useMemo(() => {
    const q = search.trim().toLowerCase();
    if (!q) return entries.slice(0, 200);
    return entries
      .filter(
        (e) =>
          e.code.toLowerCase().includes(q) ||
          (e.label_fr ?? '').toLowerCase().includes(q),
      )
      .slice(0, 200);
  }, [entries, search]);

  return (
    <Card padding="md">
      <div className="mb-4 flex flex-wrap items-center justify-between gap-4">
        <div>
          <h3 className="text-lg font-semibold">Explorateur de classifications</h3>
          <p className="text-sm text-slate-500">
            Codes et libellés courts. Aucun texte détaillé NPK reproduit (cf. mention CRB).
          </p>
        </div>
        <div className="flex items-center gap-2">
          {CATALOG_KEYS.map((key) => {
            const count = summary?.[key]?.length ?? 0;
            const isActive = active === key;
            return (
              <button
                key={key}
                type="button"
                onClick={() => {
                  setActive(key);
                  setSearch('');
                }}
                className={clsx(
                  'rounded-md border px-3 py-1.5 text-sm font-medium transition-colors',
                  isActive
                    ? 'border-rose-300 bg-rose-50 text-rose-700'
                    : 'border-slate-200 bg-white text-slate-700 hover:bg-slate-50',
                )}
              >
                <span className="font-mono">{key}</span>
                <span className="ml-1 text-xs text-slate-500">
                  ({count.toLocaleString('fr-CH')})
                </span>
              </button>
            );
          })}
        </div>
      </div>

      <div className="mb-3 flex items-center gap-2">
        <div className="relative flex-1">
          <Search className="absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
          <Input
            value={search}
            onChange={(e) => setSearch(e.target.value)}
            placeholder={`Chercher un code ou libellé ${active}…`}
            className="pl-9"
          />
        </div>
        <span className="whitespace-nowrap text-xs text-slate-500">
          {filtered.length === entries.length || !search
            ? `${filtered.length} affichés`
            : `${filtered.length} / ${entries.length}`}
        </span>
      </div>

      {filtered.length === 0 ? (
        <EmptyState
          title="Aucune entrée"
          description="Modifiez votre recherche pour afficher des résultats."
        />
      ) : (
        <div className="max-h-[420px] overflow-y-auto rounded-md border border-slate-200">
          <table className="w-full text-sm">
            <thead className="sticky top-0 bg-slate-50 text-xs uppercase tracking-wide text-slate-500">
              <tr>
                <th className="px-4 py-2 text-left font-medium">Code</th>
                <th className="px-4 py-2 text-left font-medium">Libellé (FR)</th>
                <th className="px-4 py-2 text-left font-medium">Niveau</th>
                <th className="px-4 py-2 text-left font-medium">Note</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-slate-100">
              {filtered.map((entry) => (
                <tr key={`${entry.code}-${entry.is_sipal_specific ? 'sipal' : 'std'}`}>
                  <td className="px-4 py-2 font-mono text-slate-900">{entry.code}</td>
                  <td className="px-4 py-2 text-slate-700">{entry.label_fr ?? '—'}</td>
                  <td className="px-4 py-2 text-slate-500">L{entry.level}</td>
                  <td className="px-4 py-2 text-xs text-slate-500">
                    {entry.is_sipal_specific && (
                      <Badge variant="warning">SIPaL Vaud</Badge>
                    )}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {!search && entries.length > 200 && (
        <p className="mt-2 text-xs text-slate-500">
          Affichage des 200 premières entrées. Filtrez pour cibler une référence précise.
        </p>
      )}
    </Card>
  );
}

function TaxRulesTable({ rules }: { rules: TaxRule[] | undefined }) {
  if (!rules) return <Skeleton className="h-32 w-full" />;
  return (
    <Card padding="md">
      <h3 className="mb-3 text-lg font-semibold">TVA Suisse — taux 2024+</h3>
      <table className="w-full text-sm">
        <thead className="text-xs uppercase tracking-wide text-slate-500">
          <tr>
            <th className="px-2 py-2 text-left font-medium">Code</th>
            <th className="px-2 py-2 text-left font-medium">Libellé</th>
            <th className="px-2 py-2 text-right font-medium">Taux</th>
            <th className="px-2 py-2 text-left font-medium">Cas d'usage</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100">
          {rules.map((rule) => (
            <tr key={rule.code}>
              <td className="px-2 py-3 font-mono text-xs text-slate-700">{rule.code}</td>
              <td className="px-2 py-3 font-medium">{rule.name}</td>
              <td className="px-2 py-3 text-right font-mono">
                <Badge variant="blue">{rule.rate_pct} %</Badge>
              </td>
              <td className="px-2 py-3 text-xs text-slate-500">{rule.use_case}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </Card>
  );
}

function ContractTypesTable({ types }: { types: ContractType[] | undefined }) {
  if (!types) return <Skeleton className="h-40 w-full" />;
  return (
    <Card padding="md">
      <h3 className="mb-3 text-lg font-semibold">Types de contrats — SIA 118</h3>
      <div className="grid grid-cols-1 gap-3 md:grid-cols-2">
        {types.map((c) => (
          <div
            key={c.code}
            className="rounded-md border border-slate-200 p-3 transition-colors hover:bg-slate-50"
          >
            <div className="mb-1 flex items-center justify-between">
              <span className="text-base font-semibold">{c.name}</span>
              {c.sia_reference && (
                <span className="text-xs text-slate-500">{c.sia_reference}</span>
              )}
            </div>
            <p className="text-sm text-slate-600">{c.description}</p>
            {c.name_i18n && (
              <div className="mt-2 flex flex-wrap gap-2 text-xs text-slate-500">
                {c.name_i18n.de && <span>DE: {c.name_i18n.de}</span>}
                {c.name_i18n.it && <span>IT: {c.name_i18n.it}</span>}
              </div>
            )}
          </div>
        ))}
      </div>
    </Card>
  );
}

function SiaNormsList({
  standards,
  onSelect,
  selected,
  detail,
}: {
  standards: StandardSummary[] | undefined;
  onSelect: (code: string) => void;
  selected: string | null;
  detail: StandardDetail | undefined;
}) {
  const sia = (standards ?? []).filter((s) => s.code.startsWith('SIA_'));
  return (
    <Card padding="md">
      <h3 className="mb-3 text-lg font-semibold">Normes SIA — référence</h3>
      <div className="grid grid-cols-1 gap-4 md:grid-cols-3">
        <div className="md:col-span-1">
          <ul className="divide-y divide-slate-100 rounded-md border border-slate-200">
            {sia.map((s) => (
              <li key={s.code}>
                <button
                  type="button"
                  onClick={() => onSelect(s.code)}
                  className={clsx(
                    'flex w-full items-center justify-between px-3 py-2 text-left text-sm transition-colors',
                    selected === s.code ? 'bg-rose-50 text-rose-700' : 'hover:bg-slate-50',
                  )}
                >
                  <span className="font-mono font-semibold">{s.code}</span>
                  <ArrowRight className="h-3.5 w-3.5 text-slate-400" />
                </button>
              </li>
            ))}
          </ul>
        </div>
        <div className="md:col-span-2">
          {!selected && (
            <EmptyState
              title="Sélectionnez une norme"
              description="Cliquez sur un code SIA pour afficher ses détails."
            />
          )}
          {selected && !detail && <Skeleton className="h-48 w-full" />}
          {selected && detail && (
            <div className="space-y-3">
              <div>
                <div className="text-xs uppercase tracking-wide text-slate-500">
                  {detail.sia_reference ?? detail.code}
                </div>
                <h4 className="text-base font-semibold">{detail.name}</h4>
                <p className="text-sm text-slate-600">{detail.description}</p>
              </div>
              {detail.warranty_years !== undefined && (
                <div className="flex flex-wrap gap-2">
                  <Badge variant="blue">
                    Garantie {detail.warranty_years} an(s)
                  </Badge>
                  {detail.defect_liability_years !== undefined && (
                    <Badge variant="warning">
                      Défauts cachés {detail.defect_liability_years} ans
                    </Badge>
                  )}
                </div>
              )}
              {detail.note && (
                <div className="rounded-md border border-blue-100 bg-blue-50 px-3 py-2 text-xs text-blue-900">
                  <Info className="mr-1 inline h-3.5 w-3.5" />
                  {detail.note}
                </div>
              )}
              {detail.use_case && (
                <p className="text-xs text-slate-500">
                  <strong>Cas d'usage :</strong> {detail.use_case}
                </p>
              )}
              {detail.service_phases && detail.service_phases.length > 0 && (
                <div>
                  <h5 className="mb-2 text-sm font-semibold">Phases de prestation</h5>
                  <table className="w-full text-xs">
                    <thead className="text-slate-500">
                      <tr>
                        <th className="px-2 py-1 text-left font-medium">Phase</th>
                        <th className="px-2 py-1 text-left font-medium">Titre</th>
                        <th className="px-2 py-1 text-right font-medium">Part %</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-100">
                      {detail.service_phases.map((p, i) => (
                        <tr key={`${p.subphase}-${i}`}>
                          <td className="px-2 py-1 font-mono">{p.subphase ?? p.phase}</td>
                          <td className="px-2 py-1">{p.title}</td>
                          <td className="px-2 py-1 text-right font-mono">{p.fee_share_pct ?? '—'}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          )}
        </div>
      </div>
    </Card>
  );
}

function LegalNotice({ data }: { data: SwissPackConfigSummary | undefined }) {
  const legal = data?.metadata?.legal_notice;
  const sipal = data?.metadata?.sipal_notice;
  if (!legal && !sipal) return null;
  return (
    <Card padding="md">
      <div className="flex items-start gap-3">
        <div className="rounded-md bg-slate-100 p-2 text-slate-500">
          <ScrollText className="h-5 w-5" />
        </div>
        <div className="space-y-3 text-xs leading-relaxed text-slate-600">
          {legal && <p>{legal}</p>}
          {sipal && <p>{sipal}</p>}
          {data?.metadata?.source_subproject && (
            <p className="text-slate-400">
              Source des données : <code>{data.metadata.source_subproject}</code>
              {data.metadata.generated_on && ` — généré le ${data.metadata.generated_on}`}
            </p>
          )}
        </div>
      </div>
    </Card>
  );
}

/* ── Page ───────────────────────────────────────────────────────────────── */

export function SwissPackPage() {
  const [selectedSia, setSelectedSia] = useState<string | null>('SIA_118');

  const identity = useSwissPackIdentity();
  const standards = useSwissPackStandards();
  const taxes = useTaxRules();
  const contracts = useContractTypes();
  const summary = useClassificationsSummary();
  const detail = useStandardDetail(selectedSia);

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <div className="mb-2 flex items-center gap-2 text-sm text-slate-500">
        <Briefcase className="h-4 w-4" />
        <span>Pack régional</span>
        <span>/</span>
        <span className="text-slate-900">Suisse (CH)</span>
      </div>

      <IdentityCard data={identity.data} />
      <StandardsOverview data={standards.data} />
      <ClassificationBrowser summary={summary.data} />
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <TaxRulesTable rules={taxes.data} />
        <ContractTypesTable types={contracts.data} />
      </div>
      <SiaNormsList
        standards={standards.data}
        selected={selectedSia}
        onSelect={setSelectedSia}
        detail={detail.data}
      />
      <LegalNotice data={identity.data} />
    </div>
  );
}

export default SwissPackPage;
