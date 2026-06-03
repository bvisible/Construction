/**
 * Protti BOQ Viewer — Excel-like read-only rendering of the Phase 1 corpus.
 *
 * Styled with the same OCE design tokens (oe-blue, content-primary,
 * border-light, semantic-*) as the rest of the SPA so the page reads as a
 * native Neoconstruction screen.
 */

import { useMemo, useState } from 'react';
import { useQuery } from '@tanstack/react-query';
import {
  AlertTriangle,
  ChevronDown,
  ChevronRight,
  FileSpreadsheet,
  Layers,
  Receipt,
  Search,
  SlidersHorizontal,
} from 'lucide-react';
import { useTranslation } from 'react-i18next';

import { Skeleton } from '@/shared/ui/Skeleton';

// ── Corpus shape ────────────────────────────────────────────────────────────

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
  };
  articles: CorpusArticle[];
  sheet_totals: Record<string, SheetTotals>;
}

// ── Component-type badge (OCE tone) ─────────────────────────────────────────

const TYPE_BADGE: Record<string, { bg: string; text: string; short: string }> = {
  labor: {
    bg: 'bg-amber-100 dark:bg-amber-900/30',
    text: 'text-amber-800 dark:text-amber-300',
    short: 'MO',
  },
  fg_admin: {
    bg: 'bg-amber-50 dark:bg-amber-900/20',
    text: 'text-amber-700 dark:text-amber-400',
    short: 'FG',
  },
  machine: {
    bg: 'bg-sky-100 dark:bg-sky-900/30',
    text: 'text-sky-800 dark:text-sky-300',
    short: 'Machine',
  },
  material: {
    bg: 'bg-emerald-100 dark:bg-emerald-900/30',
    text: 'text-emerald-800 dark:text-emerald-300',
    short: 'Matière',
  },
  internal_loc: {
    bg: 'bg-indigo-100 dark:bg-indigo-900/30',
    text: 'text-indigo-800 dark:text-indigo-300',
    short: 'Loc int',
  },
  external_loc: {
    bg: 'bg-indigo-50 dark:bg-indigo-900/20',
    text: 'text-indigo-700 dark:text-indigo-400',
    short: 'Loc ext',
  },
  external_margin: {
    bg: 'bg-rose-50 dark:bg-rose-900/20',
    text: 'text-rose-700 dark:text-rose-400',
    short: 'Marge ext',
  },
  subcontractor: {
    bg: 'bg-violet-100 dark:bg-violet-900/30',
    text: 'text-violet-800 dark:text-violet-300',
    short: 'S-trait',
  },
  subcontractor_margin: {
    bg: 'bg-rose-100 dark:bg-rose-900/30',
    text: 'text-rose-700 dark:text-rose-400',
    short: 'Marge ST',
  },
  misc: {
    bg: 'bg-content-tertiary/10',
    text: 'text-content-secondary',
    short: 'Divers',
  },
  transport: {
    bg: 'bg-cyan-100 dark:bg-cyan-900/30',
    text: 'text-cyan-800 dark:text-cyan-300',
    short: 'Transport',
  },
};

// ── Formatters ──────────────────────────────────────────────────────────────

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

// ── Corpus loader ───────────────────────────────────────────────────────────

async function loadCorpus(): Promise<Corpus> {
  const base = import.meta.env.BASE_URL || '/';
  const url = `${base.replace(/\/$/, '')}/data/protti_corpus.json`;
  const res = await fetch(url, { cache: 'force-cache' });
  if (!res.ok) throw new Error(`Corpus introuvable (${res.status})`);
  return (await res.json()) as Corpus;
}

