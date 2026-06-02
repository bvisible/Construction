/**
 * Protti BOQ Viewer — Excel-like read-only rendering of the Phase 1 corpus.
 *
 * Loads ``/data/protti_corpus.json`` directly (no DB seeder needed) so the
 * full Maçonnerie devis (Attalens immeuble 7 appart.) can be inspected from
 * Neoconstruction with the same shape as the source spreadsheet:
 *
 *   - Section recap (Installation, Sous-sol, RDC, …, Régie) + Brut / TVA / TTC
 *   - Per-sheet article table (code, description, unit, qty, PU, total)
 *   - Per-article drill-down → sub-blocks → typed components
 *
 * Pure client side, no backend call. Designed for the Cédric demo.
 */

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  ChevronDown,
  ChevronRight,
  FileSpreadsheet,
  Search,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Card, CardContent, CardHeader } from '@/shared/ui/Card';
import { Skeleton } from '@/shared/ui/Skeleton';

// ── Corpus shape (a strict subset of what the Phase 1 parser produces) ──

interface CorpusComponent {
  type: string;
  label?: string;
  unit?: string | null;
  unit_price?: number | null;
  discount?: number | null;
  qty?: number | null;
  yield_per_hour?: number | null;
  amount?: number | null;
}

interface CorpusSubBlock {
  label?: string;
  metre_value?: number | null;
  metre_unit?: string | null;
  sale_price_per_unit?: number | null;
  components?: CorpusComponent[];
}

interface CorpusArticle {
  sheet: string;
  row: number;
  code: string;
  description: string;
  unit: string;
  quantity?: number | null;
  unit_price?: number | null;
  total?: number | null;
  is_regie?: boolean;
  regie_percentage?: number | null;
  sub_blocks?: CorpusSubBlock[];
}

interface SectionTotal {
  label: string;
  amount: number;
}

interface SheetTotals {
  sections: SectionTotal[];
  brut?: number | null;
  escompte?: number | null;
  net?: number | null;
  tva?: number | null;
  ttc?: number | null;
}

interface Corpus {
  source_file: string;
  catalog: {
    params?: Record<string, number>;
    mo_breakdown?: Record<string, number>;
    mo_travel_distance_km?: number;
    concrete_recipes?: Array<{ name: string; sale_price_per_m3?: number }>;
    machines?: Array<{ code: string | null; name: string; hourly_rate: number }>;
  };
  articles: CorpusArticle[];
  sheet_totals: Record<string, SheetTotals>;
}

// ── Display helpers ──────────────────────────────────────────────────────────

const TYPE_BADGE: Record<string, { bg: string; label: string }> = {
  labor: { bg: 'bg-amber-100 text-amber-800', label: 'MO' },
  fg_admin: { bg: 'bg-amber-50 text-amber-700', label: 'FG' },
  machine: { bg: 'bg-sky-100 text-sky-800', label: 'Mach' },
  material: { bg: 'bg-emerald-100 text-emerald-800', label: 'Mat' },
  internal_loc: { bg: 'bg-indigo-100 text-indigo-800', label: 'Loc int' },
  external_loc: { bg: 'bg-indigo-50 text-indigo-700', label: 'Loc ext' },
  external_margin: { bg: 'bg-rose-50 text-rose-700', label: 'Marge ext' },
  subcontractor: { bg: 'bg-violet-100 text-violet-800', label: 'S-trait' },
  subcontractor_margin: { bg: 'bg-rose-100 text-rose-700', label: 'Marge ST' },
  misc: { bg: 'bg-gray-100 text-gray-700', label: 'Divers' },
  transport: { bg: 'bg-cyan-100 text-cyan-800', label: 'Transp' },
};

function fmtCHF(n: number | null | undefined, decimals = 2): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return n.toLocaleString('fr-CH', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  });
}

function fmtNum(n: number | null | undefined): string {
  if (n === null || n === undefined || Number.isNaN(n)) return '—';
  return n.toLocaleString('fr-CH', { maximumFractionDigits: 4 });
}

// ── Corpus loader (single fetch, cached forever) ─────────────────────────────

async function loadCorpus(): Promise<Corpus> {
  // Use a base-relative path so it works both at the Vite dev server root
  // (/) and behind the Frappe asset mount (/assets/neoconstruction/…/).
  const base = import.meta.env.BASE_URL || '/';
  const url = `${base.replace(/\/$/, '')}/data/protti_corpus.json`;
  const res = await fetch(url, { cache: 'force-cache' });
  if (!res.ok) {
    throw new Error(`Failed to load corpus (${res.status})`);
  }
  return (await res.json()) as Corpus;
}

