// DDC-CWICR-OE: DataDrivenConstruction · OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// GlobalSearchPage — full page route ``/files/search`` for
// cross-project file lookup. Search box + kind filter + result list.
// Each result card opens the file inside its own project context
// (we keep the navigation explicit because the file-manager URL
// shape includes the project id).

import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { Link, useSearchParams } from 'react-router-dom';
import clsx from 'clsx';
import {
  FileText,
  Image as ImageIcon,
  Layout,
  Search,
} from 'lucide-react';

import { Button } from '@/shared/ui/Button';
import { Input } from '@/shared/ui/Input';
import { useGlobalFileSearch } from './hooks';
import type { SearchHit, SearchHitKind } from './types';

const KIND_ICONS: Record<SearchHitKind, typeof FileText> = {
  document: FileText,
  sheet: Layout,
  photo: ImageIcon,
};

const ALL_KINDS: SearchHitKind[] = ['document', 'sheet', 'photo'];

interface SearchResultCardProps {
  hit: SearchHit;
}

export function SearchResultCard({ hit }: SearchResultCardProps) {
  const { t } = useTranslation();
  const Icon = KIND_ICONS[hit.kind] ?? FileText;
  // The file-manager page reads the project from the URL — point the
  // user there with the file pre-selected via ``selected`` query.
  const target = `/files?project=${encodeURIComponent(
    hit.project_id,
  )}&kind=${encodeURIComponent(hit.kind)}&selected=${encodeURIComponent(hit.file_id)}`;
  return (
    <Link
      to={target}
      data-testid={`search-result-${hit.file_id}`}
      className={clsx(
        'flex flex-col gap-1 rounded-lg border border-border bg-surface-primary',
        'px-4 py-3 hover:border-oe-blue hover:shadow-sm',
        'transition focus:outline-none focus-visible:ring-2 focus-visible:ring-oe-blue',
      )}
    >
      <div className="flex items-center gap-2">
        <Icon className="h-4 w-4 shrink-0 text-content-secondary" />
        <span className="flex-1 truncate font-medium text-content-primary">
          {hit.canonical_name || t('files.global_search.unnamed', { defaultValue: '(unnamed)' })}
        </span>
        <span className="rounded-full bg-surface-secondary px-2 py-0.5 text-[10px] uppercase tracking-wide text-content-tertiary">
          {hit.kind}
        </span>
      </div>
      <div className="flex items-center gap-2 text-xs text-content-tertiary">
        <span className="truncate">{hit.project_name}</span>
      </div>
      {hit.snippet && (
        <p className="line-clamp-2 text-xs text-content-secondary">{hit.snippet}</p>
      )}
    </Link>
  );
}

export function GlobalSearchPage() {
  const { t } = useTranslation();
  const [searchParams, setSearchParams] = useSearchParams();
  const initialQ = searchParams.get('q') ?? '';
  const [query, setQuery] = useState(initialQ);
  const [activeKinds, setActiveKinds] = useState<SearchHitKind[]>(ALL_KINDS);

  const { data, isFetching, error } = useGlobalFileSearch({
    q: query,
    kinds: activeKinds.length === ALL_KINDS.length ? undefined : activeKinds,
    limit: 100,
    enabled: query.trim().length > 0,
  });

  const hits = useMemo<SearchHit[]>(() => data?.items ?? [], [data]);

  const submit = (e: React.FormEvent) => {
    e.preventDefault();
    const trimmed = query.trim();
    const next = new URLSearchParams(searchParams);
    if (trimmed) {
      next.set('q', trimmed);
    } else {
      next.delete('q');
    }
    setSearchParams(next, { replace: true });
  };

  const toggleKind = (kind: SearchHitKind) => {
    setActiveKinds((prev) => {
      if (prev.includes(kind)) {
        return prev.filter((k) => k !== kind);
      }
      return [...prev, kind];
    });
  };

  return (
    <div className="mx-auto flex w-full max-w-5xl flex-col gap-4 px-4 py-6">
      <header className="flex flex-col gap-1">
        <h1 className="text-xl font-semibold text-content-primary">
          {t('files.global_search.title', { defaultValue: 'Search across all projects' })}
        </h1>
        <p className="text-sm text-content-secondary">
          {t('files.global_search.subtitle', {
            defaultValue:
              'Find a document, sheet or photo by name across every project you can access.',
          })}
        </p>
      </header>

      <form onSubmit={submit} className="flex flex-col gap-2 sm:flex-row sm:items-center">
        <div className="flex flex-1 items-center gap-2">
          <Search className="h-4 w-4 text-content-secondary" />
          <Input
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder={t('files.global_search.placeholder', {
              defaultValue: 'e.g. foundation plan, RFI-014, IFC-arch',
            })}
            data-testid="global-search-input"
            className="flex-1"
            autoFocus
          />
        </div>
        <Button type="submit" loading={isFetching}>
          {t('files.global_search.search_button', { defaultValue: 'Search' })}
        </Button>
      </form>

      <div className="flex flex-wrap items-center gap-2" data-testid="global-search-kind-filters">
        <span className="text-xs uppercase tracking-wide text-content-tertiary">
          {t('files.global_search.kind_filter_label', { defaultValue: 'Kinds' })}
        </span>
        {ALL_KINDS.map((kind) => {
          const Icon = KIND_ICONS[kind];
          const on = activeKinds.includes(kind);
          return (
            <button
              key={kind}
              type="button"
              onClick={() => toggleKind(kind)}
              aria-pressed={on}
              className={clsx(
                'inline-flex items-center gap-1 rounded-full border px-2.5 py-1 text-xs',
                on
                  ? 'border-oe-blue bg-oe-blue/10 text-oe-blue'
                  : 'border-border bg-surface-primary text-content-secondary hover:bg-surface-secondary',
              )}
            >
              <Icon className="h-3 w-3" />
              {kind}
            </button>
          );
        })}
      </div>

      {data && !data.used_content_index && (
        <div
          role="note"
          className="rounded-md border border-border-light bg-surface-secondary px-3 py-2 text-xs text-content-secondary"
        >
          {t('files.global_search.metadata_only_notice', {
            defaultValue:
              'Searching file names only — content-text index is not installed on this build.',
          })}
        </div>
      )}

      {error && (
        <div
          role="alert"
          className="rounded-md border border-semantic-error/40 bg-semantic-error/10 px-3 py-2 text-sm text-semantic-error"
        >
          {error instanceof Error ? error.message : String(error)}
        </div>
      )}

      <section className="flex flex-col gap-2" data-testid="global-search-results">
        {query.trim().length === 0 && (
          <p className="text-sm text-content-tertiary">
            {t('files.global_search.empty_state', {
              defaultValue: 'Type a search above to begin.',
            })}
          </p>
        )}
        {query.trim().length > 0 && !isFetching && hits.length === 0 && (
          <p className="text-sm text-content-tertiary">
            {t('files.global_search.no_results', {
              defaultValue: 'No files matched your search.',
            })}
          </p>
        )}
        {hits.map((hit) => (
          <SearchResultCard key={`${hit.kind}-${hit.file_id}`} hit={hit} />
        ))}
      </section>
    </div>
  );
}