// ── Page ────────────────────────────────────────────────────────────────────

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

  const totals = corpus?.sheet_totals[selectedSheet];

  // ── Loading / error states ──────────────────────────────────────────────
  if (corpusQuery.isLoading) {
    return (
      <div className="mx-auto max-w-7xl space-y-3 p-6">
        <Skeleton height={48} className="w-1/2" rounded="md" />
        <Skeleton height={160} className="w-full" rounded="lg" />
        <Skeleton height={48} className="w-full" rounded="md" />
        <Skeleton height={300} className="w-full" rounded="lg" />
      </div>
    );
  }
  if (corpusQuery.error || !corpus) {
    return (
      <div className="mx-auto max-w-7xl p-6">
        <div className="flex items-start gap-3 rounded-lg border border-semantic-error/30 bg-semantic-error-bg/30 p-4">
          <AlertTriangle size={18} className="mt-0.5 shrink-0 text-semantic-error" />
          <div>
            <p className="text-sm font-medium text-content-primary">
              {t('protti.error_title', {
                defaultValue: 'Impossible de charger le corpus',
              })}
            </p>
            <p className="mt-0.5 text-xs text-content-tertiary">
              {corpusQuery.error instanceof Error
                ? corpusQuery.error.message
                : 'Erreur inconnue'}
            </p>
          </div>
        </div>
      </div>
    );
  }

  const totalArticles = corpus.articles.filter((a) => a.sheet === selectedSheet).length;

  return (
    <div className="mx-auto max-w-7xl space-y-5 p-6">
      {/* ── Header ────────────────────────────────────────────────────── */}
      <header className="flex items-start gap-3">
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-oe-blue-subtle text-oe-blue-text">
          <FileSpreadsheet size={18} aria-hidden />
        </div>
        <div className="min-w-0">
          <h1 className="text-xl font-semibold text-content-primary">
            {t('protti.title', {
              defaultValue: 'Devis Protti — Immeuble Attalens',
            })}
          </h1>
          <p className="mt-0.5 text-xs text-content-tertiary">
            {t('protti.subtitle', {
              defaultValue:
                'Visualisation du devis source (corpus Phase 1) — sous-détail de prix typé par composante.',
            })}
          </p>
        </div>
      </header>

      {/* ── Catalog parameters ───────────────────────────────────────── */}
      <section className="rounded-xl border border-border-light bg-surface">
        <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
          <SlidersHorizontal size={15} className="text-content-tertiary" aria-hidden />
          <h2 className="text-sm font-semibold text-content-primary">
            {t('protti.catalog', { defaultValue: 'Paramètres de chiffrage' })}
          </h2>
          <span className="ml-2 text-xs text-content-tertiary">
            {t('protti.catalog_subtitle', {
              defaultValue: "repris de l'onglet « Bases » du fichier source",
            })}
          </span>
        </div>
        <div className="grid grid-cols-2 gap-x-6 gap-y-3 p-5 md:grid-cols-5">
          <Stat
            label={t('protti.mo_per_hour', { defaultValue: 'Coût MO / h' })}
            value={`${fmtCHF(corpus.catalog.params?.labor_cost_per_hour)} CHF`}
          />
          <Stat
            label={t('protti.fg_per_hour', { defaultValue: 'FG admin / h' })}
            value={`${fmtCHF(corpus.catalog.params?.fg_administrative)} CHF`}
          />
          <Stat
            label={t('protti.rb', { defaultValue: 'Risques & Bénéfices' })}
            value={`${((corpus.catalog.params?.rb_risk_benefit ?? 0) * 100).toFixed(1)} %`}
          />
          <Stat
            label={t('protti.metres_coef', { defaultValue: 'Coef. majoration métrés' })}
            value={fmtNum(corpus.catalog.params?.metres_coefficient)}
          />
          <Stat
            label={t('protti.central_loc', { defaultValue: 'Loc. int. centrale' })}
            value={`${fmtCHF(corpus.catalog.params?.central_loc_internal)} CHF / m³`}
          />
        </div>
      </section>

      {/* ── Sheet tabs ───────────────────────────────────────────────── */}
      <div className="-mb-px flex flex-wrap gap-1 border-b border-border-light">
        {sheetNames.map((name) => {
          const totals = corpus.sheet_totals[name];
          const isActive = selectedSheet === name;
          return (
            <button
              key={name}
              type="button"
              onClick={() => {
                setActiveSheet(name);
                setExpandedRow(null);
              }}
              className={`group inline-flex items-baseline gap-2 border-b-2 px-3 py-2.5 text-sm transition ${
                isActive
                  ? 'border-oe-blue font-semibold text-content-primary'
                  : 'border-transparent text-content-secondary hover:border-content-tertiary/40 hover:text-content-primary'
              }`}
            >
              <span>{name}</span>
              <span
                className={`text-xs tabular-nums ${
                  isActive ? 'text-oe-blue' : 'text-content-tertiary'
                }`}
              >
                {fmtCHF(totals?.brut, 0)} CHF
              </span>
            </button>
          );
        })}
      </div>

      {/* ── Recap + KPIs ─────────────────────────────────────────────── */}
      {totals && (
        <div className="grid grid-cols-1 gap-4 lg:grid-cols-3">
          {/* Section table — 2/3 */}
          <section className="lg:col-span-2 rounded-xl border border-border-light bg-surface">
            <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
              <Layers size={15} className="text-content-tertiary" aria-hidden />
              <h2 className="text-sm font-semibold text-content-primary">
                {t('protti.recap', { defaultValue: 'Récapitulation' })}
              </h2>
              <span className="ml-auto text-xs text-content-tertiary">
                {selectedSheet}
              </span>
            </div>
            <table className="w-full text-sm">
              <tbody>
                {totals.sections.map((s, i) => (
                  <tr
                    key={`${s.label}-${i}`}
                    className="border-b border-border-light/60 last:border-0"
                  >
                    <td className="px-5 py-2 text-content-secondary">{s.label}</td>
                    <td className="px-5 py-2 text-right tabular-nums text-content-primary">
                      {fmtCHF(s.amount, 0)} CHF
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>

          {/* Brut / TVA / TTC stack — 1/3 */}
          <section className="rounded-xl border border-border-light bg-surface">
            <div className="flex items-center gap-2 border-b border-border-light px-5 py-3">
              <Receipt size={15} className="text-content-tertiary" aria-hidden />
              <h2 className="text-sm font-semibold text-content-primary">
                {t('protti.totals', { defaultValue: 'Montants' })}
              </h2>
            </div>
            <dl className="divide-y divide-border-light">
              <KPI label="Brut" value={`${fmtCHF(totals.brut)} CHF`} tone="strong" />
              <KPI label="Escompte" value={`${fmtCHF(totals.escompte)} CHF`} muted />
              <KPI label="Net HT" value={`${fmtCHF(totals.net)} CHF`} />
              <KPI label="TVA 7,7 %" value={`${fmtCHF(totals.tva)} CHF`} muted />
              <KPI label="TTC" value={`${fmtCHF(totals.ttc)} CHF`} tone="primary" />
            </dl>
          </section>
        </div>
      )}

      {/* ── Articles table ───────────────────────────────────────────── */}
      <section className="rounded-xl border border-border-light bg-surface">
        <div className="flex flex-wrap items-center justify-between gap-3 border-b border-border-light px-5 py-3">
          <h2 className="text-sm font-semibold text-content-primary">
            {t('protti.articles', { defaultValue: 'Articles' })}
            <span className="ml-2 text-xs font-normal text-content-tertiary">
              {articlesForSheet.length}
              {articlesForSheet.length !== totalArticles && ` / ${totalArticles}`}
            </span>
          </h2>
          <div className="relative w-full sm:w-72">
            <Search
              size={14}
              className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-content-tertiary"
              aria-hidden
            />
            <input
              type="search"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('protti.search_placeholder', {
                defaultValue: 'Filtrer (code, description)…',
              })}
              className="h-9 w-full rounded-lg border border-border-light bg-surface pl-9 pr-3 text-sm text-content-primary placeholder:text-content-tertiary outline-none focus:border-oe-blue"
            />
          </div>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[840px] text-sm">
            <thead className="border-b border-border-light bg-surface-secondary/40">
              <tr className="text-left text-xs text-content-tertiary">
                <th className="w-8 px-3 py-2.5" />
                <th className="px-3 py-2.5 font-medium">Code</th>
                <th className="px-3 py-2.5 font-medium">Description</th>
                <th className="px-3 py-2.5 font-medium">Unité</th>
                <th className="px-3 py-2.5 text-right font-medium">Quantité</th>
                <th className="px-3 py-2.5 text-right font-medium">PU</th>
                <th className="px-3 py-2.5 text-right font-medium">Total</th>
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
              {articlesForSheet.length === 0 && (
                <tr>
                  <td colSpan={7} className="px-5 py-10 text-center text-sm text-content-tertiary">
                    {t('protti.empty', { defaultValue: 'Aucun article ne correspond' })}
                  </td>
                </tr>
              )}
            </tbody>
          </table>
        </div>
      </section>
    </div>
  );
}

// ── Article row + sub-blocks ────────────────────────────────────────────────

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
        className={`border-b border-border-light/60 transition-colors ${
          expanded
            ? 'bg-oe-blue-subtle/40'
            : 'hover:bg-surface-secondary/50'
        } ${article.is_regie ? 'italic text-content-tertiary' : ''}`}
      >
        <td className="px-3 py-2.5">
          {hasSubBlocks && (
            <button
              type="button"
              onClick={onToggle}
              className="rounded p-0.5 text-content-tertiary hover:bg-surface-secondary hover:text-content-primary"
              aria-label={expanded ? 'Replier' : 'Déplier'}
            >
              {expanded ? <ChevronDown size={14} /> : <ChevronRight size={14} />}
            </button>
          )}
        </td>
        <td className="px-3 py-2.5 font-mono text-xs text-content-secondary">
          {article.code || '—'}
        </td>
        <td className="px-3 py-2.5 max-w-2xl text-content-primary">
          {article.description}
        </td>
        <td className="px-3 py-2.5 text-xs text-content-tertiary">
          {article.unit || '—'}
        </td>
        <td className="px-3 py-2.5 text-right tabular-nums text-content-secondary">
          {fmtNum(article.quantity)}
        </td>
        <td className="px-3 py-2.5 text-right tabular-nums text-content-secondary">
          {fmtCHF(article.unit_price)}
        </td>
        <td className="px-3 py-2.5 text-right font-medium tabular-nums text-content-primary">
          {fmtCHF(article.total)}
        </td>
      </tr>
      {expanded && hasSubBlocks && (
        <tr className="border-b border-border-light bg-surface-secondary/30">
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
    <div className="rounded-lg border border-border-light bg-surface shadow-xs">
      <div className="flex flex-wrap items-baseline gap-2 border-b border-border-light px-4 py-2">
        <span className="font-mono text-xs text-content-tertiary">
          {String.fromCharCode(97 + index)})
        </span>
        <span className="text-sm font-medium text-content-primary">
          {sb.label || <em className="text-content-tertiary">(sans libellé)</em>}
        </span>
        <span className="ml-auto text-xs text-content-tertiary">
          Métré{' '}
          <strong className="text-content-primary tabular-nums">
            {fmtNum(sb.metre_value)}
          </strong>{' '}
          {sb.metre_unit ?? ''} · Prix HT sans R&B{' '}
          <strong className="text-content-primary tabular-nums">
            {fmtCHF(sb.sale_price_per_unit)}
          </strong>{' '}
          CHF
        </span>
      </div>
      {sb.components && sb.components.length > 0 && (
        <table className="w-full text-xs">
          <thead className="text-content-tertiary">
            <tr className="border-b border-border-light/60">
              <th className="w-24 px-4 py-2 text-left font-normal">Type</th>
              <th className="px-3 py-2 text-left font-normal">Libellé</th>
              <th className="w-12 px-2 py-2 text-left font-normal">Un.</th>
              <th className="w-24 px-2 py-2 text-right font-normal">Prix u.</th>
              <th className="w-16 px-2 py-2 text-right font-normal">Rem.</th>
              <th className="w-24 px-2 py-2 text-right font-normal">Quantité</th>
              <th className="w-20 px-2 py-2 text-right font-normal">U / h</th>
              <th className="w-28 px-4 py-2 text-right font-normal">Montant</th>
            </tr>
          </thead>
          <tbody>
            {sb.components.map((c, ci) => {
              const b = TYPE_BADGE[c.type] ?? {
                bg: 'bg-content-tertiary/10',
                text: 'text-content-secondary',
                short: c.type,
              };
              return (
                <tr key={ci} className="border-b border-border-light/40 last:border-0">
                  <td className="px-4 py-1.5">
                    <span
                      className={`inline-block rounded px-1.5 py-0.5 text-[10px] font-medium ${b.bg} ${b.text}`}
                    >
                      {b.short}
                    </span>
                  </td>
                  <td className="px-3 py-1.5 text-content-primary">{c.label}</td>
                  <td className="px-2 py-1.5 text-content-tertiary">{c.unit ?? '—'}</td>
                  <td className="px-2 py-1.5 text-right tabular-nums text-content-secondary">
                    {fmtCHF(c.unit_price)}
                  </td>
                  <td className="px-2 py-1.5 text-right tabular-nums text-content-tertiary">
                    {c.discount != null && c.discount > 0
                      ? `${(c.discount * 100).toFixed(0)} %`
                      : '—'}
                  </td>
                  <td className="px-2 py-1.5 text-right tabular-nums text-content-secondary">
                    {fmtNum(c.qty)}
                  </td>
                  <td className="px-2 py-1.5 text-right tabular-nums text-content-secondary">
                    {fmtNum(c.yield_per_hour)}
                  </td>
                  <td className="px-4 py-1.5 text-right font-medium tabular-nums text-content-primary">
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
      <dt className="text-[10px] uppercase tracking-wide text-content-tertiary">
        {label}
      </dt>
      <dd className="mt-0.5 text-base font-semibold tabular-nums text-content-primary">
        {value}
      </dd>
    </div>
  );
}

function KPI({
  label,
  value,
  tone,
  muted,
}: {
  label: string;
  value: string;
  tone?: 'strong' | 'primary';
  muted?: boolean;
}) {
  return (
    <div
      className={`flex items-baseline justify-between gap-3 px-5 py-2.5 ${
        tone === 'primary' ? 'bg-oe-blue-subtle/40' : ''
      }`}
    >
      <dt
        className={`text-xs ${
          tone ? 'font-semibold text-content-primary' : muted ? 'text-content-tertiary' : 'text-content-secondary'
        }`}
      >
        {label}
      </dt>
      <dd
        className={`tabular-nums ${
          tone === 'primary'
            ? 'text-base font-semibold text-oe-blue'
            : tone === 'strong'
              ? 'text-sm font-semibold text-content-primary'
              : muted
                ? 'text-xs text-content-tertiary'
                : 'text-sm text-content-primary'
        }`}
      >
        {value}
      </dd>
    </div>
  );
}
