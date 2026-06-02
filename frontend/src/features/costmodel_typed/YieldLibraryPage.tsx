import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query';
import { Library, Plus, RefreshCw, Search, Trash2 } from 'lucide-react';
import { useMemo, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/shared/ui/Button';
import { Card, CardContent, CardHeader } from '@/shared/ui/Card';
import { ConfirmDialog } from '@/shared/ui/ConfirmDialog';
import { EmptyState } from '@/shared/ui/EmptyState';
import { Skeleton } from '@/shared/ui/Skeleton';
import { getErrorMessage } from '@/shared/lib/api';
import { useToastStore } from '@/stores/useToastStore';

import {
  costModelTypedApi,
  type YieldLibraryEntry,
  type YieldLibraryEntryCreate,
  type YieldSource,
} from './api';

const SOURCE_BADGE_CLASSES: Record<YieldSource, string> = {
  import: 'bg-blue-100 text-blue-700 dark:bg-blue-900/40 dark:text-blue-300',
  calibrated:
    'bg-emerald-100 text-emerald-700 dark:bg-emerald-900/40 dark:text-emerald-300',
  manual: 'bg-gray-100 text-gray-700 dark:bg-gray-800 dark:text-gray-300',
};

function fmtNum(s: string): string {
  const n = Number(s);
  if (!Number.isFinite(n)) return s;
  return n.toLocaleString(undefined, { maximumFractionDigits: 4 });
}

function fmtDateTime(s: string | null): string {
  if (!s) return '—';
  try {
    return new Date(s).toLocaleString();
  } catch {
    return s;
  }
}

const QUERY_KEY_LIST = ['costmodel_typed', 'yield-library', 'list'] as const;
const QUERY_KEY_SEARCH = ['costmodel_typed', 'yield-library', 'search'] as const;

export function YieldLibraryPage() {
  const { t } = useTranslation();
  const queryClient = useQueryClient();
  const addToast = useToastStore((s) => s.addToast);

  const [search, setSearch] = useState('');
  const [showCreate, setShowCreate] = useState(false);
  const [pendingDelete, setPendingDelete] = useState<YieldLibraryEntry | null>(null);

  const listQuery = useQuery({
    queryKey: [...QUERY_KEY_LIST, { include_global: true, limit: 500 }],
    queryFn: () => costModelTypedApi.listYieldEntries({ include_global: true, limit: 500 }),
    enabled: search.trim().length === 0,
    retry: false,
  });

  const searchQuery = useQuery({
    queryKey: [...QUERY_KEY_SEARCH, search],
    queryFn: () => costModelTypedApi.searchYieldEntries(search, 100),
    enabled: search.trim().length >= 2,
    retry: false,
  });

  const isSearching = search.trim().length >= 2;
  const entries = isSearching ? searchQuery.data ?? [] : listQuery.data ?? [];
  const isLoading = isSearching ? searchQuery.isLoading : listQuery.isLoading;
  const error = isSearching ? searchQuery.error : listQuery.error;

  const deleteMutation = useMutation({
    mutationFn: (entryId: string) => costModelTypedApi.deleteYieldEntry(entryId),
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ['costmodel_typed', 'yield-library'] });
      addToast({
        type: 'success',
        title: t('costmodel_typed.yield_deleted', { defaultValue: 'Entry deleted' }),
      });
      setPendingDelete(null);
    },
    onError: (err) => {
      addToast({
        type: 'error',
        title: t('costmodel_typed.yield_delete_failed', { defaultValue: 'Delete failed' }),
        message: getErrorMessage(err),
      });
    },
  });

  const stats = useMemo(() => {
    const total = entries.length;
    const bySource = entries.reduce<Record<string, number>>((acc, e) => {
      acc[e.source] = (acc[e.source] ?? 0) + 1;
      return acc;
    }, {});
    return { total, bySource };
  }, [entries]);

  return (
    <div className="mx-auto max-w-7xl space-y-6 p-6">
      <header className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <div className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
            <Library className="h-6 w-6 text-primary" aria-hidden />
            {t('costmodel_typed.yield_library_title', { defaultValue: 'Yield Library' })}
          </div>
          <p className="mt-1 text-sm text-text-secondary">
            {t('costmodel_typed.yield_library_subtitle', {
              defaultValue:
                'Productivity reference (U/h) per task — global library + project-scoped entries.',
            })}
          </p>
        </div>
        <div className="flex items-center gap-2">
          <Button
            variant="secondary"
            onClick={() => queryClient.invalidateQueries({ queryKey: ['costmodel_typed', 'yield-library'] })}
            disabled={isLoading}
          >
            <RefreshCw className={`mr-2 h-4 w-4 ${isLoading ? 'animate-spin' : ''}`} />
            {t('common.refresh', { defaultValue: 'Refresh' })}
          </Button>
          <Button onClick={() => setShowCreate(true)}>
            <Plus className="mr-2 h-4 w-4" />
            {t('costmodel_typed.add_entry', { defaultValue: 'Add entry' })}
          </Button>
        </div>
      </header>

      {/* Stats row */}
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        <Card>
          <CardContent className="p-4">
            <div className="text-xs uppercase text-text-tertiary">
              {t('costmodel_typed.entries_total', { defaultValue: 'Total entries' })}
            </div>
            <div className="mt-1 text-2xl font-semibold tabular-nums">{stats.total}</div>
          </CardContent>
        </Card>
        {(['import', 'calibrated', 'manual'] as const).map((source) => (
          <Card key={source}>
            <CardContent className="p-4">
              <div className="text-xs uppercase text-text-tertiary">{source}</div>
              <div className="mt-1 text-2xl font-semibold tabular-nums">
                {stats.bySource[source] ?? 0}
              </div>
            </CardContent>
          </Card>
        ))}
      </div>

      {/* Search */}
      <Card>
        <CardContent className="p-4">
          <div className="relative">
            <Search
              className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-text-tertiary"
              aria-hidden
            />
            <input
              type="text"
              value={search}
              onChange={(e) => setSearch(e.target.value)}
              placeholder={t('costmodel_typed.search_placeholder', {
                defaultValue: 'Search a task (min 2 characters)…',
              })}
              className="h-10 w-full rounded-md border border-border bg-surface pl-10 pr-3 text-sm outline-none focus:border-primary"
            />
          </div>
        </CardContent>
      </Card>

      {/* Table */}
      <Card>
        <CardHeader
          title={
            isSearching
              ? t('costmodel_typed.search_results', { defaultValue: 'Search results' })
              : t('costmodel_typed.all_entries', { defaultValue: 'All entries' })
          }
          subtitle={`${entries.length} ${
            entries.length === 1 ? 'entry' : 'entries'
          }`}
        />
        <CardContent className="p-0">
          {error ? (
            <div className="p-6 text-sm text-red-600">{getErrorMessage(error)}</div>
          ) : isLoading ? (
            <div className="space-y-2 p-4">
              <Skeleton height={28} />
              <Skeleton height={28} />
              <Skeleton height={28} />
              <Skeleton height={28} />
              <Skeleton height={28} />
            </div>
          ) : entries.length === 0 ? (
            <EmptyState
              title={t('costmodel_typed.no_entries', { defaultValue: 'No entries yet' })}
              description={t('costmodel_typed.no_entries_hint', {
                defaultValue: 'Import the Phase 1 corpus or add one manually.',
              })}
            />
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead className="border-b border-border bg-surface-secondary/50 text-left text-xs uppercase text-text-tertiary">
                  <tr>
                    <th className="px-4 py-2.5 font-medium">
                      {t('costmodel_typed.col_task', { defaultValue: 'Task' })}
                    </th>
                    <th className="px-4 py-2.5 font-medium">
                      {t('costmodel_typed.col_unit', { defaultValue: 'Unit' })}
                    </th>
                    <th className="px-4 py-2.5 text-right font-medium">
                      {t('costmodel_typed.col_yield', { defaultValue: 'U/h' })}
                    </th>
                    <th className="px-4 py-2.5 font-medium">
                      {t('costmodel_typed.col_source', { defaultValue: 'Source' })}
                    </th>
                    <th className="px-4 py-2.5 font-medium">
                      {t('costmodel_typed.col_source_ref', { defaultValue: 'Reference' })}
                    </th>
                    <th className="px-4 py-2.5 font-medium">
                      {t('costmodel_typed.col_calibrated', { defaultValue: 'Calibrated' })}
                    </th>
                    <th className="px-4 py-2.5 text-right font-medium" />
                  </tr>
                </thead>
                <tbody>
                  {entries.map((entry) => (
                    <tr
                      key={entry.id}
                      className="border-b border-border/60 transition-colors hover:bg-surface-secondary/40"
                    >
                      <td className="px-4 py-2.5 font-medium">{entry.task_label}</td>
                      <td className="px-4 py-2.5 text-text-secondary">
                        {entry.unit || '—'}
                      </td>
                      <td className="px-4 py-2.5 text-right tabular-nums">
                        {fmtNum(entry.yield_per_hour)}
                      </td>
                      <td className="px-4 py-2.5">
                        <span
                          className={`inline-block rounded px-2 py-0.5 text-xs font-medium ${SOURCE_BADGE_CLASSES[entry.source]}`}
                        >
                          {entry.source}
                        </span>
                      </td>
                      <td
                        className="px-4 py-2.5 text-xs text-text-tertiary"
                        title={entry.source_ref ?? undefined}
                      >
                        {entry.source_ref ?? '—'}
                      </td>
                      <td className="px-4 py-2.5 text-xs text-text-tertiary">
                        {fmtDateTime(entry.last_calibrated_at)}
                      </td>
                      <td className="px-4 py-2.5 text-right">
                        <button
                          type="button"
                          onClick={() => setPendingDelete(entry)}
                          className="rounded p-1 text-text-tertiary transition hover:bg-red-50 hover:text-red-600 dark:hover:bg-red-900/30"
                          aria-label={t('common.delete', { defaultValue: 'Delete' })}
                        >
                          <Trash2 className="h-4 w-4" />
                        </button>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </CardContent>
      </Card>

      {showCreate && (
        <CreateYieldEntryModal
          onClose={() => setShowCreate(false)}
          onCreated={() => {
            queryClient.invalidateQueries({ queryKey: ['costmodel_typed', 'yield-library'] });
            setShowCreate(false);
          }}
        />
      )}

      {pendingDelete && (
        <ConfirmDialog
          open
          title={t('costmodel_typed.delete_entry_title', {
            defaultValue: 'Delete this yield entry?',
          })}
          message={t('costmodel_typed.delete_entry_msg', {
            defaultValue: `Remove «${pendingDelete.task_label}» from the library?`,
          })}
          confirmLabel={t('common.delete', { defaultValue: 'Delete' })}
          variant="danger"
          loading={deleteMutation.isPending}
          onConfirm={() => deleteMutation.mutate(pendingDelete.id)}
          onCancel={() => setPendingDelete(null)}
        />
      )}
    </div>
  );
}

// ── Create modal ─────────────────────────────────────────────────────────────

function CreateYieldEntryModal({
  onClose,
  onCreated,
}: {
  onClose: () => void;
  onCreated: () => void;
}) {
  const { t } = useTranslation();
  const addToast = useToastStore((s) => s.addToast);
  const [form, setForm] = useState<YieldLibraryEntryCreate>({
    task_label: '',
    unit: '',
    yield_per_hour: '0',
    source: 'manual',
  });

  const createMutation = useMutation({
    mutationFn: (body: YieldLibraryEntryCreate) => costModelTypedApi.createYieldEntry(body),
    onSuccess: () => {
      addToast({
        type: 'success',
        title: t('costmodel_typed.yield_created', { defaultValue: 'Yield entry created' }),
      });
      onCreated();
    },
    onError: (err) => {
      addToast({
        type: 'error',
        title: t('costmodel_typed.yield_create_failed', { defaultValue: 'Create failed' }),
        message: getErrorMessage(err),
      });
    },
  });

  const canSubmit = form.task_label.trim().length > 0;

  return (
    <div
      className="fixed inset-0 z-50 flex items-center justify-center bg-black/40 p-4"
      onClick={onClose}
    >
      <div
        className="w-full max-w-md rounded-lg border border-border bg-surface shadow-xl"
        onClick={(e) => e.stopPropagation()}
      >
        <header className="border-b border-border px-5 py-4 text-base font-semibold">
          {t('costmodel_typed.add_entry', { defaultValue: 'Add entry' })}
        </header>
        <form
          className="space-y-4 p-5"
          onSubmit={(e) => {
            e.preventDefault();
            if (canSubmit) createMutation.mutate(form);
          }}
        >
          <Field
            label={t('costmodel_typed.col_task', { defaultValue: 'Task' })}
            required
          >
            <input
              type="text"
              value={form.task_label}
              onChange={(e) => setForm({ ...form, task_label: e.target.value })}
              className="h-9 w-full rounded-md border border-border bg-surface px-3 text-sm outline-none focus:border-primary"
              autoFocus
            />
          </Field>
          <div className="grid grid-cols-2 gap-3">
            <Field label={t('costmodel_typed.col_unit', { defaultValue: 'Unit' })}>
              <input
                type="text"
                placeholder="m2, m3, ml, kg…"
                value={form.unit ?? ''}
                onChange={(e) => setForm({ ...form, unit: e.target.value })}
                className="h-9 w-full rounded-md border border-border bg-surface px-3 text-sm outline-none focus:border-primary"
              />
            </Field>
            <Field label={t('costmodel_typed.col_yield', { defaultValue: 'U/h' })}>
              <input
                type="number"
                step="0.01"
                value={form.yield_per_hour ?? '0'}
                onChange={(e) => setForm({ ...form, yield_per_hour: e.target.value })}
                className="h-9 w-full rounded-md border border-border bg-surface px-3 text-sm tabular-nums outline-none focus:border-primary"
              />
            </Field>
          </div>
          <Field label={t('costmodel_typed.col_source', { defaultValue: 'Source' })}>
            <select
              value={form.source ?? 'manual'}
              onChange={(e) =>
                setForm({ ...form, source: e.target.value as YieldSource })
              }
              className="h-9 w-full rounded-md border border-border bg-surface px-3 text-sm outline-none focus:border-primary"
            >
              <option value="manual">manual</option>
              <option value="import">import</option>
              <option value="calibrated">calibrated</option>
            </select>
          </Field>
          <Field
            label={t('costmodel_typed.col_source_ref', { defaultValue: 'Reference' })}
          >
            <input
              type="text"
              placeholder='art#001, sous-bloc c)'
              value={form.source_ref ?? ''}
              onChange={(e) => setForm({ ...form, source_ref: e.target.value })}
              className="h-9 w-full rounded-md border border-border bg-surface px-3 text-sm outline-none focus:border-primary"
            />
          </Field>
          <footer className="flex justify-end gap-2 pt-2">
            <Button variant="secondary" type="button" onClick={onClose}>
              {t('common.cancel', { defaultValue: 'Cancel' })}
            </Button>
            <Button
              type="submit"
              disabled={!canSubmit || createMutation.isPending}
            >
              {createMutation.isPending
                ? t('common.saving', { defaultValue: 'Saving…' })
                : t('common.save', { defaultValue: 'Save' })}
            </Button>
          </footer>
        </form>
      </div>
    </div>
  );
}

function Field({
  label,
  required,
  children,
}: {
  label: string;
  required?: boolean;
  children: React.ReactNode;
}) {
  return (
    <label className="block">
      <span className="mb-1 block text-xs font-medium uppercase text-text-tertiary">
        {label}
        {required && <span className="ml-0.5 text-red-500">*</span>}
      </span>
      {children}
    </label>
  );
}
