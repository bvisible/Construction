// DDC-CWICR-OE: DataDrivenConstruction - OpenConstructionERP
// Copyright (c) 2026 Artem Boiko / DataDrivenConstruction
//
// Find records - one faceted, ranked search across the whole project record
// (documents, correspondence, change orders). Every hit carries provenance
// (owning module, record type, id and the date the event occurred) so a claim
// or a dispute can be reconstructed from the evidence without hunting through
// each module in turn. Read-only and scoped to the selected project.

import { useState } from 'react';
import { useParams } from 'react-router-dom';
import { useTranslation } from 'react-i18next';
import { useQuery } from '@tanstack/react-query';
import { Search, FileSearch, SlidersHorizontal, Inbox } from 'lucide-react';
import { Card, Badge, EmptyState, SkeletonTable, DismissibleInfo } from '@/shared/ui';
import { getErrorMessage } from '@/shared/lib/api';
import { useProjectContextStore } from '@/stores/useProjectContextStore';
import { searchRecords } from './api';
import type { RetrievalQuery, RetrievalResult } from './types';

type BadgeVariant = 'neutral' | 'blue' | 'success' | 'warning' | 'error';

const RECORD_TYPE_VARIANT: Record<string, BadgeVariant> = {
  document: 'blue',
  correspondence: 'success',
  change_order: 'warning',
};

function recordTypeLabel(
  t: (k: string, o: { defaultValue: string }) => string,
  recordType: string,
): string {
  switch (recordType) {
    case 'document':
      return t('retrieval.type_document', { defaultValue: 'Document' });
    case 'correspondence':
      return t('retrieval.type_correspondence', { defaultValue: 'Correspondence' });
    case 'change_order':
      return t('retrieval.type_change_order', { defaultValue: 'Change order' });
    default:
      return recordType;
  }
}

function ResultCard({ result }: { result: RetrievalResult }) {
  const { t } = useTranslation();
  const variant = RECORD_TYPE_VARIANT[result.record_type] ?? 'neutral';
  return (
    <Card className="space-y-2 p-4">
      <div className="flex flex-wrap items-center gap-2">
        <Badge variant={variant}>{recordTypeLabel(t, result.record_type)}</Badge>
        <span className="text-sm font-semibold text-content-primary">
          {result.title || t('retrieval.untitled', { defaultValue: 'Untitled' })}
        </span>
        <span className="ms-auto text-xs tabular-nums text-content-tertiary">
          {t('retrieval.score', { defaultValue: 'score {{score}}', score: result.score.toFixed(2) })}
        </span>
      </div>
      {result.snippet && (
        <p className="text-sm text-content-secondary">{result.snippet}</p>
      )}
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1 text-xs text-content-tertiary">
        <span>{result.source_module}</span>
        {result.party && <span>{result.party}</span>}
        {result.occurred_at && <span>{result.occurred_at.slice(0, 10)}</span>}
        {result.entity_refs.map((ref) => (
          <code key={ref} className="rounded bg-surface-secondary px-1.5 py-0.5">
            {ref}
          </code>
        ))}
      </div>
      {result.matched_facets.length > 0 && (
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-xs text-content-tertiary">
            {t('retrieval.matched', { defaultValue: 'Matched:' })}
          </span>
          {result.matched_facets.map((facet) => (
            <Badge key={facet} variant="neutral">
              {facet}
            </Badge>
          ))}
        </div>
      )}
    </Card>
  );
}

