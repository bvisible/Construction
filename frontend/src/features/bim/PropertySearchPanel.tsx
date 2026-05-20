/**
 * PropertySearchPanel — DuckDB-backed property search for the BIM viewer
 * (v3.12.0 / Stream D).
 *
 * Lets the user query the full DDC Parquet (1000+ columns per element) with
 * a tiny filter builder (column / operator / value) and pipe the resulting
 * element IDs straight into the 3D viewport via the caller-supplied
 * ``onIsolate`` callback. The backend already exposes the heavy lifting via
 * ``POST /models/{id}/dataframe/query/``; this panel is just a thin builder
 * on top.
 *
 * The Parquet primary key is ``id`` (the Revit ElementId). The mesh map in
 * the viewer is keyed by ``mesh_ref`` which equals that ``id`` for DDC
 * exports, so we forward the row's ``id`` field verbatim to ``onIsolate``.
 */

import { useCallback, useEffect, useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Search, Loader2, X } from 'lucide-react';
import {
  fetchBIMDataframeSchema,
  queryBIMDataframe,
  type BIMDataframeColumn,
  type BIMDataframeFilter,
} from './api';

interface PropertySearchPanelProps {
  modelId: string;
  /** Called with the list of matching element IDs (Revit ElementId / Parquet
   *  ``id`` column). The viewer's isolate flow accepts these directly. */
  onIsolate: (elementIds: string[]) => void;
  /** Called when the user clears the search — the parent should drop any
   *  active isolation set so the user sees the full model again. */
  onClear?: () => void;
}

type SearchOp = BIMDataframeFilter['op'];

const OPS: { value: SearchOp; label: string }[] = [
  { value: 'LIKE', label: 'contains' },
  { value: '=', label: '=' },
  { value: '!=', label: '!=' },
  { value: '>', label: '>' },
  { value: '>=', label: '>=' },
  { value: '<', label: '<' },
  { value: '<=', label: '<=' },
];

/** Decide whether the user's input should be coerced to a number so the
 *  operator picks up DuckDB's numeric comparison semantics instead of
 *  lexicographic. We only coerce when the operator is one of the numeric
 *  comparators and the trimmed value parses cleanly. */
function coerceValue(op: SearchOp, raw: string): string | number {
  if (op === '=' || op === '!=' || op === '>' || op === '>=' || op === '<' || op === '<=') {
    const trimmed = raw.trim();
    if (trimmed !== '' && Number.isFinite(Number(trimmed))) {
      return Number(trimmed);
    }
  }
  // LIKE always gets the raw string with %-wildcards added by the backend
  // (backend already wraps LIKE values in % when missing — see
  // dataframe_store.query_parquet). We forward the user's raw text.
  return raw;
}