// ── Page component ───────────────────────────────────────────────────────────

export function ProttiBOQViewer() {
  const { t } = useTranslation();
  const corpusQuery = useQuery({
    queryKey: ['protti-corpus'],
    queryFn: loadCorpus,
    staleTime: Infinity,
    retry: false,
  });

  const [activeSheet, setActiveSheet] = useState<string | null>(null);
  const [expandedRow, setExpandedRow] = useState<number | null>(null);
  const [search, setSearch] = useState('');

  const corpus = corpusQuery.data;

  // Default to the heaviest sheet (211 Maçonnerie) once loaded.
  const sheetNames = useMemo(
    () => (corpus ? Object.keys(corpus.sheet_totals) : []),
    [corpus],
  );
  const selectedSheet =
    activeSheet ??
    sheetNames.find((s) => s.toLowerCase().includes('maçonnerie')) ??
    sheetNames[0] ??
    '';

  const articlesForSheet = useMemo(() => {
    if (!corpus) return [];
    const rows = corpus.articles.filter((a) => a.sheet === selectedSheet);
    const q = search.trim().toLowerCase();
    if (!q) return rows;
    return rows.filter(
      (a) =>
        a.description.toLowerCase().includes(q) ||
        (a.code || '').toLowerCase().includes(q),
    );
  }, [corpus, selectedSheet, search]);

  const sheetTotals = corpus?.sheet_totals[selectedSheet];

  if (corpusQuery.isLoading) {
    return (
      <div className="mx-auto max-w-7xl space-y-4 p-6">
        <Skeleton height={40} />
        <Skeleton height={200} />
        <Skeleton height={400} />
      </div>
    );
  }

  if (corpusQuery.error || !corpus) {
    return (
      <div className="mx-auto max-w-7xl p-6">
        <Card>
          <CardContent className="p-6 text-sm text-red-600">
            {corpusQuery.error instanceof Error
              ? corpusQuery.error.message
              : 'Corpus introuvable'}
          </CardContent>
        </Card>
      </div>
    );
  }

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      {/* ── Header ────────────────────────────────────────────────────── */}
      <header>
        <div className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
          <FileSpreadsheet className="h-6 w-6 text-primary" aria-hidden />
          {t('protti.title', {
            defaultValue: 'Devis Protti — Immeuble Attalens (7 appartements)',
          })}
        </div>
        <p className="mt-1 text-sm text-text-secondary">
          {t('protti.subtitle', {
            defaultValue:
              'Visualisation du devis source (corpus Phase 1) avec sous-détail de prix typé par composante.',
          })}
        </p>
      </header>

      {/* ── Catalog highlights ────────────────────────────────────────── */}
      <Card>
        <CardHeader
          title={t('protti.catalog', { defaultValue: 'Paramètres de chiffrage' })}
          subtitle={t('protti.catalog_subtitle', {
            defaultValue:
              'Coût horaire MO, R&B et coefficient métrés — repris de l\'onglet « Bases » du fichier source.',
          })}
        />
        <CardContent className="grid grid-cols-2 gap-3 p-4 md:grid-cols-5">
          <Stat label="Coût MO/h" value={`${fmtCHF(corpus.catalog.params?.labor_cost_per_hour)} CHF`} />
          <Stat label="FG admin/h" value={`${fmtCHF(corpus.catalog.params?.fg_administrative)} CHF`} />
          <Stat
            label="R&B"
            value={`${((corpus.catalog.params?.rb_risk_benefit ?? 0) * 100).toFixed(1)} %`}
          />
          <Stat
            label="Coef. métrés"
            value={fmtNum(corpus.catalog.params?.metres_coefficient)}
          />
          <Stat
            label="Loc int. centrale"
            value={`${fmtCHF(corpus.catalog.params?.central_loc_internal)} CHF/m³`}
          />
        </CardContent>
      </Card>

      {/* ── Sheet selector ────────────────────────────────────────────── */}
      <div className="flex flex-wrap gap-1.5">
        {sheetNames.map((name) => {
          const totals = corpus.sheet_totals[name];
          const isActive = selectedSheet === name;
          return (
            <button
              key={name}
              onClick={() => {
                setActiveSheet(name);
                setExpandedRow(null);
              }}
              className={`rounded-md border px-3 py-1.5 text-xs font-medium transition ${
                isActive
                  ? 'border-primary bg-primary/10 text-primary'
                  : 'border-border text-text-secondary hover:border-text-tertiary'
              }`}
            >
              {name}
              <span className="ml-2 text-text-tertiary">
                {fmtCHF(totals?.brut, 0)} CHF
              </span>
            </button>
          );
        })}
      </div>

      {/* ── Recap of the active sheet (sections + brut/tva/ttc) ────── */}
      {sheetTotals && (
        <Card>
          <CardHeader
            title={t('protti.recap', { defaultValue: 'Récapitulation' })}
            subtitle={selectedSheet}
          />
          <CardContent className="p-0">
            <table className="w-full text-sm">
              <tbody>
                {sheetTotals.sections.map((s, i) => (
                  <tr
                    key={`${s.label}-${i}`}
                    className="border-b border-border/40 last:border-0"
                  >
                    <td className="px-4 py-2 text-text-secondary">{s.label}</td>
                    <td className="px-4 py-2 text-right tabular-nums">
                      {fmtCHF(s.amount, 0)} CHF
                    </td>
                  </tr>
                ))}
                <tr className="border-t border-border bg-surface-secondary/50 font-semibold">
                  <td className="px-4 py-2.5">MONTANT TOTAL BRUT</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">
                    {fmtCHF(sheetTotals.brut, 2)} CHF
                  </td>
                </tr>
                <tr>
                  <td className="px-4 py-2 text-text-secondary">+ TVA 7.7 %</td>
                  <td className="px-4 py-2 text-right tabular-nums">
                    {fmtCHF(sheetTotals.tva, 2)} CHF
                  </td>
                </tr>
                <tr className="bg-primary/10 font-semibold text-primary">
                  <td className="px-4 py-2.5">MONTANT TOTAL TTC</td>
                  <td className="px-4 py-2.5 text-right tabular-nums">
                    {fmtCHF(sheetTotals.ttc, 2)} CHF
                  </td>
                </tr>
              </tbody>
            </table>
          </CardContent>
        </Card>
      )}

      {/* ── Article search ────────────────────────────────────────────── */}
      <Card>
        <CardContent className="p-3">
          <div className="relative">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-tertiary"
              aria-hidden
            />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('protti.search_placeholder', {
                defaultValue: 'Filtrer par code ou description…',
              })}
              className="h-10 w-full rounded-md border border-border bg-surface pl-10 pr-3 text-sm outline-none focus:border-primary"
            />
          </div>
        </CardContent>
      </Card>

      {/* ── Articles table with drill-down ───────────────────────────── */}
      <Card>
        <CardHeader
          title={`Articles ${articlesForSheet.length}/${corpus.articles.filter((a) => a.sheet === selectedSheet).length}`}
        />
        <CardContent className="p-0">
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead className="border-b border-border bg-surface-secondary/50 text-left text-xs uppercase text-text-tertiary">
                <tr>
                  <th className="w-6 px-2 py-2.5" />
                  <th className="px-3 py-2.5 font-medium">Code</th>
                  <th className="px-3 py-2.5 font-medium">Description</th>
                  <th className="px-3 py-2.5 font-medium">Unité</th>
                  <th className="px-3 py-2.5 text-right font-medium">Qté</th>
                  <th className="px-3 py-2.5 text-right font-medium">PU (CHF)</th>
                  <th className="px-3 py-2.5 text-right font-medium">Total (CHF)</th>
                </tr>
              </thead>
              <tbody>
                {articlesForSheet.map((art) => (
                  <ArticleRow
                    key={`${art.sheet}-${art.row}`}
                    article={art}
                    expanded={expandedRow === art.row}
                    onToggle={() =>
                      setExpandedRow(expandedRow === art.row ? null : art.row)
                    }
                  />
                ))}
              </tbody>
            </table>
          </div>
        </CardContent>
      </Card>
    </div>
  );
}