export function RetrievalPage() {
  const { t } = useTranslation();
  const { projectId: routeProjectId } = useParams();
  const activeProjectId = useProjectContextStore((s) => s.activeProjectId);
  const projectId = routeProjectId ?? activeProjectId ?? '';

  // The form state is the draft; `query` is the committed search the API runs.
  const [text, setText] = useState('');
  const [party, setParty] = useState('');
  const [recordType, setRecordType] = useState('');
  const [dateFrom, setDateFrom] = useState('');
  const [dateTo, setDateTo] = useState('');
  const [query, setQuery] = useState<RetrievalQuery | null>(null);

  const searchQuery = useQuery({
    queryKey: ['retrieval', 'search', projectId, query],
    queryFn: () => searchRecords(projectId, query ?? {}),
    enabled: !!projectId && query !== null,
    retry: false,
  });

  const runSearch = () => {
    setQuery({
      text,
      party,
      record_type: recordType,
      date_from: dateFrom,
      date_to: dateTo,
    });
  };

  if (!projectId) {
    return (
      <div className="p-4">
        <EmptyState
          icon={<FileSearch className="h-6 w-6" />}
          title={t('retrieval.no_project_title', { defaultValue: 'No project selected' })}
          description={t('retrieval.no_project_desc', {
            defaultValue: 'Select a project to search across its records.',
          })}
        />
      </div>
    );
  }

  const results = searchQuery.data?.results ?? [];

  return (
    <div className="space-y-4 p-1">
      <div>
        <h1 className="flex items-center gap-2 text-xl font-semibold text-content-primary">
          <FileSearch className="h-5 w-5" />
          {t('retrieval.title', { defaultValue: 'Find Records' })}
        </h1>
        <p className="mt-1 text-sm text-content-secondary">
          {t('retrieval.subtitle', {
            defaultValue: 'Search documents, correspondence and change orders in one place, ranked and with provenance.',
          })}
        </p>
      </div>

      <DismissibleInfo
        storageKey="retrieval-intro"
        title={t('retrieval.intro_title', { defaultValue: 'Claim-grade search' })}
      >
        {t('retrieval.intro_body', {
          defaultValue:
            'One search runs across every part of the project record at once. Narrow by party, date range or record type. Each result carries its source module, record id and the date it happened, so you can rebuild the chain of evidence behind a claim or a dispute. Leave the box empty and search to browse everything, newest first.',
        })}
      </DismissibleInfo>

      <Card className="space-y-3 p-4">
        <div className="flex flex-col gap-2 sm:flex-row">
          <div className="relative flex-1">
            <Search className="pointer-events-none absolute start-2.5 top-1/2 h-4 w-4 -translate-y-1/2 text-content-tertiary" />
            <input
              value={text}
              onChange={(e) => setText(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') runSearch();
              }}
              placeholder={t('retrieval.text_ph', { defaultValue: 'Search the project record...' })}
              className="w-full rounded-md border border-border-light bg-surface-primary ps-8 pe-2 py-2 text-sm text-content-primary"
            />
          </div>
          <button
            type="button"
            onClick={runSearch}
            className="inline-flex items-center justify-center gap-1.5 rounded-md bg-oe-blue px-4 py-2 text-sm font-medium text-white"
          >
            <Search className="h-4 w-4" />
            {t('retrieval.search', { defaultValue: 'Search' })}
          </button>
        </div>

        <details className="text-sm">
          <summary className="flex cursor-pointer items-center gap-1.5 text-content-secondary">
            <SlidersHorizontal className="h-4 w-4" />
            {t('retrieval.filters', { defaultValue: 'Filters' })}
          </summary>
          <div className="mt-3 grid gap-3 sm:grid-cols-2">
            <label className="flex flex-col gap-1 text-sm text-content-secondary">
              {t('retrieval.party', { defaultValue: 'Party' })}
              <input
                value={party}
                onChange={(e) => setParty(e.target.value)}
                placeholder={t('retrieval.party_ph', { defaultValue: 'e.g. contractor-a' })}
                className="rounded-md border border-border-light bg-surface-primary px-2 py-1 text-sm text-content-primary"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-content-secondary">
              {t('retrieval.record_type', { defaultValue: 'Record type' })}
              <select
                value={recordType}
                onChange={(e) => setRecordType(e.target.value)}
                className="rounded-md border border-border-light bg-surface-primary px-2 py-1 text-sm text-content-primary"
              >
                <option value="">{t('retrieval.type_any', { defaultValue: 'Any type' })}</option>
                <option value="document">{t('retrieval.type_document', { defaultValue: 'Document' })}</option>
                <option value="correspondence">
                  {t('retrieval.type_correspondence', { defaultValue: 'Correspondence' })}
                </option>
                <option value="change_order">
                  {t('retrieval.type_change_order', { defaultValue: 'Change order' })}
                </option>
              </select>
            </label>
            <label className="flex flex-col gap-1 text-sm text-content-secondary">
              {t('retrieval.date_from', { defaultValue: 'From date' })}
              <input
                type="date"
                value={dateFrom}
                onChange={(e) => setDateFrom(e.target.value)}
                className="rounded-md border border-border-light bg-surface-primary px-2 py-1 text-sm text-content-primary"
              />
            </label>
            <label className="flex flex-col gap-1 text-sm text-content-secondary">
              {t('retrieval.date_to', { defaultValue: 'To date' })}
              <input
                type="date"
                value={dateTo}
                onChange={(e) => setDateTo(e.target.value)}
                className="rounded-md border border-border-light bg-surface-primary px-2 py-1 text-sm text-content-primary"
              />
            </label>
          </div>
        </details>
      </Card>

      {searchQuery.isLoading ? (
        <SkeletonTable rows={3} />
      ) : searchQuery.isError ? (
        <EmptyState
          icon={<Inbox className="h-6 w-6" />}
          title={t('retrieval.error_title', { defaultValue: 'Search failed' })}
          description={getErrorMessage(searchQuery.error)}
        />
      ) : query === null ? (
        <EmptyState
          icon={<FileSearch className="h-6 w-6" />}
          title={t('retrieval.start_title', { defaultValue: 'Search the project record' })}
          description={t('retrieval.start_desc', {
            defaultValue: 'Enter a term or open Filters, then search. Leave the box empty to browse everything.',
          })}
        />
      ) : results.length === 0 ? (
        <EmptyState
          icon={<Inbox className="h-6 w-6" />}
          title={t('retrieval.empty_title', { defaultValue: 'No matching records' })}
          description={t('retrieval.empty_desc', {
            defaultValue: 'Nothing on the project record matched these facets. Try widening the search.',
          })}
        />
      ) : (
        <div className="space-y-3">
          <p className="text-xs text-content-tertiary">
            {t('retrieval.count', {
              defaultValue: '{{count}} matching records',
              count: searchQuery.data?.count ?? results.length,
            })}
          </p>
          {results.map((result) => (
            <ResultCard key={`${result.record_type}:${result.record_id}`} result={result} />
          ))}
        </div>
      )}
    </div>
  );
}

export default RetrievalPage;