export default function PropertySearchPanel({
  modelId,
  onIsolate,
  onClear,
}: PropertySearchPanelProps) {
  const { t } = useTranslation();
  const [schema, setSchema] = useState<BIMDataframeColumn[]>([]);
  const [column, setColumn] = useState<string>('');
  const [op, setOp] = useState<SearchOp>('LIKE');
  const [value, setValue] = useState<string>('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [resultCount, setResultCount] = useState<number | null>(null);

  useEffect(() => {
    if (!modelId) return;
    let cancelled = false;
    const ctrl = new AbortController();
    setError(null);
    fetchBIMDataframeSchema(modelId, ctrl.signal)
      .then((rows) => {
        if (cancelled) return;
        setSchema(rows);
        // Preselect a sensible default — prefer common DDC keys, otherwise
        // the first column. We exclude the synthetic ``id`` because the user
        // is unlikely to filter by Revit ElementId from a free-text box.
        const preferred = ['storey', 'level', 'category', 'name', 'type name'];
        const found = preferred.find((p) =>
          rows.some((r) => r.name.toLowerCase() === p.toLowerCase()),
        );
        if (found) {
          const exact = rows.find((r) => r.name.toLowerCase() === found.toLowerCase());
          if (exact) setColumn(exact.name);
        } else if (rows[0]) {
          setColumn(rows[0].name);
        }
      })
      .catch((e: unknown) => {
        if (cancelled) return;
        setError(e instanceof Error ? e.message : String(e));
      });
    return () => {
      cancelled = true;
      ctrl.abort();
    };
  }, [modelId]);

  /** Sorted, deduplicated column list. Long schemas (DDC exports can carry
   *  1000+ columns) are kept manageable by alphabetising — the user will
   *  scan, not page through. */
  const sortedColumns = useMemo(
    () => [...schema].sort((a, b) => a.name.localeCompare(b.name)),
    [schema],
  );

  const handleSearch = useCallback(async () => {
    if (!column || value.trim() === '') return;
    setLoading(true);
    setError(null);
    setResultCount(null);
    try {
      const rows = await queryBIMDataframe(modelId, {
        columns: ['id'],
        filters: [{ column, op, value: coerceValue(op, value) }],
        limit: 5000,
      });
      const ids = rows
        .map((r) => r.id)
        .filter((v): v is string | number => v !== null && v !== undefined)
        .map((v) => String(v));
      setResultCount(ids.length);
      onIsolate(ids);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }, [modelId, column, op, value, onIsolate]);

  const handleClear = useCallback(() => {
    setValue('');
    setResultCount(null);
    setError(null);
    onClear?.();
  }, [onClear]);

  const canSearch = !!column && value.trim() !== '' && !loading;

  return (
    <div className="flex flex-col gap-2 p-3" data-testid="property-search-panel">
      <h3 className="text-xs font-semibold text-content-primary uppercase tracking-wide">
        {t('bim.property_search_title', { defaultValue: 'Property search' })}
      </h3>
      <p className="text-[10px] text-content-tertiary">
        {t('bim.property_search_hint', {
          defaultValue:
            'Filter the full DDC dataframe (1000+ columns). Matches isolate in the 3D view.',
        })}
      </p>

      {/* Column dropdown */}
      <label className="block text-[10px] font-medium text-content-secondary">
        {t('bim.property_search_column', { defaultValue: 'Column' })}
      </label>
      <select
        value={column}
        onChange={(e) => setColumn(e.target.value)}
        disabled={loading || schema.length === 0}
        className="w-full min-w-0 px-2 py-1 text-[11px] rounded border border-border-light bg-surface-primary focus:outline-none focus:ring-1 focus:ring-oe-blue disabled:opacity-50"
        data-testid="property-search-column"
      >
        {schema.length === 0 && (
          <option value="">
            {t('bim.property_search_no_schema', {
              defaultValue: 'No schema available',
            })}
          </option>
        )}
        {sortedColumns.map((c) => (
          <option key={c.name} value={c.name}>
            {c.name} <span className="text-content-tertiary">({c.type})</span>
          </option>
        ))}
      </select>

      {/* Operator + value */}
      <div className="flex items-center gap-1.5 min-w-0">
        <select
          value={op}
          onChange={(e) => setOp(e.target.value as SearchOp)}
          disabled={loading}
          className="shrink-0 px-2 py-1 text-[11px] rounded border border-border-light bg-surface-primary focus:outline-none focus:ring-1 focus:ring-oe-blue"
          data-testid="property-search-op"
        >
          {OPS.map((o) => (
            <option key={o.value} value={o.value}>
              {o.label}
            </option>
          ))}
        </select>
        <input
          type="text"
          value={value}
          onChange={(e) => setValue(e.target.value)}
          onKeyDown={(e) => {
            if (e.key === 'Enter' && canSearch) handleSearch();
          }}
          placeholder={t('bim.property_search_value_placeholder', {
            defaultValue: 'Value…',
          })}
          className="min-w-0 flex-1 rounded border border-border-light bg-surface-primary px-2 py-1 text-[11px] focus:outline-none focus:ring-1 focus:ring-oe-blue"
          data-testid="property-search-value"
        />
      </div>

      <div className="flex items-center gap-1.5">
        <button
          type="button"
          onClick={handleSearch}
          disabled={!canSearch}
          className="flex-1 inline-flex items-center justify-center gap-1.5 rounded-md bg-oe-blue px-2 py-1 text-[11px] font-medium text-white hover:bg-oe-blue-dark disabled:opacity-50 disabled:cursor-not-allowed"
          data-testid="property-search-submit"
        >
          {loading ? <Loader2 size={11} className="animate-spin" /> : <Search size={11} />}
          {t('bim.property_search_run', { defaultValue: 'Search & isolate' })}
        </button>
        {resultCount !== null && (
          <button
            type="button"
            onClick={handleClear}
            className="shrink-0 inline-flex items-center gap-1 rounded-md border border-border-light bg-surface-primary px-2 py-1 text-[11px] text-content-secondary hover:bg-surface-tertiary"
            data-testid="property-search-clear"
          >
            <X size={11} />
            {t('common.clear', { defaultValue: 'Clear' })}
          </button>
        )}
      </div>

      {resultCount !== null && !error && (
        <p
          className="text-[10px] text-content-secondary"
          role="status"
          data-testid="property-search-result-count"
        >
          {t('bim.property_search_results', {
            defaultValue: '{{count}} matching element',
            defaultValue_plural: '{{count}} matching elements',
            count: resultCount,
          })}
        </p>
      )}
      {error && (
        <p
          className="text-[10px] text-rose-600 dark:text-rose-400"
          role="alert"
          data-testid="property-search-error"
        >
          {error}
        </p>
      )}

      {/*
        TODO (v3.13.0): server-persisted saved views + 3D markup persistence
        backend stub — both require an alembic migration which is out of
        scope for Stream D (v3.12.0). Tracked in MEMORY: "BIM server
        persistence deferred to v3.13.0 (requires migration)".
      */}
    </div>
  );
}