// ── Article row + expand ────────────────────────────────────────────────────

function ArticleRow({
  article,
  expanded,
  onToggle,
}: {
  article: CorpusArticle;
  expanded: boolean;
  onToggle: () => void;
}) {
  const hasSubBlocks = (article.sub_blocks?.length ?? 0) > 0;
  return (
    <>
      <tr
        className={`border-b border-border/40 transition-colors ${
          expanded ? 'bg-primary/5' : 'hover:bg-surface-secondary/40'
        } ${article.is_regie ? 'italic text-text-tertiary' : ''}`}
      >
        <td className="px-2 py-2.5">
          {hasSubBlocks ? (
            <button
              type="button"
              onClick={onToggle}
              className="rounded p-0.5 text-text-tertiary hover:bg-surface-secondary"
              aria-label="Toggle"
            >
              {expanded ? (
                <ChevronDown className="h-3.5 w-3.5" />
              ) : (
                <ChevronRight className="h-3.5 w-3.5" />
              )}
            </button>
          ) : null}
        </td>
        <td className="px-3 py-2.5 font-mono text-xs">{article.code || '—'}</td>
        <td className="px-3 py-2.5 max-w-xl text-text-primary">
          {article.description}
        </td>
        <td className="px-3 py-2.5 text-xs text-text-tertiary">
          {article.unit || '—'}
        </td>
        <td className="px-3 py-2.5 text-right tabular-nums">
          {fmtNum(article.quantity)}
        </td>
        <td className="px-3 py-2.5 text-right tabular-nums">
          {fmtCHF(article.unit_price)}
        </td>
        <td className="px-3 py-2.5 text-right font-medium tabular-nums">
          {fmtCHF(article.total)}
        </td>
      </tr>
      {expanded && hasSubBlocks && (
        <tr className="border-b border-border/60 bg-surface-secondary/30">
          <td />
          <td colSpan={6} className="px-3 py-3">
            <div className="space-y-3">
              {article.sub_blocks!.map((sb, i) => (
                <SubBlockCard key={i} sb={sb} index={i} />
              ))}
            </div>
          </td>
        </tr>
      )}
    </>
  );
}

function SubBlockCard({
  sb,
  index,
}: {
  sb: CorpusSubBlock;
  index: number;
}) {
  return (
    <div className="rounded-md border border-border bg-surface">
      <div className="flex flex-wrap items-baseline gap-2 border-b border-border px-3 py-2 text-xs">
        <span className="font-mono text-text-tertiary">
          {String.fromCharCode(97 + index)})
        </span>
        <span className="font-medium">{sb.label || '(sans libellé)'}</span>
        <span className="ml-auto text-text-tertiary">
          Métré <strong className="text-text-primary">{fmtNum(sb.metre_value)}</strong>{' '}
          {sb.metre_unit ?? ''} · Prix vente HT sans R&B{' '}
          <strong className="text-text-primary">{fmtCHF(sb.sale_price_per_unit)}</strong>{' '}
          CHF
        </span>
      </div>
      {sb.components && sb.components.length > 0 && (
        <table className="w-full text-xs">
          <thead className="text-text-tertiary">
            <tr className="border-b border-border/40">
              <th className="w-20 px-3 py-1.5 text-left font-normal">Type</th>
              <th className="px-3 py-1.5 text-left font-normal">Libellé</th>
              <th className="w-10 px-2 py-1.5 text-left font-normal">Un.</th>
              <th className="w-20 px-2 py-1.5 text-right font-normal">PU</th>
              <th className="w-16 px-2 py-1.5 text-right font-normal">Rem.</th>
              <th className="w-20 px-2 py-1.5 text-right font-normal">Qté</th>
              <th className="w-20 px-2 py-1.5 text-right font-normal">U/h</th>
              <th className="w-24 px-3 py-1.5 text-right font-normal">Montant</th>
            </tr>
          </thead>
          <tbody>
            {sb.components.map((c, ci) => {
              const badge = TYPE_BADGE[c.type] ?? {
                bg: 'bg-gray-100 text-gray-700',
                label: c.type,
              };
              return (
                <tr key={ci} className="border-b border-border/40 last:border-0">
                  <td className="px-3 py-1">
                    <span
                      className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium ${badge.bg}`}
                    >
                      {badge.label}
                    </span>
                  </td>
                  <td className="px-3 py-1 text-text-primary">{c.label}</td>
                  <td className="px-2 py-1 text-text-tertiary">{c.unit ?? '—'}</td>
                  <td className="px-2 py-1 text-right tabular-nums">
                    {fmtCHF(c.unit_price)}
                  </td>
                  <td className="px-2 py-1 text-right tabular-nums text-text-tertiary">
                    {c.discount != null ? `${(c.discount * 100).toFixed(0)} %` : '—'}
                  </td>
                  <td className="px-2 py-1 text-right tabular-nums">
                    {fmtNum(c.qty)}
                  </td>
                  <td className="px-2 py-1 text-right tabular-nums">
                    {fmtNum(c.yield_per_hour)}
                  </td>
                  <td className="px-3 py-1 text-right font-medium tabular-nums">
                    {fmtCHF(c.amount)}
                  </td>
                </tr>
              );
            })}
          </tbody>
        </table>
      )}
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <div className="text-xs uppercase text-text-tertiary">{label}</div>
      <div className="mt-0.5 text-lg font-semibold tabular-nums">{value}</div>
    </div>
  );
}
